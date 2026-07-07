import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { listUsers, createUser, updateUser, deleteUser, type User } from "@/api";
import { PageContainer, PageHeader } from "@/components/layout";
import { formatDateTime } from "@/utils/format";
import { UserPlus, Trash2, Edit, Shield, X } from "lucide-react";

const ROLE_LABEL: Record<string, string> = {
  admin: "Administrador",
  manager: "Supervisor",
  operator: "Operador",
};

const ROLE_BADGE: Record<string, string> = {
  admin: "badge-danger",
  manager: "badge-warn",
  operator: "badge-info",
};

export default function UsersView() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [editingUser, setEditingUser] = useState<User | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["users"],
    queryFn: () => listUsers(1, 100),
  });

  const createMut = useMutation({
    mutationFn: (payload: { username: string; password: string; role: string; full_name?: string; email?: string }) =>
      createUser(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      setShowForm(false);
    },
  });

  const updateMut = useMutation({
    mutationFn: ({ id, ...payload }: Partial<User> & { id: number; password?: string }) =>
      updateUser(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      setEditingUser(null);
    },
  });

  const deleteMut = useMutation({
    mutationFn: (id: number) => deleteUser(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["users"] }),
  });

  const users = data?.items ?? [];

  return (
    <>
      <PageHeader
        title="Operadores"
        subtitle="Gestión de usuarios con roles"
        actions={
          <button className="btn-primary" onClick={() => setShowForm(true)}>
            <UserPlus size={16} /> Nuevo operador
          </button>
        }
      />
      <PageContainer>
        {isLoading ? (
          <div className="card text-text-muted">Cargando...</div>
        ) : (
          <div className="card overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-text-subtle text-xs uppercase border-b border-border">
                  <th className="text-left p-3">Usuario</th>
                  <th className="text-left p-3">Nombre</th>
                  <th className="text-left p-3">Rol</th>
                  <th className="text-left p-3">Estado</th>
                  <th className="text-left p-3">Último login</th>
                  <th className="text-right p-3">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id} className="border-b border-border hover:bg-bg-hover">
                    <td className="p-3 font-medium">{u.username}</td>
                    <td className="p-3">{u.full_name || "—"}</td>
                    <td className="p-3">
                      <span className={ROLE_BADGE[u.role] || "badge-info"}>
                        <Shield size={12} /> {ROLE_LABEL[u.role] || u.role}
                      </span>
                    </td>
                    <td className="p-3">
                      {u.active ? (
                        <span className="badge-success">Activo</span>
                      ) : (
                        <span className="badge-danger">Inactivo</span>
                      )}
                    </td>
                    <td className="p-3 text-text-subtle text-xs">
                      {u.last_login ? formatDateTime(u.last_login) : "Nunca"}
                    </td>
                    <td className="p-3 text-right">
                      <button
                        className="btn-ghost p-1"
                        onClick={() => setEditingUser(u)}
                        title="Editar"
                      >
                        <Edit size={14} />
                      </button>
                      <button
                        className="btn-ghost p-1 hover:text-danger"
                        onClick={() => {
                          if (confirm(`¿Desactivar a ${u.username}?`)) deleteMut.mutate(u.id);
                        }}
                        title="Desactivar"
                      >
                        <Trash2 size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {users.length === 0 && (
              <div className="text-center py-8 text-text-muted">
                No hay operadores. Crea el primero con "Nuevo operador".
              </div>
            )}
          </div>
        )}
      </PageContainer>

      {(showForm || editingUser) && (
        <UserForm
          user={editingUser}
          onClose={() => {
            setShowForm(false);
            setEditingUser(null);
          }}
          onSubmit={(payload) => {
            if (editingUser) {
              updateMut.mutate({ id: editingUser.id, ...payload });
            } else {
              createMut.mutate(payload as { username: string; password: string; role: string });
            }
          }}
        />
      )}
    </>
  );
}

function UserForm({
  user,
  onClose,
  onSubmit,
}: {
  user: User | null;
  onClose: () => void;
  onSubmit: (payload: { username: string; password?: string; role: string; full_name?: string; email?: string }) => void;
}) {
  const [username, setUsername] = useState(user?.username || "");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState(user?.role || "operator");
  const [fullName, setFullName] = useState(user?.full_name || "");
  const [email, setEmail] = useState(user?.email || "");

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="card max-w-md w-full" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-semibold">
            {user ? "Editar operador" : "Nuevo operador"}
          </h2>
          <button className="btn-ghost p-1" onClick={onClose}>
            <X size={18} />
          </button>
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            onSubmit({
              username,
              password: password || undefined,
              role,
              full_name: fullName || undefined,
              email: email || undefined,
            });
          }}
          className="space-y-3"
        >
          <div>
            <label className="label">Usuario</label>
            <input
              className="input"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={!!user}
              required
            />
          </div>
          <div>
            <label className="label">
              Contraseña {user && "(dejar vacío para no cambiar)"}
            </label>
            <input
              type="password"
              className="input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required={!user}
              minLength={user ? 0 : 4}
            />
          </div>
          <div>
            <label className="label">Nombre completo</label>
            <input
              className="input"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
            />
          </div>
          <div>
            <label className="label">Email</label>
            <input
              type="email"
              className="input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div>
            <label className="label">Rol</label>
            <select
              className="input"
              value={role}
              onChange={(e) => setRole(e.target.value)}
            >
              <option value="admin">Administrador</option>
              <option value="manager">Supervisor</option>
              <option value="operator">Operador</option>
            </select>
          </div>
          <div className="flex gap-2 pt-2">
            <button type="submit" className="btn-primary flex-1">
              {user ? "Guardar cambios" : "Crear operador"}
            </button>
            <button type="button" className="btn-secondary" onClick={onClose}>
              Cancelar
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
