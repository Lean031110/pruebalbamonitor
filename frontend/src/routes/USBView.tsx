import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { getActiveDrives, listInsertedDrives, type InsertedDrive } from "@/api";
import { PageContainer, PageHeader } from "@/components/layout";
import { formatBytes, formatDateTime } from "@/utils/format";
import { Usb, Smartphone, RefreshCw } from "lucide-react";

export default function USBView() {
  const [filter, setFilter] = useState<"active" | "all">("active");

  const { data: active, isLoading: loadingActive, refetch: refetchActive } = useQuery<InsertedDrive[]>({
    queryKey: ["drives", "active"],
    queryFn: getActiveDrives,
    refetchInterval: 3_000,
    enabled: filter === "active",
  });

  const { data: recent, isLoading: loadingRecent, refetch: refetchRecent } = useQuery({
    queryKey: ["drives", "recent"],
    queryFn: () => listInsertedDrives({ page: 1, page_size: 20 }),
    refetchInterval: 10_000,
    enabled: filter === "all",
  });

  const drives: InsertedDrive[] = filter === "active" ? (active ?? []) : (recent?.items ?? []);
  const isLoading = filter === "active" ? loadingActive : loadingRecent;
  const refetch = filter === "active" ? refetchActive : refetchRecent;

  return (
    <>
      <PageHeader
        title="Dispositivos USB"
        subtitle="Monitoreo en tiempo real de memorias conectadas"
        actions={
          <>
            <button
              className={filter === "active" ? "btn-primary" : "btn-secondary"}
              onClick={() => setFilter("active")}
            >
              Activos
            </button>
            <button
              className={filter === "all" ? "btn-primary" : "btn-secondary"}
              onClick={() => setFilter("all")}
            >
              Recientes
            </button>
            <button className="btn-ghost" onClick={() => refetch()}>
              <RefreshCw size={16} />
            </button>
          </>
        }
      />
      <PageContainer>
        {isLoading ? (
          <div className="card text-text-muted">Cargando dispositivos...</div>
        ) : drives.length === 0 ? (
          <div className="card text-center py-12">
            <Usb size={48} className="mx-auto mb-3 text-text-subtle" />
            <div className="text-text-muted">No hay dispositivos {filter === "active" ? "activos" : "recientes"}</div>
            <div className="text-xs text-text-subtle mt-1">
              {filter === "active"
                ? "Conecta una memoria USB o un teléfono para verla aquí"
                : "Las inserciones aparecerán aquí cuando se registren"}
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {drives.map((d) => (
              <div key={d.id} className="card hover:border-accent transition-colors">
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-2">
                    {d.is_mobile ? (
                      <Smartphone size={20} className="text-accent" />
                    ) : (
                      <Usb size={20} className="text-accent" />
                    )}
                    <span className="font-medium">{d.name || "Sin nombre"}</span>
                  </div>
                  {!d.removed_drive_id && (
                    <span className="badge-success">● Activo</span>
                  )}
                </div>
                <dl className="space-y-1 text-sm">
                  <div className="flex justify-between">
                    <dt className="text-text-subtle">Volumen</dt>
                    <dd>{d.volume_label || "—"}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-text-subtle">Modelo</dt>
                    <dd className="truncate max-w-[180px]">{d.model || "—"}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-text-subtle">Capacidad</dt>
                    <dd>{d.space_bytes ? formatBytes(d.space_bytes) : "—"}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-text-subtle">Libre</dt>
                    <dd>{d.available_space_bytes ? formatBytes(d.available_space_bytes) : "—"}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-text-subtle">Inserción</dt>
                    <dd className="text-xs">{formatDateTime(d.insertion_date_time)}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-text-subtle">Visitas previas</dt>
                    <dd>{d.previous_insertions_counter}</dd>
                  </div>
                  {d.payment !== null && (
                    <div className="flex justify-between border-t border-border pt-1 mt-1">
                      <dt className="text-text-subtle">Pago</dt>
                      <dd className="font-medium text-success">{d.payment} ₱</dd>
                    </div>
                  )}
                </dl>
              </div>
            ))}
          </div>
        )}
      </PageContainer>
    </>
  );
}
