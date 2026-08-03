import iconChevron from "../assets/icons/filter-chevron.svg";

// Real filter dropdown backed by a live "distinct values" list from the
// backend — styled to look like a decorative pill (via className, e.g.
// "ac-filter-pill"/"an-filter-pill") while being a real <select> underneath.
// Shared by ActionCenterPage and AnalyticsPage.
export function FilterSelect({
  value,
  onChange,
  defaultLabel,
  options,
  formatOption,
  className,
}: {
  value: string;
  onChange: (value: string) => void;
  defaultLabel: string;
  options: string[];
  formatOption?: (value: string) => string;
  className: string;
}) {
  return (
    <div style={{ position: "relative", display: "inline-flex" }}>
      <select
        className={className}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{ appearance: "none", paddingRight: 28, cursor: "pointer", maxWidth: 200 }}
      >
        <option value="">{defaultLabel}</option>
        {options.map((opt) => (
          <option key={opt} value={opt}>
            {formatOption ? formatOption(opt) : opt}
          </option>
        ))}
      </select>
      <img
        src={iconChevron}
        alt=""
        width={12}
        height={12}
        style={{ position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)", pointerEvents: "none" }}
      />
    </div>
  );
}