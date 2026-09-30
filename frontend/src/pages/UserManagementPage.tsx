import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { ApiError } from "../api/client";
import { adminSetUserPassword, createAdminUser, getAdminUsers, updateAdminUserRole, type AdminUserRow } from "../api/auth";
import { CreateUserDialog } from "../components/CreateUserDialog";
import { AdminResetPasswordDialog } from "../components/AdminResetPasswordDialog";
import { track, EVENTS } from "../telemetry/events";
// Reuses shared classes from ActionCenterPage.css/RecordModulePage.css — plain CSS, no module scoping, same convention as other pages.
import "./ActionCenterPage.css";
import "./RecordModulePage.css";

// Backend independently re-checks Admin on every call (require_admin) — this page's own check is just so a non-admin sees a message instead of a page full of 403s.
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
  // Tracks which row's role select is mid-save, so only that dropdown disables.
  const [savingRoleFor, setSavingRoleFor] = useState<number | null>(null);
  const [resetPasswordFor, setResetPasswordFor] = useState<AdminUserRow | null>(null);
  const [resettingPassword, setResettingPassword] = useState(false);
  const [resetPasswordError, setResetPasswordError] = useState<string | null>(null);

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
    track(EVENTS.userRoleChanged, { userId, newRole: role });
    setSavingRoleFor(userId);
    setError(null);
    // Optimistic update, reverted on failure.
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
    track(EVENTS.userCreated, { role: fields.role });
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

  async function handleResetPassword(newPassword: string) {
    if (!resetPasswordFor) return;
    setResettingPassword(true);
    setResetPasswordError(null);
    try {
      await adminSetUserPassword(resetPasswordFor.id, newPassword);
      setResetPasswordFor(null);
    } catch (err) {
      setResetPasswordError(err instanceof ApiError ? String(err.detail) : "Failed to reset password");
    } finally {
      setResettingPassword(false);
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
                  <th />
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
                        // .field-value's fixed 3-line height doesn't suit this single-line dropdown — let it size naturally.
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
                    <td>
                      <button
                        type="button"
                        className="btn-outline"
                        onClick={() => {
                          setResetPasswordError(null);
                          setResetPasswordFor(u);
                        }}
                      >
                        Reset Password
                      </button>
                    </td>
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

      {resetPasswordFor && (
        <AdminResetPasswordDialog
          username={resetPasswordFor.username}
          submitting={resettingPassword}
          error={resetPasswordError}
          onCancel={() => setResetPasswordFor(null)}
          onConfirm={handleResetPassword}
        />
      )}
    </div>
  );
}
