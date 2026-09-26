import { useEffect, useState } from 'react';
import {
  Table,
  Select,
  Input,
  Tag,
  Space,
  Typography,
  Button,
  Drawer,
  Descriptions,
  message,
  Modal,
  Form,
  Upload,
  DatePicker,
  Collapse,
} from 'antd';
import {
  CheckOutlined,
  CloseOutlined,
  DownloadOutlined,
  UploadOutlined,
  LinkOutlined,
  EditOutlined,
  HistoryOutlined,
  PlusOutlined,
  ExportOutlined,
  FilterOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { evidenceApi } from '../../api/evidence';
import { ismsApi } from '../../api/isms';
import { reportsApi } from '../../api/reports';
import { usePermission } from '../../hooks/usePermission';

const STATUS_MAP: Record<string, { color: string; label: string }> = {
  draft: { color: 'default', label: '작성중' },
  submitted: { color: 'processing', label: '제출' },
  approved: { color: 'success', label: '승인' },
  rejected: { color: 'error', label: '반려' },
  expired: { color: 'warning', label: '만료' },
  replaced: { color: 'default', label: '대체됨' },
};

const TYPE_MAP: Record<string, string> = {
  document: '파일',
  external_link: '외부링크',
  prowler: 'Prowler',
  pipa_record: 'PIPA기록',
};

export default function EvidenceList() {
  const [data, setData] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<string>();
  const [search, setSearch] = useState('');
  // Advanced filter (Evidence Finder) — cross-filter by item prefix / multi-status /
  // multi-type / valid_to window / created window
  const [statusMulti, setStatusMulti] = useState<string[]>([]);
  const [typeMulti, setTypeMulti] = useState<string[]>([]);
  const [itemCodePrefix, setItemCodePrefix] = useState('');
  const [validToRange, setValidToRange] = useState<any>(null);
  const [createdRange, setCreatedRange] = useState<any>(null);
  const [selected, setSelected] = useState<any>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [linkOpen, setLinkOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [versionOpen, setVersionOpen] = useState(false);
  const [versions, setVersions] = useState<any[]>([]);
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [newVersionOpen, setNewVersionOpen] = useState(false);
  const [newVersionUploading, setNewVersionUploading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportJobId, setExportJobId] = useState<number | null>(null);
  // P1-4 curation: rows the user has ticked to include in a custom package
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [curatedGenerating, setCuratedGenerating] = useState(false);
  const { canWrite, hasRole } = usePermission();
  const [uploadForm] = Form.useForm();
  const [linkForm] = Form.useForm();
  const [editForm] = Form.useForm();
  const [newVersionForm] = Form.useForm();

  // ISMS-P items for selector
  const [allItems, setAllItems] = useState<any[]>([]);

  useEffect(() => {
    // Load all ISMS-P items for the multi-select
    ismsApi
      .getItems({ size: 200 })
      .then((r) => {
        setAllItems(r.data.items || []);
      })
      .catch(() => {});
  }, []);

  const load = () => {
    setLoading(true);
    // Advanced filters take precedence when set. The simple `status` select
    // above still works for one-click status filtering.
    const params: Record<string, any> = { page, size: 20 };
    if (search) params.search = search;
    if (statusMulti.length > 0) params.status = statusMulti.join(',');
    else if (status) params.status = status;
    if (typeMulti.length > 0) params.evidence_type = typeMulti.join(',');
    if (itemCodePrefix.trim()) params.item_code_prefix = itemCodePrefix.trim();
    if (validToRange?.[0]) params.valid_to_from = validToRange[0].format('YYYY-MM-DD');
    if (validToRange?.[1]) params.valid_to_to = validToRange[1].format('YYYY-MM-DD');
    if (createdRange?.[0]) params.created_from = createdRange[0].format('YYYY-MM-DD');
    if (createdRange?.[1]) params.created_to = createdRange[1].format('YYYY-MM-DD');
    evidenceApi
      .list(params)
      .then((r) => {
        setData(r.data.items);
        setTotal(r.data.total);
      })
      .finally(() => setLoading(false));
  };

  useEffect(load, [status, search, page, statusMulti, typeMulti, itemCodePrefix, validToRange, createdRange]);

  const resetAdvancedFilters = () => {
    setStatusMulti([]);
    setTypeMulti([]);
    setItemCodePrefix('');
    setValidToRange(null);
    setCreatedRange(null);
    setPage(1);
  };
  const advancedActive =
    statusMulti.length > 0 ||
    typeMulti.length > 0 ||
    itemCodePrefix.trim() !== '' ||
    !!validToRange?.[0] ||
    !!validToRange?.[1] ||
    !!createdRange?.[0] ||
    !!createdRange?.[1];

  const handleUpload = async (values: any) => {
    const formData = new FormData();
    formData.append('file', values.file.file);
    formData.append('title', values.title);
    if (values.description) formData.append('description', values.description);
    if (values.valid_from) formData.append('valid_from', values.valid_from.format('YYYY-MM-DD'));
    if (values.valid_to) formData.append('valid_to', values.valid_to.format('YYYY-MM-DD'));

    setUploading(true);
    try {
      const res = await evidenceApi.upload(formData);
      // Link to selected ISMS-P items
      if (values.item_codes?.length > 0) {
        await evidenceApi.linkItems(res.data.id, { item_codes: values.item_codes });
      }
      message.success(
        '증적이 업로드되었습니다' + (values.item_codes?.length ? ` (${values.item_codes.length}개 항목 연결)` : ''),
      );
      setUploadOpen(false);
      uploadForm.resetFields();
      load();
    } catch (err: any) {
      message.error(err.response?.data?.detail || '업로드 실패');
    } finally {
      setUploading(false);
    }
  };

  const handleLink = async (values: any) => {
    try {
      const res = await evidenceApi.createExternalLink({
        title: values.title,
        external_url: values.url,
        description: values.description,
        valid_to: values.valid_to?.format('YYYY-MM-DD'),
      });
      if (values.item_codes?.length > 0) {
        await evidenceApi.linkItems(res.data.id, { item_codes: values.item_codes });
      }
      message.success(
        '외부 링크가 등록되었습니다' + (values.item_codes?.length ? ` (${values.item_codes.length}개 항목 연결)` : ''),
      );
      setLinkOpen(false);
      linkForm.resetFields();
      load();
    } catch (err: any) {
      message.error(err.response?.data?.detail || '등록 실패');
    }
  };

  const handleEdit = async (values: any) => {
    if (!selected) return;
    try {
      await evidenceApi.update(selected.id, {
        title: values.title,
        description: values.description || null,
        valid_from: values.valid_from?.format('YYYY-MM-DD') || null,
        valid_to: values.valid_to?.format('YYYY-MM-DD') || null,
      });
      message.success('증적이 수정되었습니다');
      setEditOpen(false);
      editForm.resetFields();
      load();
      setSelected(null);
    } catch (err: any) {
      message.error(err.response?.data?.detail || '수정 실패');
    }
  };

  const openEdit = () => {
    if (!selected) return;
    editForm.setFieldsValue({
      title: selected.title,
      description: selected.description,
      valid_from: selected.valid_from ? dayjs(selected.valid_from) : null,
      valid_to: selected.valid_to ? dayjs(selected.valid_to) : null,
    });
    setEditOpen(true);
  };

  const handleGenerateCurated = async () => {
    if (selectedIds.length === 0) return;
    // Modal prompt for period — default to this year
    Modal.confirm({
      title: '선택 증적으로 패키지 생성',
      content: (
        <div>
          <p>
            선택된 증적 <b>{selectedIds.length}개</b>로 증적 패키지를 생성합니다.
          </p>
          <p style={{ fontSize: 12, color: '#94a3b8', marginTop: 8 }}>
            기간은 올해 전체로 기록됩니다. 생성이 완료되면 <b>보고서 관리</b> 페이지에서 다운로드할 수 있어요.
          </p>
        </div>
      ),
      okText: '생성',
      cancelText: '취소',
      onOk: async () => {
        setCuratedGenerating(true);
        try {
          const year = dayjs().year();
          const periodStart = `${year}-01-01`;
          const periodEnd = `${year}-12-31`;
          await reportsApi.generateEvidencePackage(periodStart, periodEnd, undefined, 'approved', {
            include_evidence_ids: selectedIds,
          });
          message.success(
            `${selectedIds.length}개 증적으로 패키지 생성을 시작했습니다. 보고서 관리에서 진행 상황을 확인하세요.`,
          );
          setSelectedIds([]);
        } catch (err: any) {
          message.error(err.response?.data?.detail || '패키지 생성 요청 실패');
        } finally {
          setCuratedGenerating(false);
        }
      },
    });
  };

  const handleExport = async () => {
    setExporting(true);
    try {
      const res = await evidenceApi.exportPackage(status);
      setExportJobId(res.data.job_id);
      message.info('증적 패키지 내보내기가 시작되었습니다');
      // Poll for completion
      const poll = setInterval(async () => {
        try {
          const job = await evidenceApi.getExportJob(res.data.job_id);
          if (job.data.status === 'completed') {
            clearInterval(poll);
            setExporting(false);
            setExportJobId(null);
            if (job.data.download_url) {
              window.open(job.data.download_url, '_blank');
              message.success('증적 패키지 다운로드가 시작됩니다');
            }
          } else if (job.data.status === 'failed') {
            clearInterval(poll);
            setExporting(false);
            setExportJobId(null);
            message.error(job.data.error || '내보내기에 실패했습니다');
          }
        } catch {
          clearInterval(poll);
          setExporting(false);
          setExportJobId(null);
        }
      }, 2000);
    } catch (err: any) {
      setExporting(false);
      message.error(err.response?.data?.detail || '내보내기 실패');
    }
  };

  const loadVersions = async (id: number) => {
    setVersionsLoading(true);
    try {
      const res = await evidenceApi.versions(id);
      setVersions(res.data.versions || []);
      setVersionOpen(true);
    } catch {
      message.error('버전 이력 조회 실패');
    } finally {
      setVersionsLoading(false);
    }
  };

  const handleNewVersion = async (values: any) => {
    if (!selected) return;
    const formData = new FormData();
    formData.append('file', values.file.file);
    formData.append('title', values.title);
    if (values.description) formData.append('description', values.description);
    if (values.valid_from) formData.append('valid_from', values.valid_from.format('YYYY-MM-DD'));
    if (values.valid_to) formData.append('valid_to', values.valid_to.format('YYYY-MM-DD'));
    setNewVersionUploading(true);
    try {
      await evidenceApi.newVersion(selected.id, formData);
      message.success('새 버전이 등록되었습니다 (이전 버전은 대체됨 처리)');
      setNewVersionOpen(false);
      newVersionForm.resetFields();
      setSelected(null);
      load();
    } catch (err: any) {
      message.error(err.response?.data?.detail || '새 버전 업로드 실패');
    } finally {
      setNewVersionUploading(false);
    }
  };

  const handleSubmit = async (id: number) => {
    const res = await evidenceApi.submit(id);
    message.success(res.data.message);
    if (res.data.warning) message.warning(res.data.warning);
    load();
    setSelected(null);
  };

  const handleReview = async (id: number, action: string) => {
    const comment = action === 'reject' ? prompt('거부 사유를 입력하세요:') : undefined;
    if (action === 'reject' && !comment) return;
    const res = await evidenceApi.review(id, { action, comment: comment || undefined });
    message.success(res.data.message);
    load();
    setSelected(null);
  };

  const handleDownload = async (id: number) => {
    try {
      await evidenceApi.downloadFile(id);
    } catch {
      message.error('다운로드 실패');
    }
  };

  const itemSelectOptions = allItems.map((it) => ({
    value: it.code,
    label: `${it.code} ${it.name}`,
  }));

  const columns = [
    { title: 'ID', dataIndex: 'id', width: 50, sorter: (a: any, b: any) => a.id - b.id },
    {
      title: '제목',
      dataIndex: 'title',
      ellipsis: true,
      sorter: (a: any, b: any) => (a.title || '').localeCompare(b.title || ''),
    },
    {
      title: '연결 항목',
      dataIndex: 'linked_items',
      width: 130,
      render: (items: string[]) =>
        items?.length > 0 ? (
          <Space size={2} wrap>
            {items.map((c: string) => (
              <Tag key={c} color="blue" style={{ fontSize: 11, padding: '0 4px' }}>
                {c}
              </Tag>
            ))}
          </Space>
        ) : (
          <Typography.Text type="secondary" style={{ fontSize: 11 }}>
            미연결
          </Typography.Text>
        ),
    },
    {
      title: '유형',
      dataIndex: 'evidence_type',
      width: 80,
      sorter: (a: any, b: any) => (a.evidence_type || '').localeCompare(b.evidence_type || ''),
      render: (v: string) => TYPE_MAP[v] || v,
    },
    {
      title: '상태',
      dataIndex: 'status',
      width: 80,
      sorter: (a: any, b: any) => (a.status || '').localeCompare(b.status || ''),
      render: (v: string) => {
        const s = STATUS_MAP[v];
        return s ? <Tag color={s.color}>{s.label}</Tag> : v;
      },
    },
    {
      title: '유효기간',
      dataIndex: 'valid_to',
      width: 110,
      sorter: (a: any, b: any) => (a.valid_to || '9999').localeCompare(b.valid_to || '9999'),
      render: (v: string) => v || '무기한',
    },
    { title: '버전', dataIndex: 'version', width: 60, sorter: (a: any, b: any) => (a.version || 0) - (b.version || 0) },
    {
      title: '',
      width: 50,
      render: (_: any, r: any) =>
        r.evidence_type === 'document' || r.file_name ? (
          <Button
            size="small"
            type="text"
            icon={<DownloadOutlined />}
            onClick={(e) => {
              e.stopPropagation();
              handleDownload(r.id);
            }}
          />
        ) : r.external_url ? (
          <Button
            size="small"
            type="text"
            icon={<LinkOutlined />}
            onClick={(e) => {
              e.stopPropagation();
              window.open(r.external_url, '_blank');
            }}
          />
        ) : null,
    },
  ];

  return (
    <div>
      <Typography.Title level={4} style={{ margin: 0, marginBottom: 16 }}>
        증적 관리
      </Typography.Title>
      <Space style={{ marginBottom: 16 }} wrap>
        <Select
          placeholder="상태"
          allowClear
          value={status}
          onChange={setStatus}
          style={{ width: 120 }}
          options={Object.entries(STATUS_MAP).map(([k, v]) => ({ value: k, label: v.label }))}
        />
        <Input.Search placeholder="검색..." onSearch={setSearch} allowClear style={{ width: 250 }} />
        {canWrite && (
          <>
            <Button type="primary" icon={<UploadOutlined />} onClick={() => setUploadOpen(true)}>
              파일 업로드
            </Button>
            <Button icon={<LinkOutlined />} onClick={() => setLinkOpen(true)}>
              외부 링크
            </Button>
          </>
        )}
        {hasRole('cpo', 'security_officer', 'auditor') && (
          <Button icon={<ExportOutlined />} onClick={handleExport} loading={exporting}>
            {exporting ? '내보내기 중...' : '증적 내보내기'}
          </Button>
        )}
        {hasRole('cpo', 'security_officer') && (
          <Button
            type="primary"
            ghost
            icon={<ExportOutlined />}
            onClick={handleGenerateCurated}
            disabled={selectedIds.length === 0}
            loading={curatedGenerating}
          >
            선택 {selectedIds.length}개로 패키지 생성
          </Button>
        )}
      </Space>

      <Collapse
        size="small"
        style={{ marginBottom: 16 }}
        items={[
          {
            key: 'adv',
            label: (
              <Space>
                <FilterOutlined />
                <span>고급 필터 (항목 코드 · 다중 상태 · 유효기간 · 등록일)</span>
                {advancedActive && <Tag color="blue">활성</Tag>}
              </Space>
            ),
            children: (
              <Space size="middle" wrap align="start">
                <div>
                  <div style={{ fontSize: 12, marginBottom: 4 }}>항목 코드 시작</div>
                  <Input
                    placeholder="예: 2.7 → 2.7.1, 2.7.2, ..."
                    value={itemCodePrefix}
                    onChange={(e) => {
                      setItemCodePrefix(e.target.value);
                      setPage(1);
                    }}
                    style={{ width: 220 }}
                    allowClear
                  />
                </div>
                <div>
                  <div style={{ fontSize: 12, marginBottom: 4 }}>상태 (다중)</div>
                  <Select
                    mode="multiple"
                    placeholder="상태 선택"
                    value={statusMulti}
                    onChange={(v) => {
                      setStatusMulti(v);
                      setPage(1);
                    }}
                    style={{ minWidth: 240 }}
                    options={Object.entries(STATUS_MAP).map(([k, v]) => ({ value: k, label: v.label }))}
                    allowClear
                  />
                </div>
                <div>
                  <div style={{ fontSize: 12, marginBottom: 4 }}>유형 (다중)</div>
                  <Select
                    mode="multiple"
                    placeholder="유형 선택"
                    value={typeMulti}
                    onChange={(v) => {
                      setTypeMulti(v);
                      setPage(1);
                    }}
                    style={{ minWidth: 220 }}
                    options={Object.entries(TYPE_MAP).map(([k, v]) => ({ value: k, label: v }))}
                    allowClear
                  />
                </div>
                <div>
                  <div style={{ fontSize: 12, marginBottom: 4 }}>유효 종료일 범위</div>
                  <DatePicker.RangePicker
                    value={validToRange}
                    onChange={(v) => {
                      setValidToRange(v);
                      setPage(1);
                    }}
                    allowEmpty={[true, true]}
                  />
                </div>
                <div>
                  <div style={{ fontSize: 12, marginBottom: 4 }}>등록일 범위</div>
                  <DatePicker.RangePicker
                    value={createdRange}
                    onChange={(v) => {
                      setCreatedRange(v);
                      setPage(1);
                    }}
                    allowEmpty={[true, true]}
                  />
                </div>
                <div style={{ paddingTop: 22 }}>
                  <Button onClick={resetAdvancedFilters} disabled={!advancedActive}>
                    초기화
                  </Button>
                </div>
              </Space>
            ),
          },
        ]}
      />

      <Table
        dataSource={data}
        columns={columns}
        rowKey="id"
        loading={loading}
        size="middle"
        pagination={{ current: page, total, pageSize: 20, onChange: setPage, showTotal: (t) => `총 ${t}건` }}
        rowSelection={
          hasRole('cpo', 'security_officer')
            ? {
                selectedRowKeys: selectedIds,
                onChange: (keys) => setSelectedIds(keys as number[]),
                // Auditors and viewers shouldn't be able to trigger report generation,
                // so hide the checkbox column entirely for them.
                preserveSelectedRowKeys: true,
                getCheckboxProps: (r: any) => ({
                  // Only approved evidence is meaningful in a package submitted to auditors.
                  disabled: r.status !== 'approved',
                }),
              }
            : undefined
        }
        onRow={(r) => ({ onClick: () => setSelected(r), style: { cursor: 'pointer' } })}
      />

      {/* 상세 Drawer */}
      <Drawer title={selected?.title} open={!!selected} onClose={() => setSelected(null)} width={500}>
        {selected && (
          <div>
            <Descriptions column={1} bordered size="small">
              <Descriptions.Item label="상태">
                <Tag color={STATUS_MAP[selected.status]?.color}>{STATUS_MAP[selected.status]?.label}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="유형">{TYPE_MAP[selected.evidence_type]}</Descriptions.Item>
              <Descriptions.Item label="설명">{selected.description || '-'}</Descriptions.Item>
              <Descriptions.Item label="파일">{selected.file_name || '-'}</Descriptions.Item>
              <Descriptions.Item label="SHA-256">
                {selected.file_hash ? selected.file_hash.substring(0, 32) + '...' : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="유효기간">
                {selected.valid_from || '?'} ~ {selected.valid_to || '무기한'}
              </Descriptions.Item>
              <Descriptions.Item label="버전">{selected.version}</Descriptions.Item>
            </Descriptions>
            <Space style={{ marginTop: 16 }} wrap>
              {(selected.status === 'draft' || selected.status === 'rejected') && canWrite && (
                <Button icon={<EditOutlined />} onClick={openEdit}>
                  수정
                </Button>
              )}
              {selected.status === 'draft' && canWrite && (
                <Button type="primary" icon={<CheckOutlined />} onClick={() => handleSubmit(selected.id)}>
                  제출
                </Button>
              )}
              {selected.status === 'submitted' && hasRole('cpo', 'security_officer') && (
                <>
                  <Button type="primary" icon={<CheckOutlined />} onClick={() => handleReview(selected.id, 'approve')}>
                    승인
                  </Button>
                  <Button danger icon={<CloseOutlined />} onClick={() => handleReview(selected.id, 'reject')}>
                    반려
                  </Button>
                </>
              )}
              {(selected.evidence_type === 'document' || selected.file_name) && (
                <Button icon={<DownloadOutlined />} onClick={() => handleDownload(selected.id)}>
                  다운로드
                </Button>
              )}
              {selected.external_url && (
                <Button icon={<LinkOutlined />} onClick={() => window.open(selected.external_url, '_blank')}>
                  링크 열기
                </Button>
              )}
              {selected.evidence_type === 'document' && canWrite && (
                <Button icon={<PlusOutlined />} onClick={() => setNewVersionOpen(true)}>
                  새 버전
                </Button>
              )}
              <Button icon={<HistoryOutlined />} loading={versionsLoading} onClick={() => loadVersions(selected.id)}>
                버전 이력
              </Button>
            </Space>
          </div>
        )}
      </Drawer>

      {/* 파일 업로드 Modal */}
      <Modal
        title="증적 파일 업로드"
        open={uploadOpen}
        onCancel={() => setUploadOpen(false)}
        footer={null}
        destroyOnClose
        width={560}
      >
        <Form form={uploadForm} layout="vertical" onFinish={handleUpload}>
          <Form.Item name="title" label="제목" rules={[{ required: true, message: '제목을 입력하세요' }]}>
            <Input placeholder="증적 제목" />
          </Form.Item>
          <Form.Item name="item_codes" label="ISMS-P 연결 항목 (다중 선택 가능)">
            <Select
              mode="multiple"
              placeholder="항목을 선택하세요 (예: 1.1.1)"
              options={itemSelectOptions}
              showSearch
              filterOption={(input, option) => (option?.label ?? '').toLowerCase().includes(input.toLowerCase())}
              maxTagCount={3}
              allowClear
            />
          </Form.Item>
          <Form.Item name="description" label="설명">
            <Input.TextArea rows={2} placeholder="증적 설명" />
          </Form.Item>
          <Form.Item name="file" label="파일" rules={[{ required: true, message: '파일을 선택하세요' }]}>
            <Upload beforeUpload={() => false} maxCount={1}>
              <Button icon={<UploadOutlined />}>파일 선택</Button>
            </Upload>
          </Form.Item>
          <Space>
            <Form.Item name="valid_from" label="유효 시작일">
              <DatePicker />
            </Form.Item>
            <Form.Item name="valid_to" label="유효 종료일">
              <DatePicker />
            </Form.Item>
          </Space>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={uploading} block>
              업로드
            </Button>
          </Form.Item>
        </Form>
      </Modal>

      {/* 외부 링크 Modal */}
      <Modal
        title="외부 링크 증적 등록"
        open={linkOpen}
        onCancel={() => setLinkOpen(false)}
        footer={null}
        destroyOnClose
        width={560}
      >
        <Form form={linkForm} layout="vertical" onFinish={handleLink}>
          <Form.Item name="title" label="제목" rules={[{ required: true }]}>
            <Input placeholder="증적 제목" />
          </Form.Item>
          <Form.Item name="item_codes" label="ISMS-P 연결 항목 (다중 선택 가능)">
            <Select
              mode="multiple"
              placeholder="항목을 선택하세요 (예: 1.1.1)"
              options={itemSelectOptions}
              showSearch
              filterOption={(input, option) => (option?.label ?? '').toLowerCase().includes(input.toLowerCase())}
              maxTagCount={3}
              allowClear
            />
          </Form.Item>
          <Form.Item name="url" label="URL" rules={[{ required: true, type: 'url', message: 'URL을 입력하세요' }]}>
            <Input placeholder="https://..." />
          </Form.Item>
          <Form.Item name="description" label="설명">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="valid_to" label="유효 종료일">
            <DatePicker />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block>
              등록
            </Button>
          </Form.Item>
        </Form>
      </Modal>

      {/* 버전 이력 Modal */}
      <Modal
        title="버전 이력"
        open={versionOpen}
        onCancel={() => setVersionOpen(false)}
        footer={<Button onClick={() => setVersionOpen(false)}>닫기</Button>}
        width={600}
      >
        <Table
          dataSource={versions}
          rowKey="id"
          size="small"
          pagination={false}
          columns={[
            { title: '버전', dataIndex: 'version', width: 60, render: (v: number) => `v${v}` },
            { title: '제목', dataIndex: 'title', ellipsis: true },
            {
              title: '상태',
              dataIndex: 'status',
              width: 80,
              render: (v: string) => {
                const s = STATUS_MAP[v];
                return s ? <Tag color={s.color}>{s.label}</Tag> : v;
              },
            },
            { title: '파일', dataIndex: 'file_name', ellipsis: true, width: 150, render: (v: string) => v || '-' },
            {
              title: '등록일',
              dataIndex: 'created_at',
              width: 100,
              render: (v: string) => (v ? dayjs(v).format('YYYY-MM-DD') : '-'),
            },
          ]}
        />
      </Modal>

      {/* 새 버전 업로드 Modal */}
      <Modal
        title="새 버전 업로드"
        open={newVersionOpen}
        onCancel={() => setNewVersionOpen(false)}
        footer={null}
        destroyOnClose
        width={520}
      >
        <Form form={newVersionForm} layout="vertical" onFinish={handleNewVersion}>
          <Form.Item
            name="title"
            label="제목"
            rules={[{ required: true, message: '제목을 입력하세요' }]}
            initialValue={selected?.title ? `${selected.title} (v${(selected.version || 1) + 1})` : ''}
          >
            <Input placeholder="증적 제목" />
          </Form.Item>
          <Form.Item name="description" label="설명">
            <Input.TextArea rows={2} placeholder="변경 사항 등" />
          </Form.Item>
          <Form.Item name="file" label="파일" rules={[{ required: true, message: '파일을 선택하세요' }]}>
            <Upload beforeUpload={() => false} maxCount={1}>
              <Button icon={<UploadOutlined />}>파일 선택</Button>
            </Upload>
          </Form.Item>
          <Space>
            <Form.Item name="valid_from" label="유효 시작일">
              <DatePicker />
            </Form.Item>
            <Form.Item name="valid_to" label="유효 종료일">
              <DatePicker />
            </Form.Item>
          </Space>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={newVersionUploading} block>
              업로드
            </Button>
          </Form.Item>
        </Form>
      </Modal>

      {/* 수정 Modal */}
      <Modal
        title="증적 수정"
        open={editOpen}
        onCancel={() => setEditOpen(false)}
        footer={null}
        destroyOnClose
        width={520}
      >
        <Form form={editForm} layout="vertical" onFinish={handleEdit}>
          <Form.Item name="title" label="제목" rules={[{ required: true, message: '제목을 입력하세요' }]}>
            <Input placeholder="증적 제목" />
          </Form.Item>
          <Form.Item name="description" label="설명">
            <Input.TextArea rows={2} placeholder="증적 설명" />
          </Form.Item>
          <Space>
            <Form.Item name="valid_from" label="유효 시작일">
              <DatePicker />
            </Form.Item>
            <Form.Item name="valid_to" label="유효 종료일">
              <DatePicker />
            </Form.Item>
          </Space>
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
