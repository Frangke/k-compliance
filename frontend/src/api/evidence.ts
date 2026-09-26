import client from './client';

export const evidenceApi = {
  list: (params?: {
    status?: string;
    evidence_type?: string;
    item_code?: string;
    item_code_prefix?: string;
    search?: string;
    valid_to_from?: string;
    valid_to_to?: string;
    created_from?: string;
    created_to?: string;
    page?: number;
    size?: number;
  }) => client.get('/api/evidence', { params }),

  get: (id: number) => client.get(`/api/evidence/${id}`),

  upload: (formData: FormData) =>
    client.post('/api/evidence/upload', formData, { headers: { 'Content-Type': 'multipart/form-data' } }),

  createExternalLink: (data: {
    title: string;
    external_url: string;
    description?: string;
    valid_from?: string;
    valid_to?: string;
  }) => client.post('/api/evidence/external-link', data),

  update: (id: number, data: any) => client.put(`/api/evidence/${id}`, data),

  submit: (id: number) => client.post(`/api/evidence/${id}/submit`),

  review: (id: number, data: { action: string; comment?: string }) => client.post(`/api/evidence/${id}/review`, data),

  linkItems: (id: number, data: { item_codes: string[]; relevance_note?: string }) =>
    client.post(`/api/evidence/${id}/link-items`, data),

  download: (id: number) => client.get(`/api/evidence/${id}/download`),

  /** Trigger file download via blob (works with proxy + auth cookies) */
  downloadFile: async (id: number) => {
    const meta = await client.get(`/api/evidence/${id}/download`);
    const url = meta.data.download_url;
    const fileName = meta.data.file_name || 'download';

    if (url.startsWith('/api/')) {
      // Local file: fetch via axios with credentials, then trigger download
      const res = await client.get(url, { responseType: 'blob' });
      const blobUrl = window.URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = blobUrl;
      a.download = fileName;
      a.click();
      window.URL.revokeObjectURL(blobUrl);
    } else {
      // S3 presigned URL: direct open
      window.open(url, '_blank');
    }
  },

  newVersion: (id: number, formData: FormData) =>
    client.post(`/api/evidence/${id}/new-version`, formData, { headers: { 'Content-Type': 'multipart/form-data' } }),

  versions: (id: number) => client.get(`/api/evidence/${id}/versions`),

  exportPackage: (statusFilter?: string) =>
    client.post('/api/evidence/export', null, { params: { status_filter: statusFilter || 'approved' } }),

  getExportJob: (jobId: number) => client.get(`/api/evidence/export/${jobId}`),
};
