"""Assessment entity smoke tests (P1-2):
- creation with audit_type + scope_mode
- scope auto-seeding (all_items = 101)
- validation guards (initial cannot have parent; subset requires codes)
- state machine (draft → active → closed)
"""

from app.database import async_session
from app.models.assessment import Assessment, AssessmentScopeItem
from sqlalchemy import delete


async def _cleanup(code: str):
    async with async_session() as db:
        rows = (await db.execute(_select_by_code(code))).all()
        for (aid,) in rows:
            await db.execute(delete(AssessmentScopeItem).where(AssessmentScopeItem.assessment_id == aid))
            await db.execute(delete(Assessment).where(Assessment.id == aid))
        await db.commit()


def _select_by_code(code: str):
    from sqlalchemy import select

    return select(Assessment.id).where(Assessment.code == code)


async def test_create_initial_seeds_all_items(client, cpo_cookies):
    code = "PYTEST-INIT-SEED"
    try:
        res = await client.post(
            "/api/assessments",
            json={
                "code": code,
                "name": "pytest initial",
                "audit_type": "initial",
                "scope_mode": "all_items",
                "period_start": "2026-01-01",
                "period_end": "2026-12-31",
            },
            cookies=cpo_cookies,
        )
        assert res.status_code == 201, res.text
        body = res.json()
        assert body["audit_type"] == "initial"
        assert body["scope_mode"] == "all_items"
        # 101 KISA items seeded into assessment_scope_items
        assert body["scope_total"] == 101
    finally:
        await _cleanup(code)


async def test_initial_cannot_have_parent(client, cpo_cookies):
    # Need a valid parent id — create one, then reject an initial with it as parent.
    parent_code = "PYTEST-PARENT"
    try:
        res = await client.post(
            "/api/assessments",
            json={
                "code": parent_code,
                "name": "pytest parent",
                "audit_type": "initial",
                "scope_mode": "subset",
                "scope_item_codes": ["2.1.1"],
                "period_start": "2026-01-01",
                "period_end": "2026-12-31",
            },
            cookies=cpo_cookies,
        )
        assert res.status_code == 201
        parent_id = res.json()["id"]

        bad = await client.post(
            "/api/assessments",
            json={
                "code": "PYTEST-BAD-INIT",
                "name": "bad",
                "audit_type": "initial",
                "scope_mode": "subset",
                "scope_item_codes": ["2.1.1"],
                "parent_assessment_id": parent_id,
                "period_start": "2027-01-01",
                "period_end": "2027-12-31",
            },
            cookies=cpo_cookies,
        )
        assert bad.status_code == 400
        assert "상위" in bad.json()["detail"]
    finally:
        await _cleanup(parent_code)
        await _cleanup("PYTEST-BAD-INIT")


async def test_subset_requires_codes(client, cpo_cookies):
    res = await client.post(
        "/api/assessments",
        json={
            "code": "PYTEST-SUBSET-MISSING",
            "name": "missing codes",
            "audit_type": "surveillance",
            "scope_mode": "subset",
            "period_start": "2026-01-01",
            "period_end": "2026-06-30",
        },
        cookies=cpo_cookies,
    )
    assert res.status_code == 400


async def test_state_machine_blocks_closed_regression(client, cpo_cookies):
    code = "PYTEST-STATE"
    try:
        create = await client.post(
            "/api/assessments",
            json={
                "code": code,
                "name": "pytest state",
                "audit_type": "initial",
                "scope_mode": "subset",
                "scope_item_codes": ["2.1.1", "2.1.2"],
                "period_start": "2026-01-01",
                "period_end": "2026-12-31",
            },
            cookies=cpo_cookies,
        )
        assert create.status_code == 201
        aid = create.json()["id"]

        # draft → active
        r1 = await client.post(f"/api/assessments/{aid}/transition", json={"status": "active"}, cookies=cpo_cookies)
        assert r1.status_code == 200
        assert r1.json()["status"] == "active"

        # active → closed
        r2 = await client.post(f"/api/assessments/{aid}/transition", json={"status": "closed"}, cookies=cpo_cookies)
        assert r2.status_code == 200
        assert r2.json()["status"] == "closed"

        # closed → active forbidden
        r3 = await client.post(f"/api/assessments/{aid}/transition", json={"status": "active"}, cookies=cpo_cookies)
        assert r3.status_code == 400
    finally:
        await _cleanup(code)
