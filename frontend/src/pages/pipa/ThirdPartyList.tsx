import React, { useEffect, useState } from 'react';
import { Table, Button, Typography, Space, Tag } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { thirdPartyApi } from '../../api/pipa';
import dayjs from 'dayjs';

const { Title } = Typography;

interface ThirdPartyProcessor {
  id: number;
  company_name: string;
  purpose: string;
  contract_start: string;
  contract_end: string;
  is_active: boolean;
  is_sub_delegated: boolean;
}

const ThirdPartyList: React.FC = () => {
  const [data, setData] = useState<ThirdPartyProcessor[]>([]);
  const [loading, setLoading] = useState<boolean>(false);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      const response = await thirdPartyApi.list();
      setData(response.data);
    } catch (error) {
      console.error('Failed to fetch third-party processors:', error);
    } finally {
      setLoading(false);
    }
  };

  const columns: ColumnsType<ThirdPartyProcessor> = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 80,
    },
    {
      title: 'Company Name',
      dataIndex: 'company_name',
      key: 'company_name',
    },
    {
      title: 'Purpose',
      dataIndex: 'purpose',
      key: 'purpose',
    },
    {
      title: 'Contract Start',
      dataIndex: 'contract_start',
      key: 'contract_start',
      render: (date: string) => dayjs(date).format('YYYY-MM-DD'),
    },
    {
      title: 'Contract End',
      dataIndex: 'contract_end',
      key: 'contract_end',
      render: (date: string) => dayjs(date).format('YYYY-MM-DD'),
    },
    {
      title: 'Active',
      dataIndex: 'is_active',
      key: 'is_active',
      width: 100,
      render: (is_active: boolean) => <Tag color={is_active ? 'success' : 'default'}>{is_active ? 'Yes' : 'No'}</Tag>,
    },
    {
      title: 'Sub-delegated',
      dataIndex: 'is_sub_delegated',
      key: 'is_sub_delegated',
      width: 120,
      render: (is_sub_delegated: boolean) => (
        <Tag color={is_sub_delegated ? 'warning' : 'default'}>{is_sub_delegated ? 'Yes' : 'No'}</Tag>
      ),
    },
  ];

  return (
    <div style={{ padding: '24px' }}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Title level={4} style={{ margin: 0 }}>
            Third-Party Processors
          </Title>
          <Button type="primary" icon={<PlusOutlined />}>
            Add Third Party
          </Button>
        </div>
        <Table columns={columns} dataSource={data} loading={loading} rowKey="id" pagination={{ pageSize: 10 }} />
      </Space>
    </div>
  );
};

export default ThirdPartyList;
