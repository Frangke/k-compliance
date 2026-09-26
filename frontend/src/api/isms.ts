import client from './client';

export const ismsApi = {
  getDomains: () => client.get('/api/isms/domains'),

  getItems: (params: { domain?: string; search?: string; page?: number; size?: number }) =>
    client.get('/api/isms/items', { params }),

  getItem: (code: string) => client.get(`/api/isms/items/${code}`),

  getChecklists: (code: string) => client.get(`/api/isms/items/${code}/checklists`),

  respondChecklist: (code: string, checklistId: number, data: any) =>
    client.post(`/api/isms/items/${code}/checklists/${checklistId}/respond`, data),

  assessItem: (code: string, data: any) => client.post(`/api/isms/items/${code}/assess`, data),

  getComplianceSummary: () => client.get('/api/isms/compliance-summary'),

  getAssignments: (code: string) => client.get(`/api/isms/items/${code}/assignments`),

  createAssignment: (code: string, data: { user_id: number; role_in_item?: string }) =>
    client.post(`/api/isms/items/${code}/assignments`, data),

  deleteAssignment: (code: string, userId: number) => client.delete(`/api/isms/items/${code}/assignments/${userId}`),

  getMyItems: () => client.get('/api/isms/my-items'),

  getComplianceHistory: (code: string) => client.get(`/api/isms/items/${code}/compliance-history`),

  getComplianceDetail: (status?: string) =>
    client.get('/api/isms/compliance-detail', { params: { status_filter: status || undefined } }),

  exportComplianceCsv: (status?: string) =>
    `/api/isms/compliance-detail/csv${status ? `?status_filter=${status}` : ''}`,

  getComplianceStatusMap: () => client.get<Record<string, string>>('/api/isms/compliance-status-map'),
};
