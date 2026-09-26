import { useEffect, useState } from 'react';
import {
  Table,
  Button,
  Typography,
  Tag,
  Modal,
  Form,
  Input,
  Select,
  Space,
  message,
  Popconfirm,
  Alert,
  Tooltip,
} from 'antd';
import {
  PlusOutlined,
  CloudServerOutlined,
  EditOutlined,
  DeleteOutlined,
  CheckCircleOutlined,
  KeyOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { prowlerApi, type CloudAccountPayload } from '../../api/prowler';
import { usePermission } from '../../hooks/usePermission';

const { Title, Text, Paragraph } = Typography;

type AuthType = 'instance_role' | 'assume_role';

interface CloudAccount {
  id: number;
  provider: string;
  account_id: string;
  alias: string;
  purpose: string | null;
  admin_name: string | null;
  admin_email: string | null;
  is_active: boolean;
  auth_type: AuthType;
  role_arn: string | null;
  external_id: string | null;
  default_region: string | null;
  credentials_last_updated: string | null;
}

export default function CloudAccountList() {
  const [accounts, setAccounts] = useState<CloudAccount[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<CloudAccount | null>(null);
  const [verifying, setVerifying] = useState<number | null>(null);
  const [form] = Form.useForm();
  const { hasRole } = usePermission();

  const authType = Form.useWatch('auth_type', form) as AuthType | undefined;

  const fetch = async () => {
    setLoading(true);
    try {
      setAccounts((await prowlerApi.listAccounts()).data || []);
    } catch {
      message.error('계정 목록을 불러오는데 실패했습니다');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetch();
  }, []);

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({
      provider: 'aws',
      auth_type: 'instance_role',
      default_region: 'ap-northeast-2',
    });
    setModalOpen(true);
  };

  const openEdit = (acc: CloudAccount) => {
    setEditing(acc);
    form.setFieldsValue({
      provider: acc.provider,
      account_id: acc.account_id,
      alias: acc.alias,
      purpose: acc.purpose,
      admin_name: acc.admin_name,
      admin_email: acc.admin_email,
      auth_type: acc.auth_type,
      role_arn: acc.role_arn,
      external_id: acc.external_id,
      default_region: acc.default_region || 'ap-northeast-2',
      is_active: acc.is_active,
    });
    setModalOpen(true);
  };

  const handleSubmit = async (values: CloudAccountPayload) => {
    try {
      if (editing) {
        await prowlerApi.updateAccount(editing.id, values);
        message.success('계정이 수정되었습니다');
      } else {
        await prowlerApi.createAccount(values);
        message.success('계정이 등록되었습니다');
      }
      setModalOpen(false);
      form.resetFields();
      fetch();
    } catch (err: any) {
      message.error(err.response?.data?.detail || '처리 실패');
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await prowlerApi.deleteAccount(id);
      message.success('삭제되었습니다');
      fetch();
    } catch (err: any) {
      message.error(err.response?.data?.detail || '삭제 실패');
    }
  };

  const handleVerify = async (id: number) => {
    setVerifying(id);
    try {
      const res = await prowlerApi.verifyAccount(id);
      const { ok, message: msg, caller_arn, account_id } = res.data;
      if (ok) {
        Modal.success({
          title: '자격증명 검증 성공',
          content: (
            <div>
              <Paragraph>{msg}</Paragraph>
              <Paragraph copyable={{ text: caller_arn }}>
                <Text code>{caller_arn}</Text>
              </Paragraph>
              <Text type="secondary">계정 ID: {account_id}</Text>
            </div>
          ),
        });
      } else {
        Modal.error({
          title: '자격증명 검증 실패',
          content: (
            <div>
              <Paragraph>{msg}</Paragraph>
              {caller_arn && (
                <Paragraph>
                  <Text code>{caller_arn}</Text>
                </Paragraph>
              )}
            </div>
          ),
        });
      }
    } catch (err: any) {
      message.error(err.response?.data?.detail || '검증 실패');
    } finally {
      setVerifying(null);
    }
  };

  const columns: ColumnsType<CloudAccount> = [
    { title: 'ID', dataIndex: 'id', width: 50 },
    { title: '제공자', dataIndex: 'provider', width: 70, render: (v: string) => v.toUpperCase() },
    { title: '계정 ID', dataIndex: 'account_id', width: 130 },
    { title: '별칭', dataIndex: 'alias', width: 120 },
    {
      title: '인증 방식',
      dataIndex: 'auth_type',
      width: 150,
      render: (v: AuthType, r: CloudAccount) => {
        if (v === 'instance_role') {
          return (
            <Tag color="blue" icon={<SafetyCertificateOutlined />}>
              인스턴스 프로파일
            </Tag>
          );
        }
        return (
          <Space direction="vertical" size={0}>
            <Tag color="purple" icon={<KeyOutlined />}>
              AssumeRole
            </Tag>
            {r.role_arn && (
              <Text type="secondary" style={{ fontSize: 11 }} ellipsis>
                {r.role_arn.split(':role/').pop()}
              </Text>
            )}
          </Space>
        );
      },
    },
    { title: '리전', dataIndex: 'default_region', width: 110 },
    { title: '용도', dataIndex: 'purpose', ellipsis: true },
    {
      title: '상태',
      dataIndex: 'is_active',
      width: 70,
      render: (v: boolean) => <Tag color={v ? 'success' : 'default'}>{v ? '활성' : '비활성'}</Tag>,
    },
    {
      title: '',
      width: 160,
      render: (_: any, r: CloudAccount) => (
        <Space size={4}>
          <Tooltip title="자격증명 검증 (STS GetCallerIdentity)">
            <Button
              size="small"
              type="text"
              icon={<CheckCircleOutlined />}
              loading={verifying === r.id}
              onClick={() => handleVerify(r.id)}
            />
          </Tooltip>
          <Tooltip title="수정">
            <Button size="small" type="text" icon={<EditOutlined />} onClick={() => openEdit(r)} />
          </Tooltip>
          {hasRole('cpo') && (
            <Popconfirm title="이 계정을 삭제하시겠습니까?" onConfirm={() => handleDelete(r.id)}>
              <Tooltip title="삭제 (CPO 전용)">
                <Button size="small" type="text" danger icon={<DeleteOutlined />} />
              </Tooltip>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>
          <CloudServerOutlined style={{ marginRight: 8 }} />
          클라우드 계정 관리
        </Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          계정 등록
        </Button>
      </div>

      <Alert
        type="info"
        showIcon
        message="IAM 기반 인증만 지원합니다 (장기 Access Key 미사용)"
        description={
          <div>
            <div>
              • <strong>인스턴스 프로파일</strong>: 이 서버(EC2)의 IAM Role을 그대로 사용 (동일 계정 스캔)
            </div>
            <div>
              • <strong>AssumeRole</strong>: 서버 IAM Role이 대상 계정의 Role로 AssumeRole (크로스 어카운트 스캔)
            </div>
            <div style={{ marginTop: 6, color: '#94a3b8', fontSize: 12 }}>
              대상 계정 Role의 Trust Policy에 이 서버의 IAM Role ARN을 신뢰 주체로 등록해야 합니다. 운영에서는{' '}
              <Text code>ExternalId</Text> 사용을 권장합니다.
            </div>
          </div>
        }
        style={{ marginBottom: 16 }}
      />

      <Table columns={columns} dataSource={accounts} rowKey="id" loading={loading} size="middle" pagination={false} />

      <Modal
        title={editing ? `계정 수정 — ${editing.alias}` : '클라우드 계정 등록'}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        footer={null}
        destroyOnClose
        width={560}
      >
        <Form form={form} layout="vertical" onFinish={handleSubmit}>
          <Form.Item name="provider" label="클라우드 제공자" initialValue="aws">
            <Select disabled={!!editing} options={[{ value: 'aws', label: 'AWS' }]} />
          </Form.Item>

          <Form.Item
            name="account_id"
            label="AWS 계정 번호"
            rules={[
              { required: true, message: '계정 번호를 입력하세요' },
              { pattern: /^\d{12}$/, message: '12자리 숫자여야 합니다' },
            ]}
            help="12자리 AWS 계정 번호"
          >
            <Input placeholder="123456789012" maxLength={12} disabled={!!editing} />
          </Form.Item>

          <Form.Item name="alias" label="별칭" rules={[{ required: true }]}>
            <Input placeholder="Production" />
          </Form.Item>

          <Form.Item name="auth_type" label="인증 방식" initialValue="instance_role" rules={[{ required: true }]}>
            <Select
              options={[
                {
                  value: 'instance_role',
                  label: '인스턴스 프로파일 (이 EC2의 IAM Role)',
                },
                {
                  value: 'assume_role',
                  label: 'AssumeRole (다른 AWS 계정으로 위임)',
                },
              ]}
            />
          </Form.Item>

          {authType === 'assume_role' && (
            <>
              <Form.Item
                name="role_arn"
                label="대상 Role ARN"
                rules={[
                  { required: true, message: 'Role ARN을 입력하세요' },
                  {
                    pattern: /^arn:aws:iam::\d{12}:role\/.+$/,
                    message: 'arn:aws:iam::<account>:role/<name> 형식이어야 합니다',
                  },
                ]}
                extra="대상 Role의 Trust Policy에 이 서버의 IAM Role ARN을 주체로 등록해야 합니다."
              >
                <Input placeholder="arn:aws:iam::123456789012:role/SecurityAuditRole" />
              </Form.Item>

              <Form.Item
                name="external_id"
                label="ExternalId (권장)"
                extra="Confused Deputy 방지. 대상 Role의 Trust Policy에서 동일한 값을 요구하도록 설정하세요."
              >
                <Input placeholder="선택 사항" autoComplete="off" />
              </Form.Item>
            </>
          )}

          <Form.Item name="default_region" label="기본 리전" initialValue="ap-northeast-2" rules={[{ required: true }]}>
            <Select
              options={[
                { value: 'ap-northeast-2', label: 'ap-northeast-2 (서울)' },
                { value: 'ap-northeast-1', label: 'ap-northeast-1 (도쿄)' },
                { value: 'us-east-1', label: 'us-east-1 (버지니아 북부)' },
                { value: 'us-west-2', label: 'us-west-2 (오레곤)' },
                { value: 'eu-west-1', label: 'eu-west-1 (아일랜드)' },
              ]}
            />
          </Form.Item>

          <Form.Item name="purpose" label="용도">
            <Input placeholder="예: 운영 환경, 개발/스테이징" />
          </Form.Item>

          <Form.Item name="admin_name" label="관리자명">
            <Input placeholder="홍길동" />
          </Form.Item>

          <Form.Item name="admin_email" label="관리자 이메일">
            <Input placeholder="admin@company.com" />
          </Form.Item>

          {editing && (
            <Form.Item name="is_active" label="상태">
              <Select
                options={[
                  { value: true, label: '활성' },
                  { value: false, label: '비활성' },
                ]}
              />
            </Form.Item>
          )}

          <Form.Item style={{ marginBottom: 0 }}>
            <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
              <Button onClick={() => setModalOpen(false)}>취소</Button>
              <Button type="primary" htmlType="submit">
                {editing ? '수정' : '등록'}
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
