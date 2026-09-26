import { useState } from 'react';
import { Typography, Card, Button, Alert, Modal, Table, Tag, Space, Result, Descriptions } from 'antd';
import { ExclamationCircleOutlined, DeleteOutlined, DatabaseOutlined, ExperimentOutlined } from '@ant-design/icons';
import { adminApi } from '../../api/admin';

interface TruncatedTable {
  table: string;
  deleted: number;
}

interface ResetResult {
  message: string;
  truncated: TruncatedTable[];
  preserved: string[];
}

interface SampleResult {
  message: string;
  stats: { evidence: number; assessments: number; checklists: number; corrective_actions: number };
}

export default function DevTools() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ResetResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [sampleLoading, setSampleLoading] = useState(false);
  const [sampleResult, setSampleResult] = useState<SampleResult | null>(null);
  const [sampleError, setSampleError] = useState<string | null>(null);

  const handleReset = () => {
    Modal.confirm({
      title: '데이터 초기화',
      icon: <ExclamationCircleOutlined />,
      content: (
        <div>
          <p>
            <strong>다음 데이터가 모두 삭제됩니다:</strong>
          </p>
          <ul style={{ fontSize: 13, color: '#ff4d4f' }}>
            <li>준수 평가 이력 (compliance_snapshots)</li>
            <li>체크리스트 응답 (checklist_responses)</li>
            <li>증적 파일 및 연결 (evidence)</li>
            <li>개인정보 운영 데이터 (동의, DSR, 파기, 위탁, 사고)</li>
            <li>시정조치 (corrective_actions)</li>
            <li>Prowler/Config 스캔 결과</li>
            <li>알림, 감사 로그</li>
            <li>인증 토큰, 비밀번호 이력</li>
            <li>항목 담당자 배정</li>
          </ul>
          <p>
            <strong>유지되는 데이터:</strong>
          </p>
          <ul style={{ fontSize: 13, color: '#52c41a' }}>
            <li>사용자 계정</li>
            <li>ISMS-P 도메인/서브도메인/항목/체크리스트 (시드 데이터)</li>
            <li>클라우드 계정 설정</li>
          </ul>
        </div>
      ),
      okText: '초기화 실행',
      okType: 'danger',
      cancelText: '취소',
      width: 500,
      onOk: async () => {
        setLoading(true);
        setError(null);
        setResult(null);
        try {
          const res = await adminApi.resetData();
          setResult(res.data);
        } catch (err: any) {
          setError(err.response?.data?.detail || '초기화에 실패했습니다');
        } finally {
          setLoading(false);
        }
      },
    });
  };

  const handleGenerateSample = () => {
    Modal.confirm({
      title: '샘플 데이터 생성',
      icon: <ExperimentOutlined />,
      content: (
        <div>
          <p>ISMS-P 기능 데모를 위한 샘플 데이터를 생성합니다:</p>
          <ul style={{ fontSize: 13 }}>
            <li>증적 20건 (문서 + 외부 링크, 항목 연결 포함)</li>
            <li>체크리스트 응답 (전체 항목의 ~70%)</li>
            <li>준수 상태 평가 스냅샷</li>
            <li>시정조치 8건 (다양한 상태)</li>
          </ul>
          <Alert
            type="info"
            message="기존 데이터가 있으면 중복 생성될 수 있습니다. 초기화 후 실행을 권장합니다."
            showIcon
            style={{ marginTop: 8 }}
          />
        </div>
      ),
      okText: '샘플 생성',
      cancelText: '취소',
      width: 480,
      onOk: async () => {
        setSampleLoading(true);
        setSampleError(null);
        setSampleResult(null);
        try {
          const res = await adminApi.generateSampleData();
          setSampleResult(res.data);
        } catch (err: any) {
          setSampleError(err.response?.data?.detail || '샘플 생성에 실패했습니다');
        } finally {
          setSampleLoading(false);
        }
      },
    });
  };

  return (
    <div>
      <Typography.Title level={4} style={{ margin: 0, marginBottom: 16 }}>
        개발 도구
      </Typography.Title>

      <Alert
        type="warning"
        message="개발환경 전용 기능"
        description="이 페이지의 기능들은 APP_ENV=development 환경에서만 동작합니다. 운영환경에서는 403 에러가 반환됩니다."
        showIcon
        style={{ marginBottom: 24 }}
      />

      <Space direction="vertical" size={24} style={{ width: '100%', maxWidth: 700 }}>
        {/* 샘플 데이터 생성 */}
        <Card
          title={
            <Space>
              <ExperimentOutlined /> 샘플 데이터 생성
            </Space>
          }
        >
          <p style={{ marginBottom: 16 }}>
            ISMS-P 인증 항목 평가, 증적 등록, 시정조치 등 데모용 샘플 데이터를 생성합니다. 대시보드와 보고서 기능을
            확인하는 데 사용합니다.
          </p>

          <Button
            type="primary"
            icon={<ExperimentOutlined />}
            onClick={handleGenerateSample}
            loading={sampleLoading}
            size="large"
          >
            샘플 생성
          </Button>

          {sampleError && <Alert type="error" message={sampleError} style={{ marginTop: 16 }} showIcon />}

          {sampleResult && (
            <div style={{ marginTop: 24 }}>
              <Result status="success" title={sampleResult.message} />
              <Descriptions bordered size="small" column={2}>
                <Descriptions.Item label="증적">{sampleResult.stats.evidence}건</Descriptions.Item>
                <Descriptions.Item label="체크리스트 응답">{sampleResult.stats.checklists}건</Descriptions.Item>
                <Descriptions.Item label="준수 평가">{sampleResult.stats.assessments}건</Descriptions.Item>
                <Descriptions.Item label="시정조치">{sampleResult.stats.corrective_actions}건</Descriptions.Item>
              </Descriptions>
            </div>
          )}
        </Card>

        {/* 데이터 초기화 */}
        <Card
          title={
            <Space>
              <DatabaseOutlined /> 데이터 초기화
            </Space>
          }
        >
          <p style={{ marginBottom: 16 }}>
            모든 운영 데이터(평가 이력, 증적, 개인정보, 스캔 결과 등)를 삭제하고 시드 데이터(ISMS-P 101개 항목,
            체크리스트)만 유지합니다.
          </p>

          <Button type="primary" danger icon={<DeleteOutlined />} onClick={handleReset} loading={loading} size="large">
            초기화 실행
          </Button>

          {error && <Alert type="error" message={error} style={{ marginTop: 16 }} showIcon />}

          {result && (
            <div style={{ marginTop: 24 }}>
              <Result
                status="success"
                title={result.message}
                subTitle={`${result.truncated.length}개 테이블 초기화됨`}
              />
              {result.truncated.length > 0 && (
                <Table
                  dataSource={result.truncated}
                  rowKey="table"
                  size="small"
                  pagination={false}
                  columns={[
                    { title: '테이블', dataIndex: 'table', key: 'table' },
                    {
                      title: '삭제 건수',
                      dataIndex: 'deleted',
                      key: 'deleted',
                      render: (v: number) => <Tag color="red">{v}건 삭제</Tag>,
                    },
                  ]}
                />
              )}
              <div style={{ marginTop: 12 }}>
                <Typography.Text type="secondary">유지된 테이블: </Typography.Text>
                {result.preserved.map((t) => (
                  <Tag key={t} color="green" style={{ marginBottom: 4 }}>
                    {t}
                  </Tag>
                ))}
              </div>
            </div>
          )}
        </Card>
      </Space>
    </div>
  );
}
