/**
 * Field definitions mirror the trackwise field schemas enforced by
 * InvestigationAi_DS (src/agents/shared/schemas.py and the problem-statement
 * v2 schemas). Keys must match exactly what those pydantic models accept —
 * either the declared alias, or the plain field name where no alias exists.
 *
 * Field sets are intentionally scoped per module: RCI plan needs the
 * extended Deviation fields, problem-statement generation needs the
 * extended Market Complaint fields, everything else uses the base sets.
 */

export type EventType = "Deviation" | "OOS" | "OOT" | "OOS/OOT" | "Market Complaint";
export type Module = "problem-statement" | "evidence" | "questionnaire" | "rci-plan";
export type TrackwiseFields = Record<string, string | string[]>;

export interface FieldDef {
  key: string;
  label: string;
  required: boolean;
  kind?: "text" | "textarea" | "date" | "time" | "list";
  /** Matches the card grouping on the approved Problem Statement Figma screen. Omit for field sets with no reference layout. */
  section?: string;
}

const DEVIATION_BASE_FIELDS: FieldDef[] = [
  { key: "title", label: "Title", required: true, section: "Basic Information" },
  { key: "Observed By", label: "Observed By", required: true, section: "Basic Information" },
  { key: "Batch Number / AR Number", label: "Batch / AR Number", required: true, section: "Product / Material Information" },
  { key: "Product / Material Code", label: "Product / Material Code", required: true, section: "Product / Material Information" },
  { key: "Product Name / Material Name", label: "Product / Material Name", required: true, section: "Product / Material Information" },
  { key: "Deviation To", label: "Deviation To", required: true, section: "Product / Material Information" },
  { key: "Equipment Name", label: "Equipment Name", required: true, section: "Equipment & Instrument Information" },
  { key: "Instrument ID Number", label: "Instrument ID", required: true, section: "Equipment & Instrument Information" },
  { key: "Name of the Instrument", label: "Name of the Instrument", required: true, section: "Equipment & Instrument Information" },
  { key: "description", label: "Description", required: true, kind: "textarea", section: "Descriptive Details" },
];

const DEVIATION_EXTENDED_FIELDS: FieldDef[] = [
  ...DEVIATION_BASE_FIELDS,
  { key: "Deviation Number", label: "Deviation Number", required: true },
  { key: "Date Opened", label: "Date Opened", required: true, kind: "date" },
  { key: "Observation Date", label: "Observation Date", required: true, kind: "date" },
  { key: "Observation Time", label: "Observation Time", required: true, kind: "time" },
  { key: "Failure Duration", label: "Failure Duration", required: true },
  { key: "Related Market", label: "Related Market", required: true },
  { key: "Related Customer", label: "Related Customer", required: true },
  { key: "Equipment ID", label: "Equipment ID", required: true },
  { key: "Equipment Number", label: "Equipment Number", required: true },
  { key: "Deviation Owner", label: "Deviation Owner", required: true },
  { key: "Originator", label: "Originator", required: true },
  { key: "Immediate Actions", label: "Immediate Actions (one per line)", required: false, kind: "list" },
  { key: "Impact on Deviation Batches", label: "Impact on Deviation Batches", required: true },
  { key: "Impact Details", label: "Impact Details (one per line)", required: false, kind: "list" },
  { key: "Immediate Cause Known", label: "Immediate Cause Known", required: true },
  { key: "Cause Detail", label: "Cause Detail", required: true, kind: "textarea" },
  { key: "Proposal for Resolution", label: "Proposal for Resolution (one per line)", required: false, kind: "list" },
];

// Aliased where DS declares an alias; plain field name ("observation_date")
// where it doesn't — this exact combination satisfies both the v2 (problem
// statement) schema and the shared schema used by the other three modules.
const OOS_FIELDS: FieldDef[] = [
  { key: "title", label: "Title", required: true },
  { key: "description", label: "Description", required: true, kind: "textarea" },
  { key: "observation_date", label: "Observation Date", required: true, kind: "date" },
  { key: "Laboratory Details", label: "Laboratory Details", required: true },
  { key: "Specification Number", label: "Specification Number", required: true },
  { key: "Stability Condition", label: "Stability Condition", required: true },
  { key: "Stability Protocol Number", label: "Stability Protocol Number", required: true },
  { key: "Labelled Storage Conditions", label: "Labelled Storage Conditions", required: true },
  { key: "Failure type", label: "Failure Type", required: true },
  { key: "Observation Time", label: "Observation Time", required: true, kind: "time" },
  { key: "Product Type", label: "Product Type", required: true },
  { key: "STP Number", label: "STP Number", required: true },
  { key: "Stability Time Point", label: "Stability Time Point", required: true },
  { key: "Analyst Name", label: "Analyst Name", required: false },
  { key: "Batch Number / AR Number", label: "Batch Number / AR Number", required: false },
  { key: "Product Name / Material Name", label: "Product Name / Material Name", required: false },
  { key: "Batches Details", label: "Batches Details", required: false },
  { key: "Instrument ID Number", label: "Instrument ID Number", required: false },
  { key: "Product / Material Code", label: "Product / Material Code", required: false },
  { key: "Name of the Instrument", label: "Name of the Instrument", required: false },
  { key: "Name of the Test", label: "Name of the Test", required: false },
  { key: "Sample Number", label: "Sample Number", required: false },
];

const MARKET_COMPLAINT_BASE_FIELDS: FieldDef[] = [
  { key: "title", label: "Title", required: true },
  { key: "Date Complaint Received", label: "Date Complaint Received", required: true, kind: "date" },
  { key: "Market Complaint Reported By", label: "Market Complaint Reported By", required: true },
  { key: "Reference Complaint Number", label: "Reference Complaint Number", required: true },
  { key: "description", label: "Description", required: true, kind: "textarea" },
  { key: "Products Information", label: "Products Information", required: true },
  { key: "Dosage Form", label: "Dosage Form", required: true },
  { key: "Market", label: "Market", required: true },
  { key: "Product Manufacturing Info", label: "Product Manufacturing Info", required: true },
];

const MARKET_COMPLAINT_EXTENDED_FIELDS: FieldDef[] = [
  ...MARKET_COMPLAINT_BASE_FIELDS,
  { key: "Complainant Name", label: "Complainant Name", required: true },
  { key: "Complaint Received By", label: "Complaint Received By", required: true },
  { key: "Customer", label: "Customer", required: true },
  { key: "Complaint Country", label: "Complaint Country", required: true },
  { key: "Complaint Number", label: "Complaint Number", required: false },
];

export const EVENT_TYPE_OPTIONS: Record<Module, EventType[]> = {
  "problem-statement": ["Deviation", "OOS", "OOT", "Market Complaint"],
  evidence: ["Deviation", "OOS", "OOT", "OOS/OOT", "Market Complaint"],
  questionnaire: ["Deviation", "OOS", "OOT", "OOS/OOT", "Market Complaint"],
  "rci-plan": ["Deviation", "OOS", "OOT", "OOS/OOT", "Market Complaint"],
};

export function getFieldSet(module: Module, eventType: EventType): FieldDef[] {
  if (eventType === "Market Complaint") {
    return module === "problem-statement" ? MARKET_COMPLAINT_EXTENDED_FIELDS : MARKET_COMPLAINT_BASE_FIELDS;
  }
  if (eventType === "Deviation") {
    return module === "rci-plan" ? DEVIATION_EXTENDED_FIELDS : DEVIATION_BASE_FIELDS;
  }
  return OOS_FIELDS;
}

/**
 * Fields `module` needs for `eventType` that the Problem Statement step
 * didn't already collect. Only Deviation + RCI Plan has a gap today (DS
 * requires the extended field set there) — everything else returns [].
 */
export function getAdditionalFieldsForModule(module: Module, eventType: EventType): FieldDef[] {
  const moduleFields = getFieldSet(module, eventType);
  const collectedKeys = new Set(getFieldSet("problem-statement", eventType === "OOS/OOT" ? "OOS" : eventType).map((f) => f.key));
  return moduleFields.filter((f) => !collectedKeys.has(f.key));
}
