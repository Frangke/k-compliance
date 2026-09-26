import { useEffect, useState } from 'react';
import { Card, Col, Row, Typography, Tag, List, Progress, Space, Divider, Badge, Button, Table, Select } from 'antd';
import { Pie } from '@ant-design/charts';
import { FileProtectOutlined, RobotOutlined, AlertOutlined, DownloadOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { dashboardApi } from '../api/dashboard';
import { ismsApi } from '../api/isms';
import { usePermission } from '../hooks/usePermission';

const { Title, Text } = Typography;

const STATUS_COLORS: Record<string, string> = {
  준수: '#10b981',
  부분준수: '#f59e0b',
  미준수: '#ef4444',
  해당없음: '#64748b',
  미평가: '#1e2d45',
};

/** Semi-donut */
function SemiDonut({
  percent,
  total,
  count,
  label,
  color,
}: {
  percent: number;
  total: number;
  count: number;
  label: string;
  color: string;
}) {
  const data = [
    { type: label, value: percent },
    { type: '나머지', value: Math.max(0, 100 - percent) },
  ];
  return (
    <div style={{ position: 'relative', textAlign: 'center', width: '100%', maxWidth: 280, margin: '0 auto' }}>
      <Pie
        data={data}
        angleField="value"
        colorField="type"
        color={[color, '#1e2d45']}
        radius={1}
        innerRadius={0.72}
        startAngle={Math.PI}
        endAngle={2 * Math.PI}
        label={false}
        legend={false}
        tooltip={false}
        height={200}
        autoFit
        state={{ inactive: { style: { fillOpacity: 1 } } }}
        interaction={{ elementHighlight: false }}
      />
      <div style={{ position: 'absolute', bottom: 16, left: '50%', transform: 'translateX(-50%)' }}>
        <div style={{ fontSize: 32, fontWeight: 800, color, lineHeight: 1 }}>{percent}%</div>
        <div style={{ fontSize: 13, color: '#94a3b8', marginTop: 6 }}>
          {count} / {total} 항목
        </div>
      </div>
    </div>
  );
}

/** Evidence semi-donut */
function EvidenceSemiDonut({ data, totalCount }: { data: { type: string; value: number }[]; totalCount: number }) {
  const colors: Record<string, string> = { 유효: '#10b981', 만료: '#ef4444', 만료임박: '#f59e0b', 검토대기: '#3b82f6' };
  return (
    <div style={{ position: 'relative', textAlign: 'center', width: '100%', maxWidth: 280, margin: '0 auto' }}>
      <Pie
        data={data}
        angleField="value"
        colorField="type"
        color={(d: any) => colors[d.type] || '#64748b'}
        radius={1}
        innerRadius={0.72}
        startAngle={Math.PI}
        endAngle={2 * Math.PI}
        label={false}
        legend={false}
        tooltip={{ title: false }}
        height={200}
        autoFit
      />
      <div style={{ position: 'absolute', bottom: 16, left: '50%', transform: 'translateX(-50%)' }}>
        <div style={{ fontSize: 32, fontWeight: 800, color: '#e2e8f0', lineHeight: 1 }}>{totalCount}</div>
        <div style={{ fontSize: 13, color: '#94a3b8', marginTop: 6 }}>전체 증적</div>
      </div>
      <div style={{ display: 'flex', justifyContent: 'center', gap: 12, marginTop: 4, flexWrap: 'wrap' }}>
        {data.map((d) => (
          <span key={d.type} style={{ fontSize: 12, color: '#94a3b8' }}>
            <span
              style={{
                display: 'inline-block',
                width: 8,
                height: 8,
                borderRadius: '50%',
                backgroundColor: colors[d.type],
                marginRight: 4,
              }}
            />
            {d.type} {d.value}
          </span>
        ))}
      </div>
    </div>
  );
}

export default function Dashboard() {
  const { hasRole } = usePermission();
  const showFull = hasRole('cpo', 'security_officer', 'auditor');
  const navigate = useNavigate();

  const [overview, setOverview] = useState<any>(null);
  const [myTasks, setMyTasks] = useState<any>(null);
  const [deadlines, setDeadlines] = useState<any[]>([]);
  const [prowler, setProwler] = useState<any>(null);
  const [config, setConfig] = useState<any>(null);
  const [compSummary, setCompSummary] = useState<any[]>([]);
  const [compDetail, setCompDetail] = useState<any[]>([]);
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [autoCoverage, setAutoCoverage] = useState<any>(null);

  useEffect(() => {
    dashboardApi.myAssignments().then((r) => setMyTasks(r.data));
    dashboardApi.pipaDeadlines().then((r) => setDeadlines(r.data?.slice(0, 8) || []));
    if (showFull) {
      dashboardApi.overview().then((r) => setOverview(r.data));
      dashboardApi.prowlerSummary().then((r) => setProwler(r.data));
      dashboardApi.configSummary().then((r) => setConfig(r.data));
      dashboardApi
        .automatedCoverage()
        .then((r) => setAutoCoverage(r.data))
        .catch(() => {});
      ismsApi.getComplianceSummary().then((r) => setCompSummary(r.data || []));
    }
  }, [showFull]);

  useEffect(() => {
    if (showFull) {
      ismsApi.getComplianceDetail(statusFilter).then((r) => setCompDetail(r.data || []));
    }
  }, [showFull, statusFilter]);

  const rate = overview?.compliance_rate || 0;
  const gaugeColor = rate >= 80 ? '#10b981' : rate >= 50 ? '#f59e0b' : '#ef4444';

  const evidencePie = overview
    ? [
        { type: '유효', value: overview.evidence.approved || 0 },
        { type: '만료', value: overview.evidence.expired || 0 },
        { type: '만료임박', value: overview.evidence.expiring_soon || 0 },
        { type: '검토대기', value: overview.evidence.pending_review || 0 },
      ].filter((d) => d.value > 0)
    : [];
  const evidenceTotal = evidencePie.reduce((s, d) => s + d.value, 0);

  // Aggregate status counts from compSummary
  const statusTotals = compSummary.reduce(
    (acc, d) => {
      acc.compliant += d.compliant || 0;
      acc.partial += d.partial || 0;
      acc.non_compliant += d.non_compliant || 0;
      acc.not_assessed += d.not_assessed || 0;
      return acc;
    },
    { compliant: 0, partial: 0, non_compliant: 0, not_assessed: 0 },
  );

  const statusPieData = [
    { type: '준수', value: statusTotals.compliant },
    { type: '부분준수', value: statusTotals.partial },
    { type: '미준수', value: statusTotals.non_compliant },
    { type: '미평가', value: statusTotals.not_assessed },
  ].filter((d) => d.value > 0);

  const STATUS_KR: Record<string, { color: string; label: string }> = {
    compliant: { color: 'success', label: '준수' },
    partial: { color: 'warning', label: '부분준수' },
    non_compliant: { color: 'error', label: '미준수' },
    not_applicable: { color: 'default', label: '해당없음' },
    not_assessed: { color: 'default', label: '미평가' },
  };

  const handleCsvExport = () => {
    const url = ismsApi.exportComplianceCsv(statusFilter);
    window.open(url, '_blank');
  };

  return (
    <div>
      <Title level={4} style={{ margin: 0, marginBottom: 16 }}>
        대시보드
      </Title>

      {myTasks && (
        <Card
          size="small"
          className="kc-my-tasks"
          style={{ marginBottom: 16 }}
          title={
            <Text strong style={{ fontSize: 14 }}>
              내 할 일
            </Text>
          }
        >
          {myTasks.assigned_items_detail?.length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <Text type="secondary" style={{ fontSize: 12, marginBottom: 6, display: 'block' }}>
                ISMS-P 담당 항목 ({myTasks.assigned_items}건)
              </Text>
              <Space size={8} wrap>
                {myTasks.assigned_items_detail.map((item: any) => (
                  <Tag
                    key={item.code}
                    color="blue"
                    style={{ cursor: 'pointer', padding: '4px 10px' }}
                    onClick={() => navigate(`/isms/items/${item.code}`)}
                  >
                    {item.code} {item.name}
                  </Tag>
                ))}
              </Space>
            </div>
          )}
          {myTasks.assigned_items === 0 && <Text type="secondary">배정된 ISMS-P 항목이 없습니다.</Text>}
          <Space size={12} wrap>
            {myTasks.items_missing_evidence > 0 && (
              <Tag
                color="orange"
                style={{ cursor: 'pointer', padding: '4px 12px' }}
                onClick={() => navigate('/evidence')}
              >
                증적 미제출 {myTasks.items_missing_evidence}건
              </Tag>
            )}
            {myTasks.pending_review > 0 && (
              <Tag
                color="blue"
                style={{ cursor: 'pointer', padding: '4px 12px' }}
                onClick={() => navigate('/evidence')}
              >
                검토 대기 {myTasks.pending_review}건
              </Tag>
            )}
            {myTasks.assigned_dsrs > 0 && (
              <Tag color="red" style={{ cursor: 'pointer', padding: '4px 12px' }} onClick={() => navigate('/pipa/dsr')}>
                배정 DSR {myTasks.assigned_dsrs}건
              </Tag>
            )}
            {myTasks.assigned_corrective_actions > 0 && (
              <Tag
                color="volcano"
                style={{ cursor: 'pointer', padding: '4px 12px' }}
                onClick={() => navigate('/corrective-actions')}
              >
                시정조치 {myTasks.assigned_corrective_actions}건
              </Tag>
            )}
          </Space>
        </Card>
      )}

      {showFull && overview && (
        <>
          {/* Row 1: 준수율 + 상태별 분포 + 증적 + 긴급 */}
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={6}>
              <Card title="전체 준수율" size="small" style={{ minHeight: 310 }}>
                <SemiDonut
                  percent={rate}
                  total={overview.total_items}
                  count={overview.compliant_count}
                  label="준수"
                  color={gaugeColor}
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card title="준수 상태 분포" size="small" style={{ minHeight: 310 }}>
                {statusPieData.length > 0 ? (
                  <div style={{ textAlign: 'center' }}>
                    <Pie
                      data={statusPieData}
                      angleField="value"
                      colorField="type"
                      color={(d: any) => STATUS_COLORS[d.type] || '#64748b'}
                      radius={0.85}
                      innerRadius={0.55}
                      label={false}
                      legend={false}
                      tooltip={{ title: false }}
                      height={180}
                      autoFit
                    />
                    <div style={{ display: 'flex', justifyContent: 'center', gap: 10, flexWrap: 'wrap', marginTop: 8 }}>
                      {statusPieData.map((d) => (
                        <span
                          key={d.type}
                          style={{ fontSize: 12, color: '#94a3b8', cursor: 'pointer' }}
                          onClick={() =>
                            setStatusFilter(
                              d.type === '준수'
                                ? 'compliant'
                                : d.type === '부분준수'
                                  ? 'partial'
                                  : d.type === '미준수'
                                    ? 'non_compliant'
                                    : 'not_assessed',
                            )
                          }
                        >
                          <span
                            style={{
                              display: 'inline-block',
                              width: 8,
                              height: 8,
                              borderRadius: '50%',
                              backgroundColor: STATUS_COLORS[d.type],
                              marginRight: 3,
                            }}
                          />
                          {d.type} <b>{d.value}</b>
                        </span>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div style={{ textAlign: 'center', paddingTop: 80 }}>
                    <Text type="secondary">평가 데이터 없음</Text>
                  </div>
                )}
              </Card>
            </Col>
            <Col span={6}>
              <Card
                title={
                  <>
                    <FileProtectOutlined /> 증적 현황
                  </>
                }
                size="small"
                style={{ minHeight: 310 }}
              >
                {evidencePie.length > 0 ? (
                  <EvidenceSemiDonut data={evidencePie} totalCount={evidenceTotal} />
                ) : (
                  <div style={{ textAlign: 'center', paddingTop: 80 }}>
                    <Text type="secondary">등록된 증적 없음</Text>
                  </div>
                )}
              </Card>
            </Col>
            <Col span={6}>
              <Card
                title={
                  <>
                    <AlertOutlined /> 긴급 알림
                  </>
                }
                size="small"
                style={{ minHeight: 310 }}
              >
                <Space direction="vertical" size={8} style={{ width: '100%' }}>
                  {overview.urgent.active_incidents > 0 && (
                    <Tag color="red">진행 사고 {overview.urgent.active_incidents}건</Tag>
                  )}
                  {overview.urgent.dsr_due_soon > 0 && (
                    <Tag color="orange">DSR 기한 임박 {overview.urgent.dsr_due_soon}건</Tag>
                  )}
                  {overview.urgent.ca_overdue > 0 && (
                    <Tag color="red">시정조치 미이행 {overview.urgent.ca_overdue}건</Tag>
                  )}
                  {!overview.urgent.active_incidents &&
                    !overview.urgent.dsr_due_soon &&
                    !overview.urgent.ca_overdue && <Text type="success">긴급 사항 없음</Text>}
                  <Divider style={{ margin: '8px 0' }} />
                  <Text strong>시정조치</Text>
                  <Text>
                    미완료 <b>{overview.corrective_actions.open}</b>건
                  </Text>
                  {overview.corrective_actions.overdue > 0 && (
                    <Tag color="red">초과 {overview.corrective_actions.overdue}</Tag>
                  )}
                </Space>
              </Card>
            </Col>
          </Row>

          {/* Row 2: 도메인별 + 스캔 */}
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={14}>
              <Card title="도메인별 준수 현황" size="small">
                {compSummary.map((d) => (
                  <div key={d.domain_code} style={{ marginBottom: 12 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                      <Text strong>
                        {d.domain_code}. {d.domain_name}
                      </Text>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        준수 {d.compliant} / 부분 {d.partial} / 미준수 {d.non_compliant} / 미평가 {d.not_assessed}
                      </Text>
                    </div>
                    <Progress
                      percent={d.rate}
                      size="small"
                      strokeColor={d.rate >= 80 ? '#10b981' : d.rate >= 50 ? '#f59e0b' : '#ef4444'}
                      format={() => `${d.rate}%`}
                    />
                  </div>
                ))}
              </Card>
            </Col>
            <Col span={10}>
              <Card
                title={
                  <>
                    <RobotOutlined /> 자동화 스캔
                  </>
                }
                size="small"
              >
                {autoCoverage && (
                  <div style={{ marginBottom: 12 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                      <Text strong>자동 진단 커버리지</Text>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {autoCoverage.covered}/{autoCoverage.total_items} 항목
                      </Text>
                    </div>
                    <Progress
                      percent={autoCoverage.coverage_rate}
                      size="small"
                      strokeColor={autoCoverage.coverage_rate >= 30 ? '#3b82f6' : '#f59e0b'}
                      format={() => `${autoCoverage.coverage_rate}%`}
                    />
                    <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>
                      Prowler {autoCoverage.prowler_items}항목 · Config {autoCoverage.config_items}항목 · 중복{' '}
                      {autoCoverage.both}항목
                    </div>
                    <Divider style={{ margin: '10px 0' }} />
                  </div>
                )}
                <Row gutter={16}>
                  <Col span={12}>
                    <Text strong>Prowler</Text>
                    {prowler?.scan_id ? (
                      <div>
                        <Text type="success">Pass {prowler.passed}</Text> /{' '}
                        <Text type="danger">Fail {prowler.failed}</Text>
                        {prowler.remediation_pending > 0 && (
                          <Tag color="orange" style={{ marginLeft: 4 }}>
                            미조치 {prowler.remediation_pending}
                          </Tag>
                        )}
                        <br />
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          최근: {prowler.scanned_at?.split('T')[0]}
                        </Text>
                      </div>
                    ) : (
                      <Text type="secondary">스캔 기록 없음</Text>
                    )}
                  </Col>
                  <Col span={12}>
                    <Text strong>AWS Config</Text>
                    {config?.sync_job_id ? (
                      <div>
                        <Text type="success">준수 {config.compliant}</Text> /{' '}
                        <Text type="danger">미준수 {config.non_compliant}</Text>
                        {config.remediation_pending > 0 && (
                          <Tag color="orange" style={{ marginLeft: 4 }}>
                            미조치 {config.remediation_pending}
                          </Tag>
                        )}
                        <br />
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          최근: {config.synced_at?.split('T')[0]}
                        </Text>
                      </div>
                    ) : (
                      <Text type="secondary">동기화 기록 없음</Text>
                    )}
                  </Col>
                </Row>
              </Card>
            </Col>
          </Row>

          {/* Row 3: 항목별 상세 현황 (필터 + CSV) */}
          <Card
            title="항목별 준수 현황"
            size="small"
            style={{ marginBottom: 16 }}
            extra={
              <Space>
                <Select
                  value={statusFilter}
                  onChange={setStatusFilter}
                  allowClear
                  placeholder="전체"
                  style={{ width: 130 }}
                  options={[
                    { value: 'compliant', label: '준수' },
                    { value: 'partial', label: '부분준수' },
                    { value: 'non_compliant', label: '미준수' },
                    { value: 'not_applicable', label: '해당없음' },
                    { value: 'not_assessed', label: '미평가' },
                  ]}
                />
                <Button icon={<DownloadOutlined />} onClick={handleCsvExport} size="small">
                  CSV
                </Button>
              </Space>
            }
          >
            <Table
              dataSource={compDetail}
              rowKey="code"
              size="small"
              pagination={{ pageSize: 10, showTotal: (t) => `총 ${t}건` }}
              onRow={(r) => ({ onClick: () => navigate(`/isms/items/${r.code}`), style: { cursor: 'pointer' } })}
              columns={[
                { title: '항목', dataIndex: 'code', width: 70 },
                { title: '항목명', dataIndex: 'name', ellipsis: true },
                { title: '도메인', dataIndex: 'domain_name', width: 150, ellipsis: true },
                {
                  title: '상태',
                  dataIndex: 'status',
                  width: 90,
                  render: (v: string) => {
                    const s = STATUS_KR[v];
                    return <Tag color={s?.color}>{s?.label || v}</Tag>;
                  },
                },
                {
                  title: '체크리스트',
                  width: 90,
                  render: (_: any, r: any) => `${r.checklist_checked}/${r.checklist_total}`,
                },
                { title: '증적', width: 80, render: (_: any, r: any) => `${r.evidence_approved}/${r.evidence_count}` },
              ]}
            />
          </Card>
        </>
      )}

      {deadlines.length > 0 && (
        <Card title="기한 임박" size="small">
          <List
            dataSource={deadlines}
            size="small"
            renderItem={(item: any) => (
              <List.Item>
                <Tag
                  color={
                    item.type === 'incident' ? 'red' : item.d_day <= 3 ? 'red' : item.d_day <= 7 ? 'orange' : 'blue'
                  }
                >
                  {item.type === 'incident' ? `H-${Math.round(item.hours_left || 0)}` : `D-${item.d_day}`}
                </Tag>
                <Text style={{ flex: 1 }}>{item.title}</Text>
              </List.Item>
            )}
          />
        </Card>
      )}
    </div>
  );
}
