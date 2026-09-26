"""Evidence upload + MIME validation (P1-6) smoke tests."""

from app.database import async_session
from app.models.evidence import Evidence
from sqlalchemy import delete, select


async def test_upload_rejects_elf_binary_masquerading_as_pdf(client, cpo_cookies):
    """An ELF binary renamed .pdf must 400 — validates the libmagic gate."""
    # /bin/ls is a reliable ELF file on Linux hosts.
    with open("/bin/ls", "rb") as f:
        binary = f.read()

    files = {"file": ("fake.pdf", binary, "application/pdf")}
    data = {"title": "pytest: fake pdf"}
    res = await client.post("/api/evidence/upload", files=files, data=data, cookies=cpo_cookies)
    assert res.status_code == 400
    assert "허용되지 않은" in res.json()["detail"]


async def test_upload_accepts_real_pdf(client, cpo_cookies):
    pdf_bytes = (
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Count 0>>endobj\n"
        b"xref\n0 3\n0000000000 65535 f\n%%EOF\n"
    )
    files = {"file": ("real.pdf", pdf_bytes, "application/pdf")}
    data = {"title": "pytest: real pdf"}
    res = await client.post("/api/evidence/upload", files=files, data=data, cookies=cpo_cookies)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["title"] == "pytest: real pdf"
    ev_id = body["id"]

    try:
        # Stored mime_type must come from detection, not from the client claim.
        async with async_session() as db:
            ev = (await db.execute(select(Evidence).where(Evidence.id == ev_id))).scalar_one()
            assert ev.mime_type == "application/pdf"
    finally:
        # Cleanup — delete the row and any on-disk artifact the upload path wrote.
        async with async_session() as db:
            await db.execute(delete(Evidence).where(Evidence.id == ev_id))
            await db.commit()


async def test_list_requires_auth(anon_client):
    res = await anon_client.get("/api/evidence")
    assert res.status_code == 401
