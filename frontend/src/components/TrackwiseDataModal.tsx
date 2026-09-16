import modalClose from "../assets/icons/modal-close.svg";
import type { FieldDef } from "../constants/trackwiseFields";

// All TrackWise field sections/values for a record, read-only.
export function TrackwiseDataModal({
  recordId,
  problemStatement,
  sections,
  values,
  onClose,
}: {
  recordId: string;
  problemStatement: string;
  sections: [string, FieldDef[]][];
  values: Record<string, string>;
  onClose: () => void;
}) {
  return (
    <>
      <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(73, 84, 80, 0.45)", zIndex: 60 }} />
      <div
        role="dialog"
        style={{
          position: "fixed",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -50%)",
          background: "var(--color-surface)",
          borderRadius: 10,
          width: "min(1102px, 92vw)",
          maxHeight: "88vh",
          overflowY: "auto",
          zIndex: 61,
        }}
      >
        <div style={{ borderBottom: "1px solid var(--color-card-border)", padding: "16px 16px 17px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <p style={{ margin: 0, fontWeight: 700, fontSize: "var(--font-size-lg)", color: "var(--color-text)" }}>Record Details - Record ID - {recordId}</p>
          <button type="button" aria-label="Close" onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", padding: 0 }}>
            <img src={modalClose} alt="" width={32} height={32} />
          </button>
        </div>

        <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="card">
            <div className="card-header">
              <p className="card-title">Problem Statement</p>
            </div>
            <p style={{ margin: 0, fontWeight: 600, fontSize: "var(--font-size-md)", lineHeight: 1.8, color: "var(--color-text)" }}>{problemStatement}</p>
          </div>

          {sections.map(([section, sectionFields]) => (
            <div className="card" key={section}>
              <div className="card-header">
                <p className="card-title">{section}</p>
              </div>
              <p style={{ margin: "-8px 0 8px", fontSize: "var(--font-size-xs)", fontStyle: "italic", color: "var(--color-text-muted)" }}>
                (Pulled from TrackWise)
              </p>
              <div className="field-grid" style={{ flexWrap: "wrap" }}>
                {sectionFields.map((field) => (
                  <div key={field.key} style={{ minWidth: 240 }}>
                    <p className="field-label">{field.label}</p>
                    <div className="field-value">{values[field.key] || "—"}</div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
