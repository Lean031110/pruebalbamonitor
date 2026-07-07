import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { listBackups, triggerBackup, type BackupRecord } from "@/api";
import { PageContainer, PageHeader } from "@/components/layout";
import { formatBytes, formatDateTime } from "@/utils/format";
import { HardDriveDownload, Download, Play, AlertCircle } from "lucide-react";

export default function BackupsView() {
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery<BackupRecord[]>({
    queryKey: ["backups"],
    queryFn: listBackups,
    refetchInterval: 60_000,
  });

  const triggerMut = useMutation({
    mutationFn: (notes?: string) => triggerBackup(notes ?? ""),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["backups"] });
    },
  });

  const backups = data ?? [];

  return (
    <>
      <PageHeader
        title="Backups"
        subtitle="Respaldo de la base de datos"
        actions={
          <button
            className="btn-primary"
            onClick={() => triggerMut.mutate(undefined)}
            disabled={triggerMut.isPending}
          >
            <Play size={16} /> {triggerMut.isPending ? "Creando..." : "Crear backup ahora"}
          </button>
        }
      />
      <PageContainer>
        {triggerMut.data && (
          <div
            className={`card mb-4 border-l-4 ${
              triggerMut.data.success ? "border-l-success" : "border-l-danger"
            }`}
          >
            <div className="flex items-center gap-2">
              {triggerMut.data.success ? (
                <HardDriveDownload size={20} className="text-success" />
              ) : (
                <AlertCircle size={20} className="text-danger" />
              )}
              <span className="text-sm">{triggerMut.data.message}</span>
            </div>
          </div>
        )}

        {isLoading ? (
          <div className="card text-text-muted">Cargando backups...</div>
        ) : backups.length === 0 ? (
          <div className="card text-center py-12">
            <HardDriveDownload size={48} className="mx-auto mb-3 text-text-subtle" />
            <div className="text-text-muted">No hay backups registrados</div>
            <div className="text-xs text-text-subtle mt-1">
              Crea tu primer backup con el botón "Crear backup ahora"
            </div>
          </div>
        ) : (
          <div className="card overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-text-subtle text-xs uppercase border-b border-border">
                  <th className="text-left p-3">Fecha</th>
                  <th className="text-left p-3">Archivo</th>
                  <th className="text-right p-3">Tamaño</th>
                  <th className="text-center p-3">Tipo</th>
                  <th className="text-left p-3">Notas</th>
                  <th className="text-right p-3">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {backups.map((b) => (
                  <tr key={b.id} className="border-b border-border hover:bg-bg-hover">
                    <td className="p-3 text-xs">{formatDateTime(b.created_at)}</td>
                    <td className="p-3 font-mono text-xs">
                      {b.file_path.split(/[\\/]/).pop()}
                    </td>
                    <td className="p-3 text-right">
                      {b.size_bytes ? formatBytes(b.size_bytes) : "—"}
                    </td>
                    <td className="p-3 text-center">
                      {b.auto ? (
                        <span className="badge-info">Auto</span>
                      ) : (
                        <span className="badge-warn">Manual</span>
                      )}
                    </td>
                    <td className="p-3 text-text-muted text-xs">{b.notes || "—"}</td>
                    <td className="p-3 text-right">
                      <a
                        href={`/api/backups/${b.id}/download`}
                        className="btn-ghost p-1"
                        title="Descargar"
                      >
                        <Download size={14} />
                      </a>
                    </td>
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
