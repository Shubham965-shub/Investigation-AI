export const RCI_NONE = "none";
export const toRciSegment = (rciId: string | null | undefined) => (rciId ? rciId : RCI_NONE);
export const fromRciSegment = (seg: string | undefined) => (!seg || seg === RCI_NONE ? "" : seg);
export const recordPath = (recordId: string, rciId: string | null | undefined, step: string) =>
  `/records/${recordId}/${toRciSegment(rciId)}/${step}`;
