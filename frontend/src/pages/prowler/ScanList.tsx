import { useEffect, useState } from 'react';
import {
  Table,
  Button,
  Typography,
  Tag,
  message,
  Modal,
  Select,
  Space,
  Empty,
  Card,
  Popconfirm,
  Descriptions,
} from 'antd';
import { useNavigate } from 'react-router-dom';
import { CloudServerOutlined, PlayCircleOutlined, StopOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { prowlerApi } from '../../api/prowler';

const { Title, Text } = Typography;

interface CloudAccount {
  id: number;
  provider: string;
  account_id: string;
  alias: string;
  is_active: boolean;
}
interface ProwlerScan {
  id: number;
  compliance: string;
  status: string;
  total_checks: number;
  passed: number;
  failed: number;
  started_at: string;
  completed_at: string | null;
  error_message: string | null;
  cloud_account_alias: string | null;
  cloud_account_id: string | null;
}

const STATUS_CFG: Record<string, { color: string; text: string }> = {
  pending: { color: 'orange', text: '대기중' },
  running: { color: 'processing', text: '실행중' },
  completed: { color: 'success', text: '완료' },
  failed: { color: 'error', text: '실패' },
  cancelled: { color: 'default', text: '취소됨' },
};

export default function ScanList() {
  const navigate = useNavigate();
  const [scans, setScans] = useState<ProwlerScan[]>([]);
  const [accounts, setAccounts] = useState<CloudAccount[]>([]);
  const [loading, setLoading] = useState(false);
  const [scanModalOpen, setScanModalOpen] = useState(false);
  const [selectedAccount, setSelectedAccount] = useState<number | undefined>();
  const [errorScan, setErrorScan] = useState<ProwlerScan | null>(null);

  const hasActiveScan = scans.some((s) => s.status === 'running');

  const fetchScans = async () => {
    setLoading(true);
    try {
      const res = await prowlerApi.listScans();
      setScans(res.data.items || []);
    } catch {
      message.error('스캔 목록을 불러오는데 실패했습니다.');
    } finally {
      setLoading(false);
    }
  };

  const fetchAccounts = async () => {
    try {
      setAccounts((await prowlerApi.listAccounts()).data || []);
    } catch {}
  };

  useEffect(() => {
    fetchScans();
    fetchAccounts();
  }, []);

  const handleNewScan = () => {
    if (accounts.length === 0) {
      message.warning('스캔 대상 클라우드 계정을 먼저 등록하세요.');
      navigate('/settings/cloud-accounts');
      return;
    }
    setSelectedAccount(undefined);
    setScanModalOpen(true);
  };

  const handleStartScan = async () => {
    if (!selectedAccount) {
      message.warning('대상 계정을 선택하세요.');
      return;
    }
    setScanModalOpen(false);
    try {
      await prowlerApi.createScan(selectedAccount);
      message.success('스캔이 시작되었습니다.');
      fetchScans();
    } catch (e: any) {
      message.error(e.response?.data?.detail || '스캔 시작 실패');
    }
  };

  const handleCancel = async (id: number) => {
    try {
      await prowlerApi.cancelScan(id);
      message.success('취소되었습니다.');
      fetchScans();
    } catch (e: any) {
      message.error(e.response?.data?.detail || '취소 실패');
    }
  };

  const columns: ColumnsType<ProwlerScan> = [
    { title: 'ID', dataIndex: 'id', width: 50 },
    {
      title: '대상 계정',
      width: 180,
      render: (_: any, r: ProwlerScan) =>
        r.cloud_account_alias ? (
          <span>
            {r.cloud_account_alias}{' '}
            <Text type="secondary" style={{ fontSize: 11 }}>
              ({r.cloud_account_id})
            </Text>
          </span>
        ) : (
          <Text type="secondary">미지정</Text>
        ),
    },
    {
      title: '상태',
      dataIndex: 'status',
      width: 90,
      render: (s: string, r: ProwlerScan) => {
        const c = STATUS_CFG[s];
        // Failed tag is clickable — opens a modal with the full error text
        // on demand. Row navigation is suppressed so the click doesn't fall
        // through to the detail page.
        if (s === 'failed' && r.error_message) {
          return (
            <Tag
              color={c?.color}
              style={{ cursor: 'pointer' }}
              onClick={(e) => {
                e.stopPropagation();
                setErrorScan(r);
              }}
              title="클릭하여 실패 원인 보기"
            >
              {c?.text || s}
            </Tag>
          );
        }
        return <Tag color={c?.color}>{c?.text || s}</Tag>;
      },
    },
    { title: '총 검사', dataIndex: 'total_checks', width: 70, align: 'right' },
    {
      title: '통과',
      dataIndex: 'passed',
      width: 60,
      align: 'right',
      render: (v: number) => <span style={{ color: '#10b981' }}>{v}</span>,
    },
    {
      title: '실패',
      dataIndex: 'failed',
      width: 60,
      align: 'right',
      render: (v: number) => <span style={{ color: '#ef4444' }}>{v}</span>,
    },
    {
      title: '시작',
      dataIndex: 'started_at',
      width: 130,
      render: (d: string) => (d ? dayjs(d).format('MM-DD HH:mm') : '-'),
    },
    {
      title: '완료',
      dataIndex: 'completed_at',
      width: 130,
      render: (d: string | null) => (d ? dayjs(d).format('MM-DD HH:mm') : '-'),
    },
    {
      title: '',
      width: 60,
      render: (_: any, r: ProwlerScan) =>
        r.status === 'pending' || r.status === 'running' ? (
          <Popconfirm
            title="스캔을 취소하시겠습니까?"
            onConfirm={(e) => {
              e?.stopPropagation();
              handleCancel(r.id);
            }}
            onCancel={(e) => e?.stopPropagation()}
          >
            <Button size="small" danger icon={<StopOutlined />} onClick={(e) => e.stopPropagation()}>
              취소
            </Button>
          </Popconfirm>
        ) : null,
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>
          Prowler 스캔
        </Title>
        <Space>
          <Button icon={<CloudServerOutlined />} onClick={() => navigate('/settings/cloud-accounts')}>
            계정 관리
          </Button>
          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            onClick={handleNewScan}
            disabled={hasActiveScan}
            loading={hasActiveScan}
          >
            {hasActiveScan ? '스캔 진행중...' : '새 스캔 실행'}
          </Button>
        </Space>
      </div>

      {scans.some((s) => s.status === 'pending') && !scans.some((s) => s.status === 'running') && (
        <Card size="small" style={{ marginBottom: 12, borderColor: '#f59e0b' }}>
          <Space>
            <Tag color="orange">대기중</Tag>
            <Text>대기중인 스캔이 있습니다. Prowler 엔진 연결 후 자동 시작됩니다.</Text>
          </Space>
        </Card>
      )}

      {scans.length > 0 ? (
        <Table
          columns={columns}
          dataSource={scans}
          rowKey="id"
          loading={loading}
          size="middle"
          onRow={(r) => ({ onClick: () => navigate(`/prowler/${r.id}`), style: { cursor: 'pointer' } })}
          pagination={{ showTotal: (t) => `총 ${t}건` }}
        />
      ) : (
        <Card>
          <Empty
            description={
              accounts.length === 0
                ? '클라우드 계정을 먼저 등록하세요.'
                : '스캔 기록이 없습니다. "새 스캔 실행"을 클릭하세요.'
            }
          />
        </Card>
      )}

      <Modal
        title={errorScan ? `스캔 #${errorScan.id} 실패 원인` : ''}
        open={!!errorScan}
        onCancel={() => setErrorScan(null)}
        footer={[
          <Button
            key="detail"
            onClick={() => {
              if (errorScan) {
                const id = errorScan.id;
                setErrorScan(null);
                navigate(`/prowler/${id}`);
              }
            }}
          >
            상세 보기
          </Button>,
          <Button key="close" type="primary" onClick={() => setErrorScan(null)}>
            닫기
          </Button>,
        ]}
        width={720}
      >
        {errorScan && (
          <div>
            <Descriptions size="small" column={2} style={{ marginBottom: 12 }}>
              <Descriptions.Item label="대상 계정">
                {errorScan.cloud_account_alias
                  ? `${errorScan.cloud_account_alias} (${errorScan.cloud_account_id})`
                  : '미지정'}
              </Descriptions.Item>
              <Descriptions.Item label="완료">
                {errorScan.completed_at ? dayjs(errorScan.completed_at).format('YYYY-MM-DD HH:mm:ss') : '-'}
              </Descriptions.Item>
            </Descriptions>
            <div
              style={{
                whiteSpace: 'pre-wrap',
                fontFamily: 'monospace',
                fontSize: 12,
                background: '#1a2235',
                border: '1px solid #334155',
                borderRadius: 4,
                padding: 12,
                maxHeight: 360,
                overflow: 'auto',
                color: '#fca5a5',
              }}
            >
              {errorScan.error_message || '(원인이 기록되지 않았습니다)'}
            </div>
          </div>
        )}
      </Modal>

      <Modal
        title="Prowler 스캔 실행"
        open={scanModalOpen}
        onCancel={() => setScanModalOpen(false)}
        onOk={handleStartScan}
        okText="스캔 시작"
        cancelText="취소"
        okButtonProps={{ disabled: !selectedAccount }}
      >
        <Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>
          ISMS-P 기준으로 AWS 보안 점검을 수행합니다.
        </Text>
        <div style={{ marginBottom: 12 }}>
          <Text strong>대상 계정</Text>
          <Select
            placeholder="계정을 선택하세요"
            value={selectedAccount}
            onChange={setSelectedAccount}
            style={{ width: '100%', marginTop: 4 }}
            options={accounts
              .filter((a) => a.is_active)
              .map((a) => ({ value: a.id, label: `${a.alias} — AWS ${a.account_id}` }))}
          />
        </div>
        {selectedAccount && (
          <Descriptions size="small" column={1} bordered>
            <Descriptions.Item label="스캔 범위">전체 ISMS-P 매핑 체크 항목</Descriptions.Item>
            <Descriptions.Item label="예상 소요">10~30분</Descriptions.Item>
          </Descriptions>
        )}
      </Modal>
    </div>
  );
}
