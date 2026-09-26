import client from './client';

export type AssessmentStatus = 'draft' | 'active' | 'closed';

export type AuditType = 'initial' | 'surveillance' | 'renewal';
export type ScopeMode = 'all_items' | 'subset';

export interface Assessment {
  id: number;
  code: string;
  name: string;
  framework: string;
  audit_type: AuditType;
  scope_mode: ScopeMode;
  parent_assessment_id: number | null;
  period_start: string;
  period_end: string;
  scope_note: string | null;
  status: AssessmentStatus;
  created_by: number | null;
  created_at: string | null;
  closed_at: string | null;
  snapshot_count: number;
  report_count: number;
  scope_total: number;
  assessed_count: number;
}

export interface AssessmentScopeRow {
  item_id: number;
  code: string;
  name: string;
  is_sample: boolean;
  assessed: boolean;
}

export const assessmentsApi = {
  list: () => client.get<Assessment[]>('/api/assessments'),
  get: (id: number) => client.get<Assessment>(`/api/assessments/${id}`),
  scope: (id: number) => client.get<AssessmentScopeRow[]>(`/api/assessments/${id}/scope`),
  create: (data: {
    code: string;
    name: string;
    framework?: string;
    audit_type?: 'initial' | 'surveillance' | 'renewal';
    scope_mode?: 'all_items' | 'subset';
    parent_assessment_id?: number | null;
    period_start: string;
    period_end: string;
    scope_note?: string;
    scope_item_codes?: string[];
  }) => client.post<Assessment>('/api/assessments', data),
  update: (
    id: number,
    data: {
      name?: string;
      period_start?: string;
      period_end?: string;
      scope_note?: string;
    },
  ) => client.put<Assessment>(`/api/assessments/${id}`, data),
  updateScope: (id: number, data: { add_item_codes?: string[]; remove_item_codes?: string[] }) =>
    client.post(`/api/assessments/${id}/scope`, data),
  transition: (id: number, status: 'active' | 'closed') =>
    client.post<Assessment>(`/api/assessments/${id}/transition`, { status }),
  delete: (id: number) => client.delete(`/api/assessments/${id}`),
};
