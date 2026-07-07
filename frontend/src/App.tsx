import { Routes, Route, Link, useLocation, Navigate, useNavigate } from "react-router-dom";
import {
  LayoutDashboard,
  Usb,
  History,
  Users,
  CreditCard,
  BarChart3,
  Settings,
  ShieldCheck,
  HardDriveDownload,
  ScrollText,
  Bell,
  LogOut,
} from "lucide-react";
import { clsx } from "clsx";
import { ComponentType, useEffect, useState } from "react";
import Dashboard from "./routes/Dashboard";
import USBView from "./routes/USBView";
import HistoryView from "./routes/HistoryView";
import UsersView from "./routes/UsersView";
import BillingView from "./routes/BillingView";
import StatisticsView from "./routes/StatisticsView";
import SettingsView from "./routes/SettingsView";
import LicenseView from "./routes/LicenseView";
import BackupsView from "./routes/BackupsView";
import LogsView from "./routes/LogsView";
import LoginView from "./routes/LoginView";
import NotFoundView from "./routes/NotFoundView";
import ErrorBoundary from "./components/ErrorBoundary";
import { isAuthenticated, logout, getAccessToken } from "./api";

const NAV: { to: string; label: string; icon: ComponentType<{ size?: number }>; end?: boolean }[] = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/usb", label: "USBs activos", icon: Usb },
  { to: "/history", label: "Historial", icon: History },
  { to: "/billing", label: "Cobros", icon: CreditCard },
  { to: "/users", label: "Operadores", icon: Users },
  { to: "/statistics", label: "Estadísticas", icon: BarChart3 },
  { to: "/backups", label: "Backups", icon: HardDriveDownload },
  { to: "/logs", label: "Logs", icon: ScrollText },
  { to: "/license", label: "Licencia", icon: ShieldCheck },
  { to: "/settings", label: "Configuración", icon: Settings },
];

function Sidebar() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const [authed, setAuthed] = useState(isAuthenticated());

  useEffect(() => {
    setAuthed(isAuthenticated());
  }, [pathname]);

  const handleLogout = async () => {
    await logout();
    setAuthed(false);
    navigate("/login");
  };

  return (
    <aside className="w-60 shrink-0 bg-bg-surface border-r border-border flex flex-col">
      <div className="h-14 flex items-center gap-2 px-4 border-b border-border">
        <div className="w-8 h-8 rounded-md bg-accent flex items-center justify-center font-bold text-white">
          L
        </div>
        <div>
          <div className="text-sm font-semibold leading-tight">LBAMonitor</div>
          <div className="text-xs text-text-subtle leading-tight">v4.3.0</div>
        </div>
      </div>
      <nav className="flex-1 overflow-y-auto py-2">
        {NAV.map(({ to, label, icon: Icon, end }) => {
          const active = end ? pathname === to : pathname.startsWith(to);
          return (
            <Link
              key={to}
              to={to}
              className={clsx(
                "flex items-center gap-3 px-4 py-2 text-sm transition-colors",
                active
                  ? "bg-accent-subtle text-accent border-l-2 border-accent"
                  : "text-text-muted hover:bg-bg-hover hover:text-text border-l-2 border-transparent"
              )}
            >
              <Icon size={18} />
              {label}
            </Link>
          );
        })}
      </nav>
      <div className="p-3 border-t border-border text-xs text-text-subtle">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <Bell size={14} />
            <span>Servicio:</span>
            <span className="badge-success">activo</span>
          </div>
        </div>
        {authed && (
          <button
            onClick={handleLogout}
            className="flex items-center gap-2 w-full px-2 py-1.5 rounded hover:bg-bg-hover text-text-muted hover:text-text transition"
          >
            <LogOut size={14} />
            <span>Cerrar sesión</span>
          </button>
        )}
      </div>
    </aside>
  );
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const authed = isAuthenticated();
  const location = useLocation();
  if (!authed) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }
  return <>{children}</>;
}

export default function App() {
  return (
    <ErrorBoundary>
      <Routes>
        <Route path="/login" element={<LoginView />} />
        <Route
          path="/*"
          element={
            <ProtectedRoute>
              <div className="flex h-screen overflow-hidden">
                <Sidebar />
                <main className="flex-1 overflow-auto">
                  <Routes>
                    <Route path="/" element={<Dashboard />} />
                    <Route path="/usb" element={<USBView />} />
                    <Route path="/history" element={<HistoryView />} />
                    <Route path="/billing" element={<BillingView />} />
                    <Route path="/users" element={<UsersView />} />
                    <Route path="/statistics" element={<StatisticsView />} />
                    <Route path="/backups" element={<BackupsView />} />
                    <Route path="/logs" element={<LogsView />} />
                    <Route path="/license" element={<LicenseView />} />
                    <Route path="/settings" element={<SettingsView />} />
                    <Route path="*" element={<NotFoundView />} />
                  </Routes>
                </main>
              </div>
            </ProtectedRoute>
          }
        />
      </Routes>
    </ErrorBoundary>
  );
}

// Suppress unused import (kept for future use)
void getAccessToken;
