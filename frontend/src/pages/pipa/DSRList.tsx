import React, { useEffect, useState } from 'react';
import { Table, Button, Typography, Space, Tag } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { dsrApi } from '../../api/pipa';
import dayjs from 'dayjs';

const { Title } = Typography;

interface DSRRequest {
  id: number;
  requester_name: string;
  request_type: string;
  status: string;
  due_date: string;
  assigned_to: string;
}

const DSRList: React.FC = () => {
  const [data, setData] = useState<DSRRequest[]>([]);
  const [loading, setLoading] = useState<boolean>(false);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      const response = await dsrApi.list();
      setData(response.data);
    } catch (error) {
      console.error('Failed to fetch DSR requests:', error);
    } finally {
      setLoading(false);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case 'received':
        return 'default';
      case 'assigned':
        return 'processing';
      case 'completed':
        return 'success';
      case 'rejected':
        return 'error';
      default:
        return 'default';
    }
  };

  const calculateDDay = (dueDate: string) => {
    const today = dayjs();
    const due = dayjs(dueDate);
    const diff = due.diff(today, 'day');

    let color = 'default';
    if (diff <= 3) {
      color = 'red';
    } else if (diff <= 5) {
      color = 'orange';
    }

    return { diff, color };
  };

  const columns: ColumnsType<DSRRequest> = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 80,
    },
    {
      title: 'Requester Name',
      dataIndex: 'requester_name',
      key: 'requester_name',
    },
    {
      title: 'Request Type',
      dataIndex: 'request_type',
      key: 'request_type',
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => <Tag color={getStatusColor(status)}>{status.toUpperCase()}</Tag>,
    },
    {
      title: 'Due Date',
      dataIndex: 'due_date',
      key: 'due_date',
      render: (date: string) => dayjs(date).format('YYYY-MM-DD'),
    },
    {
      title: 'D-Day',
      key: 'dday',
      render: (_, record) => {
        const { diff, color } = calculateDDay(record.due_date);
        return <Tag color={color}>{diff > 0 ? `D-${diff}` : diff === 0 ? 'D-Day' : `D+${Math.abs(diff)}`}</Tag>;
      },
    },
    {
      title: 'Assigned To',
      dataIndex: 'assigned_to',
      key: 'assigned_to',
    },
  ];

  return (
    <div style={{ padding: '24px' }}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Title level={4} style={{ margin: 0 }}>
            Data Subject Rights Requests
          </Title>
          <Button type="primary" icon={<PlusOutlined />}>
            Create DSR
          </Button>
        </div>
        <Table columns={columns} dataSource={data} loading={loading} rowKey="id" pagination={{ pageSize: 10 }} />
      </Space>
    </div>
  );
};

export default DSRList;
