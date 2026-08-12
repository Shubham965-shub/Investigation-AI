import { useRef, useState } from "react";
import uploadIcon from "../assets/icons/rci-document-upload.svg";

export function FileDropzone({
  onFileSelected,
  disabled,
  label = "Drag & Drop or Choose file to upload",
  hint = "fig, zip, pdf, png, jpeg",
  compact = false,
}: {
  onFileSelected: (file: File) => void;
  disabled?: boolean;
  label?: string;
  hint?: string;
  // Horizontal, no-hint-text button variant — matches the Task Critique
  // list page's compact per-row upload control (2026-08-12 Figma revision).
  compact?: boolean;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);

  function handleFiles(files: FileList | null) {
    if (disabled || !files || files.length === 0) return;
    onFileSelected(files[0]);
  }

  return (
    <div
      onClick={() => !disabled && inputRef.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setDragOver(true);
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
        cursor: disabled ? "default" : "pointer",
        opacity: disabled ? 0.5 : 1,
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
        cursor: disabled ? "default" : "pointer",
        opacity: disabled ? 0.5 : 1,
        textAlign: "center",
      }}
    >
      <img src={uploadIcon} alt="" width={compact ? 20 : 24} height={compact ? 20 : 24} />
      {compact ? (
        <p style={{ margin: 0, fontSize: "var(--font-size-sm)", color: "var(--color-text-faint)" }}>{label}</p>
      ) : (
        <div>
          <p style={{ margin: 0, fontSize: "var(--font-size-base)" }}>{label}</p>
          <p style={{ margin: "4px 0 0", fontSize: "var(--font-size-xs)", color: "var(--color-text-muted)" }}>{hint}</p>
        </div>
      )}
      <input
        ref={inputRef}
        type="file"
        style={{ display: "none" }}
        disabled={disabled}
        onChange={(e) => {
          handleFiles(e.target.files);
          e.target.value = "";
        }}
      />
    </div>
  );
}