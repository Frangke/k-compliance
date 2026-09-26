import client from './client';

export type UserRole = 'cpo' | 'security_officer' | 'privacy_handler' | 'auditor';

export interface UserRecord {
  id: number;
  username: string;
  name: string;
  email: string;
  role: UserRole;
  department: string | null;
  is_active: boolean;
  last_login_at: string | null;
  password_changed_at: string | null;
  created_at: string;
}

export interface UserCreatePayload {
  username: string;
  password: string;
  name: string;
  email: string;
  role: UserRole;
  department?: string | null;
}

export interface UserUpdatePayload {
  name?: string;
  email?: string;
  role?: UserRole;
  department?: string | null;
  is_active?: boolean;
}

export const usersApi = {
  list: (params?: { role?: string; department?: string; is_active?: boolean; page?: number; size?: number }) =>
    client.get<{ items: UserRecord[]; total: number }>('/api/users', { params }),

  get: (id: number) => client.get<UserRecord>(`/api/users/${id}`),

  create: (payload: UserCreatePayload) => client.post<UserRecord>('/api/users', payload),

  update: (id: number, payload: UserUpdatePayload) => client.put<UserRecord>(`/api/users/${id}`, payload),

  resetPassword: (id: number, newPassword: string) =>
    client.put(`/api/users/${id}/reset-password`, { new_password: newPassword }),

  deactivate: (id: number) => client.delete(`/api/users/${id}`),
};
