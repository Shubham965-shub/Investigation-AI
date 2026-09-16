import { useEffect, useRef, useState } from "react";

/**
 * Wordless sketch story of an investigation:
 * 1. a batch runs out of specification (deviation)
 * 2. the deviation is logged on a clipboard record
 * 3. an investigator hunts the root cause (magnifier over a fishbone)
 * 4. the investigation report is signed off and closed
 */

type Props = { dark: boolean };

const scenes = ["deviation", "record", "investigate", "closure"] as const;

function renderScene(name: (typeof scenes)[number], p: LayerProps) {
  if (name === "deviation") return <SceneDeviation {...p} />;
  if (name === "record") return <SceneRecord {...p} />;
  if (name === "investigate") return <SceneInvestigate {...p} />;
  return <SceneClosure {...p} />;
}

export function Schematic({ dark }: Props) {
  const [index, setIndex] = useState(0);
  const [prev, setPrev] = useState<number | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const id = setInterval(() => {
      setIndex((i) => {
        setPrev(i);
        if (timer.current) clearTimeout(timer.current);
        timer.current = setTimeout(() => setPrev(null), 900);
        return (i + 1) % scenes.length;
      });
    }, 4500);
    return () => {
      clearInterval(id);
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  const scene = scenes[index] ?? scenes[0]!;
  const line = dark ? "#6ee7b7" : "#00402c";
  const faint = dark ? "#71d77e" : "#00724a";
  const flow = dark ? "#c5e896" : "#00955e";
  const p: LayerProps = { line, faint, flow };

  return (
    <div className="relative flex h-full min-h-[280px] w-full flex-col">
      <div className="relative flex-1 overflow-hidden">
        {/* depth: far ambient field behind every scene */}
        <Backdrop line={line} faint={faint} flow={flow} />

        {/* outgoing scene keeps depth during the hand-off */}
        {prev !== null && (
          <div key={`out-${prev}`} className="atlas-scene-out absolute inset-0">
            {renderScene(scenes[prev]!, p)}
          </div>
        )}
        <div key={`in-${scene}`} className="atlas-scene-in absolute inset-0">
          {renderScene(scene, p)}
        </div>

        {/* foreground: AI scan sweep + soft vignette for depth of field */}
        <div className="pointer-events-none absolute inset-0 overflow-hidden">
          <div
            className="atlas-scan absolute inset-y-0 w-[26%]"
            style={{
              background: `linear-gradient(90deg, transparent, ${flow}22 45%, ${flow}44 50%, ${flow}22 55%, transparent)`,
            }}
          />
          <div
            className="absolute inset-0"
            style={{
              background: dark
                ? "radial-gradient(120% 100% at 50% 45%, transparent 45%, rgba(2,17,11,0.55) 100%)"
                : "radial-gradient(120% 100% at 50% 45%, transparent 50%, rgba(246,250,244,0.6) 100%)",
            }}
          />
        </div>
      </div>


      <div className="mt-4 flex items-center gap-2">
        {scenes.map((s, i) => (
          <span
            key={s}
            className="h-[3px] flex-1 rounded-full transition-opacity duration-500"
            style={{ background: i === index ? flow : faint, opacity: i === index ? 0.95 : 0.16 }}
          />
        ))}
      </div>
    </div>
  );
}

type LayerProps = { line: string; faint: string; flow: string };

const VB = "0 0 640 420";
const layer = "absolute inset-0 h-full w-full";

/* ---------------- 1 · batch drifts out of specification ---------------- */

function SceneDeviation({ line, faint, flow }: LayerProps) {
  return (
    <>
      <svg viewBox={VB} className={`${layer} atlas-sway-a atlas-depth-far`} fill="none" aria-hidden>
        {/* tablet batch on a conveyor, one is off-spec */}
        <g stroke={faint} strokeWidth="1.2" opacity="0.7" strokeLinecap="round">
          <path d="M60 356h520" />
          {[0, 1, 2, 3, 4, 5, 6, 7].map((i) => (
            <circle key={i} cx={92 + i * 66} r="7" cy="366" strokeWidth="0.9" />
          ))}
        </g>
        <g stroke={line} strokeWidth="1.5">
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <ellipse key={i} cx={110 + i * 74} cy="334" rx="22" ry="9" opacity={i === 4 ? 1 : 0.55} />
          ))}
        </g>
      </svg>

      <svg viewBox={VB} className={`${layer} atlas-sway-b atlas-depth-mid`} fill="none" aria-hidden>
        <g stroke={line} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
          {/* control chart axes */}
          <path d="M92 288V52" />
          <path d="M92 288h468" />
          {/* spec band */}
          <path d="M92 118h468" strokeWidth="1" strokeDasharray="7 8" opacity="0.55" />
          <path d="M92 228h468" strokeWidth="1" strokeDasharray="7 8" opacity="0.55" />
          {/* in-control run then excursion above the upper limit */}
          <path d="M100 186l64-14 60 18 62-12 58 12 66-16 62-98 56 26" strokeWidth="2.2">
            <animate attributeName="stroke-dasharray" values="0 900;900 0" dur="2.4s" fill="freeze" />
          </path>
        </g>
        {/* data markers */}
        <g fill={flow} opacity="0.9">
          {[
            [100, 186],
            [164, 172],
            [224, 190],
            [286, 178],
            [344, 190],
            [410, 174],
            [472, 76],
            [528, 102],
          ].map(([x, y], i) => (
            <circle key={i} cx={x} cy={y} r={i === 6 ? 5.5 : 3.2}>
              <animate attributeName="opacity" values="0;1" dur="0.3s" begin={`${0.3 + i * 0.24}s`} fill="freeze" />
            </circle>
          ))}
        </g>
      </svg>

      <svg viewBox={VB} className={`${layer} atlas-sway-c`} fill="none" aria-hidden>
        {/* alert on the out-of-spec point */}
        <g stroke={flow} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M472 26l30 52h-60z" />
          <path d="M472 46v14M472 68v2" />
          <circle cx="472" cy="76" r="24" strokeWidth="1.2" opacity="0.5">
            <animate attributeName="r" values="24;56" dur="2.2s" repeatCount="indefinite" />
            <animate attributeName="opacity" values="0.5;0" dur="2.2s" repeatCount="indefinite" />
          </circle>
        </g>
      </svg>
    </>
  );
}

/* ---------------- 2 · deviation logged as a record ---------------- */

function SceneRecord({ line, faint, flow }: LayerProps) {
  return (
    <>
      <svg viewBox={VB} className={`${layer} atlas-sway-b atlas-depth-mid`} fill="none" aria-hidden>
        <g stroke={line} strokeWidth="1.8" strokeLinejoin="round" strokeLinecap="round">
          {/* clipboard */}
          <path d="M190 66h228a14 14 0 0114 14v276a14 14 0 01-14 14H190a14 14 0 01-14-14V80a14 14 0 0114-14z" />
          <path d="M256 66V52a18 18 0 0118-18h60a18 18 0 0118 18v14z" />
          {/* record fields */}
          <path d="M206 118h176" strokeWidth="2.4" />
        </g>
        <g stroke={faint} strokeWidth="1.4" strokeLinecap="round">
          {[0, 1, 2].map((i) => (
            <g key={i}>
              <rect x="206" y={156 + i * 52} width="20" height="20" rx="4" strokeWidth="1.4" />
              <path d={`M244 ${166 + i * 52}h${i === 1 ? 106 : 144}`}>
                <animate
                  attributeName="stroke-dasharray"
                  values="0 200;200 0"
                  dur="0.6s"
                  begin={`${0.5 + i * 0.5}s`}
                  fill="freeze"
                />
              </path>
            </g>
          ))}
          <path d="M206 318h150M206 340h96" opacity="0.7" />
        </g>
        {/* checks appearing in the boxes */}
        <g stroke={flow} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" fill="none">
          {[0, 1, 2].map((i) => (
            <path key={i} d={`M210 ${166 + i * 52}l5 6 9 -11`}>
              <animate
                attributeName="stroke-dasharray"
                values="0 40;40 0"
                dur="0.35s"
                begin={`${0.9 + i * 0.5}s`}
                fill="freeze"
              />
            </path>
          ))}
        </g>
      </svg>

      <svg viewBox={VB} className={`${layer} atlas-sway-c`} fill="none" aria-hidden>
        {/* deviation feeding into the record */}
        <g stroke={flow} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M96 128l26 46h-52z" />
          <path d="M96 148v10" />
          <path d="M134 196c22 22 22 44 40 60" strokeDasharray="9 8" strokeWidth="1.6">
            <animate attributeName="stroke-dashoffset" values="34;0" dur="1.6s" repeatCount="indefinite" />
          </path>
          {/* signature at the bottom of the record */}
          <path d="M206 300c16-18 24 12 38-4s22 14 38-8" strokeWidth="1.8">
            <animate attributeName="stroke-dasharray" values="0 200;200 0" dur="1.4s" begin="2.2s" fill="freeze" />
          </path>
        </g>
        <circle cx="404" cy="92" r="4" fill={flow} className="atlas-dot" />
      </svg>
    </>
  );
}

/* ---------------- 3 · investigator hunts the root cause ---------------- */

function SceneInvestigate({ line, faint, flow }: LayerProps) {
  return (
    <>
      <svg viewBox={VB} className={`${layer} atlas-sway-a atlas-depth-far`} fill="none" aria-hidden>
        {/* fishbone / root-cause diagram */}
        <g stroke={faint} strokeWidth="1.4" strokeLinecap="round" opacity="0.85">
          <path d="M150 210h330" />
          <path d="M480 210l-26-16M480 210l-26 16" />
          {[0, 1, 2].map((i) => (
            <g key={i}>
              <path d={`M${200 + i * 96} 128l40 82`} />
              <path d={`M${200 + i * 96} 292l40 -82`} />
              <path d={`M${212 + i * 96} 152h34M${212 + i * 96} 268h34`} strokeWidth="1" opacity="0.7" />
            </g>
          ))}
          <path d="M150 210l-22-16M150 210l-22 16" opacity="0.6" />
        </g>
      </svg>

      <svg viewBox={VB} className={`${layer} atlas-sway-b atlas-depth-mid`} fill="none" aria-hidden>
        {/* investigator bust: hair, face, safety glasses, lab coat with badge */}
        <g stroke={line} strokeWidth="1.9" strokeLinejoin="round" strokeLinecap="round">
          {/* head */}
          <path d="M96 196v-46a30 30 0 0160 0v46a30 30 0 01-60 0z" />
          {/* hair */}
          <path d="M95 148c4-26 16-40 31-40s27 14 31 40" strokeWidth="1.6" opacity="0.85" />
          {/* safety glasses */}
          <circle cx="112" cy="164" r="8" strokeWidth="1.3" opacity="0.85" />
          <circle cx="140" cy="164" r="8" strokeWidth="1.3" opacity="0.85" />
          <path d="M120 164h12M96 162h8M148 162h8" strokeWidth="1" opacity="0.7" />
          {/* neck + shoulders / lab coat */}
          <path d="M112 224v10M144 224v10" strokeWidth="1.2" opacity="0.6" />
          <path d="M52 372v-72a72 72 0 0160-70l14 44 14-44a72 72 0 0160 70v72" />
          {/* coat opening */}
          <path d="M112 230l14 44 14-44" strokeWidth="1.3" opacity="0.75" />
          <path d="M126 274v98" strokeWidth="1" opacity="0.45" />
          {/* ID badge */}
          <rect x="150" y="292" width="30" height="22" rx="4" strokeWidth="1.3" opacity="0.8" />
          <path d="M156 300h16M156 307h10" strokeWidth="0.9" opacity="0.6" />
          {/* arm reaching out toward the diagram */}
          <path d="M196 300l40 -34" strokeWidth="1.8" />
        </g>
      </svg>

      <svg viewBox={VB} className={`${layer} atlas-sway-c`} fill="none" aria-hidden>
        {/* magnifier sweeping the fishbone; a bone is confirmed as the cause */}
        <g stroke={flow} strokeWidth="2.4" fill="none" strokeLinecap="round">
          <g>
            <circle cx="0" cy="0" r="46" />
            <circle cx="0" cy="0" r="46" opacity="0.25" strokeWidth="10" />
            <path d="M33 33l34 34" strokeWidth="6" />
            <animateTransform
              attributeName="transform"
              type="translate"
              values="264 220;340 158;424 246;300 264;264 220"
              dur="6.4s"
              repeatCount="indefinite"
            />
          </g>
        </g>
        {/* the found cause lights up */}
        <g stroke={flow} strokeWidth="2.2" strokeLinecap="round">
          <path d="M296 128l40 82" opacity="0.95">
            <animate attributeName="opacity" values="0.2;1;0.2" dur="3.2s" repeatCount="indefinite" />
          </path>
        </g>
        <circle cx="480" cy="210" r="4.5" fill={flow} className="atlas-dot" />
      </svg>
    </>
  );
}

/* ---------------- 4 · investigation closed out ---------------- */

function SceneClosure({ line, faint, flow }: LayerProps) {
  return (
    <>
      <svg viewBox={VB} className={`${layer} atlas-sway-b atlas-depth-mid`} fill="none" aria-hidden>
        <g stroke={line} strokeWidth="1.8" strokeLinejoin="round" strokeLinecap="round">
          {/* finished investigation report */}
          <path d="M150 46h198l36 36v256a14 14 0 01-14 14H164a14 14 0 01-14-14z" />
          <path d="M348 46v36h36" />
          <path d="M176 116h140" strokeWidth="2.4" />
        </g>
        <g stroke={faint} strokeWidth="1.3" strokeLinecap="round" opacity="0.75">
          {[0, 1, 2, 3].map((i) => (
            <path key={i} d={`M176 ${152 + i * 26}h${i % 2 ? 108 : 150}`} />
          ))}
        </g>
        {/* signature */}
        <g stroke={line} strokeWidth="1.8" fill="none" strokeLinecap="round">
          <path d="M176 300h130" strokeWidth="0.9" opacity="0.55" />
          <path d="M180 292c18-20 26 12 42-4s24 14 42-8">
            <animate attributeName="stroke-dasharray" values="0 200;200 0" dur="1.5s" begin="0.3s" fill="freeze" />
          </path>
        </g>
      </svg>

      <svg viewBox={VB} className={`${layer} atlas-sway-c`} fill="none" aria-hidden>
        {/* approval stamp landing on the report */}
        <g stroke={flow} strokeWidth="2.4" fill="none" strokeLinecap="round" strokeLinejoin="round">
          <g>
            <circle cx="452" cy="238" r="58" strokeDasharray="9 7" />
            <path d="M422 240l22 22 42-48" strokeWidth="5" />
            <animateTransform
              attributeName="transform"
              type="scale"
              values="1.6;1"
              dur="0.5s"
              begin="1.1s"
              fill="freeze"
              additive="sum"
            />
            <animate attributeName="opacity" values="0;1" dur="0.4s" begin="1.1s" fill="freeze" />
          </g>
          <circle cx="452" cy="238" r="58" opacity="0.4">
            <animate attributeName="r" values="58;96" dur="2.6s" begin="1.5s" repeatCount="indefinite" />
            <animate attributeName="opacity" values="0.4;0" dur="2.6s" begin="1.5s" repeatCount="indefinite" />
          </circle>
        </g>
        {/* corrective actions issued from the report */}
        <g stroke={flow} strokeWidth="1.6" fill="none" strokeLinecap="round">
          {[0, 1].map((i) => (
            <g key={i}>
              <path d={`M390 ${96 + i * 46}h44`} strokeDasharray="8 7">
                <animate
                  attributeName="stroke-dashoffset"
                  values="30;0"
                  dur={`${1.4 + i * 0.5}s`}
                  repeatCount="indefinite"
                />
              </path>
              <rect x="440" y={78 + i * 46} width="34" height="34" rx="7" />
              <path d={`M449 ${95 + i * 46}l7 8 12 -14`} strokeWidth="2.4" />
            </g>
          ))}
        </g>
      </svg>
    </>
  );
}

/* ---------------- ambient depth field behind all scenes ---------------- */

function Backdrop({ line, faint, flow }: LayerProps) {
  return (
    <div className="pointer-events-none absolute inset-0">
      {/* far: blurred dot grid slowly drifting */}
      <svg viewBox={VB} className={`${layer} atlas-drift atlas-depth-far`} fill="none" aria-hidden>
        <g fill={faint} opacity="0.5">
          {Array.from({ length: 10 }).map((_, r) =>
            Array.from({ length: 15 }).map((_, c) => (
              <circle key={`${r}-${c}`} cx={24 + c * 43} cy={20 + r * 42} r="1.4" />
            )),
          )}
        </g>
      </svg>

      {/* mid: breathing halos give the sketch a sense of space */}
      <svg viewBox={VB} className={`${layer} atlas-halo`} fill="none" aria-hidden>
        <circle cx="300" cy="200" r="150" stroke={flow} strokeWidth="0.9" opacity="0.5" />
        <circle cx="300" cy="200" r="196" stroke={flow} strokeWidth="0.7" opacity="0.3" />
      </svg>

      {/* near: data motes travelling along the depth axis */}
      <svg viewBox={VB} className={layer} fill="none" aria-hidden>
        {[
          { x: 40, y: 340, dx: 560, d: 9 },
          { x: 600, y: 90, dx: -540, d: 12 },
          { x: 120, y: 60, dx: 420, d: 15 },
        ].map((m, i) => (
          <circle key={i} cx={m.x} cy={m.y} r={2.4 - i * 0.4} fill={line} opacity="0.5">
            <animate
              attributeName="cx"
              values={`${m.x};${m.x + m.dx};${m.x}`}
              dur={`${m.d}s`}
              repeatCount="indefinite"
            />
            <animate attributeName="opacity" values="0;0.6;0" dur={`${m.d}s`} repeatCount="indefinite" />
          </circle>
        ))}
      </svg>
    </div>
  );
}
