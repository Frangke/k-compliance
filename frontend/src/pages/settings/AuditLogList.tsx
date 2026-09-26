import { useEffect, useState, useCallback } from 'react';
import {
  Typography,
  Card,
  Table,
  Tag,
  Space,
  Button,
  Select,
  Input,
  DatePicker,
  Row,
  Col,
  Drawer,
  Descriptions,
  message,
} from 'antd';
import { DownloadOutlined, ReloadOutlined, EyeOutlined, SearchOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { auditLogsApi, type AuditLogEntry, type AuditLogFilters } from '../../api/auditLogs';

const { RangePicker } = DatePicker;

function actionTagColor(action: string): string {
  const a = action.toLowerCase();
  if (a.includes('delete') || a.includes('reject')) return 'red';
  if (a.includes('create') || a.includes('add')) return 'green';
  if (a.includes('update') || a.includes('edit') || a.includes('modify')) return 'blue';
  if (a.includes('login')) return 'cyan';
  if (a.includes('approve') || a.includes('verify') || a.includes('complete')) return 'success';
  return 'default';
}

function JsonView({ data }: { data: Record<string, any> | null }) {
  if (!data) return <span style={{ color: '#94a3b8' }}>-</span>;
  return (
    <pre
      style={{
        margin: 0,
        padding: 8,
        background: '#0f172a',
        color: '#e2e8f0',
        borderRadius: 4,
        fontSize: 12,
        maxHeight: 260,
        overflow: 'auto',
      }}
    >
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}

export default function AuditLogList() {
  const [logs, setLogs] = useState<AuditLogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [entityTypes, setEntityTypes] = useState<{ entity_type: string; count: number }[]>([]);
  const [actions, setActions] = useState<{ action: string; count: number }[]>([]);
  const [detail, setDetail] = useState<AuditLogEntry | null>(null);

  const [filters, setFilters] = useState<AuditLogFilters>({ page: 1, size: 50 });
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs] | null>(null);
  const [searchText, setSearchText] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await auditLogsApi.list(filters);
      setLogs(res.data.items);
      setTotal(res.data.total);
    } catch {
      message.error('감사 로그 조회에 실패했습니다');
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    Promise.all([auditLogsApi.entityTypes(), auditLogsApi.actions()])
      .then(([et, ac]) => {
        setEntityTypes(et.data);
        setActions(ac.data);
      })
      .catch(() => {});
  }, []);

  const applyFilters = () => {
    const next: AuditLogFilters = { ...filters, page: 1 };
    next.search = searchText || undefined;
    next.date_from = dateRange?.[0]?.format('YYYY-MM-DD');
    next.date_to = dateRange?.[1]?.format('YYYY-MM-DD');
    setFilters(next);
  };

  const resetFilters = () => {
    setDateRange(null);
    setSearchText('');
    setFilters({ page: 1, size: 50 });
  };

  const handleExport = () => {
    const url = auditLogsApi.getExportUrl(filters);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'audit_logs.csv';
    a.click();
  };

  const columns = [
    { title: 'ID', dataIndex: 'id', width: 80 },
    {
      title: '일시',
      dataIndex: 'created_at',
      width: 170,
      render: (v: string | null) => (v ? new Date(v).toLocaleString('ko-KR') : '-'),
    },
    {
      title: '사용자',
      width: 160,
      render: (_: any, r: AuditLogEntry) =>
        r.username ? (
          <span>
            {r.user_name || r.username} <span style={{ color: '#94a3b8', fontSize: 11 }}>(@{r.username})</span>
          </span>
        ) : (
          <span style={{ color: '#94a3b8' }}>시스템</span>
        ),
    },
    {
      title: '액션',
      dataIndex: 'action',
      width: 180,
      render: (v: string) => <Tag color={actionTagColor(v)}>{v}</Tag>,
    },
    {
      title: '엔티티',
      width: 180,
      render: (_: any, r: AuditLogEntry) =>
        r.entity_type ? (
          <span>
            <Tag>{r.entity_type}</Tag>
            {r.entity_id ? <span style={{ color: '#94a3b8' }}>#{r.entity_id}</span> : null}
          </span>
        ) : (
          '-'
        ),
    },
    { title: 'IP', dataIndex: 'ip_address', width: 130, render: (v: string) => v || '-' },
    {
      title: '상세',
      width: 80,
      render: (_: any, r: AuditLogEntry) => <Button type="text" icon={<EyeOutlined />} onClick={() => setDetail(r)} />,
    },
  ];

  return (
    <div>
      <Typography.Title level={4} style={{ margin: 0, marginBottom: 16 }}>
        감사 로그
      </Typography.Title>

      <Card size="small" style={{ marginBottom: 12 }}>
        <Row gutter={[8, 8]} align="middle">
          <Col>
            <Select
              allowClear
              placeholder="엔티티 타입"
              style={{ width: 180 }}
              value={filters.entity_type}
              onChange={(v) => setFilters({ ...filters, entity_type: v, page: 1 })}
              options={entityTypes.map((e) => ({
                value: e.entity_type,
                label: `${e.entity_type} (${e.count})`,
              }))}
              showSearch
            />
          </Col>
          <Col>
            <Select
              allowClear
              placeholder="액션"
              style={{ width: 200 }}
              value={filters.action}
              onChange={(v) => setFilters({ ...filters, action: v, page: 1 })}
              options={actions.map((a) => ({
                value: a.action,
                label: `${a.action} (${a.count})`,
              }))}
              showSearch
            />
          </Col>
          <Col>
            <RangePicker
              value={dateRange}
              onChange={(dates) => setDateRange(dates as [dayjs.Dayjs, dayjs.Dayjs] | null)}
              style={{ width: 260 }}
            />
          </Col>
          <Col flex="auto">
            <Input
              placeholder="액션/엔티티로 검색"
              allowClear
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              onPressEnter={applyFilters}
              prefix={<SearchOutlined />}
              style={{ maxWidth: 280 }}
            />
          </Col>
          <Col>
            <Space>
              <Button type="primary" icon={<SearchOutlined />} onClick={applyFilters}>
                조회
              </Button>
              <Button icon={<ReloadOutlined />} onClick={resetFilters}>
                초기화
              </Button>
              <Button icon={<DownloadOutlined />} onClick={handleExport}>
                CSV 내보내기
              </Button>
            </Space>
          </Col>
        </Row>
      </Card>

      <Table
        dataSource={logs}
        columns={columns}
        rowKey="id"
        loading={loading}
        size="middle"
        pagination={{
          current: filters.page,
          pageSize: filters.size,
          total,
          showTotal: (t) => `총 ${t}건`,
          pageSizeOptions: ['20', '50', '100', '200'],
          showSizeChanger: true,
          onChange: (page, size) => setFilters({ ...filters, page, size }),
        }}
      />

      <Drawer
        title={detail ? `감사 로그 #${detail.id}` : ''}
        open={!!detail}
        onClose={() => setDetail(null)}
        width={640}
      >
        {detail && (
          <Descriptions column={1} bordered size="small">
            <Descriptions.Item label="일시">
              {detail.created_at ? new Date(detail.created_at).toLocaleString('ko-KR') : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="사용자">
              {detail.username
                ? `${detail.user_name || detail.username} (@${detail.username}, id=${detail.user_id})`
                : '시스템'}
            </Descriptions.Item>
            <Descriptions.Item label="액션">
              <Tag color={actionTagColor(detail.action)}>{detail.action}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="엔티티">
              {detail.entity_type ? `${detail.entity_type}` : '-'}
              {detail.entity_id ? ` #${detail.entity_id}` : ''}
            </Descriptions.Item>
            <Descriptions.Item label="IP">{detail.ip_address || '-'}</Descriptions.Item>
            <Descriptions.Item label="User-Agent">{detail.user_agent || '-'}</Descriptions.Item>
            <Descriptions.Item label="이전 값">
              <JsonView data={detail.old_values} />
            </Descriptions.Item>
            <Descriptions.Item label="신규 값">
              <JsonView data={detail.new_values} />
            </Descriptions.Item>
          </Descriptions>
        )}
      </Drawer>
    </div>
  );
}
