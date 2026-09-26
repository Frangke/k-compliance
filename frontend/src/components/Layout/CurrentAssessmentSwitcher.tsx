import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Select, Space, Tag, Typography } from 'antd';
import { ExperimentOutlined } from '@ant-design/icons';
import { assessmentsApi, type Assessment } from '../../api/assessments';
import { useCurrentAssessmentStore } from '../../store/currentAssessmentStore';

const AUDIT_TYPE_LABEL: Record<string, string> = {
  initial: '최초',
  surveillance: '사후',
  renewal: '갱신',
};

/**
 * Header switcher — shows the active assessment in large, quiet type so the
 * user can't forget which round they're recording into. When only one round
 * is active the switcher still renders so the context is visible.
 */
export default function CurrentAssessmentSwitcher() {
  const navigate = useNavigate();
  const { currentAssessmentId, setCurrentAssessmentId } = useCurrentAssessmentStore();

  // Lightweight polling — refresh once a minute and on focus. Keeps the
  // count badge roughly up to date without pulling in SWR.
  const [all, setAll] = useState<Assessment[] | null>(null);
  useEffect(() => {
    let alive = true;
    const fetchIt = () => {
      assessmentsApi
        .list()
        .then((r) => {
          if (alive) setAll(r.data);
        })
        .catch(() => {});
    };
    fetchIt();
    const t = setInterval(fetchIt, 60_000);
    const onFocus = () => fetchIt();
    window.addEventListener('focus', onFocus);
    return () => {
      alive = false;
      clearInterval(t);
      window.removeEventListener('focus', onFocus);
    };
  }, []);

  const active = useMemo(() => (all || []).filter((a) => a.status === 'active'), [all]);

  // Auto-pick when there's exactly one active round and the user hasn't
  // chosen anything yet. Clear the selection if the remembered id is gone
  // (e.g. got closed on another tab).
  useEffect(() => {
    if (!all) return;
    const still = currentAssessmentId != null ? active.find((a) => a.id === currentAssessmentId) : undefined;
    if (currentAssessmentId != null && !still) {
      setCurrentAssessmentId(null);
      return;
    }
    if (currentAssessmentId == null && active.length === 1) {
      setCurrentAssessmentId(active[0].id);
    }
  }, [all, active, currentAssessmentId, setCurrentAssessmentId]);

  const current = active.find((a) => a.id === currentAssessmentId);

  const options = [
    { value: null as any, label: '— 상시 평가 —' },
    ...active.map((a) => ({
      value: a.id,
      label: (
        <span>
          <Tag color="processing" style={{ marginRight: 6 }}>
            {AUDIT_TYPE_LABEL[a.audit_type] || a.audit_type}
          </Tag>
          {a.code} · {a.name}
        </span>
      ),
    })),
  ];

  if (active.length === 0) {
    return (
      <Typography.Text
        type="secondary"
        style={{ fontSize: 12, cursor: 'pointer' }}
        onClick={() => navigate('/assessments')}
        title="평가 세션 관리로 이동"
      >
        <ExperimentOutlined style={{ marginRight: 4 }} />
        진행중인 평가 세션 없음
      </Typography.Text>
    );
  }

  return (
    <Space size={6}>
      <ExperimentOutlined style={{ color: '#94a3b8' }} />
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        현재 평가:
      </Typography.Text>
      <Select
        size="small"
        style={{ minWidth: 280 }}
        value={currentAssessmentId ?? null}
        onChange={(v) => setCurrentAssessmentId(v)}
        options={options}
        labelRender={() =>
          current ? (
            <span>
              <Tag color="processing" style={{ marginRight: 6 }}>
                {AUDIT_TYPE_LABEL[current.audit_type] || current.audit_type}
              </Tag>
              {current.code}
              <Typography.Text type="secondary" style={{ marginLeft: 6, fontSize: 11 }}>
                {current.assessed_count}/{current.scope_total}
              </Typography.Text>
            </span>
          ) : (
            <span style={{ color: '#94a3b8' }}>— 상시 평가 —</span>
          )
        }
      />
    </Space>
  );
}
