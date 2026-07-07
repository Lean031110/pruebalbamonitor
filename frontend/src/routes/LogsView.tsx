import { useQuery } from "@tanstack/react-query";
import { listSessions, type ServiceSession } from "@/api";
import { PageContainer, PageHeader } from "@/components/layout";
import { formatDateTime, formatDuration } from "@/utils/format";
import { Server, Clock, Activity } from "lucide-react";

export default function LogsView() {
  const { data, isLoading } = useQuery({
    queryKey: ["sessions"],
    queryFn: () => listSessions(1, 100),
  });

  const sessions = data?.items ?? [];

  return (
    <>
      <PageHeader
        title="Sesiones del servicio"
        subtitle="Historial de arranques y paradas del servicio de monitoreo"
      />
      <PageContainer>
        {isLoading ? (
          <div className="card text-text-muted">Cargando...</div>
        ) : sessions.length === 0 ? (
          <div className="card text-center py-12">
            <Server size={48} className="mx-auto mb-3 text-text-subtle" />
            <div className="text-text-muted">No hay sesiones registradas</div>
            <div className="text-xs text-text-subtle mt-1">
              Inicia el servicio lbamonitor-svc para crear la primera sesión
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            {sessions.map((s: ServiceSession) => (
              <div key={s.id} className="card flex items-center gap-4">
                <div className="shrink-0">
                  {s.end_date_time === null ? (
                    <Activity size={24} className="text-success" />
                  ) : (
                    <Clock size={24} className="text-text-subtle" />
                  )}
                </div>
                <div className="flex-1">
                  <div className="font-medium">Sesión #{s.id}</div>
                  <div className="text-sm text-text-muted">
                    Inicio: {formatDateTime(s.start_date_time)}
                    {s.end_date_time && (
                      <> • Fin: {formatDateTime(s.end_date_time)}</>
                    )}
                  </div>
                  {s.alive_date_time && (
                    <div className="text-xs text-text-subtle">
                      Último heartbeat: {formatDateTime(s.alive_date_time)}
                    </div>
                  )}
                </div>
                <div className="text-right">
                  {s.end_date_time === null ? (
                    <span className="badge-success">● Activa</span>
                  ) : (
                    <span className="badge-info">
                      Duración: {formatDuration(s.session_time)}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </PageContainer>
    </>
  );
}
