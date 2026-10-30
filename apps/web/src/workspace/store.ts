import { create } from 'zustand';

export interface Toast {
  id: number;
  title: string;
  body?: string;
  tone: 'success' | 'danger' | 'info';
  to?: string;
}

const ADVANCED_KEY = 'ci.advanced-open';
function readAdvanced() {
  try {
    return localStorage.getItem(ADVANCED_KEY) === '1';
  } catch {
    return false;
  }
}

// UI state only. Customer records, files and session credentials never enter persistence;
// the only persisted value is whether the Advanced navigation group is open.
export const useWorkspaceStore = create<{
  advancedOpen: boolean;
  setAdvanced: (value: boolean) => void;
  menuOpen: boolean;
  askOpen: boolean;
  paletteOpen: boolean;
  providerConsent: boolean;
  toasts: Toast[];
  setMenu: (value: boolean) => void;
  setAsk: (value: boolean) => void;
  setPalette: (value: boolean) => void;
  consent: (value?: boolean) => void;
  toast: (toast: Omit<Toast, 'id'>) => void;
  dismiss: (id: number) => void;
  reset: () => void;
}>((set) => ({
  advancedOpen: readAdvanced(),
  setAdvanced: (advancedOpen) => {
    try {
      localStorage.setItem(ADVANCED_KEY, advancedOpen ? '1' : '0');
    } catch {
      /* storage unavailable: keep the in-memory value */
    }
    set({ advancedOpen });
  },
  menuOpen: false,
  askOpen: false,
  paletteOpen: false,
  providerConsent: false,
  toasts: [],
  setMenu: (menuOpen) => set({ menuOpen }),
  setAsk: (askOpen) => set({ askOpen }),
  setPalette: (paletteOpen) => set({ paletteOpen }),
  consent: (providerConsent = true) => set({ providerConsent }),
  toast: (toast) =>
    set((s) => ({
      toasts: [...s.toasts, { ...toast, id: Date.now() + Math.random() }],
    })),
  dismiss: (id) =>
    set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
  reset: () =>
    set({
      menuOpen: false,
      askOpen: false,
      paletteOpen: false,
      providerConsent: false,
      toasts: [],
    }),
}));
