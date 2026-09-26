import asyncio
import logging
from contextlib import asynccontextmanager

from apscheduler.events import EVENT_JOB_ERROR
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin as admin_router
from app.api import assessments as assessments_router
from app.api import audit_logs as audit_router_api
from app.api import auth as auth_router
from app.api import aws_config as aws_config_router
from app.api import corrective_actions, pipa_consent, pipa_destruction, pipa_dsr, pipa_incident, pipa_third_party
from app.api import dashboard as dashboard_router
from app.api import evidence as evidence_router
from app.api import isms as isms_router
from app.api import notifications as notifications_router
from app.api import prowler as prowler_router
from app.api import reports as reports_router
from app.api import users as users_router
from app.config import settings
from app.database import async_session
from app.models.audit import AuditLog
from app.services.deadline_tracker import check_deadlines

logger = logging.getLogger("k-compliance")
scheduler = AsyncIOScheduler()


async def _persist_scheduler_error(job_id: str, exc_text: str, traceback_text: str | None) -> None:
    """Write a scheduler.error row so a silent APScheduler failure is traceable.

    Called via asyncio.create_task from the (sync) job-error listener.
    """
    try:
        async with async_session() as db:
            db.add(
                AuditLog(
                    user_id=None,
                    action="scheduler.error",
                    entity_type="scheduler_job",
                    entity_id=None,
                    new_values={
                        "job_id": job_id,
                        "error": exc_text,
                        "traceback": (traceback_text or "")[:4000],
                    },
                )
            )
            await db.commit()
    except Exception:
        logger.exception("Failed to persist scheduler.error audit row")


def _on_scheduler_job_error(event) -> None:
    """APScheduler EVENT_JOB_ERROR listener — runs on the loop thread."""
    exc = event.exception
    exc_text = f"{type(exc).__name__}: {exc}"[:1000] if exc else "unknown"
    logger.exception(
        "Scheduler job %s failed: %s",
        event.job_id,
        exc_text,
        exc_info=exc,
    )
    try:
        asyncio.get_running_loop().create_task(_persist_scheduler_error(event.job_id, exc_text, event.traceback))
    except RuntimeError:
        # No running loop (shouldn't happen with AsyncIOScheduler) — drop to
        # avoid crashing the scheduler thread; journal still has the traceback.
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    scheduler.add_job(check_deadlines, "cron", minute=0, id="check_deadlines", replace_existing=True)
    scheduler.add_listener(_on_scheduler_job_error, EVENT_JOB_ERROR)
    scheduler.start()
    logger.info("APScheduler started (hourly deadline check)")
    yield
    # Shutdown
    scheduler.shutdown(wait=False)
    logger.info("APScheduler stopped")


app = FastAPI(
    title="K-Compliance",
    description="PIPA/ISMS-P 컴플라이언스 관리 시스템",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth_router.router)
app.include_router(users_router.router)
app.include_router(audit_router_api.router)
app.include_router(isms_router.router)
app.include_router(evidence_router.router)
app.include_router(pipa_consent.router)
app.include_router(pipa_dsr.router)
app.include_router(pipa_destruction.router)
app.include_router(pipa_third_party.router)
app.include_router(pipa_incident.router)
app.include_router(corrective_actions.router)
app.include_router(notifications_router.router)
app.include_router(prowler_router.router)
app.include_router(aws_config_router.router)
app.include_router(dashboard_router.router)
app.include_router(reports_router.router)
app.include_router(assessments_router.router)
app.include_router(admin_router.router)


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "env": settings.APP_ENV}
