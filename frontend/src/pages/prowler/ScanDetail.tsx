import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Typography, Button, Descriptions, Table, Tag, Select, message, Space, Alert } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { prowlerApi } from '../../api/prowler';

const { Title } = Typography;
const { Option } = Select;

interface ScanDetail {
  id: number;
  compliance: string;
  status: string;
  total_checks: number;
  passed: number;
  failed: number;
  started_at: string;
  completed_at: string | null;
  error_message: string | null;
}

interface Finding {
  id: number;
  check_id: string;
  check_title: string;
  status: string;
  severity: string;
  resource_uid: string;
  remediation_status: string;
}

const ScanDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [scan, setScan] = useState<ScanDetail | null>(null);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [filteredFindings, setFilteredFindings] = useState<Finding[]>([]);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [severityFilter, setSeverityFilter] = useState<string>('all');

  useEffect(() => {
    if (id) {
      fetchScanDetail();
    }
  }, [id]);

  useEffect(() => {
    applyFilters();
  }, [findings, statusFilter, severityFilter]);

  const fetchScanDetail = async () => {
    setLoading(true);
    try {
      const scanResponse = await prowlerApi.getScan(Number(id));
      setScan(scanResponse.data);

      const findingsResponse = await prowlerApi.getFindings(Number(id));
      setFindings(findingsResponse.data.items || findingsResponse.data || []);
    } catch (error) {
      message.error('스캔 상세 정보를 불러오는데 실패했습니다.');
      console.error('Error fetching scan detail:', error);
    } finally {
      setLoading(false);
    }
  };

  const applyFilters = () => {
    let filtered = [...findings];

    if (statusFilter !== 'all') {
      filtered = filtered.filter((f) => f.status === statusFilter);
    }

    if (severityFilter !== 'all') {
      filtered = filtered.filter((f) => f.severity === severityFilter);
    }

    setFilteredFindings(filtered);
  };

  const getStatusTag = (status: string) => {
    if (status === 'PASS') {
      return <Tag color="success">PASS</Tag>;
    } else if (status === 'FAIL') {
      return <Tag color="error">FAIL</Tag>;
    }
    return <Tag>{status}</Tag>;
  };

  const getSeverityTag = (severity: string) => {
    const severityConfig: Record<string, string> = {
      critical: 'red',
      high: 'orange',
      medium: 'gold',
      low: 'blue',
      informational: 'default',
    };
    const color = severityConfig[severity.toLowerCase()] || 'default';
    return <Tag color={color}>{severity.toUpperCase()}</Tag>;
  };

  const columns: ColumnsType<Finding> = [
    {
      title: 'Check ID',
      dataIndex: 'check_id',
      key: 'check_id',
      width: 200,
    },
    {
      title: 'Check Title',
      dataIndex: 'check_title',
      key: 'check_title',
      ellipsis: true,
    },
    {
      title: '상태',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => getStatusTag(status),
    },
    {
      title: '심각도',
      dataIndex: 'severity',
      key: 'severity',
      width: 120,
      render: (severity: string) => getSeverityTag(severity),
    },
    {
      title: 'Resource UID',
      dataIndex: 'resource_uid',
      key: 'resource_uid',
      width: 250,
      ellipsis: true,
    },
    {
      title: '조치 상태',
      dataIndex: 'remediation_status',
      key: 'remediation_status',
      width: 120,
      render: (status: string) => {
        const statusMap: Record<string, { color: string; text: string }> = {
          pending: { color: 'default', text: '대기' },
          in_progress: { color: 'processing', text: '진행중' },
          completed: { color: 'success', text: '완료' },
          failed: { color: 'error', text: '실패' },
        };
        const config = statusMap[status] || { color: 'default', text: status };
        return <Tag color={config.color}>{config.text}</Tag>;
      },
    },
  ];

  if (!scan) {
    return <div style={{ padding: '24px' }}>Loading...</div>;
  }

  const passRate = scan.total_checks > 0 ? ((scan.passed / scan.total_checks) * 100).toFixed(1) : '0.0';

  return (
    <div style={{ padding: '24px' }}>
      <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/prowler')} style={{ marginBottom: '24px' }}>
        뒤로 가기
      </Button>

      <Title level={2}>Prowler 스캔 상세</Title>

      {scan.status === 'failed' && (
        <Alert
          type="error"
          showIcon
          style={{ marginBottom: 16 }}
          message="스캔 실패"
          description={
            scan.error_message ? (
              <div
                style={{
                  whiteSpace: 'pre-wrap',
                  fontFamily: 'monospace',
                  fontSize: 12,
                  maxHeight: 240,
                  overflow: 'auto',
                }}
              >
                {scan.error_message}
              </div>
            ) : (
              <span>
                원인이 기록되지 않았습니다. <code>journalctl -u isms-backend</code> 로그를 확인하세요.
              </span>
            )
          }
        />
      )}

      <Descriptions bordered column={2} style={{ marginBottom: '24px' }}>
        <Descriptions.Item label="스캔 ID">{scan.id}</Descriptions.Item>
        <Descriptions.Item label="컴플라이언스">{scan.compliance}</Descriptions.Item>
        <Descriptions.Item label="상태">
          {scan.status === 'pending' && <Tag color="default">대기중</Tag>}
          {scan.status === 'running' && <Tag color="processing">실행중</Tag>}
          {scan.status === 'completed' && <Tag color="success">완료</Tag>}
          {scan.status === 'failed' && <Tag color="error">실패</Tag>}
          {scan.status === 'cancelled' && <Tag color="warning">취소됨</Tag>}
        </Descriptions.Item>
        <Descriptions.Item label="준수율">{passRate}%</Descriptions.Item>
        <Descriptions.Item label="총 검사">{scan.total_checks}</Descriptions.Item>
        <Descriptions.Item label="통과">
          <span style={{ color: '#52c41a', fontWeight: 'bold' }}>{scan.passed}</span>
        </Descriptions.Item>
        <Descriptions.Item label="실패">
          <span style={{ color: '#ff4d4f', fontWeight: 'bold' }}>{scan.failed}</span>
        </Descriptions.Item>
        <Descriptions.Item label="시작 시간">{dayjs(scan.started_at).format('YYYY-MM-DD HH:mm:ss')}</Descriptions.Item>
        <Descriptions.Item label="완료 시간">
          {scan.completed_at ? dayjs(scan.completed_at).format('YYYY-MM-DD HH:mm:ss') : '-'}
        </Descriptions.Item>
      </Descriptions>

      <div style={{ marginBottom: '16px' }}>
        <Space>
          <span>필터:</span>
          <Select value={statusFilter} onChange={setStatusFilter} style={{ width: 120 }}>
            <Option value="all">전체 상태</Option>
            <Option value="PASS">PASS</Option>
            <Option value="FAIL">FAIL</Option>
          </Select>
          <Select value={severityFilter} onChange={setSeverityFilter} style={{ width: 150 }}>
            <Option value="all">전체 심각도</Option>
            <Option value="critical">Critical</Option>
            <Option value="high">High</Option>
            <Option value="medium">Medium</Option>
            <Option value="low">Low</Option>
            <Option value="informational">Informational</Option>
          </Select>
        </Space>
      </div>

      <Table
        columns={columns}
        dataSource={filteredFindings}
        rowKey="id"
        loading={loading}
        pagination={{
          showSizeChanger: true,
          showTotal: (total) => `총 ${total}개`,
        }}
      />
    </div>
  );
};

export default ScanDetail;
