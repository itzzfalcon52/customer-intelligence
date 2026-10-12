from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlmodel import Session

from customer_intelligence.services.jobs import cancel_job, submit_job


def new_task(backend, trained) -> str:
    original = backend["client"].get(f"/api/v1/tasks/{trained['task_id']}").json()
    response = backend["client"].post(
        f"/api/v1/datasets/{trained['dataset_id']}/tasks",
        json={
            key: original[key]
            for key in (
                "target_column",
                "positive_label",
                "id_column",
                "feature_columns",
                "features_available_at_prediction",
            )
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_concurrent_submission_has_one_job(backend, trained):
    task_id = new_task(backend, trained)
    key = uuid4()

    def submit():
        with Session(backend["app"].state.engine) as session:
            session.info["settings"] = backend["settings"]
            return submit_job(
                session, "train", {"task_id": task_id, "search_trials": 0, "threshold": 0.5}, key
            ).id

    with ThreadPoolExecutor(max_workers=4) as executor:
        ids = list(executor.map(lambda _: submit(), range(8)))
    assert len(set(ids)) == 1
    backend["client"].post(f"/api/v1/jobs/{ids[0]}/cancel")


@pytest.mark.parametrize("cancel", [False, True])
def test_supervisor_stops_process_on_timeout_or_cancellation(backend, trained, monkeypatch, cancel):
    from customer_intelligence.worker import __main__ as worker

    task_id = new_task(backend, trained)
    with Session(backend["app"].state.engine) as session:
        session.info["settings"] = backend["settings"]
        job_id = submit_job(
            session, "train", {"task_id": task_id, "search_trials": 0, "threshold": 0.5}, uuid4()
        ).id

    class Child:
        terminated = False

        def poll(self):
            return 0 if self.terminated else None

        def terminate(self):
            self.terminated = True

        def wait(self, timeout=None):
            return 0

        def kill(self):
            self.terminated = True

    child = Child()

    def start(*args, **kwargs):
        if cancel:
            with Session(backend["app"].state.engine) as session:
                cancel_job(session, job_id)
        return child

    monkeypatch.setattr(worker, "engine", backend["app"].state.engine)
    monkeypatch.setattr(worker, "get_settings", lambda: backend["settings"])
    monkeypatch.setattr(worker.subprocess, "Popen", start)
    moments = iter([0, 601, 602])
    monkeypatch.setattr(worker, "monotonic", lambda: next(moments))
    assert worker.run_once()
    assert child.terminated
    status = backend["client"].get(f"/api/v1/jobs/{job_id}").json()
    assert status["state"] == ("cancelled" if cancel else "failed")


def test_queue_is_bounded(backend, trained):
    task_id = new_task(backend, trained)
    ids = []
    try:
        for _ in range(20):
            response = backend["client"].post(
                "/api/v1/jobs/train", json={"task_id": task_id, "idempotency_key": str(uuid4())}
            )
            assert response.status_code == 202
            ids.append(response.json()["id"])
        response = backend["client"].post(
            "/api/v1/jobs/train", json={"task_id": task_id, "idempotency_key": str(uuid4())}
        )
        assert response.status_code == 429
    finally:
        for job_id in ids:
            backend["client"].post(f"/api/v1/jobs/{job_id}/cancel")


def test_spawn_failure_is_persisted(backend, trained, monkeypatch):
    from customer_intelligence.worker import __main__ as worker

    task_id = new_task(backend, trained)
    response = backend["client"].post(
        "/api/v1/jobs/train", json={"task_id": task_id, "idempotency_key": str(uuid4())}
    )
    job_id = response.json()["id"]

    def fail(*args, **kwargs):
        raise OSError("spawn failure")

    monkeypatch.setattr(worker, "engine", backend["app"].state.engine)
    monkeypatch.setattr(worker, "get_settings", lambda: backend["settings"])
    monkeypatch.setattr(worker.subprocess, "Popen", fail)
    assert worker.run_once()
    result = backend["client"].get(f"/api/v1/jobs/{job_id}").json()
    assert result["state"] == "failed" and "start" in result["error"]
