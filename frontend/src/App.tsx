import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ConfigProvider, theme } from 'antd';
import koKR from 'antd/locale/ko_KR';
import AppLayout from './components/Layout/AppLayout';
import RoleGuard from './components/RoleGuard';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import ItemList from './pages/isms/ItemList';
import ItemDetail from './pages/isms/ItemDetail';
import EvidenceList from './pages/evidence/EvidenceList';
import AssessmentList from './pages/assessments/AssessmentList';
import ConsentList from './pages/pipa/ConsentList';
import DSRList from './pages/pipa/DSRList';
import DestructionList from './pages/pipa/DestructionList';
import ThirdPartyList from './pages/pipa/ThirdPartyList';
import IncidentList from './pages/pipa/IncidentList';
import CorrectiveActionList from './pages/pipa/CorrectiveActionList';
import ReportList from './pages/reports/ReportList';
import ScanList from './pages/prowler/ScanList';
import ScanDetail from './pages/prowler/ScanDetail';
import ConfigDashboard from './pages/config/ConfigDashboard';
import CloudAccountList from './pages/settings/CloudAccountList';
import DevTools from './pages/settings/DevTools';
import UserList from './pages/settings/UserList';
import AuditLogList from './pages/settings/AuditLogList';
import { useInitAuth } from './hooks/useAuth';
import { useAuthStore } from './store/authStore';

function Placeholder({ title }: { title: string }) {
  return <div style={{ padding: 24, color: '#999' }}>{title} — 추후 구현</div>;
}

// Detect code-server proxy basename from URL
const proxyMatch = window.location.pathname.match(/^\/proxy\/\d+/);
const basename = proxyMatch ? proxyMatch[0] : '';

function AppRoutes() {
  useInitAuth();
  const user = useAuthStore((s) => s.user);

  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to="/" replace /> : <Login />} />
      <Route
        element={
          <RoleGuard>
            <AppLayout />
          </RoleGuard>
        }
      >
        <Route path="/" element={<Dashboard />} />
        <Route path="/isms/items" element={<ItemList />} />
        <Route path="/isms/items/:code" element={<ItemDetail />} />
        <Route path="/evidence" element={<EvidenceList />} />
        <Route path="/assessments" element={<AssessmentList />} />
        <Route path="/pipa/consent" element={<ConsentList />} />
        <Route path="/pipa/dsr" element={<DSRList />} />
        <Route path="/pipa/destruction" element={<DestructionList />} />
        <Route path="/pipa/third-party" element={<ThirdPartyList />} />
        <Route path="/pipa/incidents" element={<IncidentList />} />
        <Route path="/corrective-actions" element={<CorrectiveActionList />} />
        <Route path="/reports" element={<ReportList />} />
        <Route path="/prowler" element={<ScanList />} />
        <Route path="/prowler/:id" element={<ScanDetail />} />
        <Route path="/config" element={<ConfigDashboard />} />
        <Route path="/settings/users" element={<UserList />} />
        <Route path="/settings/cloud-accounts" element={<CloudAccountList />} />
        <Route path="/settings/audit-log" element={<AuditLogList />} />
        <Route path="/settings/dev-tools" element={<DevTools />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <ConfigProvider
      locale={koKR}
      theme={{
        algorithm: theme.darkAlgorithm,
        token: {
          colorPrimary: '#3b82f6',
          colorBgContainer: '#1a2235',
          colorBgElevated: '#111827',
          colorBgLayout: '#0a0e17',
          colorBorder: '#1e2d45',
          colorText: '#e2e8f0',
          colorTextSecondary: '#94a3b8',
          borderRadius: 8,
          fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
        },
      }}
    >
      <BrowserRouter basename={basename}>
        <AppRoutes />
      </BrowserRouter>
    </ConfigProvider>
  );
}
