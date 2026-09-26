"""Seed loader: Load ISMS-P 101 items + checklists into DB (upsert)."""

import asyncio
import json
from pathlib import Path

from sqlalchemy import select

from app.database import async_session
from app.models.isms import ISMSChecklist, ISMSDomain, ISMSItem, ISMSSubdomain

SEED_DIR = Path(__file__).parent


async def load_isms_items():
    with open(SEED_DIR / "isms_items.json", encoding="utf-8") as f:
        data = json.load(f)

    async with async_session() as db:
        domain_count = 0
        subdomain_count = 0
        item_count = 0
        checklist_count = 0

        for d_order, domain_data in enumerate(data["domains"], 1):
            # Upsert domain
            result = await db.execute(select(ISMSDomain).where(ISMSDomain.code == domain_data["code"]))
            domain = result.scalar_one_or_none()
            if not domain:
                domain = ISMSDomain(
                    code=domain_data["code"],
                    name=domain_data["name"],
                    description=domain_data.get("description", ""),
                    sort_order=d_order,
                )
                db.add(domain)
                await db.flush()
                domain_count += 1

            for s_order, sub_data in enumerate(domain_data.get("subdomains", []), 1):
                result = await db.execute(select(ISMSSubdomain).where(ISMSSubdomain.code == sub_data["code"]))
                subdomain = result.scalar_one_or_none()
                if not subdomain:
                    subdomain = ISMSSubdomain(
                        domain_id=domain.id,
                        code=sub_data["code"],
                        name=sub_data["name"],
                        description=sub_data.get("description", ""),
                        sort_order=s_order,
                    )
                    db.add(subdomain)
                    await db.flush()
                    subdomain_count += 1

                for i_order, item_data in enumerate(sub_data.get("items", []), 1):
                    result = await db.execute(select(ISMSItem).where(ISMSItem.code == item_data["code"]))
                    item = result.scalar_one_or_none()
                    if not item:
                        item = ISMSItem(
                            subdomain_id=subdomain.id,
                            code=item_data["code"],
                            name=item_data["name"],
                            description=item_data.get("description", ""),
                            required_evidence="\n".join(item_data.get("evidence_examples", [])),
                            has_prowler_checks=item_data.get("has_prowler_checks", False),
                            prowler_check_count=item_data.get("prowler_check_count", 0),
                            has_config_rules=item_data.get("has_config_rules", False),
                            sort_order=i_order,
                        )
                        db.add(item)
                        await db.flush()
                        item_count += 1

                    # Upsert checklists
                    for c_order, question in enumerate(item_data.get("checklists", []), 1):
                        result = await db.execute(
                            select(ISMSChecklist).where(
                                ISMSChecklist.item_id == item.id,
                                ISMSChecklist.sort_order == c_order,
                            )
                        )
                        if not result.scalar_one_or_none():
                            db.add(
                                ISMSChecklist(
                                    item_id=item.id,
                                    question=question,
                                    sort_order=c_order,
                                )
                            )
                            checklist_count += 1

        await db.commit()
        print("시드 로드 완료:")
        print(f"  도메인: {domain_count}개 추가")
        print(f"  서브도메인: {subdomain_count}개 추가")
        print(f"  항목: {item_count}개 추가")
        print(f"  체크리스트: {checklist_count}개 추가")


if __name__ == "__main__":
    asyncio.run(load_isms_items())
