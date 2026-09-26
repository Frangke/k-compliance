import client from './client';
import type { User } from '../types';

export const authApi = {
  login: (username: string, password: string) =>
    client.post<{ message: string; user: User }>('/api/auth/login', { username, password }),

  logout: () => client.post('/api/auth/logout'),

  me: () => client.get<User>('/api/auth/me'),

  refresh: () => client.post('/api/auth/refresh'),

  changePassword: (currentPassword: string, newPassword: string) =>
    client.post('/api/auth/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    }),
};
