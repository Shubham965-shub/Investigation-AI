import { createContext, useContext, useState, type ReactNode } from "react";

// Tracks whether a slide-in side panel is open, so AppHeader can become sticky only while one is open.
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
