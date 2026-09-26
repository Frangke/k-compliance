import { useEffect, useRef, useState } from 'react';
import {
  Typography,
  Button,
  Table,
  Tag,
  Select,
  message,
  Card,
  Row,
  Col,
  Statistic,
  Space,
  Modal,
  Descriptions,
} from 'antd';
import { SyncOutlined, CloudServerOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { configApi } from '../../api/prowler';

const { Title, Text } = Typography;

interface ConfigSummary {
  total_rules: number;
  compliant: number;
  non_compliant: number;
  remediation_pending: number;
}
interface ConfigEvaluation {
  id: number;
  config_rule_name: string;
  compliance_type: string;
  isms_item_id: string;
  remediation_status: string;
}
interface ConfigSyncJob {
  id: number;
  conformance_pack: string;
  status: string;
  total_rules: number;
  compliant: number;
  non_compliant: number;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  cloud_account_alias: string | null;
  cloud_account_id: string | null;
}

const SYNC_STATUS_CFG: Record<string, { color: string; text: string }> = {
  pending: { color: 'orange', text: '대기중' },
  running: { color: 'processing', text: '실행중' },
  completed: { color: 'success', text: '완료' },
  failed: { color: 'error', text: '실패' },
  cancelled: { color: 'default', text: '취소됨' },
};

const REMEDIATION_MAP: Record<string, { color: string; text: string }> = {
  pending: { color: 'default', text: '대기' },
  in_progress: { color: 'processing', text: '진행중' },
  completed: { color: 'success', text: '완료' },
  failed: { color: 'error', text: '실패' },
  not_required: { color: 'default', text: '불필요' },
};

export default function ConfigDashboard() {
  const navigate = useNavigate();
  const [summary, setSummary] = useState<ConfigSummary>({
    total_rules: 0,
    compliant: 0,
    non_compliant: 0,
    remediation_pending: 0,
  });
  const [evaluations, setEvaluations] = useState<ConfigEvaluation[]>([]);
  const [filtered, setFiltered] = useState<ConfigEvaluation[]>([]);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [filter, setFilter] = useState<string>('all');
  const [syncJobs, setSyncJobs] = useState<ConfigSyncJob[]>([]);
  const [errorJob, setErrorJob] = useState<ConfigSyncJob | null>(null);
  const pollRef = useRef<number | null>(null);

  const fetchSyncJobs = async () => {
    try {
      const res = await configApi.listSyncJobs();
      setSyncJobs(res.data || []);
    } catch {
      /* silent — the error banner below will reflect latest known job */
    }
  };

  const fetchData = async () => {
    setLoading(true);
    try {
      const [sumRes, evalRes] = await Promise.all([configApi.summary(), configApi.listEvaluations()]);
      setSummary(sumRes.data);
      setEvaluations(evalRes.data.items || evalRes.data || []);
    } catch {
      message.error('AWS Config 데이터를 불러오는데 실패했습니다.');
    } finally {
      setLoading(false);
    }
    await fetchSyncJobs();
  };

  const handleSync = async () => {
    setSyncing(true);
    try {
      // Sync returns 201 + job id immediately; the worker runs in the
      // background. Poll until it terminates so we can surface success or
      // the error_message without a page refresh.
      await configApi.sync();
      message.info('동기화 작업이 시작되었습니다. 완료까지 기다려주세요.');
      if (pollRef.current) window.clearInterval(pollRef.current);
      pollRef.current = window.setInterval(async () => {
        const res = await configApi.listSyncJobs();
        const jobs: ConfigSyncJob[] = res.data || [];
        setSyncJobs(jobs);
        const latest = jobs[0];
        if (latest && (latest.status === 'completed' || latest.status === 'failed' || latest.status === 'cancelled')) {
          if (pollRef.current) {
            window.clearInterval(pollRef.current);
            pollRef.current = null;
          }
          setSyncing(false);
          if (latest.status === 'completed') {
            message.success(`동기화 완료: ${latest.compliant}/${latest.total_rules} 준수`);
            await fetchData();
          } else if (latest.status === 'failed') {
            // Short toast — the user clicks the 실패 tag in the history
            // table to see the full traceback modal on demand.
            message.error('동기화 실패 — 아래 이력에서 "실패" 태그를 눌러 원인을 확인하세요');
          }
        }
      }, 2000);
    } catch (err: any) {
      setSyncing(false);
      message.error(err.response?.data?.detail || '동기화 요청에 실패했습니다');
    }
  };

  useEffect(() => {
    fetchData();
  }, []);
  useEffect(
    () => () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    },
    [],
  );
  useEffect(() => {
    setFiltered(filter === 'all' ? evaluations : evaluations.filter((e) => e.compliance_type === filter));
  }, [evaluations, filter]);

  const rate = summary.total_rules > 0 ? ((summary.compliant / summary.total_rules) * 100).toFixed(1) : '0.0';

  const columns: ColumnsType<ConfigEvaluation> = [
    { title: '규칙명', dataIndex: 'config_rule_name', ellipsis: true },
    {
      title: '준수 상태',
      dataIndex: 'compliance_type',
      width: 120,
      render: (v: string) => (
        <Tag color={v === 'COMPLIANT' ? 'success' : 'error'}>{v === 'COMPLIANT' ? '준수' : '미준수'}</Tag>
      ),
    },
    { title: 'ISMS 항목', dataIndex: 'isms_item_id', width: 100 },
    {
      title: '조치 상태',
      dataIndex: 'remediation_status',
      width: 100,
      render: (v: string) => {
        const r = REMEDIATION_MAP[v];
        return <Tag color={r?.color}>{r?.text || v}</Tag>;
      },
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>
          AWS Config 준수 현황
        </Title>
        <Space>
          <Button icon={<CloudServerOutlined />} onClick={() => navigate('/settings/cloud-accounts')}>
            계정 관리
          </Button>
          <Button type="primary" icon={<SyncOutlined />} onClick={handleSync} loading={syncing}>
            동기화 실행
          </Button>
        </Space>
      </div>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card size="small">
            <Statistic title="전체 규칙" value={summary.total_rules} valueStyle={{ color: '#3b82f6' }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="준수" value={summary.compliant} suffix={`(${rate}%)`} valueStyle={{ color: '#10b981' }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="미준수" value={summary.non_compliant} valueStyle={{ color: '#ef4444' }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="조치 대기" value={summary.remediation_pending} valueStyle={{ color: '#f59e0b' }} />
          </Card>
        </Col>
      </Row>

      {syncJobs.length > 0 && (
        <Card
          size="small"
          style={{ marginBottom: 16 }}
          title="최근 동기화 이력"
          extra={
            <Text type="secondary" style={{ fontSize: 12 }}>
              최대 5건
            </Text>
          }
        >
          <Table
            dataSource={syncJobs.slice(0, 5)}
            rowKey="id"
            size="small"
            pagination={false}
            columns={[
              { title: 'ID', dataIndex: 'id', width: 50 },
              { title: '컨포먼스 팩', dataIndex: 'conformance_pack', ellipsis: true },
              {
                title: '계정',
                width: 160,
                render: (_: any, r: ConfigSyncJob) =>
                  r.cloud_account_alias ? `${r.cloud_account_alias} (${r.cloud_account_id})` : '-',
              },
              {
                title: '상태',
                dataIndex: 'status',
                width: 90,
                render: (s: string, r: ConfigSyncJob) => {
                  const c = SYNC_STATUS_CFG[s];
                  if (s === 'failed' && r.error_message) {
                    return (
                      <Tag
                        color={c?.color}
                        style={{ cursor: 'pointer' }}
                        onClick={() => setErrorJob(r)}
                        title="클릭하여 실패 원인 보기"
                      >
                        {c?.text || s}
                      </Tag>
                    );
                  }
                  return <Tag color={c?.color}>{c?.text || s}</Tag>;
                },
              },
              {
                title: '결과',
                width: 140,
                render: (_: any, r: ConfigSyncJob) =>
                  r.status === 'completed' ? `${r.compliant}/${r.total_rules}` : '-',
              },
              {
                title: '시작',
                dataIndex: 'started_at',
                width: 130,
                render: (v: string | null) => (v ? dayjs(v).format('MM-DD HH:mm:ss') : '-'),
              },
              {
                title: '완료',
                dataIndex: 'completed_at',
                width: 130,
                render: (v: string | null) => (v ? dayjs(v).format('MM-DD HH:mm:ss') : '-'),
              },
            ]}
          />
        </Card>
      )}

      <Space style={{ marginBottom: 12 }}>
        <Select
          value={filter}
          onChange={setFilter}
          style={{ width: 150 }}
          options={[
            { value: 'all', label: '전체' },
            { value: 'COMPLIANT', label: '준수' },
            { value: 'NON_COMPLIANT', label: '미준수' },
          ]}
        />
      </Space>

      <Table
        columns={columns}
        dataSource={filtered}
        rowKey="id"
        loading={loading}
        size="middle"
        pagination={{ showTotal: (t) => `총 ${t}건` }}
      />

      <Modal
        title={errorJob ? `동기화 작업 #${errorJob.id} 실패 원인` : ''}
        open={!!errorJob}
        onCancel={() => setErrorJob(null)}
        footer={[
          <Button key="close" type="primary" onClick={() => setErrorJob(null)}>
            닫기
          </Button>,
        ]}
        width={720}
      >
        {errorJob && (
          <div>
            <Descriptions size="small" column={2} style={{ marginBottom: 12 }}>
              <Descriptions.Item label="컨포먼스 팩">{errorJob.conformance_pack}</Descriptions.Item>
              <Descriptions.Item label="대상 계정">
                {errorJob.cloud_account_alias
                  ? `${errorJob.cloud_account_alias} (${errorJob.cloud_account_id})`
                  : '미지정'}
              </Descriptions.Item>
              <Descriptions.Item label="시작">
                {errorJob.started_at ? dayjs(errorJob.started_at).format('YYYY-MM-DD HH:mm:ss') : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="완료">
                {errorJob.completed_at ? dayjs(errorJob.completed_at).format('YYYY-MM-DD HH:mm:ss') : '-'}
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
              {errorJob.error_message || '(원인이 기록되지 않았습니다)'}
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
