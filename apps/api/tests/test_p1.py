from uuid import UUID, uuid4

import numpy as np
import pytest
from sqlmodel import Session

from customer_intelligence.core.errors import WorkflowError
from customer_intelligence.ml.evaluation import fit_and_compare_models
from customer_intelligence.models.conversation import AssistantLease
from customer_intelligence.services.analysis import final_evaluation
from customer_intelligence.services.runs import load_pipeline, read_training_run
from customer_intelligence.services.training import task_partitions


def submit(client, kind, payload):
    response = client.post(
        f"/api/v1/jobs/{kind}", json={**payload, "idempotency_key": str(uuid4())}
    )
    assert response.status_code == 202, response.text
    return response.json()


def test_calibration_serialization_freezing_comparison(backend, trained, execute_job):
    client = backend["client"]
    run_id = trained["run_id"]
    job = submit(client, "calibrate", {"run_id": run_id})
    result = execute_job(job["id"])
    assert result["state"] == "succeeded", result
    calibrated_id = result["result_id"]
    calibrated = read_training_run(UUID(calibrated_id), backend["settings"].data_directory)
    original = read_training_run(UUID(run_id), backend["settings"].data_directory)
    metadata = calibrated.calibration
    assert metadata is not None
    assert metadata["source_run_id"] == run_id
    fit = metadata["fit_row_assignments"]
    diagnostic = metadata["diagnostic_row_assignments"]
    assert not set(fit) & set(diagnostic)
    assert sorted(fit + diagnostic) == sorted(original.split.row_assignments["validation"])
    assert not set(fit + diagnostic) & set(original.split.row_assignments["test"])
    pipeline = load_pipeline(calibrated, backend["settings"].data_directory)
    with Session(backend["app"].state.engine) as session:
        task, _, frame = task_partitions(session, backend["settings"], UUID(trained["task_id"]))
        scores = pipeline.predict_proba(frame.head(10).loc[:, task.feature_columns])
    assert scores.shape == (10, 2) and np.isfinite(scores).all()
    compare = client.post("/api/v1/runs/compare", json={"run_ids": [run_id, calibrated_id]})
    assert compare.status_code == 200
    assert compare.json()["differences"] == ["calibration_status"]
    report = client.get(f"/api/v1/runs/{calibrated_id}/report")
    assert "sigmoid" in report.text and "before calibration" in report.text
    job = submit(client, "evaluate", {"run_id": calibrated_id})
    result = execute_job(job["id"])
    assert result["state"] == "succeeded", result
    evaluation = client.get(f"/api/v1/runs/{calibrated_id}/evaluation").json()
    assert evaluation["metrics"]["row_count"] == original.split.summary.test.row_count
    assert 0 <= evaluation["calibration_checks"]["brier_score"] <= 1
    for operation, payload in [
        ("train", {"task_id": trained["task_id"]}),
        ("calibrate", {"run_id": run_id}),
    ]:
        response = client.post(
            f"/api/v1/jobs/{operation}", json={**payload, "idempotency_key": str(uuid4())}
        )
        assert response.status_code == 409, response.text
    with Session(backend["app"].state.engine) as session:
        with pytest.raises(WorkflowError, match="Another run"):
            final_evaluation(session, backend["settings"], UUID(run_id))


def test_partial_candidate_failure_is_visible(backend, trained, monkeypatch):
    from customer_intelligence.ml import evaluation

    class FailedForest:
        def __init__(self, **kwargs):
            pass

        def fit(self, features, labels):
            raise ValueError("candidate failure")

    monkeypatch.setattr(evaluation, "RandomForestClassifier", FailedForest)
    with Session(backend["app"].state.engine) as session:
        task, split, frame = task_partitions(session, backend["settings"], UUID(trained["task_id"]))
    train = frame.iloc[split.row_assignments["train"]]
    valid = frame.iloc[split.row_assignments["validation"]]

    def labels(data):
        return [task.label_mapping[str(v)] for v in data[task.target_column]]

    result = fit_and_compare_models(
        train.loc[:, task.feature_columns],
        labels(train),
        valid.loc[:, task.feature_columns],
        labels(valid),
        task.feature_columns,
        task.random_seed,
    )
    assert len(result.results) == 3
    assert len(result.failures) == 1 and result.failures[0].model_name == "random_forest"
    assert result.best_pipeline is not None


def test_corrupt_scores_return_controlled_error(backend, trained, execute_job):
    client = backend["client"]
    job = submit(
        client,
        "score",
        {"run_id": trained["run_id"], "dataset_id": trained["dataset_id"], "contact_count": 5},
    )
    status = execute_job(job["id"])
    assert status["state"] == "succeeded", status
    path = backend["settings"].data_directory / "scores" / status["result_id"] / "rows.json"
    content = path.read_bytes()
    path.write_text("[]")
    try:
        response = client.get(f"/api/v1/scores/{status['result_id']}/customers")
        assert response.status_code == 409
        assert response.json()["code"] == "invalid_workflow"
    finally:
        path.write_bytes(content)


def test_active_assistant_blocks_deletion_and_cascade_removes_artifacts(backend, trained):
    client = backend["client"]
    key = str(uuid4())
    with Session(backend["app"].state.engine) as session:
        session.add(AssistantLease(idempotency_key=key, dataset_id=UUID(trained["dataset_id"])))
        session.commit()
    response = client.delete(f"/api/v1/datasets/{trained['dataset_id']}?cascade=true")
    assert response.status_code == 409 and "assistant" in response.text
    with Session(backend["app"].state.engine) as session:
        session.delete(session.get(AssistantLease, key))
        session.commit()
    response = client.delete(f"/api/v1/datasets/{trained['dataset_id']}?cascade=true")
    assert response.status_code == 204, response.text
    assert client.get(f"/api/v1/runs/{trained['run_id']}").status_code == 404
    assert client.get(f"/api/v1/tasks/{trained['task_id']}").status_code == 404
    assert not (
        backend["settings"].data_directory / "uploads" / f"{trained['dataset_id']}.csv"
    ).exists()
