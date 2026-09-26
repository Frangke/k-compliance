import axios from 'axios';
import { useAuthStore } from '../store/authStore';

// Detect code-server proxy prefix from current URL
// e.g. /proxy/5173/login → baseURL = /proxy/5173
const proxyMatch = window.location.pathname.match(/^\/proxy\/\d+/);
const baseURL = proxyMatch ? proxyMatch[0] : '';

const client = axios.create({
  baseURL,
  withCredentials: true,
});

client.interceptors.response.use(
  (response) => {
    useAuthStore.getState().touchActivity();
    return response;
  },
  async (error) => {
    const status = error.response?.status;
    const url = error.config?.url || '';

    // A 401 from auth endpoints is the caller's direct answer (wrong
    // credentials, invalid refresh token, no session yet) — not a sign that
    // our access token expired mid-session. Don't try to refresh or
    // redirect; let the caller surface the error. Otherwise a login failure
    // would kick off refresh → 401 → hard reload → login page mounts →
    // me() fires again → infinite loop.
    const isAuthEndpoint =
      url.includes('/api/auth/login') ||
      url.includes('/api/auth/refresh') ||
      url.includes('/api/auth/logout') ||
      url.includes('/api/auth/me');

    // Don't redirect if we're already on the login page — the user is here
    // to authenticate, a forced reload would just loop.
    const alreadyOnLogin = window.location.pathname.endsWith('/login');

    if (status === 401 && !isAuthEndpoint && !error.config._retry) {
      error.config._retry = true;
      try {
        await client.post('/api/auth/refresh');
        return client(error.config);
      } catch {
        useAuthStore.getState().logout();
        if (!alreadyOnLogin) {
          window.location.href = (baseURL || '') + '/login';
        }
      }
    }

    return Promise.reject(error);
  },
);

export default client;
