import { useAuthStore } from '../store/authStore';
import type { Role } from '../types';

export function usePermission() {
  const user = useAuthStore((s) => s.user);
  const role = user?.role;

  return {
    user,
    role,
    hasRole: (...roles: Role[]) => !!role && roles.includes(role),
    canWrite: role === 'cpo' || role === 'security_officer' || role === 'privacy_handler',
    isReadOnly: role === 'auditor',
  };
}
