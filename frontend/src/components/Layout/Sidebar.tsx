import { useNavigate, useLocation } from 'react-router-dom';
import { Layout, Menu } from 'antd';
import {
  DashboardOutlined,
  SafetyCertificateOutlined,
  FileProtectOutlined,
  BugOutlined,
  ToolOutlined,
  SettingOutlined,
  CloudServerOutlined,
  ExperimentOutlined,
} from '@ant-design/icons';
import { usePermission } from '../../hooks/usePermission';

const { Sider } = Layout;

export default function Sidebar() {
  const navigate = useNavigate();
  const location = useLocation();
  const { hasRole } = usePermission();

  const showFull = hasRole('cpo', 'security_officer', 'auditor');

  const menuItems = [
    { key: '/', icon: <DashboardOutlined />, label: '대시보드' },
    ...(showFull
      ? [
          {
            key: 'isms',
            icon: <SafetyCertificateOutlined />,
            label: 'ISMS-P',
            children: [
              { key: '/isms/items', label: '인증 항목' },
              { key: '/evidence', label: '증적 관리' },
              { key: '/assessments', label: '평가 세션' },
              { key: '/corrective-actions', label: '시정조치' },
              { key: '/reports', label: '보고서' },
            ],
          },
        ]
      : []),
    {
      key: 'pipa',
      icon: <FileProtectOutlined />,
      label: '개인정보',
      children: [
        { key: '/pipa/consent', label: '동의 관리' },
        { key: '/pipa/dsr', label: '정보주체 요청' },
        { key: '/pipa/destruction', label: '파기 관리' },
        { key: '/pipa/third-party', label: '위탁 관리' },
        { key: '/pipa/incidents', label: '사고 대응' },
      ],
    },
    ...(showFull
      ? [
          { key: '/settings/cloud-accounts', icon: <CloudServerOutlined />, label: '클라우드 계정' },
          {
            key: 'scan',
            icon: <BugOutlined />,
            label: '자동 진단',
            children: [
              { key: '/prowler', label: 'Prowler 스캔' },
              { key: '/config', label: 'AWS Config' },
            ],
          },
        ]
      : []),
    ...(hasRole('cpo')
      ? [
          {
            key: 'settings',
            icon: <SettingOutlined />,
            label: '설정',
            children: [
              { key: '/settings/users', label: '사용자 관리' },
              { key: '/settings/audit-log', label: '감사 로그' },
              { key: '/settings/dev-tools', label: '초기화 (개발환경)', icon: <ExperimentOutlined /> },
            ],
          },
        ]
      : []),
  ];

  return (
    <Sider width={220}>
      <div className="kc-sidebar-logo">K-Compliance</div>
      <Menu
        mode="inline"
        selectedKeys={[location.pathname]}
        defaultOpenKeys={['isms', 'pipa', 'scan']}
        items={menuItems}
        onClick={({ key }) => navigate(key)}
        style={{ borderRight: 0 }}
      />
    </Sider>
  );
}
