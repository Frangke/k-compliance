import client from './client';

export interface CloudAccountPayload {
  provider?: 'aws';
  account_id?: string;
  alias?: string;
  purpose?: string | null;
  admin_name?: string | null;
  admin_email?: string | null;
  auth_type?: 'instance_role' | 'assume_role';
  role_arn?: string | null;
  external_id?: string | null;
  default_region?: string;
  is_active?: boolean;
}

export const prowlerApi = {
  listAccounts: () => client.get('/api/prowler/cloud-accounts'),
  createAccount: (data: CloudAccountPayload) => client.post('/api/prowler/cloud-accounts', data),
  updateAccount: (id: number, data: CloudAccountPayload) => client.put(`/api/prowler/cloud-accounts/${id}`, data),
  deleteAccount: (id: number) => client.delete(`/api/prowler/cloud-accounts/${id}`),
  verifyAccount: (id: number) => client.post(`/api/prowler/cloud-accounts/${id}/verify`),
  listScans: (params?: any) => client.get('/api/prowler/scans', { params }),
  createScan: (cloudAccountId?: number) =>
    client.post('/api/prowler/scans', null, { params: cloudAccountId ? { cloud_account_id: cloudAccountId } : {} }),
  getScan: (id: number) => client.get(`/api/prowler/scans/${id}`),
  getFindings: (scanId: number, params?: any) => client.get(`/api/prowler/scans/${scanId}/findings`, { params }),
  cancelScan: (id: number) => client.post(`/api/prowler/scans/${id}/cancel`),
  remediateFinding: (id: number, status: string, notes?: string) =>
    client.put(`/api/prowler/findings/${id}/remediate`, null, { params: { remediation_status: status, notes } }),
};

export const configApi = {
  listSyncJobs: () => client.get('/api/config/sync-jobs'),
  sync: (cloudAccountId?: number) =>
    client.post('/api/config/sync', null, {
      params: cloudAccountId ? { cloud_account_id: cloudAccountId } : {},
    }),
  getSyncJob: (id: number) => client.get(`/api/config/sync-jobs/${id}`),
  listEvaluations: (params?: any) => client.get('/api/config/evaluations', { params }),
  remediateEvaluation: (id: number, status: string, notes?: string) =>
    client.put(`/api/config/evaluations/${id}/remediate`, null, { params: { remediation_status: status, notes } }),
  summary: () => client.get('/api/config/summary'),
};
