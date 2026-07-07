import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { listInsertedDrives, getDriveCopies, type InsertedDrive, type Copy } from "@/api";
import { PageContainer, PageHeader } from "@/components/layout";
import { formatBytes, formatDateTime } from "@/utils/format";
import { Search, History, FileVideo, FileText, Music, Image as ImageIcon } from "lucide-react";

const CATEGORY_ICON: Record<string, React.ElementType> = {
  video: FileVideo,
  movie: FileVideo,
  series: FileVideo,
  music: Music,
  document: FileText,
  image: ImageIcon,
};

export default function HistoryView() {
  const [search, setSearch] = useState("");
  const [selectedDriveId, setSelectedDriveId] = useState<number | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["history", search],
    queryFn: () =>
      listInsertedDrives({
        page: 1,
        page_size: 50,
        device_name: search || undefined,
        device_serial: search || undefined,
        comment_contains: search || undefined,
      }),
    refetchInterval: 15_000,
  });

  const { data: copies } = useQuery<Copy[]>({
    queryKey: ["drive-copies", selectedDriveId],
    queryFn: () => getDriveCopies(selectedDriveId!),
    enabled: selectedDriveId !== null,
  });

  const drives = data?.items ?? [];

  return (
    <>
      <PageHeader title="Historial" subtitle="Busca y revisa inserciones pasadas" />
      <PageContainer>
        <div className="flex gap-4 mb-4">
          <div className="flex-1 relative">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-subtle" />
            <input
              className="input pl-9"
              placeholder="Buscar por nombre, serial o comentario..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Lista de inserciones */}
          <div className="card">
            <h3 className="text-sm font-medium text-text-muted uppercase tracking-wide mb-3">
              Inserciones ({drives.length})
            </h3>
            {isLoading ? (
              <div className="text-text-muted text-sm">Cargando...</div>
            ) : drives.length === 0 ? (
              <div className="text-center py-8 text-text-muted">
                <History size={32} className="mx-auto mb-2 text-text-subtle" />
                <div className="text-sm">Sin resultados</div>
              </div>
            ) : (
              <div className="space-y-2 max-h-[600px] overflow-y-auto">
                {drives.map((d: InsertedDrive) => (
                  <button
                    key={d.id}
                    onClick={() => setSelectedDriveId(d.id)}
                    className={`w-full text-left p-3 rounded border transition-colors ${
                      selectedDriveId === d.id
                        ? "border-accent bg-accent-subtle"
                        : "border-border hover:bg-bg-hover"
                    }`}
                  >
                    <div className="flex justify-between items-start">
                      <div>
                        <div className="font-medium text-sm">
                          {d.volume_label || d.name || `#${d.id}`}
                        </div>
                        <div className="text-xs text-text-subtle">
                          {formatDateTime(d.insertion_date_time)}
                          {d.model && ` • ${d.model}`}
                        </div>
                      </div>
                      {d.payment !== null && (
                        <span className="badge-success text-xs">{d.payment} ₱</span>
                      )}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Detalle de copias */}
          <div className="card">
            <h3 className="text-sm font-medium text-text-muted uppercase tracking-wide mb-3">
              {selectedDriveId ? `Copias de inserción #${selectedDriveId}` : "Selecciona una inserción"}
            </h3>
            {!selectedDriveId ? (
              <div className="text-center py-8 text-text-muted text-sm">
                Haz clic en una inserción para ver sus copias
              </div>
            ) : (copies?.length ?? 0) === 0 ? (
              <div className="text-center py-8 text-text-muted text-sm">
                Sin copias registradas
              </div>
            ) : (
              <div className="space-y-1 max-h-[600px] overflow-y-auto">
                {copies?.map((c) => {
                  const Icon = CATEGORY_ICON[c.category || ""] || FileText;
                  return (
                    <div key={c.id} className="flex items-center gap-2 p-2 hover:bg-bg-hover rounded text-sm">
                      <Icon size={14} className="text-text-subtle shrink-0" />
                      <span className="truncate flex-1">{c.file_name}</span>
                      <span className="text-text-subtle text-xs">{formatBytes(c.size_bytes)}</span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </PageContainer>
    </>
  );
}
