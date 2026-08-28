"""PROCESS_DEMO_MATCH: the Phase-1 stand-in pipeline job. Generates a
deterministic synthetic match (see volley_domain.synthetic) and persists it,
so the rest of the product (Match Analysis, Rally Explorer, stats views) can
be built before any real CV pipeline exists.

Idempotency / no-duplicate-results: the task is looked up by `dedup_key`
(one row per match, created by the API before enqueueing -- see
services/api/src/volley_api/api/routes/matches.py). If that row is already
COMPLETED with result data, this is a no-op: a redelivered/retried Celery
message must never regenerate a different result or create a second job row.

Retry policy: every exception in the try block below is caught and turned
into a manual `self.retry()` -- deliberately, so a transient DB/broker
hiccup and a genuine bug get the same bounded-retry-then-fail treatment
without needing to enumerate every transient exception type Celery's
`autoretry_for` would otherwise require (and silently stop matching the day
a new transient failure mode shows up in a type it doesn't list).
"""

import hashlib

import structlog
from volley_domain.models import JobStatus, Match, MatchStatus, ProcessingJob
from volley_domain.synthetic import generate_synthetic_match
from volley_domain.tasks import PROCESS_DEMO_MATCH_TASK_NAME

from volley_worker.celery_app import celery_app
from volley_worker.db import session_scope

logger = structlog.get_logger(__name__)


def _seed_from_match_id(match_id: str) -> int:
    """Deterministic per-match seed so re-running the same match (after a
    genuine failure + retry) produces the same synthetic data, not a
    different random match each time."""
    return int(hashlib.sha256(match_id.encode()).hexdigest(), 16) % (2**31)


@celery_app.task(
    bind=True,
    name=PROCESS_DEMO_MATCH_TASK_NAME,
    max_retries=3,
    default_retry_delay=10,
)
def process_demo_match(self, match_id: str, dedup_key: str) -> dict:
    log = logger.bind(match_id=match_id, dedup_key=dedup_key, celery_task_id=self.request.id)

    with session_scope() as db:
        job = db.query(ProcessingJob).filter_by(dedup_key=dedup_key).one_or_none()
        if job is None:
            # The API always creates the row before enqueueing -- an absent
            # row means something upstream is broken. Fail loud, don't
            # silently create an orphaned job here.
            log.error("process_demo_match_missing_job_row")
            raise ValueError(f"No ProcessingJob found for dedup_key={dedup_key}")

        if job.status == JobStatus.COMPLETED and job.result_data is not None:
            log.info("process_demo_match_already_completed_noop")
            return {"status": "already_completed", "job_id": job.id}

        job.status = JobStatus.RUNNING
        job.stage = "generating"
        job.progress = 10
        job.celery_task_id = self.request.id

        match = db.get(Match, match_id)
        home_team = match.home_team if match else "Home"
        away_team = match.away_team if match else "Away"

    try:
        synthetic = generate_synthetic_match(
            seed=_seed_from_match_id(match_id), home_team=home_team, away_team=away_team
        )

        with session_scope() as db:
            job = db.query(ProcessingJob).filter_by(dedup_key=dedup_key).one()
            job.progress = 70
            job.stage = "saving"

        result_data = synthetic.model_dump(mode="json")

        with session_scope() as db:
            job = db.query(ProcessingJob).filter_by(dedup_key=dedup_key).one()
            job.status = JobStatus.COMPLETED
            job.progress = 100
            job.stage = "completed"
            job.result_data = result_data

            match = db.get(Match, match_id)
            if match:
                match.status = MatchStatus.COMPLETED

        rally_count = sum(len(s["rallies"]) for s in result_data["sets"])
        log.info("process_demo_match_completed", rally_count=rally_count)
        return {"status": "completed", "job_id": job.id}

    except Exception as exc:
        log.exception("process_demo_match_failed")
        with session_scope() as db:
            job = db.query(ProcessingJob).filter_by(dedup_key=dedup_key).one_or_none()
            if job:
                job.status = JobStatus.FAILED
                job.error = str(exc)
            match = db.get(Match, match_id)
            if match:
                match.status = MatchStatus.FAILED
        raise self.retry(exc=exc) from exc
