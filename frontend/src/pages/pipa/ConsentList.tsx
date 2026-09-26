import React, { useEffect, useState } from 'react';
import { Table, Button, Typography, Space, Tag } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { consentApi } from '../../api/pipa';

const { Title } = Typography;

interface ConsentTemplate {
  id: number;
  purpose: string;
  legal_basis: string;
  is_active: boolean;
}

const ConsentList: React.FC = () => {
  const [data, setData] = useState<ConsentTemplate[]>([]);
  const [loading, setLoading] = useState<boolean>(false);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      const response = await consentApi.list();
      setData(response.data);
    } catch (error) {
      console.error('Failed to fetch consent templates:', error);
    } finally {
      setLoading(false);
    }
  };

  const columns: ColumnsType<ConsentTemplate> = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 80,
    },
    {
      title: 'Purpose',
      dataIndex: 'purpose',
      key: 'purpose',
    },
    {
      title: 'Legal Basis',
      dataIndex: 'legal_basis',
      key: 'legal_basis',
    },
    {
      title: 'Status',
      dataIndex: 'is_active',
      key: 'is_active',
      width: 100,
      render: (is_active: boolean) => (
        <Tag color={is_active ? 'success' : 'default'}>{is_active ? 'Active' : 'Inactive'}</Tag>
      ),
    },
  ];

  return (
    <div style={{ padding: '24px' }}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Title level={4} style={{ margin: 0 }}>
            Consent Templates
          </Title>
          <Button type="primary" icon={<PlusOutlined />}>
            Create Template
          </Button>
        </div>
        <Table columns={columns} dataSource={data} loading={loading} rowKey="id" pagination={{ pageSize: 10 }} />
      </Space>
    </div>
  );
};

export default ConsentList;
