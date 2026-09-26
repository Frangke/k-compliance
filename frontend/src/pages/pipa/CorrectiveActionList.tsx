import { useEffect, useState } from 'react';
import {
  Table,
  Button,
  Typography,
  Space,
  Tag,
  Modal,
  Form,
  Input,
  Select,
  DatePicker,
  message,
  Drawer,
  Descriptions,
  Upload,
} from 'antd';
import { PlusOutlined, UploadOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { correctiveApi } from '../../api/pipa';
import { evidenceApi } from '../../api/evidence';
import { ismsApi } from '../../api/isms';
import { usePermission } from '../../hooks/usePermission';
import dayjs from 'dayjs';

const { Title, Text } = Typography;

const STATUS_MAP: Record<string, { color: string; label: string }> = {
  open: { color: 'default', label: '미조치' },
  in_progress: { color: 'processing', label: '진행중' },
  completed: { color: 'success', label: '완료' },
  verified: { color: 'cyan', label: '검증완료' },
  overdue: { color: 'error', label: '기한초과' },
};

const SOURCE_MAP: Record<string, string> = {
  external_audit: '외부 심사',
  internal_review: '내부 점검',
  prowler: 'Prowler',
  config: 'AWS Config',
  other: '기타',
};

interface CorrectiveAction {
  id: number;
  source: string;
  source_detail: string | null;
  isms_item_id: number | null;
  title: string;
  description: string;
  status: string;
  due_date: string;
  assigned_to: number | null;
  result: string | null;
  completed_at: string | null;
}

export default function CorrectiveActionList() {
  const [data, setData] = useState<CorrectiveAction[]>([]);
  const [filteredData, setFilteredData] = useState<CorrectiveAction[]>([]);
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [loading, setLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [selected, setSelected] = useState<CorrectiveAction | null>(null);
  const [completeOpen, setCompleteOpen] = useState(false);
  const [allItems, setAllItems] = useState<any[]>([]);
  const { hasRole } = usePermission();
  const [form] = Form.useForm();
  const [completeForm] = Form.useForm();

  const fetchData = async () => {
    setLoading(true);
    try {
      setData((await correctiveApi.list()).data || []);
    } catch {
      message.error('시정조치 목록을 불러오는데 실패했습니다.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    ismsApi
      .getItems({ size: 200 })
      .then((r) => setAllItems(r.data.items || []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    setFilteredData(statusFilter ? data.filter((d) => d.status === statusFilter) : data);
  }, [data, statusFilter]);

  const getItemName = (itemId: number | null) => {
    if (!itemId) return null;
    const item = allItems.find((i) => i.id === itemId);
    return item ? `${item.code} ${item.name}` : `항목 #${itemId}`;
  };

  const handleCreate = async (values: any) => {
    try {
      await correctiveApi.create({ ...values, due_date: values.due_date.format('YYYY-MM-DD') });
      message.success('시정조치가 등록되었습니다.');
      setCreateOpen(false);
      form.resetFields();
      fetchData();
    } catch (err: any) {
      message.error(err.response?.data?.detail || '등록 실패');
    }
  };

  const handleComplete = async (values: any) => {
    if (!selected) return;
    try {
      let evidenceId: number | undefined;
      // 증적 파일 첨부 시 업로드
      if (values.file?.file) {
        const formData = new FormData();
        formData.append('file', values.file.file);
        formData.append('title', values.evidenceTitle || `시정조치 #${selected.id} 증적`);
        const evRes = await evidenceApi.upload(formData);
        evidenceId = evRes.data.id;
        // 관련 ISMS-P 항목이 있으면 연결
        if (selected.isms_item_id) {
          const itemCode = allItems.find((i) => i.id === selected.isms_item_id)?.code;
          if (itemCode) await evidenceApi.linkItems(evRes.data.id, { item_codes: [itemCode] });
        }
      }
      await correctiveApi.complete(selected.id, { result: values.result, evidence_id: evidenceId });
      message.success('조치 완료 처리되었습니다.' + (evidenceId ? ' (증적 첨부됨)' : ''));
      setCompleteOpen(false);
      completeForm.resetFields();
      setSelected(null);
      fetchData();
    } catch (err: any) {
      message.error(err.response?.data?.detail || '완료 처리 실패');
    }
  };

  const handleVerify = async (id: number) => {
    try {
      await correctiveApi.verify(id);
      message.success('검증이 완료되었습니다.');
      setSelected(null);
      fetchData();
    } catch (err: any) {
      message.error(err.response?.data?.detail || '검증 실패');
    }
  };

  const getDDay = (dueDate: string) => {
    const diff = dayjs(dueDate).diff(dayjs(), 'day');
    const color = diff < 0 ? 'red' : diff <= 3 ? 'red' : diff <= 7 ? 'orange' : 'blue';
    return <Tag color={color}>{diff < 0 ? `D+${Math.abs(diff)}` : diff === 0 ? 'D-Day' : `D-${diff}`}</Tag>;
  };

  const itemOptions = allItems.map((i) => ({ value: i.id, label: `${i.code} ${i.name}` }));

  const columns: ColumnsType<CorrectiveAction> = [
    { title: 'ID', dataIndex: 'id', width: 50, sorter: (a, b) => a.id - b.id },
    {
      title: '관련 항목',
      width: 160,
      sorter: (a, b) => (a.isms_item_id || 0) - (b.isms_item_id || 0),
      render: (_: any, r: CorrectiveAction) => {
        const name = getItemName(r.isms_item_id);
        return name ? <Tag color="blue">{name}</Tag> : <Text type="secondary">-</Text>;
      },
    },
    {
      title: '출처',
      dataIndex: 'source',
      width: 90,
      sorter: (a, b) => a.source.localeCompare(b.source),
      render: (v: string) => SOURCE_MAP[v] || v,
    },
    { title: '제목', dataIndex: 'title', ellipsis: true, sorter: (a, b) => a.title.localeCompare(b.title) },
    {
      title: '상태',
      dataIndex: 'status',
      width: 90,
      sorter: (a, b) => a.status.localeCompare(b.status),
      render: (v: string) => {
        const s = STATUS_MAP[v];
        return s ? <Tag color={s.color}>{s.label}</Tag> : v;
      },
    },
    {
      title: '기한',
      dataIndex: 'due_date',
      width: 100,
      sorter: (a, b) => a.due_date.localeCompare(b.due_date),
      render: (v: string) => dayjs(v).format('YYYY-MM-DD'),
    },
    {
      title: 'D-Day',
      width: 70,
      sorter: (a, b) => dayjs(a.due_date).diff(dayjs()) - dayjs(b.due_date).diff(dayjs()),
      render: (_: any, r: CorrectiveAction) => getDDay(r.due_date),
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>
          시정조치 관리
        </Title>
        <Space>
          <Select
            placeholder="상태"
            allowClear
            value={statusFilter}
            onChange={setStatusFilter}
            style={{ width: 130 }}
            options={Object.entries(STATUS_MAP).map(([k, v]) => ({ value: k, label: v.label }))}
          />
          {hasRole('cpo', 'security_officer') && (
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
              조치 등록
            </Button>
          )}
        </Space>
      </div>

      <Table
        columns={columns}
        dataSource={filteredData}
        rowKey="id"
        loading={loading}
        size="middle"
        pagination={{ pageSize: 20, showTotal: (t) => `총 ${t}건` }}
        onRow={(r) => ({ onClick: () => setSelected(r), style: { cursor: 'pointer' } })}
      />

      <Drawer title={selected?.title} open={!!selected} onClose={() => setSelected(null)} width={480}>
        {selected && (
          <div>
            <Descriptions column={1} bordered size="small">
              {selected.isms_item_id && (
                <Descriptions.Item label="관련 ISMS-P 항목">
                  <Tag color="blue">{getItemName(selected.isms_item_id)}</Tag>
                </Descriptions.Item>
              )}
              <Descriptions.Item label="출처">{SOURCE_MAP[selected.source] || selected.source}</Descriptions.Item>
              <Descriptions.Item label="출처 상세">{selected.source_detail || '-'}</Descriptions.Item>
              <Descriptions.Item label="상태">
                <Tag color={STATUS_MAP[selected.status]?.color}>{STATUS_MAP[selected.status]?.label}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="설명">{selected.description}</Descriptions.Item>
              <Descriptions.Item label="기한">
                {dayjs(selected.due_date).format('YYYY-MM-DD')} {getDDay(selected.due_date)}
              </Descriptions.Item>
              {selected.result && <Descriptions.Item label="조치 결과">{selected.result}</Descriptions.Item>}
              {selected.completed_at && (
                <Descriptions.Item label="완료일">
                  {dayjs(selected.completed_at).format('YYYY-MM-DD HH:mm')}
                </Descriptions.Item>
              )}
            </Descriptions>
            <Space style={{ marginTop: 16 }}>
              {(selected.status === 'open' || selected.status === 'in_progress') && (
                <Button type="primary" onClick={() => setCompleteOpen(true)}>
                  조치 완료
                </Button>
              )}
              {selected.status === 'completed' && hasRole('cpo', 'security_officer') && (
                <Button type="primary" onClick={() => handleVerify(selected.id)}>
                  검증 완료
                </Button>
              )}
            </Space>
          </div>
        )}
      </Drawer>

      <Modal
        title="시정조치 등록"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        footer={null}
        destroyOnClose
        width={560}
      >
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          <Form.Item name="isms_item_id" label="관련 ISMS-P 항목">
            <Select
              placeholder="항목 선택 (선택사항)"
              options={itemOptions}
              allowClear
              showSearch
              filterOption={(input, opt) => (opt?.label ?? '').toLowerCase().includes(input.toLowerCase())}
            />
          </Form.Item>
          <Form.Item name="title" label="제목" rules={[{ required: true, message: '제목을 입력하세요' }]}>
            <Input placeholder="시정조치 제목" />
          </Form.Item>
          <Form.Item name="source" label="출처" rules={[{ required: true }]} initialValue="internal_review">
            <Select options={Object.entries(SOURCE_MAP).map(([k, v]) => ({ value: k, label: v }))} />
          </Form.Item>
          <Form.Item name="source_detail" label="출처 상세">
            <Input placeholder="예: 2026년 1차 내부 점검, Prowler 스캔 #3" />
          </Form.Item>
          <Form.Item name="description" label="설명" rules={[{ required: true, message: '설명을 입력하세요' }]}>
            <Input.TextArea rows={3} placeholder="발견된 문제점 및 조치 필요 사항" />
          </Form.Item>
          <Form.Item name="action_plan" label="조치 계획">
            <Input.TextArea rows={2} placeholder="예정된 조치 방안" />
          </Form.Item>
          <Form.Item name="due_date" label="조치 기한" rules={[{ required: true, message: '기한을 선택하세요' }]}>
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block>
              등록
            </Button>
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="조치 완료"
        open={completeOpen}
        onCancel={() => setCompleteOpen(false)}
        footer={null}
        destroyOnClose
        width={520}
      >
        <Form form={completeForm} layout="vertical" onFinish={handleComplete}>
          <Form.Item name="result" label="조치 결과" rules={[{ required: true, message: '조치 결과를 입력하세요' }]}>
            <Input.TextArea rows={3} placeholder="수행한 조치 내용과 결과" />
          </Form.Item>
          <Form.Item label="증적 첨부 (선택)">
            <Form.Item name="evidenceTitle" noStyle>
              <Input placeholder="증적 제목 (미입력 시 자동 생성)" style={{ marginBottom: 8 }} />
            </Form.Item>
            <Form.Item name="file" noStyle>
              <Upload beforeUpload={() => false} maxCount={1}>
                <Button icon={<UploadOutlined />}>조치 증적 파일 선택</Button>
              </Upload>
            </Form.Item>
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block>
              완료 처리
            </Button>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
