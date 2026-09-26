import { useEffect, useState } from 'react';
import {
  Table,
  Button,
  Modal,
  Form,
  Input,
  DatePicker,
  Space,
  Tag,
  Typography,
  Drawer,
  Descriptions,
  message,
  Popconfirm,
  Select,
  Progress,
} from 'antd';
import { PlusOutlined, PlayCircleOutlined, CheckCircleOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import {
  assessmentsApi,
  type Assessment,
  type AssessmentStatus,
  type AuditType,
  type ScopeMode,
} from '../../api/assessments';
import { ismsApi } from '../../api/isms';
import { usePermission } from '../../hooks/usePermission';

const STATUS_MAP: Record<AssessmentStatus, { color: string; label: string }> = {
  draft: { color: 'default', label: '준비' },
  active: { color: 'processing', label: '진행중' },
  closed: { color: 'success', label: '종료' },
};

const AUDIT_TYPE_MAP: Record<AuditType, { color: string; label: string }> = {
  initial: { color: 'geekblue', label: '최초' },
  surveillance: { color: 'gold', label: '사후' },
  renewal: { color: 'purple', label: '갱신' },
};

const SCOPE_MODE_MAP: Record<ScopeMode, string> = {
  all_items: '전체 (101개)',
  subset: '샘플링',
};

export default function AssessmentList() {
  const [rows, setRows] = useState<Assessment[]>([]);
  const [loading, setLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [selected, setSelected] = useState<Assessment | null>(null);
  const [scopeRows, setScopeRows] = useState<any[]>([]);
  const [scopeLoading, setScopeLoading] = useState(false);
  const [allItems, setAllItems] = useState<any[]>([]);
  const [createForm] = Form.useForm();
  const [editForm] = Form.useForm();
  const { hasRole } = usePermission();
  const canWrite = hasRole('cpo', 'security_officer');
  const canDelete = hasRole('cpo');

  // Watch the create form's scope_mode so we can show/hide the sample picker.
  const [createScopeMode, setCreateScopeMode] = useState<ScopeMode>('all_items');
  const [createAuditType, setCreateAuditType] = useState<AuditType>('initial');

  const load = () => {
    setLoading(true);
    assessmentsApi
      .list()
      .then((r) => setRows(r.data))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    // Items needed for the subset picker; cheap once, cached for the page life.
    ismsApi
      .getItems({ size: 200 })
      .then((r) => {
        setAllItems(r.data.items || []);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!selected) {
      setScopeRows([]);
      return;
    }
    setScopeLoading(true);
    assessmentsApi
      .scope(selected.id)
      .then((r) => setScopeRows(r.data))
      .finally(() => setScopeLoading(false));
  }, [selected?.id]);

  const handleCreate = async (values: any) => {
    try {
      await assessmentsApi.create({
        code: values.code,
        name: values.name,
        framework: values.framework || 'kisa_isms_p_2023',
        audit_type: values.audit_type,
        scope_mode: values.scope_mode,
        parent_assessment_id: values.parent_assessment_id || null,
        period_start: values.period[0].format('YYYY-MM-DD'),
        period_end: values.period[1].format('YYYY-MM-DD'),
        scope_note: values.scope_note,
        scope_item_codes: values.scope_mode === 'subset' ? values.scope_item_codes || [] : undefined,
      });
      message.success('평가 세션이 생성되었습니다');
      setCreateOpen(false);
      createForm.resetFields();
      setCreateScopeMode('all_items');
      setCreateAuditType('initial');
      load();
    } catch (err: any) {
      message.error(err.response?.data?.detail || '생성 실패');
    }
  };

  const handleEdit = async (values: any) => {
    if (!selected) return;
    try {
      await assessmentsApi.update(selected.id, {
        name: values.name,
        period_start: values.period[0].format('YYYY-MM-DD'),
        period_end: values.period[1].format('YYYY-MM-DD'),
        scope_note: values.scope_note,
      });
      message.success('수정되었습니다');
      setEditOpen(false);
      editForm.resetFields();
      load();
      const fresh = await assessmentsApi.get(selected.id);
      setSelected(fresh.data);
    } catch (err: any) {
      message.error(err.response?.data?.detail || '수정 실패');
    }
  };

  const handleTransition = async (a: Assessment, target: 'active' | 'closed') => {
    try {
      const res = await assessmentsApi.transition(a.id, target);
      message.success(`${STATUS_MAP[target].label} 상태로 전이되었습니다`);
      setSelected(res.data);
      load();
    } catch (err: any) {
      message.error(err.response?.data?.detail || '상태 전이 실패');
    }
  };

  const handleDelete = async (a: Assessment) => {
    try {
      await assessmentsApi.delete(a.id);
      message.success('삭제되었습니다');
      setSelected(null);
      load();
    } catch (err: any) {
      message.error(err.response?.data?.detail || '삭제 실패');
    }
  };

  const openEdit = () => {
    if (!selected) return;
    editForm.setFieldsValue({
      name: selected.name,
      period: [dayjs(selected.period_start), dayjs(selected.period_end)],
      scope_note: selected.scope_note || '',
    });
    setEditOpen(true);
  };

  const itemOptions = allItems.map((it) => ({
    value: it.code,
    label: `${it.code} · ${it.name}`,
  }));

  // Only initial/renewal rounds are plausible parents for a surveillance
  // round. Excluding draft/closed isn't strictly necessary — the server
  // only validates existence — but it keeps the dropdown usable.
  const parentOptions = rows
    .filter((r) => r.audit_type !== 'surveillance')
    .map((r) => ({
      value: r.id,
      label: `${AUDIT_TYPE_MAP[r.audit_type].label} · ${r.code} · ${r.name}`,
    }));

  const columns = [
    {
      title: '코드',
      dataIndex: 'code',
      width: 140,
      sorter: (a: Assessment, b: Assessment) => a.code.localeCompare(b.code),
    },
    { title: '이름', dataIndex: 'name', ellipsis: true },
    {
      title: '유형',
      dataIndex: 'audit_type',
      width: 80,
      render: (v: AuditType) => <Tag color={AUDIT_TYPE_MAP[v].color}>{AUDIT_TYPE_MAP[v].label}</Tag>,
    },
    {
      title: '범위',
      dataIndex: 'scope_mode',
      width: 130,
      render: (v: ScopeMode, r: Assessment) =>
        v === 'all_items' ? (
          <span style={{ fontSize: 12 }}>전체 ({r.scope_total})</span>
        ) : (
          <span style={{ fontSize: 12 }}>샘플 ({r.scope_total})</span>
        ),
    },
    {
      title: '진행률',
      width: 180,
      render: (_: any, r: Assessment) => {
        const pct = r.scope_total > 0 ? Math.round((r.assessed_count / r.scope_total) * 100) : 0;
        return <Progress percent={pct} size="small" format={() => `${r.assessed_count}/${r.scope_total}`} />;
      },
    },
    { title: '기간', width: 200, render: (_: any, r: Assessment) => `${r.period_start} ~ ${r.period_end}` },
    {
      title: '상태',
      dataIndex: 'status',
      width: 90,
      render: (v: AssessmentStatus) => <Tag color={STATUS_MAP[v].color}>{STATUS_MAP[v].label}</Tag>,
    },
  ];

  const scopeColumns = [
    { title: '코드', dataIndex: 'code', width: 90 },
    { title: '항목명', dataIndex: 'name', ellipsis: true },
    {
      title: '평가',
      dataIndex: 'assessed',
      width: 80,
      render: (v: boolean) => (v ? <Tag color="success">완료</Tag> : <Tag color="default">미평가</Tag>),
    },
    {
      title: '샘플',
      dataIndex: 'is_sample',
      width: 70,
      render: (v: boolean) => (v ? <Tag color="gold">샘플</Tag> : null),
    },
  ];

  const assessedItemIds = new Set(scopeRows.filter((r) => r.assessed).map((r) => r.item_id));
  const scopeItemIds = new Set(scopeRows.map((r) => r.item_id));

  return (
    <div>
      <Typography.Title level={4} style={{ margin: 0, marginBottom: 16 }}>
        평가 세션
      </Typography.Title>
      <Space style={{ marginBottom: 16 }}>
        {canWrite && (
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
            평가 세션 생성
          </Button>
        )}
      </Space>
      <Typography.Paragraph type="secondary" style={{ marginTop: -8, marginBottom: 16, fontSize: 13 }}>
        ISMS-P 심사 유형 — <Tag color="geekblue">최초</Tag> 전체 101개, <Tag color="gold">사후</Tag> 매년 샘플링,
        <Tag color="purple" style={{ marginLeft: 4 }}>
          갱신
        </Tag>{' '}
        3년마다 전체. 진행중 세션은 화면 상단 헤더에서 선택할 수 있으며, 선택하면 모든 평가 기록이 해당 세션에 자동
        연결됩니다.
      </Typography.Paragraph>

      <Table
        dataSource={rows}
        columns={columns}
        rowKey="id"
        loading={loading}
        size="middle"
        pagination={{ pageSize: 20, showTotal: (t) => `총 ${t}건` }}
        onRow={(r) => ({ onClick: () => setSelected(r), style: { cursor: 'pointer' } })}
      />

      <Drawer title={selected?.name} open={!!selected} onClose={() => setSelected(null)} width={640}>
        {selected && (
          <div>
            <Descriptions column={1} bordered size="small">
              <Descriptions.Item label="코드">{selected.code}</Descriptions.Item>
              <Descriptions.Item label="유형">
                <Tag color={AUDIT_TYPE_MAP[selected.audit_type].color}>{AUDIT_TYPE_MAP[selected.audit_type].label}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="범위 모드">{SCOPE_MODE_MAP[selected.scope_mode]}</Descriptions.Item>
              <Descriptions.Item label="상태">
                <Tag color={STATUS_MAP[selected.status].color}>{STATUS_MAP[selected.status].label}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="상위 심사">
                {selected.parent_assessment_id
                  ? rows.find((r) => r.id === selected.parent_assessment_id)?.code ||
                    `#${selected.parent_assessment_id}`
                  : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="기간">
                {selected.period_start} ~ {selected.period_end}
              </Descriptions.Item>
              <Descriptions.Item label="프레임워크">{selected.framework}</Descriptions.Item>
              <Descriptions.Item label="범위/메모">{selected.scope_note || '-'}</Descriptions.Item>
              <Descriptions.Item label="진행률">
                <Progress
                  percent={
                    selected.scope_total > 0 ? Math.round((selected.assessed_count / selected.scope_total) * 100) : 0
                  }
                  size="small"
                  format={() => `${selected.assessed_count}/${selected.scope_total}`}
                />
              </Descriptions.Item>
              <Descriptions.Item label="생성/종료">
                {selected.created_at ? dayjs(selected.created_at).format('YYYY-MM-DD HH:mm') : '-'}
                {selected.closed_at && <> · 종료 {dayjs(selected.closed_at).format('YYYY-MM-DD HH:mm')}</>}
              </Descriptions.Item>
            </Descriptions>

            <Space style={{ marginTop: 16 }} wrap>
              {canWrite && selected.status !== 'closed' && (
                <Button icon={<EditOutlined />} onClick={openEdit}>
                  수정
                </Button>
              )}
              {canWrite && selected.status === 'draft' && (
                <Popconfirm title="진행중 상태로 전이할까요?" onConfirm={() => handleTransition(selected, 'active')}>
                  <Button type="primary" icon={<PlayCircleOutlined />}>
                    진행 시작
                  </Button>
                </Popconfirm>
              )}
              {canWrite && selected.status === 'active' && (
                <Popconfirm
                  title="종료하시겠어요?"
                  description="종료된 세션에는 더 이상 평가를 기록할 수 없습니다."
                  onConfirm={() => handleTransition(selected, 'closed')}
                >
                  <Button icon={<CheckCircleOutlined />}>세션 종료</Button>
                </Popconfirm>
              )}
              {canDelete && selected.status === 'draft' && (
                <Popconfirm title="삭제하시겠어요?" onConfirm={() => handleDelete(selected)}>
                  <Button danger icon={<DeleteOutlined />}>
                    삭제
                  </Button>
                </Popconfirm>
              )}
            </Space>

            <Typography.Title level={5} style={{ marginTop: 24 }}>
              범위 항목 ({scopeRows.length})
              {scopeRows.length > 0 && (
                <Typography.Text type="secondary" style={{ fontSize: 12, marginLeft: 8 }}>
                  평가 완료 {assessedItemIds.size}개
                </Typography.Text>
              )}
            </Typography.Title>

            {canWrite && selected.status !== 'closed' && (
              <Space style={{ marginBottom: 12 }}>
                <Select
                  mode="multiple"
                  style={{ minWidth: 320 }}
                  placeholder="항목 추가"
                  options={itemOptions.filter((o) => !scopeItemIds.has(allItems.find((it) => it.code === o.value)?.id))}
                  showSearch
                  filterOption={(input, option) =>
                    (option?.label as string).toLowerCase().includes(input.toLowerCase())
                  }
                  onChange={async (codes: string[]) => {
                    if (codes.length === 0) return;
                    try {
                      await assessmentsApi.updateScope(selected.id, { add_item_codes: codes });
                      message.success(`${codes.length}개 항목을 범위에 추가했습니다`);
                      const s = await assessmentsApi.scope(selected.id);
                      setScopeRows(s.data);
                      load();
                    } catch (err: any) {
                      message.error(err.response?.data?.detail || '추가 실패');
                    }
                  }}
                  value={[]}
                  maxTagCount={0}
                />
              </Space>
            )}

            <Table
              dataSource={scopeRows}
              columns={scopeColumns}
              rowKey="item_id"
              size="small"
              loading={scopeLoading}
              pagination={{ pageSize: 15 }}
            />
          </div>
        )}
      </Drawer>

      <Modal
        title="평가 세션 생성"
        open={createOpen}
        onCancel={() => {
          setCreateOpen(false);
          setCreateScopeMode('all_items');
          setCreateAuditType('initial');
        }}
        footer={null}
        destroyOnClose
        width={640}
      >
        <Form
          form={createForm}
          layout="vertical"
          onFinish={handleCreate}
          initialValues={{ audit_type: 'initial', scope_mode: 'all_items', framework: 'kisa_isms_p_2023' }}
        >
          <Space size="middle" style={{ display: 'flex' }}>
            <Form.Item
              name="code"
              label="코드 (고유)"
              rules={[{ required: true, message: '코드를 입력하세요' }]}
              style={{ flex: 1 }}
              help="예: A-2026-INIT, A-2027-S1"
            >
              <Input placeholder="A-2026-INIT" />
            </Form.Item>
            <Form.Item name="audit_type" label="심사 유형" style={{ flex: 1 }}>
              <Select
                onChange={(v: AuditType) => {
                  setCreateAuditType(v);
                  if (v === 'surveillance') {
                    createForm.setFieldsValue({ scope_mode: 'subset' });
                    setCreateScopeMode('subset');
                  } else {
                    createForm.setFieldsValue({ scope_mode: 'all_items' });
                    setCreateScopeMode('all_items');
                  }
                }}
                options={[
                  { value: 'initial', label: '최초 심사 (전체 평가)' },
                  { value: 'surveillance', label: '사후 심사 (샘플링)' },
                  { value: 'renewal', label: '갱신 심사 (전체 재평가)' },
                ]}
              />
            </Form.Item>
          </Space>
          <Form.Item name="name" label="이름" rules={[{ required: true }]}>
            <Input placeholder="2026 최초 심사" />
          </Form.Item>
          {createAuditType !== 'initial' && (
            <Form.Item
              name="parent_assessment_id"
              label="상위 심사 (선택)"
              help="사후/갱신 심사는 어떤 최초/갱신 심사의 연장인지 지정하세요"
            >
              <Select
                options={parentOptions}
                allowClear
                showSearch
                filterOption={(input, option) => (option?.label as string).toLowerCase().includes(input.toLowerCase())}
              />
            </Form.Item>
          )}
          <Form.Item name="scope_mode" label="범위 모드">
            <Select
              onChange={(v: ScopeMode) => setCreateScopeMode(v)}
              options={[
                { value: 'all_items', label: '전체 (101개 자동 시드)' },
                { value: 'subset', label: '샘플링 (선택한 항목만)' },
              ]}
            />
          </Form.Item>
          {createScopeMode === 'subset' && (
            <Form.Item
              name="scope_item_codes"
              label="샘플 항목 선택"
              rules={[{ required: true, message: '샘플 항목을 선택하세요' }]}
            >
              <Select
                mode="multiple"
                placeholder="도메인 또는 항목 검색"
                options={itemOptions}
                showSearch
                filterOption={(input, option) => (option?.label as string).toLowerCase().includes(input.toLowerCase())}
                maxTagCount={6}
              />
            </Form.Item>
          )}
          <Form.Item name="period" label="심사 기간" rules={[{ required: true }]}>
            <DatePicker.RangePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="framework" label="프레임워크">
            <Input />
          </Form.Item>
          <Form.Item name="scope_note" label="범위/메모">
            <Input.TextArea rows={3} placeholder="예: 전사 AWS 계정 (ap-northeast-2, us-east-1)" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block>
              생성
            </Button>
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="평가 세션 수정"
        open={editOpen}
        onCancel={() => setEditOpen(false)}
        footer={null}
        destroyOnClose
        width={540}
      >
        <Form form={editForm} layout="vertical" onFinish={handleEdit}>
          <Form.Item name="name" label="이름" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="period" label="심사 기간" rules={[{ required: true }]}>
            <DatePicker.RangePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="scope_note" label="범위/메모">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block>
              저장
            </Button>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
