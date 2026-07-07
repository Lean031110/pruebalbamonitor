import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getBusinessInfo, setBusinessInfo, type BusinessInfo } from "@/api";
import { PageContainer, PageHeader } from "@/components/layout";
import { Save, Check } from "lucide-react";

export default function SettingsView() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<BusinessInfo>({
    name: "",
    marketing_text: "",
    address: "",
  });
  const [saved, setSaved] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["business-info"],
    queryFn: getBusinessInfo,
  });

  useEffect(() => {
    if (data) {
      setForm(data);
    }
  }, [data]);

  const saveMut = useMutation({
    mutationFn: (payload: BusinessInfo) => setBusinessInfo(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["business-info"] });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    },
  });

  if (isLoading) {
    return (
      <>
        <PageHeader title="Configuración" />
        <PageContainer>
          <div className="card text-text-muted">Cargando configuración...</div>
        </PageContainer>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Configuración"
        subtitle="Información del negocio (aparece en facturas y reportes)"
        actions={
          <button
            className="btn-primary"
            onClick={() => saveMut.mutate(form)}
            disabled={saveMut.isPending}
          >
            {saved ? <Check size={16} /> : <Save size={16} />}
            {saved ? "Guardado" : "Guardar"}
          </button>
        }
      />
      <PageContainer>
        <div className="card max-w-2xl">
          <h3 className="text-sm font-medium text-text-muted uppercase tracking-wide mb-4">
            Información del negocio
          </h3>
          <div className="space-y-4">
            <div>
              <label className="label">Nombre del negocio</label>
              <input
                className="input"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="Mi Copistería"
              />
            </div>
            <div>
              <label className="label">Texto de marketing (aparece en factura)</label>
              <textarea
                className="input min-h-[80px]"
                value={form.marketing_text}
                onChange={(e) => setForm({ ...form, marketing_text: e.target.value })}
                placeholder="¡Síguenos en redes sociales!"
              />
            </div>
            <div>
              <label className="label">Dirección</label>
              <input
                className="input"
                value={form.address}
                onChange={(e) => setForm({ ...form, address: e.target.value })}
                placeholder="Calle Principal #123"
              />
            </div>
          </div>
        </div>

        <div className="card max-w-2xl mt-4">
          <h3 className="text-sm font-medium text-text-muted uppercase tracking-wide mb-4">
            Configuración avanzada
          </h3>
          <p className="text-sm text-text-muted">
            La configuración de precios, moneda, rutas y backup se edita desde el archivo
            <code className="mx-1 px-1 py-0.5 bg-bg-elevated rounded text-xs">config.toml</code>
            o desde la app desktop de administración.
          </p>
        </div>
      </PageContainer>
    </>
  );
}
