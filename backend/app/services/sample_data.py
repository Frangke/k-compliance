"""Generate sample data for demo/testing — ISMS-P assessments, evidence, corrective actions."""

import hashlib
import random
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.compliance import ChecklistResponse, ComplianceLevel, ComplianceSnapshot
from app.models.corrective import CorrectiveAction, CorrectiveSource, CorrectiveStatus
from app.models.evidence import Evidence, EvidenceItemLink, EvidenceStatus, EvidenceType
from app.models.isms import ISMSChecklist, ISMSItem
from app.models.user import User

# ── Evidence templates ──────────────────────────────────────────────
_EVIDENCE_TEMPLATES = [
    ("정보보호 정책서 v3.2", "document", "정보보호 정책 수립 및 승인 문서"),
    ("접근권한 관리 대장", "document", "사용자별 시스템 접근권한 현황"),
    ("암호화 적용 현황표", "document", "전송·저장 암호화 적용 현황"),
    ("취약점 점검 결과 보고서", "document", "분기별 인프라 취약점 스캔 결과"),
    ("보안 교육 수료 명단", "document", "연간 보안 인식 교육 수료 현황"),
    ("위험 평가 보고서 2026", "document", "연간 정보보호 위험 평가 결과"),
    ("물리적 보안 점검표", "document", "서버실 출입통제 및 환경 점검"),
    ("로그 모니터링 현황", "document", "보안 이벤트 모니터링 운영 현황"),
    ("백업/복구 테스트 결과", "document", "연간 재해복구 테스트 결과 보고"),
    ("네트워크 구성도 v2.1", "document", "보안 영역 분리 및 네트워크 토폴로지"),
    ("개인정보 처리방침 v4.0", "document", "공개된 개인정보 처리방침 최신 버전"),
    ("개인정보 영향평가 보고서", "document", "신규 시스템 개인정보 영향평가"),
    ("IAM 정책 검토 결과", "document", "AWS IAM 최소 권한 원칙 점검"),
    ("S3 버킷 보안 설정 현황", "document", "S3 퍼블릭 접근 차단 및 암호화 현황"),
    ("CloudTrail 활성화 증빙", "external_link", "AWS CloudTrail 콘솔 설정 캡처"),
    ("GuardDuty 운영 현황", "external_link", "Amazon GuardDuty 탐지 대시보드"),
    ("MFA 적용 현황 캡처", "external_link", "IAM 사용자 MFA 활성화 콘솔 캡처"),
    ("Config 규칙 현황", "external_link", "AWS Config 적합성 팩 결과"),
    ("VPC Flow Logs 설정", "external_link", "VPC 트래픽 로깅 설정 캡처"),
    ("WAF 규칙 설정 현황", "external_link", "AWS WAF 웹 ACL 규칙 설정"),
]

# ── Corrective action templates ─────────────────────────────────────
_CA_TEMPLATES = [
    ("IAM 루트 계정 MFA 미설정", "internal_review", "루트 계정에 MFA가 설정되어 있지 않음. 하드웨어 MFA 키 등록 필요."),
    ("S3 버킷 퍼블릭 접근 허용", "prowler", "일부 S3 버킷에 퍼블릭 접근이 허용됨. Block Public Access 설정 필요."),
    ("CloudTrail 로그 암호화 미적용", "config", "CloudTrail 로그 파일에 SSE-KMS 암호화가 적용되지 않음."),
    ("비밀번호 정책 미흡", "external_audit", "비밀번호 복잡도 정책이 ISMS-P 2.5.4 기준 미달. 3종 이상 조합 필요."),
    ("보안 교육 미이수자 존재", "internal_review", "연간 보안 교육 미이수자 3명 확인. 추가 교육 일정 수립 필요."),
    ("로그 보관 기간 부족", "external_audit", "보안 로그 보관 기간이 6개월로 설정되어 있으나, 1년 보관 필요."),
    ("DB 접근 제어 미흡", "internal_review", "데이터베이스 접근 제어 정책이 미비하여 불필요한 계정 접근 가능."),
    ("암호키 교체 주기 초과", "config", "KMS 키 자동 교체가 비활성화된 키 존재. 365일 주기 자동 교체 활성화 필요."),
]


async def generate_sample_data(db: AsyncSession, user: User) -> dict:
    """Generate realistic sample data for demo purposes."""
    now = datetime.now(UTC)
    today = date.today()
    stats = {"evidence": 0, "assessments": 0, "checklists": 0, "corrective_actions": 0}

    # ── 1. Load all items & checklists ────────────────────────
    all_items = (await db.execute(select(ISMSItem).order_by(ISMSItem.code))).scalars().all()

    if not all_items:
        return {"error": "ISMS-P 항목 시드 데이터가 없습니다. 시드 로드를 먼저 실행하세요."}

    # ── 2. Create evidence records ────────────────────────────
    evidence_ids = []
    for title, ev_type, desc in _EVIDENCE_TEMPLATES:
        ev = Evidence(
            title=title,
            description=desc,
            evidence_type=EvidenceType(ev_type),
            status=random.choice(
                [
                    EvidenceStatus.approved,
                    EvidenceStatus.approved,
                    EvidenceStatus.approved,
                    EvidenceStatus.submitted,
                    EvidenceStatus.draft,
                ]
            ),
            valid_from=today - timedelta(days=random.randint(30, 180)),
            valid_to=today + timedelta(days=random.randint(90, 365)) if random.random() > 0.3 else None,
            version=1,
            uploaded_by=user.id,
            file_hash=hashlib.sha256(title.encode()).hexdigest() if ev_type == "document" else None,
            file_name=f"{title.replace(' ', '_')}.pdf" if ev_type == "document" else None,
            file_size=random.randint(50000, 5000000) if ev_type == "document" else None,
            mime_type="application/pdf" if ev_type == "document" else None,
            external_url=f"https://console.aws.amazon.com/example/{title.replace(' ', '-').lower()}"
            if ev_type == "external_link"
            else None,
        )
        # Approved evidence gets review info
        if ev.status == EvidenceStatus.approved:
            ev.reviewed_by = user.id
            ev.reviewed_at = now - timedelta(days=random.randint(1, 30))
        db.add(ev)
        await db.flush()
        evidence_ids.append(ev.id)
        stats["evidence"] += 1

    # ── 3. Link evidence to items (M:N) ──────────────────────
    # Each evidence links to 1~4 related items
    linked_items_per_evidence = {}
    for ev_id in evidence_ids:
        num_links = random.randint(1, 4)
        linked = random.sample(all_items, min(num_links, len(all_items)))
        linked_items_per_evidence[ev_id] = [item.id for item in linked]
        for item in linked:
            db.add(
                EvidenceItemLink(
                    evidence_id=ev_id,
                    item_id=item.id,
                    linked_by=user.id,
                )
            )

    # ── 4. Checklist responses ────────────────────────────────
    # Respond to checklists for ~70% of items
    items_to_assess = random.sample(all_items, int(len(all_items) * 0.7))
    for item in items_to_assess:
        checklists = (await db.execute(select(ISMSChecklist).where(ISMSChecklist.item_id == item.id))).scalars().all()

        for cl in checklists:
            # 80% checked
            is_checked = random.random() < 0.8
            existing = (
                await db.execute(select(ChecklistResponse).where(ChecklistResponse.checklist_id == cl.id))
            ).scalar_one_or_none()
            if not existing:
                db.add(
                    ChecklistResponse(
                        checklist_id=cl.id,
                        is_checked=is_checked,
                        checked_by=user.id,
                        checked_at=now - timedelta(days=random.randint(1, 60)),
                    )
                )
                stats["checklists"] += 1

    await db.flush()

    # ── 5. Compliance assessments ─────────────────────────────
    # Create snapshots for ~65% of items over the last 3 months
    for item in items_to_assess:
        checklists = (await db.execute(select(ISMSChecklist).where(ISMSChecklist.item_id == item.id))).scalars().all()

        cl_total = len(checklists)
        cl_checked_count = 0
        cl_snapshot = []
        for cl in checklists:
            resp = (
                await db.execute(select(ChecklistResponse).where(ChecklistResponse.checklist_id == cl.id))
            ).scalar_one_or_none()
            checked = resp.is_checked if resp else False
            if checked:
                cl_checked_count += 1
            cl_snapshot.append(
                {
                    "question": cl.question,
                    "is_checked": checked,
                    "checked_by": user.name if checked else None,
                }
            )

        # Evidence counts for this item
        ev_count = (
            await db.execute(
                select(func.count()).select_from(EvidenceItemLink).where(EvidenceItemLink.item_id == item.id)
            )
        ).scalar()
        ev_approved = (
            await db.execute(
                select(func.count())
                .select_from(EvidenceItemLink)
                .join(Evidence)
                .where(
                    EvidenceItemLink.item_id == item.id,
                    Evidence.status == EvidenceStatus.approved,
                )
            )
        ).scalar()

        # Determine status based on checklist completion
        ratio = cl_checked_count / cl_total if cl_total > 0 else 0
        if ratio >= 0.8 and ev_approved > 0:
            status = ComplianceLevel.compliant
        elif ratio >= 0.5:
            status = ComplianceLevel.partial
        elif ratio > 0:
            status = ComplianceLevel.non_compliant
        else:
            status = random.choice([ComplianceLevel.non_compliant, ComplianceLevel.not_applicable])

        assessed_at = now - timedelta(days=random.randint(1, 90))
        db.add(
            ComplianceSnapshot(
                item_id=item.id,
                status=status,
                checklist_checked=cl_checked_count,
                checklist_total=cl_total,
                evidence_count=ev_count,
                evidence_approved=ev_approved,
                checklist_snapshot=cl_snapshot,
                notes=f"샘플 평가 데이터 — {item.code}",
                assessed_by=user.id,
                assessed_at=assessed_at,
            )
        )
        stats["assessments"] += 1

    # ── 6. Corrective actions ─────────────────────────────────
    ca_items = random.sample(all_items, min(len(_CA_TEMPLATES), len(all_items)))
    for i, (title, source, desc) in enumerate(_CA_TEMPLATES):
        item = ca_items[i]
        status = random.choice(
            [
                CorrectiveStatus.open,
                CorrectiveStatus.in_progress,
                CorrectiveStatus.completed,
                CorrectiveStatus.verified,
            ]
        )
        due = today + timedelta(days=random.randint(-15, 60))
        ca = CorrectiveAction(
            source=CorrectiveSource(source),
            source_detail=f"2026년 자체점검 #{i + 1}",
            isms_item_id=item.id,
            title=title,
            description=desc,
            action_plan=f"{title}에 대한 조치 계획: 담당자 지정 → 조치 수행 → 검증",
            due_date=due,
            status=status,
            assigned_to=user.id,
            created_by=user.id,
        )
        if status in (CorrectiveStatus.completed, CorrectiveStatus.verified):
            ca.result = f"{title} 조치 완료"
            ca.completed_at = now - timedelta(days=random.randint(1, 30))
        if status == CorrectiveStatus.verified:
            ca.verified_by = user.id
            ca.verified_at = now - timedelta(days=random.randint(0, 10))
            ca.verification_note = "조치 결과 확인 완료"

        db.add(ca)
        stats["corrective_actions"] += 1

    await db.commit()
    return stats
