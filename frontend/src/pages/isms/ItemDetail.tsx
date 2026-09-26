import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Tabs,
  Typography,
  Descriptions,
  Tag,
  Checkbox,
  Input,
  Button,
  Select,
  Space,
  Modal,
  message,
  Table,
  Form,
  Upload,
  DatePicker,
  Empty,
} from 'antd';
import {
  ArrowLeftOutlined,
  UploadOutlined,
  LinkOutlined,
  CheckOutlined,
  DownloadOutlined,
  UserAddOutlined,
  DeleteOutlined,
} from '@ant-design/icons';
import { ismsApi } from '../../api/isms';
import { evidenceApi } from '../../api/evidence';
import { prowlerApi } from '../../api/prowler';
import { usersApi } from '../../api/users';
import { assessmentsApi, type Assessment } from '../../api/assessments';
import { useCurrentAssessmentStore } from '../../store/currentAssessmentStore';
import { usePermission } from '../../hooks/usePermission';
import dayjs from 'dayjs';

const STATUS_MAP: Record<string, { color: string; label: string }> = {
  draft: { color: 'default', label: '작성중' },
  submitted: { color: 'processing', label: '제출' },
  approved: { color: 'success', label: '승인' },
  rejected: { color: 'error', label: '반려' },
  expired: { color: 'warning', label: '만료' },
};

const SEVERITY_COLOR: Record<string, string> = {
  critical: 'red',
  high: 'volcano',
  medium: 'orange',
  low: 'blue',
  informational: 'default',
};

export default function ItemDetail() {
  const { code } = useParams<{ code: string }>();
  const navigate = useNavigate();
  const { hasRole, canWrite } = usePermission();
  const [item, setItem] = useState<any>(null);
  const [checklists, setChecklists] = useState<any[]>([]);
  const [assessModal, setAssessModal] = useState(false);
  const [assessForm, setAssessForm] = useState<{
    status: string;
    notes: string;
    evidenceMode: string;
    existingEvidenceId?: number;
    newFile?: any;
    newTitle?: string;
  }>({ status: 'compliant', notes: '', evidenceMode: 'none' });
  const [activeAssessments, setActiveAssessments] = useState<Assessment[]>([]);
  // Which of those active assessments include this specific item?
  const [itemInScopeIds, setItemInScopeIds] = useState<Set<number>>(new Set());
  const currentAssessmentId = useCurrentAssessmentStore((s) => s.currentAssessmentId);
  const currentAssessment = activeAssessments.find((a) => a.id === currentAssessmentId);

  // Evidence state
  const [evidenceList, setEvidenceList] = useState<any[]>([]);
  const [evidenceTotal, setEvidenceTotal] = useState(0);
  const [evidencePage, setEvidencePage] = useState(1);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [linkOpen, setLinkOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadForm] = Form.useForm();
  const [linkForm] = Form.useForm();

  // Prowler state
  const [prowlerFindings, setProwlerFindings] = useState<any[]>([]);
  const [prowlerTotal, setProwlerTotal] = useState(0);

  // Compliance history (item-specific)
  const [compHistory, setCompHistory] = useState<any[]>([]);
  const [expandedRows, setExpandedRows] = useState<number[]>([]);

  // Assignment state
  const [assignments, setAssignments] = useState<any[]>([]);
  const [allUsers, setAllUsers] = useState<any[]>([]);
  const [assignUserId, setAssignUserId] = useState<number | undefined>();
  const [assignRole, setAssignRole] = useState('담당자');

  useEffect(() => {
    if (!code) return;
    ismsApi.getItem(code).then((res) => setItem(res.data));
  }, [code]);

  const loadChecklists = () => {
    if (!code) return;
    ismsApi.getChecklists(code).then((res) => setChecklists(res.data.checklists));
  };

  useEffect(loadChecklists, [code]);

  const loadEvidence = () => {
    if (!code) return;
    evidenceApi.list({ item_code: code, page: evidencePage, size: 20 }).then((r) => {
      setEvidenceList(r.data.items);
      setEvidenceTotal(r.data.total);
    });
  };

  useEffect(loadEvidence, [code, evidencePage]);

  useEffect(() => {
    if (!item?.id) return;
    prowlerApi
      .listScans({ size: 1 })
      .then((r) => {
        const scans = r.data.items || r.data;
        if (scans?.length > 0) {
          prowlerApi.getFindings(scans[0].id, { isms_item_id: item.id, size: 50 }).then((fr) => {
            setProwlerFindings(fr.data.items || []);
            setProwlerTotal(fr.data.total || 0);
          });
        }
      })
      .catch(() => {});
    if (code) {
      ismsApi
        .getComplianceHistory(code)
        .then((r) => {
          setCompHistory(r.data || []);
        })
        .catch(() => {});
    }
  }, [item?.id, code]);

  // Load assignments + users
  const loadAssignments = () => {
    if (!code) return;
    ismsApi
      .getAssignments(code)
      .then((r) => setAssignments(r.data || []))
      .catch(() => {});
  };
  useEffect(loadAssignments, [code]);
  // Load active assessments + figure out which ones include this item in
  // their scope. We do this per-page load so the "not in scope" banner is
  // accurate even after the user tweaks scope elsewhere.
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const r = await assessmentsApi.list();
        if (!alive) return;
        const active = r.data.filter((a) => a.status === 'active');
        setActiveAssessments(active);
        if (!item?.id) return;
        const in_ids = new Set<number>();
        await Promise.all(
          active.map(async (a) => {
            try {
              const s = await assessmentsApi.scope(a.id);
              if (s.data.some((row: any) => row.item_id === item.id)) in_ids.add(a.id);
            } catch {
              /* ignore */
            }
          }),
        );
        if (alive) setItemInScopeIds(in_ids);
      } catch {
        /* ignore */
      }
    })();
    return () => {
      alive = false;
    };
  }, [item?.id]);
  useEffect(() => {
    if (hasRole('cpo', 'security_officer')) {
      usersApi
        .list()
        .then((r) => setAllUsers(r.data?.items || r.data || []))
        .catch(() => {});
    }
  }, []);

  const handleAssign = async () => {
    if (!code || !assignUserId) return;
    try {
      await ismsApi.createAssignment(code, { user_id: assignUserId, role_in_item: assignRole });
      message.success('담당자가 배정되었습니다');
      setAssignUserId(undefined);
      loadAssignments();
    } catch (err: any) {
      message.error(err.response?.data?.detail || '배정 실패');
    }
  };

  const handleUnassign = async (userId: number) => {
    if (!code) return;
    try {
      await ismsApi.deleteAssignment(code, userId);
      message.success('담당자가 해제되었습니다');
      loadAssignments();
    } catch (err: any) {
      message.error(err.response?.data?.detail || '해제 실패');
    }
  };

  const handleCheckToggle = async (clId: number, checked: boolean) => {
    await ismsApi.respondChecklist(code!, clId, { is_checked: checked });
    loadChecklists();
  };

  const handleAssess = async () => {
    try {
      if (assessForm.evidenceMode === 'upload' && assessForm.newFile) {
        const formData = new FormData();
        formData.append('file', assessForm.newFile);
        formData.append('title', assessForm.newTitle || `${code} 평가 증적`);
        const evRes = await evidenceApi.upload(formData);
        await evidenceApi.linkItems(evRes.data.id, { item_codes: [code!] });
      }

      const res = await ismsApi.assessItem(code!, {
        status: assessForm.status,
        notes: assessForm.notes,
        // Attach to the header's "current assessment" by default. The user
        // can still clear it by switching the header to "상시 평가".
        assessment_id: currentAssessmentId ?? undefined,
      });
      message.success(res.data.message);
      if (res.data.warnings) res.data.warnings.forEach((w: string) => message.warning(w));

      setAssessModal(false);
      setAssessForm({ status: 'compliant', notes: '', evidenceMode: 'none' });
      loadEvidence();
      if (code) ismsApi.getComplianceHistory(code).then((r) => setCompHistory(r.data || []));
    } catch (err: any) {
      message.error(err.response?.data?.detail || '평가 실패');
    }
  };

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
      await evidenceApi.linkItems(res.data.id, { item_codes: [code!] });
      message.success(`증적이 업로드되고 ${code} 항목에 연결되었습니다`);
      setUploadOpen(false);
      uploadForm.resetFields();
      loadEvidence();
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
      await evidenceApi.linkItems(res.data.id, { item_codes: [code!] });
      message.success(`외부 링크가 등록되고 ${code} 항목에 연결되었습니다`);
      setLinkOpen(false);
      linkForm.resetFields();
      loadEvidence();
    } catch (err: any) {
      message.error(err.response?.data?.detail || '등록 실패');
    }
  };

  const handleDownload = async (id: number) => {
    try {
      await evidenceApi.downloadFile(id);
    } catch {
      message.error('다운로드 실패');
    }
  };

  if (!item) return null;

  const evidenceColumns = [
    { title: 'ID', dataIndex: 'id', width: 50 },
    { title: '제목', dataIndex: 'title', ellipsis: true },
    {
      title: '유형',
      dataIndex: 'evidence_type',
      width: 90,
      render: (v: string) => (v === 'document' ? '파일' : v === 'external_link' ? '링크' : v),
    },
    {
      title: '상태',
      dataIndex: 'status',
      width: 80,
      render: (v: string) => {
        const s = STATUS_MAP[v];
        return s ? <Tag color={s.color}>{s.label}</Tag> : v;
      },
    },
    { title: '유효기간', dataIndex: 'valid_to', width: 110, render: (v: string) => v || '무기한' },
    { title: '버전', dataIndex: 'version', width: 60 },
    {
      title: '',
      width: 40,
      render: (_: any, r: any) =>
        r.evidence_type === 'document' || r.file_name ? (
          <Button size="small" type="text" icon={<DownloadOutlined />} onClick={() => handleDownload(r.id)} />
        ) : null,
    },
  ];

  const prowlerColumns = [
    { title: 'Check', dataIndex: 'check_id', width: 160, ellipsis: true },
    { title: '제목', dataIndex: 'check_title', ellipsis: true },
    {
      title: '상태',
      dataIndex: 'status',
      width: 70,
      render: (v: string) => <Tag color={v === 'PASS' ? 'success' : v === 'FAIL' ? 'error' : 'default'}>{v}</Tag>,
    },
    {
      title: '심각도',
      dataIndex: 'severity',
      width: 90,
      render: (v: string) => <Tag color={SEVERITY_COLOR[v?.toLowerCase()] || 'default'}>{v}</Tag>,
    },
    { title: '리소스', dataIndex: 'resource_uid', ellipsis: true, width: 180 },
    {
      title: '조치',
      dataIndex: 'remediation_status',
      width: 80,
      render: (v: string) =>
        v === 'resolved' ? (
          <Tag color="success">완료</Tag>
        ) : v === 'in_progress' ? (
          <Tag color="processing">진행중</Tag>
        ) : (
          <Tag>미조치</Tag>
        ),
    },
  ];

  const tabItems = [
    {
      key: 'overview',
      label: '개요',
      children: (
        <Descriptions column={1} bordered size="small">
          <Descriptions.Item label="코드">{item.code}</Descriptions.Item>
          <Descriptions.Item label="항목명">{item.name}</Descriptions.Item>
          <Descriptions.Item label="설명">{item.description}</Descriptions.Item>
          <Descriptions.Item label="필요 증적">{item.required_evidence || '-'}</Descriptions.Item>
          <Descriptions.Item label="Prowler 체크">
            {item.has_prowler_checks ? `${item.prowler_check_count}개` : '-'}
          </Descriptions.Item>
          <Descriptions.Item label="Config 규칙">{item.has_config_rules ? '있음' : '-'}</Descriptions.Item>
        </Descriptions>
      ),
    },
    {
      key: 'checklist',
      label: `체크리스트 (${checklists.filter((c) => c.is_checked).length}/${checklists.length})`,
      children: (
        <div>
          {hasRole('cpo', 'security_officer') && (
            <Space style={{ marginBottom: 16 }}>
              <Button
                type="primary"
                onClick={() => {
                  const checked = checklists.filter((c) => c.is_checked).length;
                  const total = checklists.length;
                  const suggested =
                    total === 0
                      ? 'not_applicable'
                      : checked === total
                        ? 'compliant'
                        : checked > 0
                          ? 'partial'
                          : 'non_compliant';
                  setAssessForm({ status: suggested, notes: '', evidenceMode: 'none' });
                  setAssessModal(true);
                }}
              >
                준수 상태 평가
              </Button>
            </Space>
          )}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {checklists.map((cl) => (
              <div key={cl.id} style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                <Checkbox
                  checked={cl.is_checked}
                  onChange={(e) => handleCheckToggle(cl.id, e.target.checked)}
                  disabled={!hasRole('cpo', 'security_officer')}
                />
                <div>
                  <div>{cl.question}</div>
                  {cl.evidence_warning && <Tag color="orange">{cl.evidence_warning}</Tag>}
                </div>
              </div>
            ))}
          </div>
        </div>
      ),
    },
    {
      key: 'evidence',
      label: `증적 (${evidenceTotal}건)`,
      children: (
        <div>
          {canWrite && (
            <Space style={{ marginBottom: 16 }}>
              <Button type="primary" icon={<UploadOutlined />} onClick={() => setUploadOpen(true)}>
                파일 업로드
              </Button>
              <Button icon={<LinkOutlined />} onClick={() => setLinkOpen(true)}>
                외부 링크
              </Button>
            </Space>
          )}
          {evidenceList.length > 0 ? (
            <Table
              dataSource={evidenceList}
              columns={evidenceColumns}
              rowKey="id"
              size="small"
              pagination={{
                current: evidencePage,
                total: evidenceTotal,
                pageSize: 20,
                onChange: setEvidencePage,
                showTotal: (t) => `총 ${t}건`,
              }}
            />
          ) : (
            <Empty description="이 항목에 연결된 증적이 없습니다" />
          )}
        </div>
      ),
    },
    {
      key: 'prowler',
      label: `Prowler (${prowlerTotal}건)`,
      children: (
        <div>
          {prowlerFindings.length > 0 ? (
            <>
              <Space style={{ marginBottom: 12 }}>
                <Tag color="success">PASS {prowlerFindings.filter((f) => f.status === 'PASS').length}</Tag>
                <Tag color="error">FAIL {prowlerFindings.filter((f) => f.status === 'FAIL').length}</Tag>
              </Space>
              <Table
                dataSource={prowlerFindings}
                columns={prowlerColumns}
                rowKey="id"
                size="small"
                pagination={{ pageSize: 20, showTotal: (t) => `총 ${t}건` }}
              />
            </>
          ) : (
            <Empty
              description={
                item.has_prowler_checks
                  ? '스캔 결과가 없습니다. Prowler 스캔을 먼저 실행하세요.'
                  : '이 항목에는 Prowler 체크가 매핑되어 있지 않습니다.'
              }
            />
          )}
        </div>
      ),
    },
    {
      key: 'history',
      label: `준수 이력 (${compHistory.length})`,
      children: (
        <div>
          {compHistory.length > 0 ? (
            <Table
              dataSource={compHistory}
              rowKey="id"
              size="small"
              pagination={{ pageSize: 10, showTotal: (t) => `총 ${t}건` }}
              onRow={(record: any) => ({
                onClick: () => {
                  setExpandedRows((prev) =>
                    prev.includes(record.id) ? prev.filter((k) => k !== record.id) : [...prev, record.id],
                  );
                },
                style: { cursor: 'pointer' },
              })}
              expandable={{
                expandedRowKeys: expandedRows,
                onExpandedRowsChange: (keys) => setExpandedRows(keys as number[]),
                expandedRowRender: (record: any) => (
                  <div style={{ padding: '8px 0' }}>
                    <Typography.Text strong style={{ display: 'block', marginBottom: 8 }}>
                      체크리스트 상세 ({record.checklist_checked}/{record.checklist_total})
                    </Typography.Text>
                    {record.checklist_detail?.map((cl: any, i: number) => (
                      <div
                        key={i}
                        style={{
                          display: 'flex',
                          gap: 8,
                          alignItems: 'center',
                          padding: '4px 0',
                          borderBottom: '1px solid var(--border-color, #1e2d45)',
                        }}
                      >
                        <Checkbox checked={cl.is_checked} disabled />
                        <Typography.Text style={{ flex: 1 }}>{cl.question}</Typography.Text>
                        {cl.checked_by && <Tag>{cl.checked_by}</Tag>}
                      </div>
                    ))}
                    {(!record.checklist_detail || record.checklist_detail.length === 0) && (
                      <Typography.Text type="secondary">체크리스트 항목이 없습니다.</Typography.Text>
                    )}
                  </div>
                ),
                rowExpandable: (record: any) => record.checklist_total > 0,
              }}
              columns={[
                {
                  title: '평가일시',
                  dataIndex: 'assessed_at',
                  width: 140,
                  render: (v: string) => (v ? dayjs(v).format('YYYY-MM-DD HH:mm') : '-'),
                },
                {
                  title: '상태',
                  dataIndex: 'status',
                  width: 100,
                  render: (v: string) => {
                    const m: Record<string, { color: string; label: string }> = {
                      compliant: { color: 'success', label: '준수' },
                      partial: { color: 'warning', label: '부분 준수' },
                      non_compliant: { color: 'error', label: '미준수' },
                      not_applicable: { color: 'default', label: '해당없음' },
                    };
                    const s = m[v] || { color: 'default', label: v };
                    return <Tag color={s.color}>{s.label}</Tag>;
                  },
                },
                { title: '평가자', dataIndex: 'assessed_by_name', width: 80 },
                {
                  title: '체크리스트',
                  width: 110,
                  render: (_: any, r: any) => (
                    <span>
                      {r.checklist_checked}/{r.checklist_total}{' '}
                      {r.checklist_total > 0 && (
                        <Tag color="blue" style={{ fontSize: 10, padding: '0 4px', marginLeft: 4 }}>
                          상세
                        </Tag>
                      )}
                    </span>
                  ),
                },
                { title: '증적', width: 90, render: (_: any, r: any) => `${r.evidence_approved}/${r.evidence_count}` },
                { title: '메모', dataIndex: 'notes', ellipsis: true },
              ]}
            />
          ) : (
            <Empty
              description={`${item.code} 항목에 대한 준수 평가 이력이 없습니다. 체크리스트 탭에서 '준수 상태 평가'를 먼저 수행하세요.`}
            />
          )}
        </div>
      ),
    },
    {
      key: 'assignments',
      label: `담당자 (${assignments.length})`,
      children: (
        <div>
          {hasRole('cpo', 'security_officer') && (
            <Space style={{ marginBottom: 16 }}>
              <Select
                placeholder="사용자 선택"
                value={assignUserId}
                onChange={setAssignUserId}
                style={{ width: 200 }}
                showSearch
                filterOption={(input, option) => (option?.label ?? '').toLowerCase().includes(input.toLowerCase())}
                options={allUsers
                  .filter((u: any) => !assignments.find((a: any) => a.user_id === u.id))
                  .map((u: any) => ({ value: u.id, label: `${u.name} (${u.username})` }))}
              />
              <Select
                value={assignRole}
                onChange={setAssignRole}
                style={{ width: 120 }}
                options={[
                  { value: '담당자', label: '담당자' },
                  { value: '검토자', label: '검토자' },
                  { value: '승인자', label: '승인자' },
                ]}
              />
              <Button type="primary" icon={<UserAddOutlined />} onClick={handleAssign} disabled={!assignUserId}>
                배정
              </Button>
            </Space>
          )}
          {assignments.length > 0 ? (
            <Table
              dataSource={assignments}
              rowKey="id"
              size="small"
              pagination={false}
              columns={[
                { title: '이름', dataIndex: 'name', width: 100 },
                { title: '아이디', dataIndex: 'username', width: 100 },
                {
                  title: '역할',
                  dataIndex: 'role_in_item',
                  width: 80,
                  render: (v: string) => <Tag>{v || '담당자'}</Tag>,
                },
                {
                  title: '배정일',
                  dataIndex: 'assigned_at',
                  width: 120,
                  render: (v: string) => (v ? dayjs(v).format('YYYY-MM-DD HH:mm') : '-'),
                },
                ...(hasRole('cpo', 'security_officer')
                  ? [
                      {
                        title: '',
                        width: 50,
                        render: (_: any, r: any) => (
                          <Button
                            size="small"
                            type="text"
                            danger
                            icon={<DeleteOutlined />}
                            onClick={() => handleUnassign(r.user_id)}
                          />
                        ),
                      },
                    ]
                  : []),
              ]}
            />
          ) : (
            <Empty description="배정된 담당자가 없습니다" />
          )}
        </div>
      ),
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/isms/items')}>
          목록
        </Button>
        <Typography.Title level={4} style={{ margin: 0 }}>
          {item.code} {item.name}
        </Typography.Title>
      </Space>

      <Tabs items={tabItems} />

      <Modal
        title="준수 상태 평가"
        open={assessModal}
        onOk={handleAssess}
        onCancel={() => setAssessModal(false)}
        okText="평가 저장"
        cancelText="취소"
        width={520}
      >
        <Space direction="vertical" style={{ width: '100%' }} size={12}>
          {/* Auto-attach banner: no dropdown per item. The header switcher
              decides which round we're in; here we just surface the result
              plus a scope warning if the item doesn't belong. */}
          {currentAssessment ? (
            itemInScopeIds.has(currentAssessment.id) ? (
              <div
                style={{
                  padding: '8px 12px',
                  background: '#0f2942',
                  border: '1px solid #1f4e79',
                  borderRadius: 6,
                  fontSize: 12,
                }}
              >
                <Typography.Text style={{ color: '#93c5fd' }}>
                  이 평가는{' '}
                  <b>
                    {currentAssessment.code} · {currentAssessment.name}
                  </b>
                  에 기록됩니다.
                </Typography.Text>
              </div>
            ) : (
              <div
                style={{
                  padding: '8px 12px',
                  background: '#2b1a12',
                  border: '1px solid #7c3a22',
                  borderRadius: 6,
                  fontSize: 12,
                }}
              >
                <Typography.Text style={{ color: '#fbbf24' }}>
                  항목 <b>{code}</b>은 현재 평가 <b>{currentAssessment.code}</b>의 범위가 아닙니다. 저장은 가능하지만
                  경고가 함께 기록되며, 필요하면 평가 세션 범위에 추가하세요.
                </Typography.Text>
              </div>
            )
          ) : (
            <div
              style={{
                padding: '8px 12px',
                background: '#1a2235',
                border: '1px solid #334155',
                borderRadius: 6,
                fontSize: 12,
              }}
            >
              <Typography.Text type="secondary">
                현재 선택된 평가 세션이 없습니다. 상시 평가로 저장됩니다. (상단 헤더에서 평가 세션을 선택할 수
                있습니다.)
              </Typography.Text>
            </div>
          )}
          <div>
            <Typography.Text strong style={{ display: 'block', marginBottom: 4 }}>
              준수 상태
            </Typography.Text>
            <Select
              value={assessForm.status}
              onChange={(v) => setAssessForm({ ...assessForm, status: v })}
              style={{ width: '100%' }}
              options={[
                { value: 'compliant', label: '준수' },
                { value: 'partial', label: '부분 준수' },
                { value: 'non_compliant', label: '미준수' },
                { value: 'not_applicable', label: '해당없음' },
              ]}
            />
          </div>
          <div>
            <Typography.Text strong style={{ display: 'block', marginBottom: 4 }}>
              증적 첨부
            </Typography.Text>
            <Select
              value={assessForm.evidenceMode}
              onChange={(v) => setAssessForm({ ...assessForm, evidenceMode: v })}
              style={{ width: '100%', marginBottom: 8 }}
              options={[
                { value: 'none', label: '증적 없이 평가' },
                { value: 'upload', label: '새 파일 업로드' },
                { value: 'existing', label: '기존 증적 선택' },
              ]}
            />
            {assessForm.evidenceMode === 'upload' && (
              <Space direction="vertical" style={{ width: '100%' }}>
                <Input
                  placeholder="증적 제목 (미입력 시 자동 생성)"
                  value={assessForm.newTitle}
                  onChange={(e) => setAssessForm({ ...assessForm, newTitle: e.target.value })}
                />
                <Upload
                  beforeUpload={(file) => {
                    setAssessForm({ ...assessForm, newFile: file });
                    return false;
                  }}
                  maxCount={1}
                >
                  <Button icon={<UploadOutlined />}>
                    {assessForm.newFile ? (assessForm.newFile as any).name : '파일 선택'}
                  </Button>
                </Upload>
              </Space>
            )}
            {assessForm.evidenceMode === 'existing' && evidenceList.length > 0 && (
              <Select
                placeholder="증적 선택"
                style={{ width: '100%' }}
                onChange={(v) => setAssessForm({ ...assessForm, existingEvidenceId: v })}
                options={evidenceList.map((e: any) => ({ value: e.id, label: `#${e.id} ${e.title}` }))}
              />
            )}
            {assessForm.evidenceMode === 'existing' && evidenceList.length === 0 && (
              <Typography.Text type="secondary">
                이 항목에 연결된 증적이 없습니다. 증적 탭에서 먼저 업로드하세요.
              </Typography.Text>
            )}
          </div>
          <div>
            <Typography.Text strong style={{ display: 'block', marginBottom: 4 }}>
              평가 메모
            </Typography.Text>
            <Input.TextArea
              placeholder="평가 근거, 판단 사유 등"
              value={assessForm.notes}
              onChange={(e) => setAssessForm({ ...assessForm, notes: e.target.value })}
              rows={3}
            />
          </div>
        </Space>
      </Modal>

      <Modal
        title={`증적 파일 업로드 → ${code}`}
        open={uploadOpen}
        onCancel={() => setUploadOpen(false)}
        footer={null}
        destroyOnClose
      >
        <Form form={uploadForm} layout="vertical" onFinish={handleUpload}>
          <Form.Item name="title" label="제목" rules={[{ required: true, message: '제목을 입력하세요' }]}>
            <Input placeholder="증적 제목" />
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

      <Modal
        title={`외부 링크 등록 → ${code}`}
        open={linkOpen}
        onCancel={() => setLinkOpen(false)}
        footer={null}
        destroyOnClose
      >
        <Form form={linkForm} layout="vertical" onFinish={handleLink}>
          <Form.Item name="title" label="제목" rules={[{ required: true }]}>
            <Input placeholder="증적 제목" />
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
    </div>
  );
}
