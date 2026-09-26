import { create } from 'zustand';
import type { User } from '../types';

interface AuthState {
  user: User | null;
  lastActivity: number;
  setUser: (user: User | null) => void;
  touchActivity: () => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  lastActivity: Date.now(),
  setUser: (user) => set({ user }),
  touchActivity: () => set({ lastActivity: Date.now() }),
  logout: () => set({ user: null }),
}));
