import client from './client';

export interface AuditLogEntry {
  id: number;
  user_id: number | null;
  username: string | null;
  user_name: string | null;
  action: string;
  entity_type: string | null;
  entity_id: number | null;
  old_values: Record<string, any> | null;
  new_values: Record<string, any> | null;
  ip_address: string | null;
  user_agent: string | null;
  created_at: string | null;
}

export interface AuditLogListResponse {
  items: AuditLogEntry[];
  total: number;
}

export interface AuditLogFilters {
  entity_type?: string;
  entity_id?: number;
  user_id?: number;
  action?: string;
  date_from?: string;
  date_to?: string;
  search?: string;
  page?: number;
  size?: number;
}

export const auditLogsApi = {
  list: (filters: AuditLogFilters = {}) => client.get<AuditLogListResponse>('/api/audit-logs', { params: filters }),

  entityTypes: () => client.get<{ entity_type: string; count: number }[]>('/api/audit-logs/entity-types'),

  actions: () => client.get<{ action: string; count: number }[]>('/api/audit-logs/actions'),

  getExportUrl: (filters: AuditLogFilters = {}) => {
    const base = client.defaults.baseURL || '';
    const qs = new URLSearchParams(
      Object.entries(filters).reduce<Record<string, string>>((acc, [k, v]) => {
        if (v !== undefined && v !== null && v !== '') acc[k] = String(v);
        return acc;
      }, {}),
    ).toString();
    return `${base}/api/audit-logs/export.csv${qs ? `?${qs}` : ''}`;
  },
};
