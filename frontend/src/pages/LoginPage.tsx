import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { useTheme } from "../theme/ThemeContext";
import stridesLogo from "../assets/icons/logo.png";
import athenaLogo from "../assets/icons/athena-logo.svg";
import "./LoginPage.css";

function EyeIcon({ open }: { open: boolean }) {
  return open ? (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  ) : (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c6.5 0 10 7 10 7a13.16 13.16 0 0 1-2.16 3.19M6.5 6.6C3.7 8.4 2 11 2 11s3.5 7 10 7a9.28 9.28 0 0 0 4.32-1.05M14.12 14.12a3 3 0 1 1-4.24-4.24" />
      <path d="M1 1l22 22" />
    </svg>
  );
}

function ThemeIcon({ dark }: { dark: boolean }) {
  return dark ? (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
    </svg>
  ) : (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79Z" />
    </svg>
  );
}

export function LoginPage() {
  const { login, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const { theme, toggleTheme } = useTheme();
  const isDark = theme === "dark";
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Navigating here (rather than immediately after `await login(...)`
  // resolves) avoids a race: navigate() could otherwise run before React
  // actually commits the setUsername() state update from login(), so
  // ProtectedRoute would read the still-stale isAuthenticated=false and
  // bounce straight back to /login despite the login having succeeded —
  // this effect only fires once the auth state has genuinely landed.
  useEffect(() => {
    if (isAuthenticated) navigate("/", { replace: true });
  }, [isAuthenticated, navigate]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(username, password);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="login-page login-split-page">
      {/* Left half — solid Strides green brand panel */}
      <aside className="login-brand-half">
        <div aria-hidden className="login-brand-grid" />
        <div style={{ position: "relative", zIndex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", flex: 1, gap: 28, padding: "48px 32px", textAlign: "center" }}>
          <img src={athenaLogo} alt="" style={{ height: 72, animation: "login-rise 700ms ease both" }} />
          <div style={{ animation: "login-rise 700ms ease 100ms both" }}>
            <h1 style={{ margin: 0, fontFamily: "var(--font-heading)", fontWeight: 700, fontSize: "2.25rem", color: "#fafafa", letterSpacing: "0.02em" }}>
              Athena
            </h1>
            <p
              style={{
                margin: "10px auto 0",
                maxWidth: 360,
                fontSize: "var(--font-size-md)",
                lineHeight: 1.6,
                color: "rgba(250,250,250,0.75)",
              }}
            >
              Sign in to manage investigations, RCI Plans and RCI reports, all in one place.
            </p>
          </div>
        </div>
        <div style={{ position: "relative", zIndex: 1, display: "flex", alignItems: "center", justifyContent: "center", gap: 10, padding: "0 32px 32px" }}>
          <span style={{ fontSize: "var(--font-size-xs)", color: "rgba(250,250,250,0.55)", textTransform: "uppercase", letterSpacing: "0.15em" }}>Powered by</span>
          <img src={stridesLogo} alt="Strides" style={{ height: 20 }} />
        </div>
      </aside>

      {/* Right half — radar + login panel */}
      <section className="login-form-half">
        {/* Faint grid, fading out toward the edges */}
        <div
          aria-hidden
          style={{
            position: "absolute",
            inset: 0,
            opacity: 0.07,
            pointerEvents: "none",
            backgroundImage: isDark
              ? "linear-gradient(to right, #c6f7e2 1px, transparent 1px), linear-gradient(to bottom, #c6f7e2 1px, transparent 1px)"
              : "linear-gradient(to right, #00402c 1px, transparent 1px), linear-gradient(to bottom, #00402c 1px, transparent 1px)",
            backgroundSize: "56px 56px",
            maskImage: "radial-gradient(ellipse at center, black 40%, transparent 75%)",
          }}
        />

        {/* Decorative radar sweep */}
        <div className="login-radar" aria-hidden style={{ position: "absolute", left: "50%", top: "50%", transform: "translate(-50%, -50%)", pointerEvents: "none" }}>
          <div style={{ position: "relative", width: 720, height: 720 }}>
            {[0, 1, 2, 3, 4].map((i) => (
              <div
                key={i}
                style={{
                  position: "absolute",
                  inset: 0,
                  borderRadius: "50%",
                  border: "1px solid rgba(16,185,129,0.18)",
                  transform: `scale(${0.35 + i * 0.16})`,
                  animation: `login-pulse 4.5s ease-out ${i * 0.7}s infinite`,
                }}
              />
            ))}
            <div
              style={{
                position: "absolute",
                inset: 0,
                borderRadius: "50%",
                background: "conic-gradient(from 0deg, transparent 0deg, rgba(16,185,129,0.35) 30deg, transparent 60deg)",
                animation: "login-sweep 6s linear infinite",
                maskImage: "radial-gradient(circle, black 0%, black 60%, transparent 70%)",
              }}
            />
            <div
              style={{
                position: "absolute",
                left: "50%",
                top: "50%",
                width: 12,
                height: 12,
                borderRadius: "50%",
                transform: "translate(-50%, -50%)",
                background: "#10b981",
                boxShadow: "0 0 24px #10b981, 0 0 60px rgba(16,185,129,0.5)",
              }}
            />
          </div>
        </div>

        <button
          type="button"
          onClick={toggleTheme}
          aria-label="Toggle theme"
          style={{
            position: "absolute",
            top: 24,
            right: 24,
            zIndex: 2,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            width: 36,
            height: 36,
            borderRadius: "50%",
            border: "1px solid var(--color-card-border)",
            background: "var(--color-surface)",
            color: "var(--color-text)",
            cursor: "pointer",
          }}
        >
          <ThemeIcon dark={isDark} />
        </button>

        <div style={{ position: "relative", zIndex: 1, width: "100%", maxWidth: 400, animation: "login-rise 700ms ease 150ms both" }}>
          <div
            aria-hidden
            style={{
              position: "absolute",
              inset: -1,
              borderRadius: 24,
              opacity: 0.6,
              filter: "blur(24px)",
              background: "linear-gradient(135deg, rgba(16,185,129,0.45), rgba(0,64,44,0.15) 60%, transparent)",
            }}
          />
          <form
            onSubmit={handleSubmit}
            style={{
              position: "relative",
              borderRadius: 24,
              border: "1px solid var(--color-card-border)",
              background: "var(--color-surface)",
              boxShadow: "0 25px 50px rgba(0,0,0,0.25)",
              padding: 32,
              display: "flex",
              flexDirection: "column",
              gap: 16,
            }}
          >
            <div>
              <h2 style={{ margin: "4px 0 0", fontFamily: "var(--font-heading)", fontWeight: 700, fontSize: "var(--font-size-xl)", color: "var(--color-text)" }}>
                Welcome back
              </h2>
            </div>

            <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: "var(--font-size-base)", fontWeight: 600, color: "var(--color-text-muted)" }}>
              Username
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                autoFocus
                style={{ padding: "9px 13px", borderRadius: "var(--radius-btn)", border: "1px solid var(--color-card-border)", background: "var(--color-bg)", color: "var(--color-text)" }}
              />
            </label>

            <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: "var(--font-size-base)", fontWeight: 600, color: "var(--color-text-muted)" }}>
              Password
              <div style={{ position: "relative" }}>
                <input
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  style={{ width: "100%", padding: "9px 40px 9px 13px", borderRadius: "var(--radius-btn)", border: "1px solid var(--color-card-border)", background: "var(--color-bg)", color: "var(--color-text)" }}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((s) => !s)}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  style={{ position: "absolute", right: 8, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", padding: 4, display: "flex", color: "var(--color-text-muted)", cursor: "pointer" }}
                >
                  <EyeIcon open={showPassword} />
                </button>
              </div>
            </label>

            {error && <p style={{ color: "var(--color-danger-text)", fontSize: "var(--font-size-base)", margin: 0 }}>{error}</p>}

            <button
              type="submit"
              disabled={submitting}
              className="login-submit"
              style={{
                marginTop: 4,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 8,
                background: "var(--color-primary)",
                color: "#fafafa",
                border: "none",
                borderRadius: "var(--radius-btn)",
                padding: "12px 16px",
                fontFamily: "var(--font-heading)",
                fontWeight: 700,
                fontSize: "var(--font-size-base)",
                cursor: submitting ? "default" : "pointer",
                opacity: submitting ? 0.75 : 1,
              }}
            >
              <span className="login-submit-shimmer" aria-hidden />
              {submitting ? (
                <>
                  <span className="login-spinner" />
                  Logging in…
                </>
              ) : (
                "Log in"
              )}
            </button>

            <p style={{ margin: 0, textAlign: "center", fontSize: "var(--font-size-xs)", color: "var(--color-text-muted)" }}>
              © {new Date().getFullYear()} Strides Pharma Science
            </p>
          </form>
        </div>
      </section>
    </div>
  );
}
