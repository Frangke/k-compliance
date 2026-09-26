import { useState, useCallback } from 'react';
import { Outlet, useNavigate } from 'react-router-dom';
import { Layout, Modal } from 'antd';
import Sidebar from './Sidebar';
import Header from './Header';
import { useIdleTimeout } from '../../hooks/useAuth';
import { useAuthStore } from '../../store/authStore';
import { authApi } from '../../api/auth';

const { Content } = Layout;

export default function AppLayout() {
  const [warnVisible, setWarnVisible] = useState(false);
  const navigate = useNavigate();
  const logout = useAuthStore((s) => s.logout);
  const touchActivity = useAuthStore((s) => s.touchActivity);

  const handleWarn = useCallback(() => {
    setWarnVisible(true);
  }, []);

  const handleExpire = useCallback(async () => {
    setWarnVisible(false);
    try {
      await authApi.logout();
    } catch {
      /* ignore */
    }
    logout();
    navigate('/login');
  }, [logout, navigate]);

  useIdleTimeout(handleWarn, handleExpire);

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sidebar />
      <Layout>
        <Header />
        <Content className="kc-content">
          <Outlet />
        </Content>
      </Layout>

      <Modal
        title="세션 만료 임박"
        open={warnVisible}
        okText="연장"
        cancelText="로그아웃"
        onOk={() => {
          touchActivity();
          setWarnVisible(false);
        }}
        onCancel={handleExpire}
        closable={false}
      >
        <p>5분 내에 세션이 만료됩니다. 계속 사용하시겠습니까?</p>
      </Modal>
    </Layout>
  );
}
