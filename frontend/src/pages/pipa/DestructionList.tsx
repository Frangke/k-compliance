import React, { useEffect, useState } from 'react';
import { Table, Button, Typography, Space, Tag } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { destructionApi } from '../../api/pipa';
import dayjs from 'dayjs';

const { Title } = Typography;

interface DestructionRecord {
  id: number;
  data_category: string;
  retention_expiry: string;
  scheduled_date: string;
  status: string;
  handler: string;
}

const DestructionList: React.FC = () => {
  const [data, setData] = useState<DestructionRecord[]>([]);
  const [loading, setLoading] = useState<boolean>(false);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      const response = await destructionApi.list();
      setData(response.data);
    } catch (error) {
      console.error('Failed to fetch destruction records:', error);
    } finally {
      setLoading(false);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case 'open':
        return 'default';
      case 'in_progress':
        return 'processing';
      case 'completed':
        return 'success';
      case 'verified':
        return 'success';
      case 'overdue':
        return 'error';
      default:
        return 'default';
    }
  };

  const calculateDDay = (scheduledDate: string) => {
    const today = dayjs();
    const scheduled = dayjs(scheduledDate);
    const diff = scheduled.diff(today, 'day');

    let color = 'default';
    if (diff <= 3) {
      color = 'red';
    } else if (diff <= 5) {
      color = 'orange';
    }

    return { diff, color };
  };

  const columns: ColumnsType<DestructionRecord> = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 80,
    },
    {
      title: 'Data Category',
      dataIndex: 'data_category',
      key: 'data_category',
    },
    {
      title: 'Retention Expiry',
      dataIndex: 'retention_expiry',
      key: 'retention_expiry',
      render: (date: string) => dayjs(date).format('YYYY-MM-DD'),
    },
    {
      title: 'Scheduled Date',
      dataIndex: 'scheduled_date',
      key: 'scheduled_date',
      render: (date: string) => dayjs(date).format('YYYY-MM-DD'),
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => <Tag color={getStatusColor(status)}>{status.toUpperCase().replace('_', ' ')}</Tag>,
    },
    {
      title: 'D-Day',
      key: 'dday',
      render: (_, record) => {
        const { diff, color } = calculateDDay(record.scheduled_date);
        return <Tag color={color}>{diff > 0 ? `D-${diff}` : diff === 0 ? 'D-Day' : `D+${Math.abs(diff)}`}</Tag>;
      },
    },
    {
      title: 'Handler',
      dataIndex: 'handler',
      key: 'handler',
    },
  ];

  return (
    <div style={{ padding: '24px' }}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Title level={4} style={{ margin: 0 }}>
            Data Destruction Records
          </Title>
          <Button type="primary" icon={<PlusOutlined />}>
            Create Destruction Record
          </Button>
        </div>
        <Table columns={columns} dataSource={data} loading={loading} rowKey="id" pagination={{ pageSize: 10 }} />
      </Space>
    </div>
  );
};

export default DestructionList;
