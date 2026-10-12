import csv
import io
import os
import subprocess
import sys
from uuid import UUID, uuid4

import pytest
from sqlmodel import Session

from customer_intelligence.core.config import Settings
from customer_intelligence.main import create_app
from customer_intelligence.ml.diagnostics import contact_metrics
from customer_intelligence.ml.evaluation import evaluate_binary
from customer_intelligence.services.jobs import claim_job, recover_interrupted_jobs, submit_job
from customer_intelligence.services.runs import load_pipeline, read_training_run
from customer_intelligence.services.scoring import spreadsheet_safe


def submit(client, kind: str, payload: dict) -> dict:
    response = client.post(
        f"/api/v1/jobs/{kind}", json={**payload, "idempotency_key": str(uuid4())}
    )
    assert response.status_code == 202, response.text
    return response.json()


def test_real_upload_profile_split_and_saved_run(backend, trained):
    client = backend["client"]
    profile = client.get(f"/api/v1/datasets/{trained['dataset_id']}/profile")
    assert profile.status_code == 200
    report = client.get(f"/api/v1/runs/{trained['run_id']}").json()["report"]
    assert len(report["results"]) == 4 and report["test_evaluated"] is False
    assert report["best_validation_candidate_id"]
    manifest = read_training_run(UUID(trained["run_id"]), backend["settings"].data_directory)
    assignments = manifest.split.row_assignments
    assert sorted(assignments["train"] + assignments["validation"] + assignments["test"]) == list(
        range(480)
    )
    pipeline = load_pipeline(manifest, backend["settings"].data_directory)
    assert (
        pipeline.named_steps["preprocessing"].named_steps["schema"].feature_columns
        == manifest.task.feature_columns
    )


def test_idempotency_and_queued_cancellation(backend, trained):
    client = backend["client"]
    key = str(uuid4())
    payload = {"task_id": trained["task_id"], "idempotency_key": key}
    first = client.post("/api/v1/jobs/train", json=payload)
    repeat = client.post("/api/v1/jobs/train", json=payload)
    assert first.status_code == repeat.status_code == 202
    assert first.json()["id"] == repeat.json()["id"]
    conflict = client.post("/api/v1/jobs/train", json={**payload, "threshold": 0.3})
    assert conflict.status_code == 409
    result = client.post(f"/api/v1/jobs/{first.json()['id']}/cancel")
    assert result.json()["state"] == "cancelled"


def test_real_separate_worker_training(backend, trained):
    client = backend["client"]
    job = submit(client, "train", {"task_id": trained["task_id"], "search_trials": 1})
    env = {
        **os.environ,
        "CI_DATA_DIRECTORY": str(backend["settings"].data_directory),
        "CI_ENVIRONMENT": "test",
        "NEBIUS_API_KEY": "test-key",
        "NEBIUS_BASE_URL": "https://example.invalid/v1",
        "NEBIUS_MODEL": "test-model",
    }
    result = subprocess.run(
        [sys.executable, "-m", "customer_intelligence.worker", "--once"],
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stderr
    status = client.get(f"/api/v1/jobs/{job['id']}").json()
    assert status["state"] == "succeeded", status
    report = client.get(f"/api/v1/runs/{status['result_id']}").json()["report"]
    assert len(report["results"]) == 5 and not report["test_evaluated"]


def test_frozen_test_evaluation_is_cached(backend, trained, execute_job):
    client = backend["client"]
    job = submit(client, "evaluate", {"run_id": trained["run_id"]})
    assert execute_job(job["id"])["state"] == "succeeded"
    path = backend["settings"].data_directory / "runs" / trained["run_id"] / "evaluation.json"
    original = path.read_bytes()
    result = client.get(f"/api/v1/runs/{trained['run_id']}/evaluation").json()
    assert result["partition"] == "test" and result["metrics"]["row_count"] > 0
    repeated = submit(client, "evaluate", {"run_id": trained["run_id"]})
    assert execute_job(repeated["id"])["state"] == "succeeded"
    assert path.read_bytes() == original


def scoring_csv() -> str:
    return (
        "customerID,tenure,Contract,MonthlyCharges,TotalCharges,Value\n"
        "=SUM(1),12,Monthly,50,600,100\n"
        "C-new,12,Monthly,50,600,200\n"
        "C-unknown,45,Unseen,70,3150,300\n"
    )


def test_scoring_rank_export_and_p1(backend, trained, execute_job):
    client = backend["client"]
    uploaded = client.post(
        "/api/v1/datasets/upload", files={"file": ("current.csv", scoring_csv())}
    ).json()
    job = submit(
        client,
        "score",
        {
            "run_id": trained["run_id"],
            "dataset_id": uploaded["id"],
            "contact_count": 2,
            "value_column": "Value",
            "value_unit": "INR",
            "ranking": "risk_x_value",
        },
    )
    status = execute_job(job["id"])
    assert status["state"] == "succeeded", status
    score_id = status["result_id"]
    manifest = client.get(f"/api/v1/scores/{score_id}").json()
    assert manifest["row_count"] == 3 and any("unseen" in w for w in manifest["warnings"])
    page = client.get(f"/api/v1/scores/{score_id}/customers?limit=2").json()
    assert len(page["customers"]) == 2 and page["total"] == 3
    full = client.get(f"/api/v1/scores/{score_id}/customers").json()["customers"]
    assert sorted(row["row_reference"] for row in full) == [1, 2, 3]
    assert [row["priority_rank"] for row in full] == [1, 2, 3]
    text = client.get(f"/api/v1/scores/{score_id}/export").text
    exported = list(csv.DictReader(io.StringIO(text)))
    assert any(row["customer_id"] == "'=SUM(1)" for row in exported)
    assert (
        len(
            list(
                csv.DictReader(
                    io.StringIO(client.get(f"/api/v1/scores/{score_id}/export?top_k=2").text)
                )
            )
        )
        == 2
    )
    explanation = submit(client, "explain", {"score_id": score_id, "row_reference": 1})
    result = execute_job(explanation["id"])
    assert result["state"] == "succeeded", result
    effects = client.get(f"/api/v1/analyses/{result['result_id']}").json()
    assert (
        effects["method"] == "one_feature_reference_perturbation" and len(effects["effects"]) == 4
    )


def test_diagnostics_segments_heuristic_and_leakage(backend, trained, execute_job):
    client = backend["client"]
    job = submit(
        client,
        "diagnostics",
        {
            "run_id": trained["run_id"],
            "segment_column": "segment",
            "heuristic_column": "tenure",
            "heuristic_direction": "lower_risk",
        },
    )
    status = execute_job(job["id"])
    assert status["state"] == "succeeded", status
    result = client.get(f"/api/v1/analyses/{status['result_id']}").json()
    assert len(result["permutation_importance"]) == 4
    assert len(result["segments"]) == 2 and result["heuristic"]["average_precision"] >= 0
    assert result["calibration"]["calibration_fitted"] is False
    assert result["contact_curve"][-1]["recall"] == 1
    job = submit(client, "leakage-demo", {"task_id": trained["task_id"]})
    status = execute_job(job["id"])
    assert status["state"] == "succeeded", status
    demo = client.get(f"/api/v1/analyses/{status['result_id']}").json()
    assert demo["results"]["with_leakage"]["average_precision"] == 1
    assert demo["test_evaluated"] is False
    report = client.get(f"/api/v1/runs/{trained['run_id']}/report")
    assert report.status_code == 200 and "Frozen final test evaluation" in report.text


def test_missing_features_fail_job_without_losing_rows(backend, trained, execute_job):
    client = backend["client"]
    response = client.post(
        "/api/v1/datasets/upload", files={"file": ("bad.csv", "customerID,tenure\nA,3\nB,4\n")}
    )
    job = submit(
        client,
        "score",
        {"run_id": trained["run_id"], "dataset_id": response.json()["id"], "contact_count": 1},
    )
    status = execute_job(job["id"])
    assert status["state"] == "failed" and "missing" in status["error"].lower()


def test_corrupted_model_and_manifest_are_rejected(backend, trained):
    settings = backend["settings"]
    run_id = UUID(trained["run_id"])
    run = read_training_run(run_id, settings.data_directory)
    path = settings.data_directory / "runs" / str(run_id) / "pipeline.joblib"
    original = path.read_bytes()
    try:
        path.write_bytes(original + b"changed")
        with pytest.raises(ValueError, match="checksum"):
            load_pipeline(run, settings.data_directory)
    finally:
        path.write_bytes(original)
    bad_id = uuid4()
    folder = settings.data_directory / "runs" / str(bad_id)
    folder.mkdir()
    (folder / "manifest.json").write_text("{broken")
    assert backend["client"].get(f"/api/v1/runs/{bad_id}").status_code == 409
    import shutil

    shutil.rmtree(folder)


def test_metrics_and_formula_escaping():
    metrics = evaluate_binary([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9])
    assert metrics.average_precision == metrics.roc_auc == 1
    contact = contact_metrics([1, 0, 1, 0], [0.8, 0.8, 0.7, 0.1], 1)
    assert contact.true_positive == 1 and contact.lift == 2
    assert evaluate_binary([0, 0, 0, 1], [0.25] * 4).precision is None
    for text in ["=cmd", " +cmd", "-1", "@cmd", "\ttext"]:
        assert spreadsheet_safe(text).startswith("'")
    assert spreadsheet_safe("C001") == "C001"


def test_recovery_and_deletion_policy(backend, trained):
    client = backend["client"]
    assert client.delete(f"/api/v1/datasets/{trained['dataset_id']}").status_code == 409
    with Session(backend["app"].state.engine) as session:
        session.info["settings"] = backend["settings"]
        job = submit_job(
            session,
            "leakage",
            {
                "task_id": trained["task_id"],
                "search_trials": 0,
                "threshold": 0.5,
            },
            uuid4(),
        )
        job_id = job.id
        claimed = claim_job(session)
        assert claimed and claimed.id == job_id
        assert recover_interrupted_jobs(session) == 1
    assert client.get(f"/api/v1/jobs/{job_id}").json()["state"] == "failed"
    fresh = client.post(
        "/api/v1/datasets/upload", files={"file": ("delete.csv", "id,x\nA,1\n")}
    ).json()["id"]
    assert client.delete(f"/api/v1/datasets/{fresh}").status_code == 204
    assert client.get(f"/api/v1/datasets/{fresh}").status_code == 404
    assert not (backend["settings"].data_directory / "uploads" / f"{fresh}.csv").exists()


def test_api_token_and_invalid_inputs(tmp_path):
    from fastapi.testclient import TestClient
    from pydantic import SecretStr

    settings = Settings(_env_file=None, data_directory=tmp_path, api_token=SecretStr("private"))
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/health").status_code == 200
        assert client.get("/api/v1/datasets").status_code == 401
        assert (
            client.get("/api/v1/datasets", headers={"Authorization": "Bearer private"}).status_code
            == 200
        )
        assert (
            client.post(
                "/api/v1/jobs/train",
                headers={"Authorization": "Bearer private", "Origin": "https://untrusted.example"},
                json={},
            ).status_code
            == 403
        )
        assert (
            client.get("/api/v1/jobs/bad", headers={"Authorization": "Bearer private"}).status_code
            == 422
        )
    with pytest.raises(RuntimeError):
        create_app(Settings(_env_file=None, data_directory=tmp_path, environment="production"))


def test_excel_import_and_rejection(backend):
    from openpyxl import Workbook

    def workbook_bytes(formula=False, multiple=False):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["customerID", "tenure"])
        sheet.append(["001", "=1+1" if formula else 2])
        if multiple:
            workbook.create_sheet("other")
        output = io.BytesIO()
        workbook.save(output)
        return output.getvalue()

    client = backend["client"]
    valid = client.post(
        "/api/v1/datasets/upload", files={"file": ("customers.xlsx", workbook_bytes())}
    )
    assert valid.status_code == 201, valid.text
    assert valid.json()["column_count"] == 2
    assert (
        client.post(
            "/api/v1/datasets/upload", files={"file": ("formula.xlsx", workbook_bytes(True))}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/v1/datasets/upload",
            files={"file": ("sheets.xlsx", workbook_bytes(multiple=True))},
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/v1/datasets/upload?sheet_name=Sheet",
            files={"file": ("sheets.xlsx", workbook_bytes(multiple=True))},
        ).status_code
        == 201
    )


def test_bad_csv_and_target_rejected(backend, trained):
    client = backend["client"]
    assert (
        client.post(
            "/api/v1/datasets/upload", files={"file": ("bad.csv", "a,a\n1,2\n")}
        ).status_code
        == 400
    )
    assert (
        client.post(
            f"/api/v1/datasets/{trained['dataset_id']}/tasks",
            json={
                "target_column": "Churn",
                "positive_label": "Yes",
                "feature_columns": ["Churn"],
                "features_available_at_prediction": True,
            },
        ).status_code
        == 400
    )
