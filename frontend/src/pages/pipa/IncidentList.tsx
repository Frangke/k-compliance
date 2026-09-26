import React, { useEffect, useState } from 'react';
import { Table, Button, Typography, Space, Tag } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { incidentApi } from '../../api/pipa';
import dayjs from 'dayjs';

const { Title } = Typography;

interface Incident {
  id: number;
  title: string;
  severity: string;
  status: string;
  detected_at: string;
  notification_deadline: string;
}

const IncidentList: React.FC = () => {
  const [data, setData] = useState<Incident[]>([]);
  const [loading, setLoading] = useState<boolean>(false);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      const response = await incidentApi.list();
      setData(response.data);
    } catch (error) {
      console.error('Failed to fetch incidents:', error);
    } finally {
      setLoading(false);
    }
  };

  const getSeverityColor = (severity: string) => {
    switch (severity.toLowerCase()) {
      case 'critical':
        return 'error';
      case 'high':
        return 'warning';
      case 'medium':
        return 'processing';
      case 'low':
        return 'default';
      default:
        return 'default';
    }
  };

  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case 'detected':
        return 'warning';
      case 'in_progress':
        return 'processing';
      case 'closed':
        return 'default';
      case 'completed':
        return 'success';
      default:
        return 'default';
    }
  };

  const calculateHoursRemaining = (deadline: string) => {
    const now = dayjs();
    const deadlineDate = dayjs(deadline);
    const hours = deadlineDate.diff(now, 'hour');

    let color = 'default';
    if (hours < 0) {
      color = 'red';
    } else if (hours <= 24) {
      color = 'orange';
    }

    return { hours, color };
  };

  const columns: ColumnsType<Incident> = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 80,
    },
    {
      title: 'Title',
      dataIndex: 'title',
      key: 'title',
    },
    {
      title: 'Severity',
      dataIndex: 'severity',
      key: 'severity',
      render: (severity: string) => <Tag color={getSeverityColor(severity)}>{severity.toUpperCase()}</Tag>,
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => <Tag color={getStatusColor(status)}>{status.toUpperCase().replace('_', ' ')}</Tag>,
    },
    {
      title: 'Detected At',
      dataIndex: 'detected_at',
      key: 'detected_at',
      render: (date: string) => dayjs(date).format('YYYY-MM-DD HH:mm'),
    },
    {
      title: 'Notification Deadline',
      dataIndex: 'notification_deadline',
      key: 'notification_deadline',
      render: (date: string) => dayjs(date).format('YYYY-MM-DD HH:mm'),
    },
    {
      title: 'Hours Remaining',
      key: 'hours_remaining',
      render: (_, record) => {
        const { hours, color } = calculateHoursRemaining(record.notification_deadline);
        return <Tag color={color}>{hours >= 0 ? `${hours}h` : `${Math.abs(hours)}h overdue`}</Tag>;
      },
    },
  ];

  return (
    <div style={{ padding: '24px' }}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Title level={4} style={{ margin: 0 }}>
            Privacy Incidents
          </Title>
          <Button type="primary" icon={<PlusOutlined />}>
            Report Incident
          </Button>
        </div>
        <Table columns={columns} dataSource={data} loading={loading} rowKey="id" pagination={{ pageSize: 10 }} />
      </Space>
    </div>
  );
};

export default IncidentList;
