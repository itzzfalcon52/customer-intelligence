import csv
import io
from collections.abc import Iterator
from uuid import UUID

import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlmodel import Session

from customer_intelligence.core.config import Settings
from customer_intelligence.main import create_app
from customer_intelligence.services.training import train_task


@pytest.fixture(scope="module")
def backend(tmp_path_factory) -> Iterator[dict]:
    settings = Settings(
        _env_file=None,
        data_directory=tmp_path_factory.mktemp("backend"),
        environment="test",
        nebius_model="test-model",
        nebius_api_key=SecretStr("test-key"),
        nebius_base_url="https://example.invalid/v1",
    )
    app = create_app(settings)
    with TestClient(app) as client:
        yield {"settings": settings, "app": app, "client": client}


@pytest.fixture(scope="module")
def trained(backend: dict) -> dict:
    rng = np.random.default_rng(42)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "customerID",
            "tenure",
            "Contract",
            "MonthlyCharges",
            "TotalCharges",
            "Churn",
            "segment",
            "Value",
        ]
    )
    for index in range(480):
        tenure = int(rng.integers(1, 73))
        spend = float(rng.integers(20, 120))
        churn = rng.random() < (0.65 if tenure < 20 else 0.15)
        writer.writerow(
            [
                f"C{index:04}",
                tenure,
                "Monthly" if index % 3 else "Annual",
                spend,
                "" if index % 21 == 0 else tenure * spend,
                "Yes" if churn else "No",
                "A" if index % 2 else "B",
                100 + index,
            ]
        )
    client = backend["client"]
    response = client.post(
        "/api/v1/datasets/upload", files={"file": ("training.csv", output.getvalue(), "text/csv")}
    )
    assert response.status_code == 201, response.text
    dataset_id = response.json()["id"]
    response = client.post(
        f"/api/v1/datasets/{dataset_id}/tasks",
        json={
            "target_column": "Churn",
            "positive_label": "Yes",
            "id_column": "customerID",
            "feature_columns": ["tenure", "Contract", "MonthlyCharges", "TotalCharges"],
            "features_available_at_prediction": True,
        },
    )
    assert response.status_code == 201, response.text
    task_id = response.json()["id"]
    with Session(backend["app"].state.engine) as session:
        path = train_task(session, backend["settings"], UUID(task_id))
    return {
        "dataset_id": dataset_id,
        "task_id": task_id,
        "run_id": path.name,
        "csv": output.getvalue(),
    }


@pytest.fixture
def execute_job(backend: dict, monkeypatch):
    from customer_intelligence.services.jobs import claim_job
    from customer_intelligence.worker import execute as worker

    monkeypatch.setattr(worker, "engine", backend["app"].state.engine)
    monkeypatch.setattr(worker, "get_settings", lambda: backend["settings"])

    def execute(job_id: str) -> dict:
        with Session(backend["app"].state.engine) as session:
            job = claim_job(session)
            assert job is not None and str(job.id) == job_id
        worker.execute(UUID(job_id))
        return backend["client"].get(f"/api/v1/jobs/{job_id}").json()

    return execute
