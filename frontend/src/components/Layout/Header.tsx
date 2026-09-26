import { Layout, Dropdown, Badge, Button, Space, Avatar } from 'antd';
import { BellOutlined, UserOutlined, LogoutOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../../store/authStore';
import { authApi } from '../../api/auth';
import { ROLE_LABELS } from '../../types';
import CurrentAssessmentSwitcher from './CurrentAssessmentSwitcher';

const { Header: AntHeader } = Layout;

export default function Header() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const navigate = useNavigate();

  const handleLogout = async () => {
    try {
      await authApi.logout();
    } catch {
      /* ignore */
    }
    logout();
    navigate('/login');
  };

  const userMenuItems = [
    { key: 'profile', icon: <UserOutlined />, label: `${user?.name} (${user ? ROLE_LABELS[user.role] : ''})` },
    { type: 'divider' as const },
    { key: 'logout', icon: <LogoutOutlined />, label: '로그아웃', danger: true },
  ];

  return (
    <AntHeader style={{ padding: '0 24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <CurrentAssessmentSwitcher />
      <Space size={16}>
        <Badge count={0} size="small">
          <Button type="text" icon={<BellOutlined />} />
        </Badge>
        <Dropdown
          menu={{
            items: userMenuItems,
            onClick: ({ key }) => {
              if (key === 'logout') handleLogout();
            },
          }}
        >
          <Space style={{ cursor: 'pointer' }}>
            <Avatar size="small" icon={<UserOutlined />} />
            <span>{user?.name}</span>
          </Space>
        </Dropdown>
      </Space>
    </AntHeader>
  );
}
