import { useState, useEffect } from 'react';
import {
  Typography,
  Card,
  Button,
  Table,
  Space,
  Tag,
  Modal,
  message,
  Popconfirm,
  Tooltip,
  DatePicker,
  Select,
  Dropdown,
  Row,
  Col,
} from 'antd';
import type { MenuProps } from 'antd';
import {
  FileTextOutlined,
  PlusOutlined,
  EyeOutlined,
  DownloadOutlined,
  DeleteOutlined,
  LoadingOutlined,
  DownOutlined,
  FileZipOutlined,
  AuditOutlined,
  DashboardOutlined,
  FileExcelOutlined,
} from '@ant-design/icons';
import { reportsApi, type ReportType } from '../../api/reports';
import { usePermission } from '../../hooks/usePermission';
import dayjs from 'dayjs';

const { RangePicker } = DatePicker;

interface Report {
  id: number;
  report_code: string;
  report_type: ReportType;
  title: string;
  period_start: string;
  period_end: string;
  status: string;
  file_size: number | null;
  generated_by: number | null;
  generated_at: string | null;
}

const REPORT_TYPE_LABELS: Record<string, string> = {
  isms_assessment: 'ISMS 대응 보고서',
  corrective_action: '시정조치 보고서',
  evidence_package: '증적 패키지(ZIP)',
  dashboard_snapshot: '대시보드 스냅샷',
  evidence_summary: '증적 현황 보고서',
};

const REPORT_TYPE_ICONS: Record<string, React.ReactNode> = {
  isms_assessment: <FileTextOutlined />,
  corrective_action: <AuditOutlined />,
  evidence_package: <FileZipOutlined />,
  dashboard_snapshot: <DashboardOutlined />,
};

const REPORT_TYPE_COLORS: Record<string, string> = {
  isms_assessment: 'blue',
  corrective_action: 'orange',
  evidence_package: 'purple',
  dashboard_snapshot: 'geekblue',
  evidence_summary: 'cyan',
};

function formatBytes(bytes: number | null): string {
  if (!bytes) return '-';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function ReportList() {
  const [reports, setReports] = useState<Report[]>([]);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState<ReportType | null>(null);
  const [typeFilter, setTypeFilter] = useState<string | undefined>(undefined);
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs]>([
    dayjs().startOf('quarter'),
    dayjs().endOf('quarter'),
  ]);
  const [evidenceDomain, setEvidenceDomain] = useState<string | undefined>(undefined);
  const [previewId, setPreviewId] = useState<number | null>(null);
  const { hasRole } = usePermission();
  const canGenerate = hasRole('cpo', 'security_officer');

  const fetchReports = async () => {
    setLoading(true);
    try {
      const res = await reportsApi.list();
      setReports(res.data);
    } catch {
      message.error('보고서 목록을 불러올 수 없습니다');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchReports();
  }, []);

  const requirePeriod = (): [string, string] | null => {
    if (!dateRange[0] || !dateRange[1]) {
      message.warning('기간을 선택하세요');
      return null;
    }
    return [dateRange[0].format('YYYY-MM-DD'), dateRange[1].format('YYYY-MM-DD')];
  };

  const handleGenerate = async (type: ReportType) => {
    setGenerating(type);
    try {
      if (type === 'isms_assessment') {
        const range = requirePeriod();
        if (!range) return;
        await reportsApi.generateIsms(range[0], range[1]);
      } else if (type === 'corrective_action') {
        const range = requirePeriod();
        if (!range) return;
        await reportsApi.generateCorrective(range[0], range[1]);
      } else if (type === 'evidence_package') {
        const range = requirePeriod();
        if (!range) return;
        await reportsApi.generateEvidencePackage(range[0], range[1], evidenceDomain, 'approved');
      } else if (type === 'dashboard_snapshot') {
        await reportsApi.generateDashboardSnapshot();
      }
      message.success(`${REPORT_TYPE_LABELS[type]} 생성이 시작되었습니다 (백그라운드에서 진행)`);
      fetchReports();
      // Generator is now async (P0-3). Poll the list while anything is still
      // in "generating" state so the UI flips to "완료" / "실패" without a
      // manual refresh.
      const interval = setInterval(async () => {
        try {
          const r = await reportsApi.list();
          setReports(r.data);
          const stillRunning = (r.data || []).some((x: Report) => x.status === 'generating');
          if (!stillRunning) clearInterval(interval);
        } catch {
          clearInterval(interval);
        }
      }, 2000);
      // Safety stop after 5 minutes even if the server never transitions the state
      setTimeout(() => clearInterval(interval), 5 * 60 * 1000);
    } catch (err: any) {
      message.error(err.response?.data?.detail || '보고서 생성에 실패했습니다');
    } finally {
      setGenerating(null);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await reportsApi.delete(id);
      message.success('보고서가 삭제되었습니다');
      fetchReports();
    } catch (err: any) {
      message.error(err.response?.data?.detail || '삭제에 실패했습니다');
    }
  };

  const handleDownload = (report: Report) => {
    const url =
      report.report_type === 'evidence_package'
        ? reportsApi.getDownloadUrl(report.id)
        : reportsApi.getHtmlUrl(report.id);
    const a = document.createElement('a');
    a.href = url;
    const ext = report.report_type === 'evidence_package' ? '.zip' : '.html';
    a.download = `${report.report_code}_${report.title}${ext}`.replace(/[\/\\:*?"<>|]/g, '_');
    a.click();
  };

  const handleDownloadCsv = (report: Report) => {
    const a = document.createElement('a');
    a.href = reportsApi.getCsvUrl(report.id);
    a.download = `${report.report_code}.csv`;
    a.click();
  };

  const generateMenu: MenuProps['items'] = [
    {
      key: 'isms_assessment',
      icon: <FileTextOutlined />,
      label: 'ISMS 대응 보고서 (HTML)',
    },
    {
      key: 'corrective_action',
      icon: <AuditOutlined />,
      label: '시정조치 보고서 (HTML + CSV)',
    },
    {
      key: 'evidence_package',
      icon: <FileZipOutlined />,
      label: '증적 패키지 (ZIP)',
    },
    {
      key: 'dashboard_snapshot',
      icon: <DashboardOutlined />,
      label: '대시보드 스냅샷 (경영진 보고용)',
    },
  ];

  const filteredReports = typeFilter ? reports.filter((r) => r.report_type === typeFilter) : reports;

  const columns = [
    { title: '보고서 ID', dataIndex: 'report_code', width: 140 },
    {
      title: '유형',
      dataIndex: 'report_type',
      width: 160,
      render: (v: string) => (
        <Tag icon={REPORT_TYPE_ICONS[v]} color={REPORT_TYPE_COLORS[v] || 'default'}>
          {REPORT_TYPE_LABELS[v] || v}
        </Tag>
      ),
      filters: Object.entries(REPORT_TYPE_LABELS).map(([value, text]) => ({ text, value })),
      onFilter: (value: any, record: Report) => record.report_type === value,
    },
    { title: '제목', dataIndex: 'title', ellipsis: true },
    {
      title: '기간',
      width: 190,
      render: (_: any, r: Report) =>
        r.report_type === 'dashboard_snapshot' ? `${r.period_start} 기준` : `${r.period_start} ~ ${r.period_end}`,
    },
    {
      title: '상태',
      dataIndex: 'status',
      width: 90,
      render: (v: string) => {
        if (v === 'completed') return <Tag color="success">완료</Tag>;
        if (v === 'generating')
          return (
            <Tag icon={<LoadingOutlined spin />} color="processing">
              생성 중
            </Tag>
          );
        return <Tag color="error">실패</Tag>;
      },
    },
    { title: '크기', dataIndex: 'file_size', width: 80, render: formatBytes },
    {
      title: '생성일시',
      dataIndex: 'generated_at',
      width: 160,
      render: (v: string | null) => (v ? new Date(v).toLocaleString('ko-KR') : '-'),
    },
    {
      title: '작업',
      width: 170,
      render: (_: any, record: Report) => (
        <Space size={4}>
          {record.report_type !== 'evidence_package' && (
            <Tooltip title="미리보기">
              <Button
                type="text"
                icon={<EyeOutlined />}
                disabled={record.status !== 'completed'}
                onClick={() => setPreviewId(record.id)}
              />
            </Tooltip>
          )}
          <Tooltip title={record.report_type === 'evidence_package' ? 'ZIP 다운로드' : 'HTML 다운로드'}>
            <Button
              type="text"
              icon={<DownloadOutlined />}
              disabled={record.status !== 'completed'}
              onClick={() => handleDownload(record)}
            />
          </Tooltip>
          {record.report_type === 'corrective_action' && (
            <Tooltip title="CSV 다운로드">
              <Button
                type="text"
                icon={<FileExcelOutlined />}
                disabled={record.status !== 'completed'}
                onClick={() => handleDownloadCsv(record)}
              />
            </Tooltip>
          )}
          {canGenerate && (
            <Popconfirm
              title="이 보고서를 삭제하시겠습니까?"
              onConfirm={() => handleDelete(record.id)}
              okText="삭제"
              cancelText="취소"
            >
              <Button type="text" danger icon={<DeleteOutlined />} />
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Typography.Title level={4} style={{ margin: 0, marginBottom: 16 }}>
        보고서 관리
      </Typography.Title>

      {canGenerate && (
        <Card style={{ marginBottom: 24 }} size="small" title="보고서 생성">
          <Row gutter={[12, 12]} align="middle">
            <Col>
              <span style={{ color: '#64748b' }}>기간:</span>
            </Col>
            <Col>
              <RangePicker
                value={dateRange}
                onChange={(dates) => {
                  if (dates) setDateRange(dates as [dayjs.Dayjs, dayjs.Dayjs]);
                }}
                style={{ width: 260 }}
              />
            </Col>
            <Col>
              <span style={{ color: '#64748b' }}>도메인(증적팩 전용):</span>
            </Col>
            <Col>
              <Select
                allowClear
                value={evidenceDomain}
                onChange={setEvidenceDomain}
                style={{ width: 130 }}
                placeholder="전체"
                options={[
                  { value: '1', label: '1. 관리체계' },
                  { value: '2', label: '2. 보호대책' },
                  { value: '3', label: '3. 개인정보' },
                ]}
              />
            </Col>
            <Col flex="auto" style={{ textAlign: 'right' }}>
              <Dropdown
                menu={{
                  items: generateMenu,
                  onClick: ({ key }) => handleGenerate(key as ReportType),
                }}
                disabled={!!generating}
              >
                <Button type="primary" icon={<PlusOutlined />} loading={!!generating}>
                  보고서 생성 <DownOutlined />
                </Button>
              </Dropdown>
            </Col>
          </Row>
          <div style={{ marginTop: 12, color: '#64748b', fontSize: 12 }}>
            💡 ISMS 대응/시정조치/증적 패키지는 기간이 필요합니다. 대시보드 스냅샷은 현재 시점 기준으로 생성됩니다.
          </div>
        </Card>
      )}

      <Card size="small" style={{ marginBottom: 12 }}>
        <Space>
          <span style={{ color: '#64748b' }}>유형 필터:</span>
          <Select
            allowClear
            value={typeFilter}
            onChange={setTypeFilter}
            style={{ width: 200 }}
            placeholder="전체"
            options={Object.entries(REPORT_TYPE_LABELS).map(([value, label]) => ({ value, label }))}
          />
          <span style={{ color: '#64748b' }}>총 {filteredReports.length}건</span>
        </Space>
      </Card>

      <Table
        dataSource={filteredReports}
        columns={columns}
        rowKey="id"
        loading={loading}
        pagination={{ pageSize: 20 }}
        size="middle"
      />

      <Modal
        title="보고서 미리보기"
        open={previewId !== null}
        onCancel={() => setPreviewId(null)}
        footer={[
          <Button key="close" onClick={() => setPreviewId(null)}>
            닫기
          </Button>,
          <Button
            key="download"
            type="primary"
            icon={<DownloadOutlined />}
            onClick={() => {
              const report = reports.find((r) => r.id === previewId);
              if (report) handleDownload(report);
            }}
          >
            다운로드
          </Button>,
        ]}
        width="90vw"
        style={{ top: 20 }}
        styles={{ body: { padding: 0, height: '80vh' } }}
      >
        {previewId && (
          <iframe
            src={reportsApi.getHtmlUrl(previewId)}
            style={{ width: '100%', height: '80vh', border: 'none', background: '#fff' }}
            title="보고서 미리보기"
          />
        )}
      </Modal>
    </div>
  );
}
