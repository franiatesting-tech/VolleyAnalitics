from volley_domain.models import JobStatus, Match, MatchStatus, ProcessingJob
from volley_domain.ontology import Action, ModelRun
from volley_domain.ontology import MatchSet as MatchSetRow


def _seed_match_and_job(session_factory, match_id="m1", dedup_key="m1:process_demo_match:v1"):
    with session_factory() as db:
        db.add(
            Match(
                id=match_id,
                organization_id="org1",
                home_team="Alpha",
                away_team="Beta",
                status=MatchStatus.PROCESSING,
                created_by_user_id="user1",
            )
        )
        db.add(
            ProcessingJob(
                id="job1",
                match_id=match_id,
                organization_id="org1",
                task_name="process_demo_match",
                dedup_key=dedup_key,
                status=JobStatus.QUEUED,
                progress=0,
            )
        )
        db.commit()


def test_process_demo_match_completes_and_persists_result(sqlite_session_factory):
    from volley_worker.tasks import process_demo_match

    _seed_match_and_job(sqlite_session_factory)

    result = process_demo_match.run(match_id="m1", dedup_key="m1:process_demo_match:v1")

    assert result["status"] == "completed"

    with sqlite_session_factory() as db:
        job = db.query(ProcessingJob).filter_by(id="job1").one()
        assert job.status == JobStatus.COMPLETED
        assert job.progress == 100
        assert job.result_data is not None
        assert job.result_data["home_roster"]["team_name"] == "Alpha"

        match = db.get(Match, "m1")
        assert match.status == MatchStatus.COMPLETED


def test_process_demo_match_persists_the_real_ontology_not_just_the_json_blob(
    sqlite_session_factory,
):
    """The whole point of wiring persist_synthetic_match into this task:
    completion must leave real MatchSet/Action/ModelRun rows behind, not
    just the Phase 1 JSON blob -- see ADR-004."""
    from volley_worker.tasks import process_demo_match

    _seed_match_and_job(sqlite_session_factory)
    result = process_demo_match.run(match_id="m1", dedup_key="m1:process_demo_match:v1")
    assert result["status"] == "completed"

    with sqlite_session_factory() as db:
        job = db.query(ProcessingJob).filter_by(id="job1").one()
        assert job.pipeline_run_id is not None

        sets = db.query(MatchSetRow).filter_by(match_id="m1").all()
        assert len(sets) > 0

        model_run = db.query(ModelRun).filter_by(pipeline_run_id=job.pipeline_run_id).one()
        actions = db.query(Action).filter_by(model_run_id=model_run.id).all()
        assert len(actions) > 0


def test_process_demo_match_is_idempotent_on_redelivery(sqlite_session_factory):
    from volley_worker.tasks import process_demo_match

    _seed_match_and_job(sqlite_session_factory)
    first = process_demo_match.run(match_id="m1", dedup_key="m1:process_demo_match:v1")

    with sqlite_session_factory() as db:
        first_result_data = db.query(ProcessingJob).filter_by(id="job1").one().result_data

    # Simulate Celery redelivering the same message (e.g. broker ack lost).
    second = process_demo_match.run(match_id="m1", dedup_key="m1:process_demo_match:v1")

    assert second["status"] == "already_completed"
    with sqlite_session_factory() as db:
        second_result_data = db.query(ProcessingJob).filter_by(id="job1").one().result_data
    assert first_result_data == second_result_data
    assert first["job_id"] == "job1"


def test_redelivery_does_not_duplicate_ontology_rows(sqlite_session_factory):
    """persist_synthetic_match itself has no dedup check -- it's the task's
    top-level "already COMPLETED" short-circuit that must prevent a second
    call on redelivery. This proves that guard actually protects the
    ontology-persistence path, not just the JSON blob."""
    from volley_worker.tasks import process_demo_match

    _seed_match_and_job(sqlite_session_factory)
    process_demo_match.run(match_id="m1", dedup_key="m1:process_demo_match:v1")

    with sqlite_session_factory() as db:
        sets_after_first = db.query(MatchSetRow).filter_by(match_id="m1").count()

    process_demo_match.run(match_id="m1", dedup_key="m1:process_demo_match:v1")

    with sqlite_session_factory() as db:
        sets_after_second = db.query(MatchSetRow).filter_by(match_id="m1").count()

    assert sets_after_second == sets_after_first


def test_process_demo_match_raises_if_job_row_missing(sqlite_session_factory):
    from volley_worker.tasks import process_demo_match

    with sqlite_session_factory() as db:
        db.add(
            Match(
                id="m2",
                organization_id="org1",
                home_team="A",
                away_team="B",
                created_by_user_id="user1",
            )
        )
        db.commit()

    try:
        process_demo_match.run(match_id="m2", dedup_key="does-not-exist")
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_same_match_id_produces_same_synthetic_seed_across_runs(sqlite_session_factory):
    """Retrying a genuinely failed job for the same match should regenerate
    the *same* synthetic data, not a random new match each time."""
    from volley_worker.tasks import _seed_from_match_id

    assert _seed_from_match_id("m1") == _seed_from_match_id("m1")
    assert _seed_from_match_id("m1") != _seed_from_match_id("m2")
