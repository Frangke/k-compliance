import { useEffect } from 'react';
import { useAuthStore } from '../store/authStore';
import { authApi } from '../api/auth';

const IDLE_TIMEOUT = 30 * 60 * 1000; // 30 minutes
const WARN_BEFORE = 5 * 60 * 1000; // warn at 25 min

export function useIdleTimeout(onWarn: () => void, onExpire: () => void) {
  const lastActivity = useAuthStore((s) => s.lastActivity);

  useEffect(() => {
    const check = setInterval(() => {
      const elapsed = Date.now() - lastActivity;
      if (elapsed >= IDLE_TIMEOUT) {
        onExpire();
      } else if (elapsed >= IDLE_TIMEOUT - WARN_BEFORE) {
        onWarn();
      }
    }, 30_000); // check every 30s
    return () => clearInterval(check);
  }, [lastActivity, onWarn, onExpire]);
}

export function useInitAuth() {
  const setUser = useAuthStore((s) => s.setUser);

  useEffect(() => {
    authApi
      .me()
      .then((res) => setUser(res.data))
      .catch(() => setUser(null));
  }, [setUser]);
}
