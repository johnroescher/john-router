import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';
import type { PlanningLoopResult } from '@/types';

interface PlanningState {
  planning: PlanningLoopResult | null;
  setPlanning: (planning: PlanningLoopResult | null) => void;
  clearPlanning: () => void;
}

export const usePlanningStore = create<PlanningState>()(
  immer((set) => ({
    planning: null,
    setPlanning: (planning) => set((state) => {
      state.planning = planning;
    }),
    clearPlanning: () => set((state) => {
      state.planning = null;
    }),
  }))
);
