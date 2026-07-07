import { useQuery } from "@tanstack/react-query";
import { getStatistics, type KPIs } from "@/api";
import { PageContainer, PageHeader } from "@/components/layout";
import { formatCurrency, formatNumber } from "@/utils/format";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
} from "recharts";
import { TrendingUp, DollarSign, HardDrive, FileText, Users, Clock, Zap, UserCheck } from "lucide-react";

const PIE_COLORS = ["#CD7F32", "#C0C0C0", "#FFD700", "#E5E4E2", "#B9F2FF"];

function KpiCard({
  label,
  value,
  icon: Icon,
  accent,
}: {
  label: string;
  value: string;
  icon: React.ElementType;
  accent?: boolean;
}) {
  return (
    <div className="kpi-card">
      <div className="flex items-center justify-between">
        <span className="kpi-label">{label}</span>
        <Icon size={16} className={accent ? "text-accent" : "text-text-subtle"} />
      </div>
      <div className="kpi-value">{value}</div>
    </div>
  );
}

export default function StatisticsView() {
  const { data, isLoading } = useQuery({
    queryKey: ["statistics"],
    queryFn: getStatistics,
    refetchInterval: 30_000,
  });

  if (isLoading || !data) {
    return (
      <>
        <PageHeader title="Estadísticas" />
        <PageContainer>
          <div className="card text-text-muted">Cargando estadísticas...</div>
        </PageContainer>
      </>
    );
  }

  const today = data.today_kpis;
  const month = data.month_kpis;
  const insights = data.insights;

  return (
    <>
      <PageHeader
        title="Estadísticas"
        subtitle={`KPIs actualizados: hoy, mes y año`}
      />
      <PageContainer>
        {/* KPIs Hoy */}
        <h3 className="text-sm font-medium text-text-muted uppercase tracking-wide mb-3">
          Hoy
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <KpiCard label="Ingresos" value={formatCurrency(today.revenue)} icon={DollarSign} accent />
          <KpiCard label="Transacciones" value={formatNumber(today.transactions)} icon={TrendingUp} />
          <KpiCard label="USBs insertadas" value={formatNumber(today.usb_count)} icon={HardDrive} />
          <KpiCard label="GB copiados" value={formatNumber(today.gb_copied, 2)} icon={FileText} />
        </div>

        {/* KPIs Mes */}
        <h3 className="text-sm font-medium text-text-muted uppercase tracking-wide mb-3">
          Este mes
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <KpiCard label="Ingresos mes" value={formatCurrency(month.revenue)} icon={DollarSign} accent />
          <KpiCard label="Transacciones" value={formatNumber(month.transactions)} icon={TrendingUp} />
          <KpiCard label="USBs mes" value={formatNumber(month.usb_count)} icon={HardDrive} />
          <KpiCard label="Promedio/sesión" value={formatCurrency(month.avg_per_session)} icon={TrendingUp} />
        </div>

        {/* Insights */}
        <h3 className="text-sm font-medium text-text-muted uppercase tracking-wide mb-3">
          Insights del negocio
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <KpiCard
            label="Día más ocupado"
            value={insights.busiest_day_of_week || "—"}
            icon={Clock}
          />
          <KpiCard
            label="Hora pico"
            value={insights.peak_hour !== null ? `${insights.peak_hour}:00` : "—"}
            icon={Zap}
          />
          <KpiCard
            label="Clientes nuevos (30d)"
            value={formatNumber(insights.new_clients_30d)}
            icon={UserCheck}
          />
          <KpiCard
            label="Inactivos (60d)"
            value={formatNumber(insights.inactive_clients_60d)}
            icon={Users}
          />
        </div>

        {/* Gráfico de ingresos por día */}
        <div className="card mb-6">
          <h3 className="text-sm font-medium text-text-muted uppercase tracking-wide mb-3">
            Ingresos por día (últimos 30 días)
          </h3>
          {data.revenue_by_day.length === 0 ? (
            <div className="text-center py-8 text-text-muted text-sm">Sin datos aún</div>
          ) : (
            <ResponsiveContainer width="100%" height={250}>
              <AreaChart data={data.revenue_by_day}>
                <defs>
                  <linearGradient id="rev" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#0078D4" stopOpacity={0.4} />
                    <stop offset="100%" stopColor="#0078D4" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#2E2E38" />
                <XAxis dataKey="label" stroke="#71717A" fontSize={11} />
                <YAxis stroke="#71717A" fontSize={11} />
                <Tooltip
                  contentStyle={{ background: "#1A1A1F", border: "1px solid #2E2E38", borderRadius: 8 }}
                  labelStyle={{ color: "#E4E4E7" }}
                />
                <Area
                  type="monotone"
                  dataKey="value"
                  stroke="#0078D4"
                  strokeWidth={2}
                  fill="url(#rev)"
                  name="Ingresos"
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Top USBs y top clientes */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
          <div className="card">
            <h3 className="text-sm font-medium text-text-muted uppercase tracking-wide mb-3">
              Top 10 USBs más frecuentes
            </h3>
            {data.top_usb.length === 0 ? (
              <div className="text-center py-4 text-text-muted text-sm">Sin datos</div>
            ) : (
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={data.top_usb} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="#2E2E38" />
                  <XAxis type="number" stroke="#71717A" fontSize={11} />
                  <YAxis
                    type="category"
                    dataKey="alias"
                    stroke="#71717A"
                    fontSize={11}
                    width={100}
                  />
                  <Tooltip
                    contentStyle={{ background: "#1A1A1F", border: "1px solid #2E2E38", borderRadius: 8 }}
                  />
                  <Bar dataKey="visit_count" fill="#0078D4" radius={[0, 4, 4, 0]} name="Visitas" />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>

          <div className="card">
            <h3 className="text-sm font-medium text-text-muted uppercase tracking-wide mb-3">
              Top 10 clientes
            </h3>
            {data.top_clients.length === 0 ? (
              <div className="text-center py-4 text-text-muted text-sm">Sin datos</div>
            ) : (
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie
                    data={data.top_clients}
                    dataKey="total_spent"
                    nameKey="tier"
                    cx="50%"
                    cy="50%"
                    outerRadius={100}
                    label={(e) => e.tier}
                  >
                    {data.top_clients.map((_, i) => (
                      <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ background: "#1A1A1F", border: "1px solid #2E2E38", borderRadius: 8 }}
                  />
                </PieChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
      </PageContainer>
    </>
  );
}
