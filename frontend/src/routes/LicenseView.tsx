import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { getLicenseStatus, getMachineId, activateLicense, type LicenseStatus } from "@/api";
import { PageContainer, PageHeader } from "@/components/layout";
import { ShieldCheck, Copy, Check, AlertCircle, Key } from "lucide-react";

export default function LicenseView() {
  const [licenseKey, setLicenseKey] = useState("");
  const [copied, setCopied] = useState(false);

  const { data: status, isLoading } = useQuery<LicenseStatus>({
    queryKey: ["license-status"],
    queryFn: getLicenseStatus,
  });

  const { data: machineIdData } = useQuery({
    queryKey: ["machine-id"],
    queryFn: getMachineId,
  });

  const activateMut = useMutation({
    mutationFn: (key: string) => activateLicense(key),
    onSuccess: () => {
      setLicenseKey("");
    },
  });

  const copyMachineId = () => {
    if (machineIdData?.machine_id) {
      navigator.clipboard.writeText(machineIdData.machine_id);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  if (isLoading || !status) {
    return (
      <>
        <PageHeader title="Licencia" />
        <PageContainer>
          <div className="card text-text-muted">Verificando licencia...</div>
        </PageContainer>
      </>
    );
  }

  return (
    <>
      <PageHeader title="Licencia" subtitle="Estado de la licencia y activación" />
      <PageContainer>
        {/* Estado actual */}
        <div className={`card mb-4 border-l-4 ${status.valid ? "border-l-success" : "border-l-warn"}`}>
          <div className="flex items-center gap-3 mb-2">
            {status.valid ? (
              <ShieldCheck size={24} className="text-success" />
            ) : (
              <AlertCircle size={24} className="text-warn" />
            )}
            <div>
              <div className="text-lg font-semibold">
                {status.valid ? "Licencia activa" : "Sin licencia activa"}
              </div>
              <div className="text-sm text-text-muted">
                {status.valid
                  ? `Tier: ${status.tier}`
                  : status.reason || "Modo trial activado"}
              </div>
            </div>
          </div>
          {status.expires && (
            <div className="text-sm text-text-muted">
              Expira: {new Date(status.expires).toLocaleDateString("es-ES")}
            </div>
          )}
        </div>

        {/* Machine ID */}
        <div className="card mb-4">
          <h3 className="text-sm font-medium text-text-muted uppercase tracking-wide mb-3">
            Machine ID (identificador único de este PC)
          </h3>
          <p className="text-sm text-text-muted mb-3">
            Copia este código y envíaselo al proveedor de la licencia para generar tu código de activación.
          </p>
          <div className="flex gap-2">
            <input
              className="input flex-1 font-mono text-xs"
              value={machineIdData?.machine_id || "Calculando..."}
              readOnly
            />
            <button
              className="btn-secondary"
              onClick={copyMachineId}
              disabled={!machineIdData?.machine_id}
            >
              {copied ? <Check size={16} /> : <Copy size={16} />}
              {copied ? "Copiado" : "Copiar"}
            </button>
          </div>
        </div>

        {/* Activar licencia */}
        <div className="card">
          <h3 className="text-sm font-medium text-text-muted uppercase tracking-wide mb-3">
            Activar licencia
          </h3>
          <p className="text-sm text-text-muted mb-3">
            Pega aquí el código de activación que te envió el proveedor.
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (licenseKey.trim()) {
                activateMut.mutate(licenseKey.trim());
              }
            }}
            className="flex gap-2"
          >
            <input
              className="input flex-1 font-mono text-xs"
              placeholder="Pega tu licencia aquí..."
              value={licenseKey}
              onChange={(e) => setLicenseKey(e.target.value)}
            />
            <button
              type="submit"
              className="btn-primary"
              disabled={!licenseKey.trim() || activateMut.isPending}
            >
              <Key size={16} /> Activar
            </button>
          </form>
          {activateMut.data && (
            <div className={`mt-3 text-sm ${activateMut.data.success ? "text-success" : "text-danger"}`}>
              {activateMut.data.message}
            </div>
          )}
        </div>
      </PageContainer>
    </>
  );
}
