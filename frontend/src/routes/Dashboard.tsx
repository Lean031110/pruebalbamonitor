import { useQuery } from "@tanstack/react-query";
import { getHealth, HealthResponse } from "@/api";
import { PageContainer, PageHeader } from "@/components/layout";
import { Usb, Copy, FileText, Server } from "lucide-react";

function Kpi({
  label,
  value,
  icon: Icon,
  accent,
}: {
  label: string;
  value: string | number;
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

export default function Dashboard() {
  const { data, isLoading, error } = useQuery<HealthResponse>({
    queryKey: ["health"],
    queryFn: getHealth,
    refetchInterval: 5_000,
  });

  if (isLoading) {
    return (
      <>
        <PageHeader title="Dashboard" subtitle="Cargando..." />
        <PageContainer>
          <div className="text-text-muted">Conectando con el servidor...</div>
        </PageContainer>
      </>
    );
  }

  if (error) {
    return (
      <>
        <PageHeader title="Dashboard" />
        <PageContainer>
          <div className="card border-danger/40">
            <div className="text-danger font-medium mb-1">
              No se pudo conectar con el servidor LBAMonitor
            </div>
            <div className="text-sm text-text-muted">
              Verifica que el servicio esté corriendo en http://127.0.0.1:8123
            </div>
          </div>
        </PageContainer>
      </>
    );
  }

  const counts = data?.counts ?? {};
  const session = data?.service_session;

  return (
    <>
      <PageHeader
        title="Dashboard"
        subtitle={`Servidor ${data?.name} v${data?.version} • ${data?.platform.system}`}
      />
      <PageContainer>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <Kpi
            label="Dispositivos USB"
            value={counts.usb_devices ?? 0}
            icon={Usb}
            accent
          />
          <Kpi label="Inserciones" value={counts.inserted_drives ?? 0} icon={Server} />
          <Kpi label="Copias registradas" value={counts.copies ?? 0} icon={Copy} />
          <Kpi
            label="Estado servicio"
            value={session?.is_running ? "Activo" : "Detenido"}
            icon={FileText}
          />
        </div>

        <div className="card mb-6">
          <h3 className="text-sm font-medium text-text-muted uppercase tracking-wide mb-3">
            Información del sistema
          </h3>
          <dl className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
            <div>
              <dt className="text-text-subtle">Versión API</dt>
              <dd className="font-medium">{data?.version}</dd>
            </div>
            <div>
              <dt className="text-text-subtle">Plataforma</dt>
              <dd className="font-medium">
                {data?.platform.system} {data?.platform.machine}
              </dd>
            </div>
            <div>
              <dt className="text-text-subtle">Python</dt>
              <dd className="font-medium">{data?.python}</dd>
            </div>
            <div>
              <dt className="text-text-subtle">Motor BD</dt>
              <dd className="font-medium uppercase">{data?.config.database_engine}</dd>
            </div>
            <div>
              <dt className="text-text-subtle">Escuchando en</dt>
              <dd className="font-medium">
                {data?.config.host}:{data?.config.port}
              </dd>
            </div>
            <div>
              <dt className="text-text-subtle">Timestamp</dt>
              <dd className="font-medium font-mono text-xs">
                {data?.timestamp}
              </dd>
            </div>
          </dl>
        </div>

        {session && (
          <div className="card">
            <h3 className="text-sm font-medium text-text-muted uppercase tracking-wide mb-3">
              Sesión del servicio
            </h3>
            <dl className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
              <div>
                <dt className="text-text-subtle">ID</dt>
                <dd className="font-medium">#{session.id}</dd>
              </div>
              <div>
                <dt className="text-text-subtle">Inicio</dt>
                <dd className="font-medium font-mono text-xs">{session.start}</dd>
              </div>
              <div>
                <dt className="text-text-subtle">Último heartbeat</dt>
                <dd className="font-medium font-mono text-xs">
                  {session.alive ?? "—"}
                </dd>
              </div>
              <div>
                <dt className="text-text-subtle">Estado</dt>
                <dd>
                  {session.is_running ? (
                    <span className="badge-success">● En ejecución</span>
                  ) : (
                    <span className="badge-danger">● Detenido</span>
                  )}
                </dd>
              </div>
            </dl>
          </div>
        )}
      </PageContainer>
    </>
  );
}
