import { useState, FormEvent } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { login } from "../api";

export default function LoginView() {
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string })?.from || "/";

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      await login(username, password);
      navigate(from, { replace: true });
    } catch (err: unknown) {
      const e = err as { response?: { status?: number; data?: { detail?: string } } };
      if (e.response?.status === 401) {
        setError("Usuario o contraseña incorrectos");
      } else if (e.response?.status === 429) {
        setError("Demasiados intentos. Espere un minuto.");
      } else if (!e.response) {
        setError("No se pudo conectar al servidor. Verifique que el servicio esté activo.");
      } else {
        setError(e.response?.data?.detail || "Error al iniciar sesión");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 px-4">
      <div className="max-w-md w-full bg-slate-800/70 backdrop-blur-sm rounded-2xl shadow-2xl border border-slate-700 p-8">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-white tracking-tight">LBAMonitor</h1>
          <p className="text-slate-400 mt-2 text-sm">Sistema de monitoreo de copias USB</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1.5">Usuario</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoFocus
              disabled={loading}
              className="w-full px-4 py-2.5 bg-slate-900 border border-slate-700 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-500 focus:border-transparent transition"
              placeholder="admin"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1.5">Contraseña</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              disabled={loading}
              className="w-full px-4 py-2.5 bg-slate-900 border border-slate-700 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-500 focus:border-transparent transition"
              placeholder="••••••••"
            />
          </div>

          {error && (
            <div className="bg-red-500/10 border border-red-500/40 rounded-lg px-4 py-2.5 text-red-300 text-sm">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading || !username || !password}
            className="w-full py-2.5 bg-cyan-600 hover:bg-cyan-500 disabled:bg-slate-700 disabled:text-slate-500 text-white font-medium rounded-lg transition focus:outline-none focus:ring-2 focus:ring-cyan-400 focus:ring-offset-2 focus:ring-offset-slate-800"
          >
            {loading ? "Ingresando..." : "Ingresar"}
          </button>
        </form>

        <p className="text-xs text-slate-500 text-center mt-6">
          v4.3.0 — © LBAMonitor
        </p>
      </div>
    </div>
  );
}
