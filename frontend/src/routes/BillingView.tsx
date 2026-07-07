import { useQuery } from "@tanstack/react-query";
import { listInsertedDrives, type InsertedDrive } from "@/api";
import { PageContainer, PageHeader } from "@/components/layout";
import { formatCurrency, formatDateTime } from "@/utils/format";
import { CreditCard } from "lucide-react";

export default function BillingView() {
  const { data, isLoading } = useQuery({
    queryKey: ["billing-history"],
    queryFn: () => listInsertedDrives({ page: 1, page_size: 100, has_payment: true }),
    refetchInterval: 15_000,
  });

  const drives = (data?.items ?? []).filter((d) => d.payment !== null && d.payment !== undefined);

  const totalCharged = drives.reduce((sum, d) => sum + (d.payment || 0), 0);
  const avgCharged = drives.length > 0 ? totalCharged / drives.length : 0;

  return (
    <>
      <PageHeader
        title="Cobros"
        subtitle="Historial de pagos registrados"
      />
      <PageContainer>
        {/* KPIs */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          <div className="kpi-card">
            <div className="flex items-center justify-between">
              <span className="kpi-label">Total cobrado</span>
              <CreditCard size={16} className="text-accent" />
            </div>
            <div className="kpi-value">{formatCurrency(totalCharged)}</div>
          </div>
          <div className="kpi-card">
            <div className="flex items-center justify-between">
              <span className="kpi-label">Transacciones</span>
            </div>
            <div className="kpi-value">{drives.length}</div>
          </div>
          <div className="kpi-card">
            <div className="flex items-center justify-between">
              <span className="kpi-label">Promedio/cobro</span>
            </div>
            <div className="kpi-value">{formatCurrency(avgCharged)}</div>
          </div>
        </div>

        {/* Tabla */}
        {isLoading ? (
          <div className="card text-text-muted">Cargando cobros...</div>
        ) : drives.length === 0 ? (
          <div className="card text-center py-12">
            <CreditCard size={48} className="mx-auto mb-3 text-text-subtle" />
            <div className="text-text-muted">No hay cobros registrados</div>
            <div className="text-xs text-text-subtle mt-1">
              Los cobros aparecerán aquí cuando asignes pagos a las inserciones
            </div>
          </div>
        ) : (
          <div className="card overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-text-subtle text-xs uppercase border-b border-border">
                  <th className="text-left p-3">Fecha</th>
                  <th className="text-left p-3">Dispositivo</th>
                  <th className="text-left p-3">Modelo</th>
                  <th className="text-right p-3">Pago</th>
                  <th className="text-left p-3">Comentario</th>
                </tr>
              </thead>
              <tbody>
                {drives.map((d: InsertedDrive) => (
                  <tr key={d.id} className="border-b border-border hover:bg-bg-hover">
                    <td className="p-3 text-xs">{formatDateTime(d.insertion_date_time)}</td>
                    <td className="p-3 font-medium">
                      {d.volume_label || d.name || `#${d.id}`}
                    </td>
                    <td className="p-3 text-text-muted">{d.model || "—"}</td>
                    <td className="p-3 text-right font-medium text-success">
                      {d.payment} ₱
                    </td>
                    <td className="p-3 text-text-muted text-xs">{d.comment || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </PageContainer>
    </>
  );
}
