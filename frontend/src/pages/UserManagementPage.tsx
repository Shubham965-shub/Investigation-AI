import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { ApiError } from "../api/client";
import { createAdminUser, getAdminUsers, updateAdminUserRole, type AdminUserRow } from "../api/auth";
import { CreateUserDialog } from "../components/CreateUserDialog";
// Reuses .ac-page/.ac-card/.ac-title/.ac-table from ActionCenterPage.css and
// .field-label/.field-value/.btn-primary/.btn-outline/.error-banner from
// RecordModulePage.css — plain CSS imports (no CSS Modules scoping in this
// app), so importing both here is the same convention other pages already
// follow rather than duplicating these rules into a third file.
import "./ActionCenterPage.css";
import "./RecordModulePage.css";

// Admin-only page (2026-09-08, per the user) — lists every athena_users row
// with role/created/last-login, plus create-user and edit-role actions. The
// backend independently re-checks the Admin role on every call here
// (require_admin) — this page's own role check is just so a non-admin who
// somehow lands on the URL sees a plain message instead of a page full of
// requests that immediately 403.
function formatTimestamp(iso: string | null): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function UserManagementPage() {
  const { roles } = useAuth();
  const navigate = useNavigate();
  const isAdmin = roles.includes("Admin");

  const [users, setUsers] = useState<AdminUserRow[] | null>(null);
  const [roleOptions, setRoleOptions] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  // Tracks which row's role select is mid-save, so its own dropdown can
  // disable without blocking every other row's (2026-09-08, per the user).
  const [savingRoleFor, setSavingRoleFor] = useState<number | null>(null);

  useEffect(() => {
    if (!isAdmin) return;
    let cancelled = false;
    getAdminUsers()
      .then((data) => {
        if (cancelled) return;
        setUsers(data.users);
        setRoleOptions(data.roles);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? String(err.detail) : "Could not reach the database.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isAdmin]);

  if (!isAdmin) {
    return (
      <div className="ac-page-bg">
        <div className="ac-page">
          <div className="ac-card">
            <p style={{ margin: 0 }}>This page is only available to Admin users.</p>
            <button type="button" className="btn-outline" style={{ marginTop: 12 }} onClick={() => navigate("/")}>
              Back to Action Center
            </button>
          </div>
        </div>
      </div>
    );
  }

  async function handleRoleChange(userId: number, role: string) {
    setSavingRoleFor(userId);
    setError(null);
    // Optimistic update, reverted on failure — same convention as the
    // filter/toggle state elsewhere in Action Center.
    const previous = users;
    setUsers((prev) => prev?.map((u) => (u.id === userId ? { ...u, role } : u)) ?? prev);
    try {
      const updated = await updateAdminUserRole(userId, role);
      setUsers((prev) => prev?.map((u) => (u.id === userId ? updated : u)) ?? prev);
    } catch (err) {
      setUsers(previous);
      setError(err instanceof ApiError ? String(err.detail) : "Failed to update role");
    } finally {
      setSavingRoleFor(null);
    }
  }

  async function handleCreate(fields: { fullName: string; username: string; password: string; role: string }) {
    setCreating(true);
    setCreateError(null);
    try {
      const created = await createAdminUser({
        full_name: fields.fullName,
        username: fields.username,
        password: fields.password,
        role: fields.role,
      });
      setUsers((prev) => (prev ? [...prev, created] : [created]));
      setShowCreate(false);
    } catch (err) {
      setCreateError(err instanceof ApiError ? String(err.detail) : "Failed to create user");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="ac-page-bg">
      <div className="ac-page">
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <h1 className="ac-title">User Management</h1>
          <button type="button" className="btn-primary" onClick={() => setShowCreate(true)}>
            Create User
          </button>
        </div>

        <div className="ac-card">
          {loading && <p style={{ margin: 0, color: "var(--color-text-muted)" }}>Loading users…</p>}
          {error && <p className="error-banner">{error}</p>}

          {users && (
            <table className="ac-table">
              <thead>
                <tr>
                  <th>Full Name</th>
                  <th>Email / Username</th>
                  <th>Role</th>
                  <th>Created On</th>
                  <th>Last Logged In</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id}>
                    <td>{u.full_name ?? "—"}</td>
                    <td>{u.username}</td>
                    <td>
                      <select
                        className="field-value"
                        // .field-value's fixed 3-line height (built for the
                        // multi-line grid fields it was designed for
                        // elsewhere) makes no sense for this single-line
                        // role dropdown (2026-09-08, per the user) — just
                        // let it size to its own natural content.
                        style={{ height: "auto", overflowY: "visible" }}
                        value={u.role ?? ""}
                        disabled={savingRoleFor === u.id}
                        onChange={(e) => handleRoleChange(u.id, e.target.value)}
                      >
                        {!u.role && <option value="">—</option>}
                        {roleOptions.map((r) => (
                          <option key={r} value={r}>
                            {r}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td>{formatTimestamp(u.created_at)}</td>
                    <td>{formatTimestamp(u.last_login)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {showCreate && (
        <CreateUserDialog
          roles={roleOptions}
          submitting={creating}
          error={createError}
          onCancel={() => {
            setShowCreate(false);
            setCreateError(null);
          }}
          onConfirm={handleCreate}
        />
      )}
    </div>
  );
}
