import { useEffect, useState, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Table, Input, Space, Typography, Badge, Tag, Tooltip, Select } from 'antd';
import {
  RobotOutlined,
  SearchOutlined,
  CheckCircleFilled,
  ExclamationCircleFilled,
  CloseCircleFilled,
  MinusCircleFilled,
} from '@ant-design/icons';
import { ismsApi } from '../../api/isms';

interface ItemRecord {
  key: string;
  code: string;
  name: string;
  evidence_count: number;
  checklist_total: number;
  has_prowler_checks: boolean;
  has_config_rules: boolean;
  sort_order: number;
  compliance_status?: string;
}

interface SubdomainGroup {
  key: string;
  subdomain_code: string;
  subdomain_name: string;
  item_count: number;
  compliance: ComplianceCounts;
  children: ItemRecord[];
}

interface DomainGroup {
  key: string;
  domain_code: string;
  domain_name: string;
  item_count: number;
  compliance: ComplianceCounts;
  children: SubdomainGroup[];
}

interface ComplianceCounts {
  compliant: number;
  partial: number;
  non_compliant: number;
  not_applicable: number;
  not_assessed: number;
  total: number;
}

const DOMAIN_META: Record<string, { label: string; number: string; color: string }> = {
  '1': { label: '관리체계 수립 및 운영', number: '①', color: '#1677ff' },
  '2': { label: '보호대책 요구사항', number: '②', color: '#52c41a' },
  '3': { label: '개인정보 처리 단계별 요구사항', number: '③', color: '#fa8c16' },
};

const STATUS_CONFIG = {
  compliant: { color: '#52c41a', label: '준수', icon: CheckCircleFilled },
  partial: { color: '#faad14', label: '일부', icon: ExclamationCircleFilled },
  non_compliant: { color: '#ff4d4f', label: '미준수', icon: CloseCircleFilled },
  not_applicable: { color: '#d9d9d9', label: 'N/A', icon: MinusCircleFilled },
  not_assessed: { color: '#e8e8e8', label: '미평가', icon: MinusCircleFilled },
} as const;

function ComplianceBar({ counts }: { counts: ComplianceCounts }) {
  const { compliant, partial, non_compliant, not_applicable, not_assessed, total } = counts;
  if (total === 0) return null;

  const segments = [
    { count: compliant, ...STATUS_CONFIG.compliant },
    { count: partial, ...STATUS_CONFIG.partial },
    { count: non_compliant, ...STATUS_CONFIG.non_compliant },
    { count: not_applicable, ...STATUS_CONFIG.not_applicable },
    { count: not_assessed, ...STATUS_CONFIG.not_assessed },
  ];

  const assessed = compliant + partial + non_compliant + not_applicable;
  const rate = total > 0 ? Math.round((compliant / total) * 100) : 0;

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 260 }}>
      {/* Segmented bar */}
      <Tooltip
        title={segments
          .filter((s) => s.count > 0)
          .map((s) => `${s.label}: ${s.count}개`)
          .join(' / ')}
      >
        <div
          style={{
            display: 'flex',
            height: 8,
            borderRadius: 4,
            overflow: 'hidden',
            flex: 1,
            minWidth: 100,
            background: '#f0f0f0',
          }}
        >
          {segments.map((seg, i) =>
            seg.count > 0 ? (
              <div
                key={i}
                style={{
                  width: `${(seg.count / total) * 100}%`,
                  backgroundColor: seg.color,
                  transition: 'width 0.3s',
                }}
              />
            ) : null,
          )}
        </div>
      </Tooltip>
      {/* Summary text */}
      <span style={{ fontSize: 12, color: '#595959', whiteSpace: 'nowrap' }}>
        <span style={{ color: '#52c41a', fontWeight: 600 }}>{compliant}</span>
        <span style={{ color: '#8c8c8c' }}>/{total}</span>
        <span
          style={{
            marginLeft: 4,
            color: rate === 100 ? '#52c41a' : rate >= 70 ? '#595959' : '#ff4d4f',
            fontWeight: 500,
          }}
        >
          ({rate}%)
        </span>
      </span>
    </div>
  );
}

function ItemStatusTag({ status }: { status?: string }) {
  if (!status)
    return (
      <Tag color="default" style={{ fontSize: 11 }}>
        미평가
      </Tag>
    );
  const cfg = STATUS_CONFIG[status as keyof typeof STATUS_CONFIG];
  if (!cfg) return <Tag color="default">{status}</Tag>;
  const Icon = cfg.icon;
  return (
    <Tag
      icon={<Icon />}
      color={
        cfg.color === '#52c41a'
          ? 'success'
          : cfg.color === '#faad14'
            ? 'warning'
            : cfg.color === '#ff4d4f'
              ? 'error'
              : 'default'
      }
      style={{ fontSize: 11 }}
    >
      {cfg.label}
    </Tag>
  );
}

export default function ItemList() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [allItems, setAllItems] = useState<any[]>([]);
  const [statusMap, setStatusMap] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);

  const search = searchParams.get('search') || '';

  // Load all items + compliance status
  useEffect(() => {
    setLoading(true);
    Promise.all([ismsApi.getItems({ size: 200 }), ismsApi.getComplianceStatusMap()])
      .then(([itemsRes, statusRes]) => {
        setAllItems(itemsRes.data.items);
        setStatusMap(statusRes.data);
      })
      .finally(() => setLoading(false));
  }, []);

  // Filter and group into domain → subdomain → items
  const treeData = useMemo(() => {
    let filtered = allItems;
    if (search) {
      const q = search.toLowerCase();
      filtered = allItems.filter(
        (item) =>
          item.code.toLowerCase().includes(q) ||
          item.name.toLowerCase().includes(q) ||
          (item.description || '').toLowerCase().includes(q),
      );
    }

    const domainMap = new Map<string, Map<string, ItemRecord[]>>();

    for (const item of filtered) {
      const domainCode = item.code.split('.')[0];
      const parts = item.code.split('.');
      const subCode = `${parts[0]}.${parts[1]}`;

      if (!domainMap.has(domainCode)) domainMap.set(domainCode, new Map());
      const subMap = domainMap.get(domainCode)!;
      if (!subMap.has(subCode)) subMap.set(subCode, []);
      subMap.get(subCode)!.push({
        ...item,
        key: item.code,
        compliance_status: statusMap[item.code],
      });
    }

    const domains: DomainGroup[] = [];
    for (const [dCode, subMap] of [...domainMap.entries()].sort((a, b) => a[0].localeCompare(b[0]))) {
      const meta = DOMAIN_META[dCode];
      const subdomains: SubdomainGroup[] = [];
      const domainCounts: ComplianceCounts = {
        compliant: 0,
        partial: 0,
        non_compliant: 0,
        not_applicable: 0,
        not_assessed: 0,
        total: 0,
      };

      for (const [sCode, items] of [...subMap.entries()].sort((a, b) => {
        const [, aN] = a[0].split('.');
        const [, bN] = b[0].split('.');
        return Number(aN) - Number(bN);
      })) {
        const subCounts = countCompliance(items);
        addCounts(domainCounts, subCounts);

        subdomains.push({
          key: `sub-${sCode}`,
          subdomain_code: sCode,
          subdomain_name: getSubdomainName(sCode),
          item_count: items.length,
          compliance: subCounts,
          children: items.sort((a, b) => a.sort_order - b.sort_order),
        });
      }

      domains.push({
        key: `domain-${dCode}`,
        domain_code: dCode,
        domain_name: meta?.label || `도메인 ${dCode}`,
        item_count: domainCounts.total,
        compliance: domainCounts,
        children: subdomains,
      });
    }

    return domains;
  }, [allItems, search, statusMap]);

  const columns = [
    {
      title: '코드 / 항목명',
      key: 'name',
      render: (_: any, record: any) => {
        if (record.domain_code) {
          const meta = DOMAIN_META[record.domain_code];
          return (
            <span style={{ fontWeight: 600, fontSize: 15 }}>
              <Tag color={meta?.color} style={{ marginRight: 8 }}>
                {meta?.number}
              </Tag>
              {record.domain_name}
              <Badge count={`${record.item_count}개`} style={{ backgroundColor: meta?.color, marginLeft: 8 }} />
            </span>
          );
        }
        if (record.subdomain_code) {
          return (
            <span style={{ fontWeight: 500, color: '#595959' }}>
              {record.subdomain_code}. {record.subdomain_name}
              <span style={{ color: '#8c8c8c', marginLeft: 8, fontWeight: 400 }}>({record.item_count}개)</span>
            </span>
          );
        }
        return (
          <span>
            <span style={{ color: '#1677ff', fontWeight: 500, marginRight: 8 }}>{record.code}</span>
            {record.name}
          </span>
        );
      },
    },
    {
      title: '준수 현황',
      key: 'compliance',
      width: 320,
      render: (_: any, record: any) => {
        if (record.domain_code || record.subdomain_code) {
          return <ComplianceBar counts={record.compliance} />;
        }
        return <ItemStatusTag status={record.compliance_status} />;
      },
    },
    {
      title: '증적',
      key: 'evidence',
      width: 60,
      align: 'center' as const,
      render: (_: any, record: any) => {
        if (record.domain_code || record.subdomain_code) return null;
        return `${record.evidence_count}건`;
      },
    },
    {
      title: '체크리스트',
      key: 'checklist',
      width: 80,
      align: 'center' as const,
      render: (_: any, record: any) => {
        if (record.domain_code || record.subdomain_code) return null;
        return `${record.checklist_total}개`;
      },
    },
    {
      title: '자동화',
      key: 'auto',
      width: 60,
      align: 'center' as const,
      render: (_: any, record: any) => {
        if (record.domain_code || record.subdomain_code) return null;
        return record.has_prowler_checks || record.has_config_rules ? (
          <RobotOutlined style={{ color: '#1677ff' }} />
        ) : (
          <span style={{ color: '#ccc' }}>-</span>
        );
      },
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Typography.Title level={4} style={{ margin: 0 }}>
          ISMS-P 인증 항목 관리
        </Typography.Title>
        <Space>
          <Input.Search
            placeholder="코드 또는 항목명 검색..."
            prefix={<SearchOutlined />}
            defaultValue={search}
            onSearch={(v) => {
              const p = new URLSearchParams(searchParams);
              if (v) p.set('search', v);
              else p.delete('search');
              setSearchParams(p);
            }}
            style={{ width: 300 }}
            allowClear
          />
        </Space>
      </div>

      <Table
        dataSource={treeData}
        columns={columns}
        rowKey="key"
        loading={loading}
        pagination={false}
        expandable={{
          defaultExpandedRowKeys: search ? treeData.flatMap((d) => [d.key, ...d.children.map((s) => s.key)]) : [],
        }}
        onRow={(record: any) => {
          if (!record.domain_code && !record.subdomain_code && record.code) {
            return {
              onClick: () => navigate(`/isms/items/${record.code}`),
              style: { cursor: 'pointer' },
            };
          }
          return {};
        }}
        size="middle"
      />
    </div>
  );
}

// --- Helpers ---

function countCompliance(items: ItemRecord[]): ComplianceCounts {
  const counts: ComplianceCounts = {
    compliant: 0,
    partial: 0,
    non_compliant: 0,
    not_applicable: 0,
    not_assessed: 0,
    total: items.length,
  };
  for (const item of items) {
    const s = item.compliance_status;
    if (s === 'compliant') counts.compliant++;
    else if (s === 'partial') counts.partial++;
    else if (s === 'non_compliant') counts.non_compliant++;
    else if (s === 'not_applicable') counts.not_applicable++;
    else counts.not_assessed++;
  }
  return counts;
}

function addCounts(target: ComplianceCounts, source: ComplianceCounts) {
  target.compliant += source.compliant;
  target.partial += source.partial;
  target.non_compliant += source.non_compliant;
  target.not_applicable += source.not_applicable;
  target.not_assessed += source.not_assessed;
  target.total += source.total;
}

const SUBDOMAIN_NAMES: Record<string, string> = {
  '1.1': '관리체계 기반 마련',
  '1.2': '위험 관리',
  '1.3': '관리체계 운영',
  '1.4': '관리체계 점검 및 개선',
  '2.1': '정책, 조직, 자산 관리',
  '2.2': '인적 보안',
  '2.3': '외부자 보안',
  '2.4': '물리 보안',
  '2.5': '인증 및 권한관리',
  '2.6': '접근통제',
  '2.7': '암호화 적용',
  '2.8': '정보시스템 도입 및 개발 보안',
  '2.9': '시스템 및 서비스 운영관리',
  '2.10': '시스템 및 서비스 보안관리',
  '2.11': '사고 예방 및 대응',
  '2.12': '재해복구',
  '3.1': '개인정보 수집 시 보호조치',
  '3.2': '개인정보 보유 및 이용 시 보호조치',
  '3.3': '개인정보 제공 시 보호조치',
  '3.4': '개인정보 파기 시 보호조치',
  '3.5': '정보주체 권리보호',
};

function getSubdomainName(code: string): string {
  return SUBDOMAIN_NAMES[code] || code;
}
