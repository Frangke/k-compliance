import client from './client';

export const consentApi = {
  list: () => client.get('/api/pipa/consent'),
  create: (data: any) => client.post('/api/pipa/consent', data),
  createVersion: (id: number, data: any) => client.post(`/api/pipa/consent/${id}/versions`, data),
  publish: (id: number, ver: number) => client.post(`/api/pipa/consent/${id}/versions/${ver}/publish`),
};

export const dsrApi = {
  list: (params?: any) => client.get('/api/pipa/dsr', { params }),
  create: (data: any) => client.post('/api/pipa/dsr', data),
  update: (id: number, data: any) => client.put(`/api/pipa/dsr/${id}`, data),
  assign: (id: number, userId: number) => client.post(`/api/pipa/dsr/${id}/assign?assigned_to=${userId}`),
  complete: (id: number, result: string) =>
    client.post(`/api/pipa/dsr/${id}/complete?result_description=${encodeURIComponent(result)}`),
  reject: (id: number, reason: string) =>
    client.post(`/api/pipa/dsr/${id}/reject?rejection_reason=${encodeURIComponent(reason)}`),
};

export const destructionApi = {
  list: (params?: any) => client.get('/api/pipa/destruction', { params }),
  create: (data: any) => client.post('/api/pipa/destruction', data),
  execute: (id: number, data: any) => client.post(`/api/pipa/destruction/${id}/execute`, data),
  verify: (id: number, data?: any) => client.post(`/api/pipa/destruction/${id}/verify`, data),
};

export const thirdPartyApi = {
  list: (params?: any) => client.get('/api/pipa/third-party', { params }),
  create: (data: any) => client.post('/api/pipa/third-party', data),
  update: (id: number, data: any) => client.put(`/api/pipa/third-party/${id}`, data),
  audit: (id: number, result: string) =>
    client.post(`/api/pipa/third-party/${id}/audit?audit_result=${encodeURIComponent(result)}`),
};

export const incidentApi = {
  list: () => client.get('/api/pipa/incidents'),
  create: (data: any) => client.post('/api/pipa/incidents', data),
  update: (id: number, data: any) => client.put(`/api/pipa/incidents/${id}`, data),
  addTimeline: (id: number, data: any) => client.post(`/api/pipa/incidents/${id}/timeline`, data),
  reportAuthority: (id: number, type: string) => client.post(`/api/pipa/incidents/${id}/report-authority`, { type }),
  notifySubjects: (id: number, data: any) => client.post(`/api/pipa/incidents/${id}/notify-subjects`, data),
};

export const correctiveApi = {
  list: (params?: any) => client.get('/api/corrective-actions', { params }),
  create: (data: any) => client.post('/api/corrective-actions', data),
  get: (id: number) => client.get(`/api/corrective-actions/${id}`),
  update: (id: number, data: any) => client.put(`/api/corrective-actions/${id}`, data),
  complete: (id: number, data: any) => client.post(`/api/corrective-actions/${id}/complete`, data),
  verify: (id: number, data?: any) => client.post(`/api/corrective-actions/${id}/verify`, data || {}),
};

export const notificationApi = {
  list: (params?: any) => client.get('/api/notifications', { params }),
  markRead: (id: number) => client.put(`/api/notifications/${id}/read`),
};
