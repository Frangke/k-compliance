import { create } from 'zustand';
import { persist } from 'zustand/middleware';

/**
 * The "current assessment" is a UI-side convenience: the user sets it once
 * and every assess/report action in the same session quietly attaches to
 * that round. The server never reads it — the client still has to forward
 * assessment_id explicitly when calling the API.
 */
interface CurrentAssessmentState {
  currentAssessmentId: number | null;
  setCurrentAssessmentId: (id: number | null) => void;
}

export const useCurrentAssessmentStore = create<CurrentAssessmentState>()(
  persist(
    (set) => ({
      currentAssessmentId: null,
      setCurrentAssessmentId: (id) => set({ currentAssessmentId: id }),
    }),
    { name: 'kc-current-assessment' },
  ),
);
