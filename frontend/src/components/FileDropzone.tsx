import { useRef, useState } from "react";

export function FileDropzone({
  onFileSelected,
  disabled,
  loading = false,
  label = "Drag & Drop or Choose file to upload",
  hint = "fig, zip, pdf, png, jpeg",
  compact = false,
}: {
  onFileSelected: (file: File) => void;
  disabled?: boolean;
  // An upload/critique triggered by this dropzone is in flight — shows a
  // spinner in place of the upload icon and swaps the label to "Uploading…"
  // instead of leaving the control merely dimmed with no feedback that
  // anything is happening (2026-08-13, per the user).
  loading?: boolean;
  label?: string;
  hint?: string;
  // Horizontal, no-hint-text button variant — matches the Task Critique
  // list page's compact per-row upload control (2026-08-12 Figma revision).
  compact?: boolean;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const isDisabled = disabled || loading;

  function handleFiles(files: FileList | null) {
    if (isDisabled || !files || files.length === 0) return;
    onFileSelected(files[0]);
  }

  const displayLabel = loading ? "Uploading…" : label;

  return (
    <div
      onClick={() => !isDisabled && inputRef.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        if (!isDisabled) setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        handleFiles(e.dataTransfer.files);
      }}
      style={compact ? {
        border: `1px dashed ${dragOver ? "var(--color-primary)" : "var(--color-card-border)"}`,
        borderRadius: 6,
        padding: "16px 24px",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 8,
        background: "var(--color-bg)",
        cursor: isDisabled ? "default" : "pointer",
        opacity: disabled && !loading ? 0.5 : 1,
        whiteSpace: "nowrap",
      } : {
        border: `1px dashed ${dragOver ? "var(--color-primary)" : "var(--color-card-border)"}`,
        borderRadius: 6,
        padding: "16px 24px",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 12,
        background: "var(--color-bg)",
        cursor: isDisabled ? "default" : "pointer",
        opacity: disabled && !loading ? 0.5 : 1,
        textAlign: "center",
      }}
    >
      {loading && <span className="spinner" style={{ color: "var(--color-text-faint)" }} />}
      {compact ? (
        <p style={{ margin: 0, fontSize: "var(--font-size-sm)", color: "var(--color-text-faint)" }}>{displayLabel}</p>
      ) : (
        <div>
          <p style={{ margin: 0, fontSize: "var(--font-size-base)" }}>{displayLabel}</p>
          {!loading && <p style={{ margin: "4px 0 0", fontSize: "var(--font-size-xs)", color: "var(--color-text-muted)" }}>{hint}</p>}
        </div>
      )}
      <input
        ref={inputRef}
        type="file"
        style={{ display: "none" }}
        disabled={isDisabled}
        onChange={(e) => {
          handleFiles(e.target.files);
          e.target.value = "";
        }}
      />
    </div>
  );
}