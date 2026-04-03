/**
 * Preferences store using Zustand with persistence
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { immer } from 'zustand/middleware/immer';
import type { UserPreferences, SportType, SurfacePreferences } from '@/types';

interface PreferencesState extends UserPreferences {
  // User auth state
  isAuthenticated: boolean;
  userId: string | null;
  token: string | null;

  // Actions
  setPreferences: (prefs: Partial<UserPreferences>) => void;
  setBikeType: (type: SportType) => void;
  setFitnessLevel: (level: UserPreferences['fitnessLevel']) => void;
  setMtbSkill: (skill: UserPreferences['mtbSkill']) => void;
  setRiskTolerance: (tolerance: UserPreferences['riskTolerance']) => void;
  setSurfacePreferences: (prefs: SurfacePreferences) => void;
  addAvoidance: (avoidance: string) => void;
  removeAvoidance: (avoidance: string) => void;
  setUnits: (units: 'imperial' | 'metric') => void;
  setAuthenticated: (auth: { userId: string; token: string } | null) => void;
  reset: () => void;
}

const defaultPreferences: UserPreferences = {
  bikeType: 'road',
  fitnessLevel: 'intermediate',
  ftp: undefined,
  typicalSpeedMph: 12,
  maxClimbToleranceFt: 3000,
  mtbSkill: 'intermediate',
  riskTolerance: 'medium',
  surfacePreferences: {
    pavement: 0.2,
    gravel: 0.3,
    singletrack: 0.5,
  },
  avoidances: [],
  units: 'imperial',
};

export const usePreferencesStore = create<PreferencesState>()(
  persist(
    immer((set) => ({
      // Initial state
      ...defaultPreferences,
      isAuthenticated: false,
      userId: null,
      token: null,

      // Actions
      setPreferences: (prefs) => set((state) => {
        Object.assign(state, prefs);
      }),

      setBikeType: (type) => set((state) => {
        state.bikeType = type;
      }),

      setFitnessLevel: (level) => set((state) => {
        state.fitnessLevel = level;
      }),

      setMtbSkill: (skill) => set((state) => {
        state.mtbSkill = skill;
      }),

      setRiskTolerance: (tolerance) => set((state) => {
        state.riskTolerance = tolerance;
      }),

      setSurfacePreferences: (prefs) => set((state) => {
        state.surfacePreferences = prefs;
      }),

      addAvoidance: (avoidance) => set((state) => {
        if (!state.avoidances.includes(avoidance)) {
          state.avoidances.push(avoidance);
        }
      }),

      removeAvoidance: (avoidance) => set((state) => {
        const index = state.avoidances.indexOf(avoidance);
        if (index > -1) {
          state.avoidances.splice(index, 1);
        }
      }),

      setUnits: (units) => set((state) => {
        state.units = units;
      }),

      setAuthenticated: (auth) => set((state) => {
        if (auth) {
          state.isAuthenticated = true;
          state.userId = auth.userId;
          state.token = auth.token;
        } else {
          state.isAuthenticated = false;
          state.userId = null;
          state.token = null;
        }
      }),

      reset: () => set((state) => {
        Object.assign(state, defaultPreferences);
      }),
    })),
    {
      name: 'john-router-preferences',
      partialize: (state) => ({
        bikeType: state.bikeType,
        fitnessLevel: state.fitnessLevel,
        ftp: state.ftp,
        typicalSpeedMph: state.typicalSpeedMph,
        maxClimbToleranceFt: state.maxClimbToleranceFt,
        mtbSkill: state.mtbSkill,
        riskTolerance: state.riskTolerance,
        surfacePreferences: state.surfacePreferences,
        avoidances: state.avoidances,
        units: state.units,
        isAuthenticated: state.isAuthenticated,
        userId: state.userId,
        token: state.token,
      }),
    }
  )
);
