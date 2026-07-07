export function formatBytes(num: number | null | undefined): string {
  if (num === null || num === undefined || num < 0) return "—";
  if (num === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB", "PB"];
  let i = 0;
  let n = num;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i++;
  }
  return `${n.toFixed(2)} ${units[i]}`;
}

export function formatCurrency(value: number | null | undefined, symbol = "₱", decimals = 2): string {
  if (value === null || value === undefined) value = 0;
  return `${value.toLocaleString("es", { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}${symbol}`;
}

export function formatDate(dt: string | Date | null | undefined, fmt: string = "%Y-%m-%d"): string {
  if (!dt) return "—";
  const d = typeof dt === "string" ? new Date(dt) : dt;
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("es-ES");
}

export function formatDateTime(dt: string | Date | null | undefined): string {
  if (!dt) return "—";
  const d = typeof dt === "string" ? new Date(dt) : dt;
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleString("es-ES", { dateStyle: "short", timeStyle: "medium" });
}

export function formatDuration(seconds: number | null | undefined): string {
  if (!seconds || seconds < 0) return "0s";
  const s = Math.floor(seconds);
  if (s < 60) return `${s}s`;
  if (s < 3600) {
    const m = Math.floor(s / 60);
    return `${m}m ${s % 60}s`;
  }
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return `${h}h ${m}m ${s % 60}s`;
}

export function formatNumber(value: number | null | undefined, decimals = 0): string {
  if (value === null || value === undefined) return "0";
  return value.toLocaleString("es-ES", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}
