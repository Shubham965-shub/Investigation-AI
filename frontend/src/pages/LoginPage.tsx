import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, Activity, Eye, EyeOff, Loader2, Moon, Sun } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { useTheme } from "../theme/ThemeContext";
import { getPublicStats } from "../api/auth";
import { Schematic } from "./Schematic";
import stridesLogoDark from "../assets/icons/logo.png";
import stridesIconLight from "../assets/icons/strides-icon.png";
import stridesWordmarkLight from "../assets/icons/strides-wordmark-light.png";
import athenaLogo from "../assets/icons/athena-logo.svg";
import "./LoginPage.css";

export function LoginPage() {
  const { login, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const { theme, toggleTheme } = useTheme();
  const dark = theme === "dark";

  const [mounted, setMounted] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPass, setShowPass] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [openInvestigations, setOpenInvestigations] = useState<number | null>(null);

  useEffect(() => {
    const id = requestAnimationFrame(() => setMounted(true));
    return () => cancelAnimationFrame(id);
  }, []);

  // Unauthenticated endpoint — this page runs before any token exists.
  useEffect(() => {
    getPublicStats()
      .then((stats) => setOpenInvestigations(stats.open_investigations))
      .catch(() => {});
  }, []);

  // Navigates only once isAuthenticated actually lands — navigating right after login() resolves
  // risks ProtectedRoute reading a stale isAuthenticated=false and bouncing back to /login.
  useEffect(() => {
    if (isAuthenticated) navigate("/", { replace: true });
  }, [isAuthenticated, navigate]);

  async function signIn(e: React.FormEvent) {
    e.preventDefault();
    if (submitting) return;
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

  const background = dark
    ? {
        backgroundImage:
          "radial-gradient(900px 620px at 88% 6%, rgba(10,74,51,0.75), transparent 70%), radial-gradient(760px 560px at 6% 96%, rgba(10,74,51,0.55), transparent 72%), linear-gradient(180deg, #02160e 0%, #03241a 52%, #02110b 100%)",
      }
    : {
        backgroundImage:
          "radial-gradient(900px 620px at 88% 6%, rgba(197,232,150,0.6), transparent 70%), radial-gradient(760px 560px at 6% 96%, rgba(113,215,126,0.38), transparent 72%), linear-gradient(180deg, #f6faf4 0%, #ecf6e8 100%)",
      };

  const gridLine = dark ? "rgba(255,255,255,0.07)" : "rgba(0,64,44,0.07)";
  const enter = "transition-all duration-700 ease-out";
  const shown = mounted ? "opacity-100 translate-y-0" : "opacity-0 translate-y-3";

  const cardShell = dark ? "border-white/10 bg-white/[0.04]" : "border-[#00402c]/12 bg-white/80";
  const label = dark ? "text-emerald-100/55" : "text-[#00402c]/60";
  const heading = dark ? "text-emerald-50" : "text-[#00402c]";
  const body = dark ? "text-emerald-100/65" : "text-[#383536]/75";
  const field = dark
    ? "border-white/10 bg-white/[0.03] text-emerald-50 placeholder:text-emerald-100/25"
    : "border-[#00402c]/15 bg-white text-[#383536] placeholder:text-[#383536]/35";

  // Dark mode: single flat wordmark (icon+text sized proportionally). Light mode's source
  // asset has a much bigger icon-to-text ratio, so rendered at one height the text comes out
  // visibly smaller than dark mode's — split into separate icon/wordmark images so each can be
  // sized independently to match dark mode's visual proportions.

  return (
    <div className="relative h-screen overflow-hidden" style={background}>
      {/* grid overlay */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          backgroundImage: `linear-gradient(to right, ${gridLine} 1px, transparent 1px), linear-gradient(to bottom, ${gridLine} 1px, transparent 1px)`,
          backgroundSize: "56px 56px",
          maskImage: "radial-gradient(ellipse at center, black 40%, transparent 75%)",
          WebkitMaskImage: "radial-gradient(ellipse at center, black 40%, transparent 75%)",
        }}
      />

      {/* radar decoration */}
      <div
        aria-hidden
        className="pointer-events-none absolute top-1/2 -right-40 hidden size-[720px] -translate-y-1/2 lg:block"
      >
        {[0, 1, 2, 3, 4].map((i) => (
          <span
            key={i}
            className="absolute inset-0 rounded-full border"
            style={{
              borderColor: dark ? "rgba(0,212,150,0.28)" : "rgba(0,114,74,0.22)",
              transform: `scale(${0.35 + i * 0.16})`,
              animation: `atlas-pulse 4.5s ease-out ${i * 0.7}s infinite`,
            }}
          />
        ))}
        <span className="absolute left-0 top-1/2 h-px w-full bg-emerald-500/10" />
        <span className="absolute left-1/2 top-0 h-full w-px bg-emerald-500/10" />
        <span
          className="absolute inset-0 rounded-full"
          style={{
            backgroundImage:
              "conic-gradient(from 0deg, transparent 0deg, rgba(0,212,150,0.35) 30deg, transparent 60deg)",
            animation: "atlas-sweep 6s linear infinite",
            maskImage: "radial-gradient(circle at center, black 68%, transparent 70%)",
            WebkitMaskImage: "radial-gradient(circle at center, black 68%, transparent 70%)",
          }}
        />
        <span
          className="absolute left-1/2 top-1/2 size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full"
          style={{
            background: "#00ffae",
            boxShadow: "0 0 12px rgba(0,255,174,0.85), 0 0 34px rgba(0,255,174,0.4)",
          }}
        />
      </div>

      <div className="relative mx-auto flex h-full max-w-[1600px] flex-col px-6 md:px-10">
        {/* top bar */}
        <header className="flex shrink-0 items-center justify-between py-5">
          <div className="flex items-center gap-3">
            {dark ? (
              <img src={stridesLogoDark} alt="Strides" className="h-8" />
            ) : (
              <span className="flex items-center gap-1.5">
                <img src={stridesIconLight} alt="" className="h-8" />
                <img src={stridesWordmarkLight} alt="Strides" className="h-[15px] w-[68px]" />
              </span>
            )}
            <span className={`h-7 w-px ${dark ? "bg-white/12" : "bg-[#00402c]/15"}`} />
            <img src={athenaLogo} alt="" className="h-8" />
            <span className="leading-tight">
              <span className={`font-display block text-[19px] font-semibold ${heading}`}>Athena</span>
              <span className={`block text-[9px] font-semibold uppercase ${label}`} style={{ letterSpacing: "0.25em" }}>
                Investigation AI Assistance
              </span>
            </span>
          </div>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={toggleTheme}
              aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
              className={`grid size-9 place-items-center rounded-full border transition ${
                dark
                  ? "border-white/12 bg-white/[0.04] text-emerald-100 hover:bg-white/[0.09]"
                  : "border-[#00402c]/15 bg-white/70 text-[#00402c] hover:bg-white"
              }`}
            >
              {dark ? <Sun className="size-[16px]" /> : <Moon className="size-[16px]" />}
            </button>
          </div>
        </header>

        {/* main */}
        <main className="grid min-h-0 flex-1 grid-cols-1 items-center gap-16 pb-8 lg:grid-cols-2">
          {/* left: story */}
          <section className={`flex h-full min-h-0 flex-col justify-center ${enter} ${shown}`}>
            <h1
              className="font-display max-w-xl bg-clip-text text-3xl font-bold leading-[1.12] tracking-tight text-transparent md:text-4xl"
              style={{
                backgroundImage: dark
                  ? "linear-gradient(100deg, #c5e896, #6ee7b7 45%, #00d496)"
                  : "linear-gradient(100deg, #00402c, #00724a 45%, #00955e)",
              }}
            >
              Intelligence that drives better Investigations
            </h1>

            <div className="mt-5 flex flex-wrap items-center gap-6 text-[11.5px] font-semibold">
              <span className={`inline-flex items-center gap-2 ${dark ? "text-emerald-200/80" : "text-[#00724a]"}`}>
                <Activity className="size-4" /> {openInvestigations ?? "—"} investigations · live
              </span>
            </div>

            <div className="mt-6 min-h-0 flex-1">
              <Schematic dark={dark} />
            </div>
          </section>

          {/* right: login card */}
          <section className={`flex items-center justify-center ${enter} delay-150 ${shown}`}>
            <div className="relative w-full max-w-md">
              <div
                aria-hidden
                className="absolute -inset-6 rounded-[32px] blur-2xl"
                style={{
                  backgroundImage: dark
                    ? "linear-gradient(135deg, rgba(0,212,150,0.28), rgba(110,231,183,0.12) 55%, transparent)"
                    : "linear-gradient(135deg, rgba(113,215,126,0.4), rgba(197,232,150,0.25) 55%, transparent)",
                }}
              />

              <div className={`relative rounded-3xl border p-8 shadow-2xl backdrop-blur-2xl ${cardShell}`}>
                {/* corner ticks */}
                {[
                  "left-3 top-3 border-l border-t",
                  "right-3 top-3 border-r border-t",
                  "left-3 bottom-3 border-b border-l",
                  "right-3 bottom-3 border-b border-r",
                ].map((pos) => (
                  <span
                    key={pos}
                    aria-hidden
                    className={`pointer-events-none absolute size-3 border-emerald-400/40 ${pos}`}
                  />
                ))}

                <p className={`text-[10px] font-bold uppercase ${label}`} style={{ letterSpacing: "0.25em" }}>
                  Secure access
                </p>
                <h2 className={`font-display mt-2 text-[26px] font-bold tracking-tight ${heading}`}>
                  Welcome back
                </h2>

                <form className="mt-7 space-y-5" onSubmit={signIn}>
                  <div className="group relative">
                    <label htmlFor="username" className={`block text-[10px] font-bold uppercase tracking-[0.18em] ${label}`}>
                      Username
                    </label>
                    <input
                      id="username"
                      type="text"
                      required
                      autoFocus
                      autoComplete="username"
                      value={username}
                      onChange={(e) => setUsername(e.target.value)}
                      className={`mt-2 w-full rounded-xl border px-4 py-3 text-[13px] outline-none transition focus:border-emerald-400/50 ${field}`}
                    />
                    <span
                      aria-hidden
                      className="absolute bottom-0 left-0 h-px w-full origin-left scale-x-0 bg-gradient-to-r from-[#6ee7b7] via-[#00d496] to-transparent transition-transform duration-500 group-focus-within:scale-x-100"
                    />
                  </div>

                  <div className="group relative">
                    <div className="flex items-baseline justify-between gap-3">
                      <label htmlFor="password" className={`block text-[10px] font-bold uppercase tracking-[0.18em] ${label}`}>
                        Password
                      </label>
                    </div>
                    <div className="relative">
                      <input
                        id="password"
                        type={showPass ? "text" : "password"}
                        required
                        autoComplete="current-password"
                        placeholder="••••••••••••"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        className={`mt-2 w-full rounded-xl border px-4 py-3 pr-11 text-[13px] outline-none transition focus:border-emerald-400/50 ${field}`}
                      />
                      <button
                        type="button"
                        onClick={() => setShowPass((s) => !s)}
                        aria-label={showPass ? "Hide password" : "Show password"}
                        className={`absolute right-3 top-1/2 mt-1 -translate-y-1/2 border-0 bg-transparent p-0 transition ${
                          dark ? "text-emerald-400/70 hover:text-emerald-400" : "text-[#383536]/45 hover:text-[#00402c]"
                        }`}
                      >
                        {showPass ? <EyeOff className="size-[16px]" /> : <Eye className="size-[16px]" />}
                      </button>
                    </div>
                    <span
                      aria-hidden
                      className="absolute bottom-0 left-0 h-px w-full origin-left scale-x-0 bg-gradient-to-r from-[#6ee7b7] via-[#00d496] to-transparent transition-transform duration-500 group-focus-within:scale-x-100"
                    />
                  </div>

                  {error && <p className="text-[12.5px] text-red-400">{error}</p>}

                  <button
                    type="submit"
                    disabled={submitting}
                    className="group relative flex w-full items-center justify-center gap-2 overflow-hidden rounded-xl py-3.5 text-[13.5px] font-semibold text-[#02160e] transition disabled:opacity-80"
                    style={{
                      backgroundImage: "linear-gradient(100deg, #6ee7b7, #00d496 52%, #00955e)",
                      boxShadow: "0 12px 30px -12px rgba(0,212,150,0.65), inset 0 1px 0 rgba(255,255,255,0.45)",
                    }}
                  >
                    <span
                      aria-hidden
                      className="pointer-events-none absolute inset-0 -translate-x-full bg-white/30 transition-transform duration-700 group-hover:translate-x-full"
                    />
                    {submitting ? (
                      <>
                        <Loader2 className="size-4 animate-spin" /> Authenticating…
                      </>
                    ) : (
                      <>
                        Enter Athena
                        <ArrowRight className="size-4 transition-transform duration-300 group-hover:translate-x-1" />
                      </>
                    )}
                  </button>
                </form>

                <p className={`mt-6 text-center text-[11px] ${body}`}>
                  Protected by end-to-end encryption · {new Date().getFullYear()}
                </p>
              </div>
            </div>
          </section>
        </main>
      </div>
    </div>
  );
}
