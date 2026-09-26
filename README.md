# K-Compliance

> PIPA(개인정보 보호법) 운영과 ISMS-P 인증심사 대응을 통합 관리하는 자사 전용 내부 웹 애플리케이션.

싱글 테넌트 내부 도구(~10명 사용자)로, ISMS-P 101개 인증항목의 증적 라이프사이클
(업로드 → 검토 → 항목 연결 → 준수 평가 → 심사 응답)과 PIPA 법정 기한(DSR 10일 /
침해사고 72시간 / 파기·위탁·시정조치)을 하나의 시스템에서 추적합니다. Prowler +
AWS Config로 자동 진단 결과를 ISMS-P 항목에 매핑하고, 심사 대응용 증적 패키지
ZIP·보고서 HTML을 원클릭으로 생성합니다.

## 로컬 실행

필요: Python 3.12, Node.js, PostgreSQL 18, libmagic (`python-magic`용 시스템 라이브러리)

```bash
# 1. DB (예: macOS Homebrew)
brew install postgresql@18 libmagic && brew services start postgresql@18
createuser kcompliance && createdb -O kcompliance kcompliance

# 2. 설정: .env.example을 루트 .env로 복사 후 값 채우기
#    (DATABASE_URL, DATABASE_URL_SYNC, JWT_SECRET_KEY, ENCRYPTION_KEY)

# 3. 백엔드
cd backend
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m app.seeds.load
.venv/bin/python -m app.cli create-admin <username> <email>   # 임시 비밀번호 출력
.venv/bin/python -m uvicorn app.main:app --reload --port 8000

# 4. 프론트엔드 (다른 터미널)
cd frontend && npm install && npm run dev
```

접속: http://localhost:5173 (API는 `/api` → :8000 프록시), Swagger: http://localhost:8000/docs

## 기술 스택

| 레이어 | 기술 |
|---|---|
| Backend | Python 3.12 · FastAPI · SQLAlchemy 2.0 (async) · Alembic · APScheduler |
| Frontend | React 18 · TypeScript · Vite · Ant Design 5 · @ant-design/charts |
| DB | PostgreSQL 18 |
| Storage | AWS S3 (SSE-S3) with local `uploads/` fallback |
| Scan | Prowler 5.x (ISMS-P 2023) · AWS Config (K-ISMS 적합성 팩) |

## 핵심 설계 원칙

1. **수동 증적 관리가 본체, 자동 진단은 보조.** 101개 항목 중 26개만 자동화 매핑됨 (Prowler 546 체크 + AWS Config 116 규칙).
2. **감사 추적 우선.** 모든 쓰기 엔드포인트(11개 파일, 약 90개 라우트)가 `audit_logs`에 기록합니다 (ISMS-P 2.9.3 / PIPA 제29조). 자기 담당 업무를 자기가 처리한 경우 `self_*` 플래그가 함께 남습니다 (직무분리 추적).
3. **법정 기한 엄수.** APScheduler(1 worker)가 매 시간 DSR/사고/파기/위탁/시정조치 기한 점검 + 자동 overdue 전이.
4. **연속 평가(Continuous Assessment).** AWS Audit Manager 철학 — 분기·반기 구분 없이 타임스탬프 기반 평가, 보고서 생성 시 날짜 범위 지정.
5. **증적 무결성.** SHA-256 해시 + S3 SSE + 심사 패키지 `MANIFEST.sha256`.

## 사용자 역할

- **CPO (Chief Privacy Officer)**: 모든 권한. 단일 슈퍼유저 역할. 직무분리 예외 시 audit_log에 `self_*` 플래그 기록.
- **security_officer**: ISMS-P 관리, 증적 검토, 스캔 실행, 보고서 생성.
- **privacy_handler**: PIPA 업무(DSR 처리, 파기 실행, 동의 관리) 담당. 대시보드는 "내 할 일" 위주.
- **auditor**: 읽기 전용. 감사 로그 조회 허용, 쓰기 권한 없음.

## 프로젝트 구조

```
k-compliance/
├── backend/              FastAPI 앱, Alembic 마이그레이션, 시드 데이터
│   ├── app/api/          18개 라우터 (auth, isms, evidence, pipa_*, prowler, ...)
│   ├── app/models/       SQLAlchemy 모델 (15개 파일, 30개+ 테이블)
│   ├── app/services/     audit, auth, crypto, aws_session, prowler_service, ...
│   ├── app/seeds/        KISA 공식 ISMS-P 101 items + Prowler/Config 매핑
│   ├── app/templates/    Jinja2 리포트 템플릿 3개
│   └── alembic/versions/ DB 마이그레이션
├── frontend/             React SPA (Vite)
│   ├── src/api/          axios 기반 REST 클라이언트
│   ├── src/pages/        페이지 컴포넌트 (ISMS, Evidence, PIPA, Prowler, ...)
│   └── src/components/   Layout, 공통 컴포넌트
```

## ISMS-P 숫자

| 항목 | 수량 |
|---|---|
| ISMS-P 인증항목 | 101개 (도메인 3 / 서브도메인 21) |
| 세부 체크리스트 | 328개 |
| Prowler 자동 체크 매핑 | 26개 항목, 546개 unique 체크 (1,236 인스턴스) |
| AWS Config 규칙 매핑 | 26개 항목 (K-ISMS 적합성 팩 116 규칙) |
| 시드 출처 | KISA 인증기준 안내서 (2023.11) + 세부점검항목 XLSX |

## 개발

- **테스트**: `cd backend && .venv/bin/python -m pytest` (백엔드), `cd frontend && npx tsc --noEmit` (타입체크)
- **마이그레이션 추가**: `cd backend && .venv/bin/python -m alembic revision --autogenerate -m "..."`
- **시드 로드**: idempotent upsert — 재실행해도 중복 없음
