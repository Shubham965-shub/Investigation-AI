import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(username, password);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "var(--color-bg)" }}>
      <form
        onSubmit={handleSubmit}
        style={{
          background: "var(--color-surface)",
          border: "1px solid var(--color-card-border)",
          borderRadius: "var(--radius-card)",
          padding: 32,
          width: 360,
          display: "flex",
          flexDirection: "column",
          gap: 16,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
          <span style={{ fontFamily: "var(--font-heading)", fontWeight: 700, fontSize: 22, color: "var(--color-header-bg)" }}>
            Strides
          </span>
          <span style={{ color: "var(--color-primary)" }}>|</span>
          <span style={{ fontFamily: "var(--font-heading)", fontWeight: 700, fontSize: 22 }}>Athena</span>
        </div>

        <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 14, fontWeight: 600, color: "var(--color-text-muted)" }}>
          Username
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
            style={{ padding: "9px 13px", borderRadius: "var(--radius-btn)", border: "1px solid var(--color-card-border)", background: "var(--color-bg)" }}
          />
        </label>

        <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 14, fontWeight: 600, color: "var(--color-text-muted)" }}>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            style={{ padding: "9px 13px", borderRadius: "var(--radius-btn)", border: "1px solid var(--color-card-border)", background: "var(--color-bg)" }}
          />
        </label>

        {error && <p style={{ color: "#b91c1c", fontSize: 14, margin: 0 }}>{error}</p>}

        <button
          type="submit"
          disabled={submitting}
          style={{
            background: "var(--color-primary)",
            color: "#fafafa",
            border: "none",
            borderRadius: "var(--radius-btn)",
            padding: "10px 16px",
            fontFamily: "var(--font-heading)",
            fontWeight: 700,
          }}
        >
          {submitting ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
