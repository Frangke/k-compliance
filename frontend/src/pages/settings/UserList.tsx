import { useEffect, useState } from 'react';
import {
  Typography,
  Card,
  Table,
  Tag,
  Button,
  Space,
  Modal,
  Form,
  Input,
  Select,
  message,
  Popconfirm,
  Tooltip,
  Switch,
  Alert,
} from 'antd';
import { UserAddOutlined, EditOutlined, KeyOutlined, StopOutlined } from '@ant-design/icons';
import {
  usersApi,
  type UserRecord,
  type UserRole,
  type UserCreatePayload,
  type UserUpdatePayload,
} from '../../api/users';

const ROLE_LABELS: Record<UserRole, string> = {
  cpo: 'CPO',
  security_officer: '보안담당자',
  privacy_handler: '개인정보취급자',
  auditor: '감사자',
};

const ROLE_COLORS: Record<UserRole, string> = {
  cpo: 'purple',
  security_officer: 'blue',
  privacy_handler: 'cyan',
  auditor: 'default',
};

export default function UserList() {
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [editUser, setEditUser] = useState<UserRecord | null>(null);
  const [resetUser, setResetUser] = useState<UserRecord | null>(null);
  const [createForm] = Form.useForm<UserCreatePayload>();
  const [editForm] = Form.useForm<UserUpdatePayload>();
  const [resetForm] = Form.useForm<{ new_password: string }>();

  const load = async () => {
    setLoading(true);
    try {
      const res = await usersApi.list({ size: 100 });
      setUsers(res.data.items);
    } catch {
      message.error('사용자 목록을 불러올 수 없습니다');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleCreate = async () => {
    try {
      const values = await createForm.validateFields();
      await usersApi.create(values);
      message.success('사용자가 생성되었습니다');
      setCreateOpen(false);
      createForm.resetFields();
      load();
    } catch (err: any) {
      if (err?.errorFields) return;
      message.error(err.response?.data?.detail || '사용자 생성에 실패했습니다');
    }
  };

  const handleEdit = async () => {
    if (!editUser) return;
    try {
      const values = await editForm.validateFields();
      await usersApi.update(editUser.id, values);
      message.success('사용자 정보가 수정되었습니다');
      setEditUser(null);
      load();
    } catch (err: any) {
      if (err?.errorFields) return;
      message.error(err.response?.data?.detail || '수정에 실패했습니다');
    }
  };

  const handleResetPassword = async () => {
    if (!resetUser) return;
    try {
      const values = await resetForm.validateFields();
      await usersApi.resetPassword(resetUser.id, values.new_password);
      message.success(`${resetUser.username}의 비밀번호가 초기화되었습니다`);
      setResetUser(null);
      resetForm.resetFields();
    } catch (err: any) {
      if (err?.errorFields) return;
      message.error(err.response?.data?.detail || '비밀번호 초기화에 실패했습니다');
    }
  };

  const handleDeactivate = async (u: UserRecord) => {
    try {
      await usersApi.deactivate(u.id);
      message.success(`${u.username} 계정이 비활성화되었습니다`);
      load();
    } catch (err: any) {
      message.error(err.response?.data?.detail || '비활성화에 실패했습니다');
    }
  };

  const handleToggleActive = async (u: UserRecord, newValue: boolean) => {
    if (u.role === 'cpo' && !newValue) {
      const activeCpos = users.filter((x) => x.role === 'cpo' && x.is_active).length;
      if (activeCpos <= 1) {
        message.error('마지막 CPO 계정은 비활성화할 수 없습니다');
        return;
      }
    }
    try {
      await usersApi.update(u.id, { is_active: newValue });
      message.success(newValue ? '활성화되었습니다' : '비활성화되었습니다');
      load();
    } catch (err: any) {
      message.error(err.response?.data?.detail || '상태 변경 실패');
    }
  };

  const openEdit = (u: UserRecord) => {
    setEditUser(u);
    editForm.setFieldsValue({
      name: u.name,
      email: u.email,
      role: u.role,
      department: u.department ?? undefined,
      is_active: u.is_active,
    });
  };

  const columns = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    { title: '아이디', dataIndex: 'username', width: 140 },
    { title: '이름', dataIndex: 'name', width: 120 },
    { title: '이메일', dataIndex: 'email', width: 220 },
    {
      title: '역할',
      dataIndex: 'role',
      width: 140,
      render: (r: UserRole) => <Tag color={ROLE_COLORS[r]}>{ROLE_LABELS[r]}</Tag>,
      filters: (Object.entries(ROLE_LABELS) as [UserRole, string][]).map(([v, t]) => ({
        text: t,
        value: v,
      })),
      onFilter: (v: any, record: UserRecord) => record.role === v,
    },
    { title: '부서', dataIndex: 'department', width: 120, render: (v: string) => v || '-' },
    {
      title: '활성',
      dataIndex: 'is_active',
      width: 90,
      render: (v: boolean, record: UserRecord) => (
        <Switch checked={v} size="small" onChange={(newValue) => handleToggleActive(record, newValue)} />
      ),
    },
    {
      title: '최종 로그인',
      dataIndex: 'last_login_at',
      width: 160,
      render: (v: string | null) => (v ? new Date(v).toLocaleString('ko-KR') : '-'),
    },
    {
      title: '비번 변경',
      dataIndex: 'password_changed_at',
      width: 110,
      render: (v: string | null) => (v ? new Date(v).toLocaleDateString('ko-KR') : '-'),
    },
    {
      title: '작업',
      width: 150,
      render: (_: any, record: UserRecord) => (
        <Space size={4}>
          <Tooltip title="수정">
            <Button type="text" icon={<EditOutlined />} onClick={() => openEdit(record)} />
          </Tooltip>
          <Tooltip title="비밀번호 초기화">
            <Button type="text" icon={<KeyOutlined />} onClick={() => setResetUser(record)} />
          </Tooltip>
          <Popconfirm
            title="이 계정을 비활성화하시겠습니까?"
            onConfirm={() => handleDeactivate(record)}
            okText="비활성화"
            cancelText="취소"
            disabled={!record.is_active}
          >
            <Tooltip title="비활성화">
              <Button type="text" danger icon={<StopOutlined />} disabled={!record.is_active} />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Typography.Title level={4} style={{ margin: 0, marginBottom: 16 }}>
        사용자 관리
      </Typography.Title>

      <Alert
        style={{ marginBottom: 16 }}
        type="info"
        showIcon
        message="CPO 역할만 사용자를 생성·수정·비밀번호 초기화할 수 있습니다. 마지막 CPO 계정은 비활성화할 수 없습니다."
      />

      <Card
        size="small"
        style={{ marginBottom: 12 }}
        title={`사용자 목록 (${users.length}명)`}
        extra={
          <Button type="primary" icon={<UserAddOutlined />} onClick={() => setCreateOpen(true)}>
            사용자 생성
          </Button>
        }
      >
        <Table
          dataSource={users}
          columns={columns}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 20 }}
          size="middle"
        />
      </Card>

      {/* Create modal */}
      <Modal
        title="사용자 생성"
        open={createOpen}
        onCancel={() => {
          setCreateOpen(false);
          createForm.resetFields();
        }}
        onOk={handleCreate}
        okText="생성"
        cancelText="취소"
      >
        <Form form={createForm} layout="vertical" requiredMark="optional">
          <Form.Item name="username" label="아이디" rules={[{ required: true, min: 3, max: 50 }]}>
            <Input autoComplete="off" />
          </Form.Item>
          <Form.Item
            name="password"
            label="임시 비밀번호"
            rules={[{ required: true, min: 8 }]}
            extra="영문 대/소문자, 숫자, 특수문자 중 3종 이상 조합 · 최소 8자 (ISMS-P 2.5.4)"
          >
            <Input.Password autoComplete="new-password" />
          </Form.Item>
          <Form.Item name="name" label="이름" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="email" label="이메일" rules={[{ required: true, type: 'email' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="role" label="역할" rules={[{ required: true }]}>
            <Select
              options={(Object.entries(ROLE_LABELS) as [UserRole, string][]).map(([v, t]) => ({
                value: v,
                label: t,
              }))}
            />
          </Form.Item>
          <Form.Item name="department" label="부서">
            <Input />
          </Form.Item>
        </Form>
      </Modal>

      {/* Edit modal */}
      <Modal
        title={editUser ? `사용자 수정 — ${editUser.username}` : ''}
        open={!!editUser}
        onCancel={() => setEditUser(null)}
        onOk={handleEdit}
        okText="저장"
        cancelText="취소"
      >
        <Form form={editForm} layout="vertical">
          <Form.Item name="name" label="이름" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="email" label="이메일" rules={[{ required: true, type: 'email' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="role" label="역할" rules={[{ required: true }]}>
            <Select
              options={(Object.entries(ROLE_LABELS) as [UserRole, string][]).map(([v, t]) => ({
                value: v,
                label: t,
              }))}
            />
          </Form.Item>
          <Form.Item name="department" label="부서">
            <Input />
          </Form.Item>
          <Form.Item name="is_active" label="활성" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      {/* Reset password modal */}
      <Modal
        title={resetUser ? `비밀번호 초기화 — ${resetUser.username}` : ''}
        open={!!resetUser}
        onCancel={() => {
          setResetUser(null);
          resetForm.resetFields();
        }}
        onOk={handleResetPassword}
        okText="초기화"
        cancelText="취소"
        okButtonProps={{ danger: true }}
      >
        <Alert
          type="warning"
          message="비밀번호를 사용자에게 안전한 채널로 전달하고, 첫 로그인 후 즉시 변경하도록 안내하세요."
          style={{ marginBottom: 16 }}
        />
        <Form form={resetForm} layout="vertical">
          <Form.Item
            name="new_password"
            label="새 임시 비밀번호"
            rules={[{ required: true, min: 8 }]}
            extra="영문 대/소문자, 숫자, 특수문자 중 3종 이상 조합 · 최소 8자"
          >
            <Input.Password autoComplete="new-password" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
