import client from './client';

export type ReportType =
  | 'isms_assessment'
  | 'corrective_action'
  | 'evidence_package'
  | 'dashboard_snapshot'
  | 'evidence_summary';

export const reportsApi = {
  list: () => client.get('/api/reports'),

  generateIsms: (periodStart: string, periodEnd: string) =>
    client.post('/api/reports/isms-assessment', null, {
      params: { period_start: periodStart, period_end: periodEnd },
    }),

  generateCorrective: (periodStart: string, periodEnd: string) =>
    client.post('/api/reports/corrective-action', null, {
      params: { period_start: periodStart, period_end: periodEnd },
    }),

  generateEvidencePackage: (
    periodStart: string,
    periodEnd: string,
    domain?: string,
    statusFilter: string = 'approved',
    curation?: { include_evidence_ids?: number[]; exclude_evidence_ids?: number[] },
  ) =>
    client.post(
      '/api/reports/evidence-package',
      curation && (curation.include_evidence_ids?.length || curation.exclude_evidence_ids?.length) ? curation : null,
      {
        params: {
          period_start: periodStart,
          period_end: periodEnd,
          ...(domain ? { domain } : {}),
          status_filter: statusFilter,
        },
      },
    ),

  generateDashboardSnapshot: () => client.post('/api/reports/dashboard-snapshot'),

  /** Back-compat: legacy callers treat generate() as ISMS report. */
  generate: (periodStart: string, periodEnd: string) =>
    client.post('/api/reports/isms-assessment', null, {
      params: { period_start: periodStart, period_end: periodEnd },
    }),

  getHtmlUrl: (id: number) => {
    const base = client.defaults.baseURL || '';
    return `${base}/api/reports/${id}/html`;
  },

  getCsvUrl: (id: number) => {
    const base = client.defaults.baseURL || '';
    return `${base}/api/reports/${id}/csv`;
  },

  getDownloadUrl: (id: number) => {
    const base = client.defaults.baseURL || '';
    return `${base}/api/reports/${id}/download`;
  },

  delete: (id: number) => client.delete(`/api/reports/${id}`),
};
