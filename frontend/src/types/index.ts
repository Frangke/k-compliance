export interface User {
  id: number;
  username: string;
  name: string;
  email: string;
  role: 'cpo' | 'security_officer' | 'privacy_handler' | 'auditor';
  department: string | null;
  is_active: boolean;
  last_login_at: string | null;
  password_changed_at: string | null;
  created_at: string;
}

export type Role = User['role'];

export const ROLE_LABELS: Record<Role, string> = {
  cpo: 'CPO',
  security_officer: '보안담당자',
  privacy_handler: '개인정보취급자',
  auditor: '감사자',
};
