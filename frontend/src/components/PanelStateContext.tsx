import { createContext, useContext, useState, type ReactNode } from "react";

// Tracks whether any slide-in side panel (e.g. InvestigationPreviewPanel) is
// currently open, so AppHeader can become sticky only while one is open —
// otherwise the header scrolls away with the page as normal.
interface PanelStateContextValue {
  isPanelOpen: boolean;
  setPanelOpen: (open: boolean) => void;
}

const PanelStateContext = createContext<PanelStateContextValue | undefined>(undefined);

export function PanelStateProvider({ children }: { children: ReactNode }) {
  const [isPanelOpen, setPanelOpen] = useState(false);
  return <PanelStateContext.Provider value={{ isPanelOpen, setPanelOpen }}>{children}</PanelStateContext.Provider>;
}

export function usePanelState(): PanelStateContextValue {
  const context = useContext(PanelStateContext);
  if (!context) throw new Error("usePanelState must be used within a PanelStateProvider");
  return context;
}
