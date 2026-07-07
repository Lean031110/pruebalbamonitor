/* ========================================================================
   LBAMonitor — Dashboard JS en tiempo real (vanilla, sin librerías)
   v4.3
   - Conexión WebSocket a /ws/events con reconexión exponencial
   - Fallback: fetch /api/statistics cada 30s
   - Manejo de cookies HTTPOnly (fetch incluye credentials: 'same-origin')
   ======================================================================== */

(function () {
    'use strict';

    const INITIAL = window.__LBAMONITOR_INITIAL__ || {};
    const CURRENCY = INITIAL.currency_symbol || '₱';
    const WS_URL = INITIAL.ws_url || `ws://${location.host}/ws/events`;

    // Estado de conexión WS
    let ws = null;
    let wsRetryDelay = 1000;     // 1s inicial, hasta 30s
    let wsRetryTimer = null;
    let fallbackTimer = null;
    let pingTimer = null;

    // ─── Utilidades ────────────────────────────────────────────────────

    function fmtMoney(v) {
        const n = Number(v || 0);
        return n.toLocaleString('es-ES', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    }

    function fmtNum(v) {
        return Number(v || 0).toLocaleString('es-ES');
    }

    function fmtGb(v) {
        return Number(v || 0).toFixed(1);
    }

    function isoShort(iso) {
        if (!iso) return '—';
        return iso.slice(0, 19).replace('T', ' ');
    }

    function setKpi(id, value) {
        const el = document.getElementById(id);
        if (!el) return;
        if (el.textContent !== String(value)) {
            el.textContent = value;
            // flash
            const parent = el.closest('.kpi');
            if (parent) {
                parent.classList.remove('flash');
                void parent.offsetWidth; // reflow
                parent.classList.add('flash');
            }
        }
    }

    function setKpiMoney(id, value) {
        const el = document.getElementById(id);
        if (!el) return;
        const newHtml = `${fmtMoney(value)} <span class="currency">${CURRENCY}</span>`;
        if (el.innerHTML !== newHtml) {
            el.innerHTML = newHtml;
            const parent = el.closest('.kpi');
            if (parent) {
                parent.classList.remove('flash');
                void parent.offsetWidth;
                parent.classList.add('flash');
            }
        }
    }

    // ─── Status WS indicator ───────────────────────────────────────────

    function setWsStatus(state) {
        const el = document.getElementById('ws-status');
        if (!el) return;
        el.className = 'ws-status ws-' + state;
        const labels = {
            connected: 'WS: conectado',
            disconnected: 'WS: desconectado',
            connecting: 'WS: conectando…',
        };
        el.textContent = labels[state] || 'WS: ?';
    }

    // ─── Render KPIs ───────────────────────────────────────────────────

    function renderKpis(kpis) {
        if (!kpis) return;
        setKpi('kpi-transactions', fmtNum(kpis.transactions));
        setKpiMoney('kpi-revenue', kpis.revenue);
        setKpi('kpi-usb', fmtNum(kpis.usb_count));
        setKpi('kpi-gb', fmtGb(kpis.gb_copied));
        setKpi('kpi-files', fmtNum(kpis.files_copied));
        setKpiMoney('kpi-avg-session', kpis.avg_per_session);
    }

    // ─── Render Insights ───────────────────────────────────────────────

    function renderInsights(insights) {
        if (!insights) return;
        const set = (id, txt) => {
            const el = document.getElementById(id);
            if (el) el.innerHTML = txt;
        };
        set('insight-busiest-day', insights.busiest_day_of_week || '—');
        set('insight-peak-hour',
            insights.peak_hour !== null && insights.peak_hour !== undefined
                ? String(insights.peak_hour).padStart(2, '0') + ':00'
                : '—');
        set('insight-new-clients', fmtNum(insights.new_clients_30d));
        set('insight-inactive', fmtNum(insights.inactive_clients_60d));
        if (insights.top_usb) {
            const alias = insights.top_usb.alias || (insights.top_usb.serial || '—').slice(0, 16);
            set('insight-top-usb',
                escapeHtml(alias) +
                ` <span class="muted small">(${fmtNum(insights.top_usb.visit_count)} visitas)</span>`);
        }
        if (insights.top_client) {
            const alias = insights.top_client.alias || ('Cliente #' + insights.top_client.device_id);
            set('insight-top-client',
                escapeHtml(alias) +
                ` <span class="muted small">(${fmtNum(insights.top_client.visit_count)} visitas)</span>`);
        }
    }

    function escapeHtml(s) {
        if (s == null) return '';
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    // ─── Render active drives ──────────────────────────────────────────

    function renderActiveDrives(drives) {
        const tbody = document.querySelector('#active-drives-table tbody');
        const countBadge = document.getElementById('active-count');
        if (!tbody) return;
        if (!drives || drives.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" class="empty-row muted">Sin dispositivos activos</td></tr>';
            if (countBadge) countBadge.textContent = '0';
            return;
        }
        if (countBadge) countBadge.textContent = String(drives.length);

        // Map de IDs existentes para detectar nuevos
        const existingIds = new Set(
            Array.from(tbody.querySelectorAll('tr[data-drive-id]'))
                .map(r => r.getAttribute('data-drive-id'))
        );

        tbody.innerHTML = drives.map(d => {
            const isNew = !existingIds.has(String(d.id));
            return `<tr data-drive-id="${d.id}" class="${isNew ? 'flash' : ''}">
                <td>${escapeHtml(d.id)}</td>
                <td>${escapeHtml(d.name || '—')}</td>
                <td>${escapeHtml(d.model || '—')}</td>
                <td class="mono">${escapeHtml((d.serial || '').slice(0, 16))}</td>
                <td>${fmtGb(d.space_gb)} GB</td>
                <td>${fmtGb(d.available_gb)} GB</td>
                <td class="num">${escapeHtml(String(d.payment || 0))}</td>
                <td class="muted small">${isoShort(d.inserted_at)}</td>
            </tr>`;
        }).join('');
    }

    // ─── Render recent billings ────────────────────────────────────────

    function renderRecentBillings(billings) {
        const tbody = document.querySelector('#recent-billings-table tbody');
        if (!tbody) return;
        if (!billings || billings.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-row muted">Sin cobros recientes</td></tr>';
            return;
        }

        const existingIds = new Set(
            Array.from(tbody.querySelectorAll('tr[data-billing-id]'))
                .map(r => r.getAttribute('data-billing-id'))
        );

        tbody.innerHTML = billings.map(b => {
            const isNew = !existingIds.has(String(b.id));
            const chargedCell = b.not_charged
                ? `<td class="num text-red">${fmtMoney(b.charged)} ✗</td>`
                : `<td class="num text-green">${fmtMoney(b.charged)}</td>`;
            return `<tr data-billing-id="${b.id}" class="${isNew ? 'flash' : ''}">
                <td>${escapeHtml(b.id)}</td>
                <td>${escapeHtml(b.session_id)}</td>
                <td class="num">${fmtMoney(b.total)}</td>
                ${chargedCell}
                <td class="num">${fmtMoney(b.discount_amount)}</td>
                <td>${escapeHtml(b.created_by || '—')}</td>
                <td class="muted small">${isoShort(b.created_at)}</td>
            </tr>`;
        }).join('');
    }

    // ─── Revenue chart (Canvas simple) ─────────────────────────────────

    function drawRevenueChart(series) {
        const canvas = document.getElementById('revenue-chart');
        if (!canvas || !series || series.length === 0) return;

        // Asegurar alta resolución
        const dpr = window.devicePixelRatio || 1;
        const cssW = canvas.clientWidth || 900;
        const cssH = 260;
        canvas.width = cssW * dpr;
        canvas.height = cssH * dpr;
        canvas.style.height = cssH + 'px';
        const ctx = canvas.getContext('2d');
        ctx.scale(dpr, dpr);

        ctx.clearRect(0, 0, cssW, cssH);

        const padL = 60, padR = 20, padT = 20, padB = 40;
        const w = cssW - padL - padR;
        const h = cssH - padT - padB;

        const values = series.map(p => Number(p.value || 0));
        const maxV = Math.max(1, ...values);
        const niceMax = Math.ceil(maxV * 1.1);

        // Grid horizontal + etiquetas Y
        ctx.strokeStyle = '#2E2E38';
        ctx.fillStyle = '#71717A';
        ctx.font = '11px system-ui, sans-serif';
        ctx.lineWidth = 1;
        const gridLines = 4;
        for (let i = 0; i <= gridLines; i++) {
            const y = padT + (h * i) / gridLines;
            ctx.beginPath();
            ctx.moveTo(padL, y);
            ctx.lineTo(padL + w, y);
            ctx.stroke();
            const val = niceMax * (1 - i / gridLines);
            ctx.textAlign = 'right';
            ctx.fillText(fmtMoney(val), padL - 8, y + 4);
        }

        // Barras
        const barW = w / series.length;
        const barGap = barW * 0.2;
        const barWInner = barW - barGap;
        ctx.fillStyle = '#0078D4';
        series.forEach((p, i) => {
            const v = Number(p.value || 0);
            const barH = (v / niceMax) * h;
            const x = padL + i * barW + barGap / 2;
            const y = padT + h - barH;
            // Bar
            ctx.fillRect(x, y, barWInner, barH);
            // Etiqueta X (fecha corta)
            ctx.fillStyle = '#71717A';
            ctx.textAlign = 'center';
            const label = String(p.label || '').slice(5); // YYYY-MM-DD → MM-DD
            ctx.fillText(label, x + barWInner / 2, padT + h + 18);
            // Valor encima
            if (v > 0) {
                ctx.fillStyle = '#22C55E';
                ctx.textAlign = 'center';
                ctx.fillText(fmtMoney(v), x + barWInner / 2, y - 6);
            }
            ctx.fillStyle = '#0078D4';
        });

        // Título eje
        ctx.fillStyle = '#A1A1AA';
        ctx.textAlign = 'left';
        ctx.fillText(`Ingresos (${CURRENCY})`, padL, 14);
    }

    // ─── Event log ─────────────────────────────────────────────────────

    function appendEvent(type, data, timestamp) {
        const log = document.getElementById('event-log');
        if (!log) return;
        const line = document.createElement('div');
        line.className = 'event-line';
        const time = new Date(timestamp || Date.now()).toLocaleTimeString('es-ES');
        const typeClass = 'event-type ' + (type || '').replace(/\./g, '_');
        line.innerHTML =
            `<span class="event-time">${time}</span>` +
            `<span class="${typeClass}">${escapeHtml(type || 'event')}</span>` +
            `<span class="event-data">${escapeHtml(JSON.stringify(data || {}))}</span>`;
        log.insertBefore(line, log.firstChild);
        // Limitar a 50 líneas
        while (log.children.length > 50) {
            log.removeChild(log.lastChild);
        }
    }

    // expuesta en window para el botón Limpiar
    window.clearEventLog = function () {
        const log = document.getElementById('event-log');
        if (log) log.innerHTML = '';
    };

    // ─── Event handler ─────────────────────────────────────────────────

    function handleWsMessage(msg) {
        if (!msg || !msg.type) return;
        const type = msg.type;
        const data = msg.data || {};
        const ts = msg.timestamp;

        // Ignorar pings
        if (type === 'ping' || type === 'connection.established') {
            if (type === 'connection.established') {
                appendEvent('connection.established', data, ts);
            }
            return;
        }

        // Loguear evento
        appendEvent(type, data, ts);

        // Reaccionar a eventos relevantes
        switch (type) {
            case 'drive.inserted':
            case 'drive.removed':
                // Refrescar USBs activos
                fetchActiveDrives();
                break;
            case 'billing.registered':
            case 'payment.altered':
                // Refrescar KPIs + cobros recientes
                fetchStatistics();
                fetchRecentBillings();
                break;
            case 'file.copied':
            case 'file.deleted':
                // Refrescar KPIs (gb_copied, files_copied)
                fetchStatistics();
                break;
            case 'reward.granted':
            case 'membership.upgraded':
                // Refrescar insights
                fetchInsights();
                break;
        }
    }

    // ─── Fallback: fetch a la API ──────────────────────────────────────

    async function fetchJson(url) {
        try {
            const resp = await fetch(url, { credentials: 'same-origin' });
            if (!resp.ok) {
                console.warn('fetch', url, '→', resp.status);
                return null;
            }
            return await resp.json();
        } catch (e) {
            console.warn('fetch', url, 'error:', e);
            return null;
        }
    }

    async function fetchStatistics() {
        const data = await fetchJson('/api/statistics');
        if (data && data.today_kpis) {
            renderKpis(data.today_kpis);
        }
        if (data && data.revenue_by_day) {
            drawRevenueChart(data.revenue_by_day.slice(-7));
        }
    }

    async function fetchInsights() {
        const data = await fetchJson('/api/statistics/insights');
        if (data) renderInsights(data);
    }

    async function fetchActiveDrives() {
        const data = await fetchJson('/api/inserted-drives/active');
        if (Array.isArray(data)) {
            const mapped = data.map(d => ({
                id: d.id,
                name: d.name,
                model: d.model,
                serial: d.serial_number,
                space_gb: (d.space_bytes || 0) / (1024 ** 3),
                available_gb: (d.available_space_bytes || 0) / (1024 ** 3),
                payment: d.payment,
                inserted_at: d.insertion_date_time,
            }));
            renderActiveDrives(mapped);
        }
    }

    async function fetchRecentBillings() {
        const data = await fetchJson('/api/billings?page=1&page_size=10');
        if (data && Array.isArray(data.items)) {
            renderRecentBillings(data.items);
        }
    }

    // ─── WebSocket connection ──────────────────────────────────────────

    function connectWs() {
        if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
            return;
        }
        setWsStatus('connecting');
        try {
            ws = new WebSocket(WS_URL);
        } catch (e) {
            console.warn('No se pudo crear WebSocket:', e);
            scheduleReconnect();
            return;
        }

        ws.onopen = () => {
            setWsStatus('connected');
            wsRetryDelay = 1000; // reset backoff
            console.log('[WS] conectado a', WS_URL);
            // Ping cada 25s para mantener viva la conexión
            if (pingTimer) clearInterval(pingTimer);
            pingTimer = setInterval(() => {
                if (ws && ws.readyState === WebSocket.OPEN) {
                    try { ws.send(JSON.stringify({ type: 'client.ping' })); } catch (e) {}
                }
            }, 25000);
        };

        ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                handleWsMessage(msg);
            } catch (e) {
                console.warn('[WS] mensaje no-JSON:', event.data);
            }
        };

        ws.onerror = (err) => {
            console.warn('[WS] error:', err);
        };

        ws.onclose = () => {
            setWsStatus('disconnected');
            if (pingTimer) { clearInterval(pingTimer); pingTimer = null; }
            scheduleReconnect();
        };
    }

    function scheduleReconnect() {
        if (wsRetryTimer) clearTimeout(wsRetryTimer);
        console.log(`[WS] reconectando en ${wsRetryDelay}ms…`);
        wsRetryTimer = setTimeout(() => {
            wsRetryDelay = Math.min(wsRetryDelay * 2, 30000); // backoff hasta 30s
            connectWs();
        }, wsRetryDelay);
    }

    // ─── Fallback polling (cada 30s) ───────────────────────────────────

    function startFallbackPolling() {
        if (fallbackTimer) clearInterval(fallbackTimer);
        fallbackTimer = setInterval(() => {
            // Solo si el WS no está conectado, hacer fetch
            if (!ws || ws.readyState !== WebSocket.OPEN) {
                console.log('[fallback] WS caído — polling manual');
                fetchStatistics();
                fetchActiveDrives();
                fetchRecentBillings();
            } else {
                // Aunque el WS esté up, refrescar KPIs cada 30s por si perdemos
                // algún evento (mejor ser idempotente)
                fetchStatistics();
            }
        }, 30000);
    }

    // ─── Init ──────────────────────────────────────────────────────────

    function init() {
        // Render inicial con los datos ya embebidos en el HTML
        renderKpis(INITIAL.kpis);
        renderInsights(INITIAL.insights);
        renderActiveDrives(INITIAL.active_drives);
        renderRecentBillings(INITIAL.recent_billings);
        drawRevenueChart(INITIAL.revenue_by_day);

        // Conectar WS
        connectWs();

        // Iniciar fallback (también refresca KPIs cada 30s aunque WS esté up)
        startFallbackPolling();

        // Re-dibujar chart en resize
        let resizeTimer;
        window.addEventListener('resize', () => {
            clearTimeout(resizeTimer);
            resizeTimer = setTimeout(() => {
                drawRevenueChart(INITIAL.revenue_by_day);
            }, 200);
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
