"""Run an explicitly synthetic workflow against a running local API and worker."""

import argparse
import csv
import io
import json
import os
import random
import time
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import httpx


def synthetic_csv(labeled: bool) -> bytes:
    rng = random.Random(42 if labeled else 43)
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    header = ["customerID", "tenure", "Contract", "MonthlyCharges", "TotalCharges", "Value"]
    writer.writerow(header + (["Churn"] if labeled else []))
    for index in range(600 if labeled else 24):
        tenure = rng.randint(1, 72)
        charges = rng.randint(20, 120)
        contract = "Monthly" if index % 3 else "Annual"
        row = [
            f"SYN-{'H' if labeled else 'C'}-{index:04d}",
            tenure,
            contract,
            charges,
            "" if index % 21 == 0 else tenure * charges,
            charges * 12,
        ]
        risk = 0.65 if tenure < 20 and contract == "Monthly" else 0.25
        writer.writerow(row + (["Yes" if rng.random() < risk else "No"] if labeled else []))
    return output.getvalue().encode()


def run(base_url: str, output: Path, with_agent: bool, calibrate: bool) -> dict:
    if urlparse(base_url).hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("This demo is intended for a local API URL.")
    token = os.environ.get("CI_API_TOKEN")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    output = output / str(uuid4())
    output.mkdir(parents=True)
    with httpx.Client(base_url=base_url.rstrip("/") + "/", headers=headers, timeout=100) as client:

        def request(method: str, path: str, **kwargs) -> httpx.Response:
            response = client.request(method, "api/v1/" + path, **kwargs)
            if response.is_error:
                raise RuntimeError(f"{path}: HTTP {response.status_code}: {response.text[:500]}")
            return response

        def job(kind: str, payload: dict) -> str:
            record = request(
                "POST", "jobs/" + kind, json={**payload, "idempotency_key": str(uuid4())}
            ).json()
            deadline = time.monotonic() + 640
            while time.monotonic() < deadline:
                state = request("GET", "jobs/" + record["id"]).json()
                if state["state"] == "succeeded":
                    return state["result_id"]
                if state["state"] in {"failed", "cancelled"}:
                    raise RuntimeError(f"{kind}: {state['state']}: {state['error']}")
                time.sleep(0.3)
            raise RuntimeError("Job did not finish. Check that the worker is running.")

        request("GET", "health")
        history = synthetic_csv(True)
        current = synthetic_csv(False)
        (output / "synthetic-history.csv").write_bytes(history)
        (output / "synthetic-current.csv").write_bytes(current)
        dataset = request(
            "POST",
            "datasets/upload",
            files={"file": ("synthetic-history.csv", history, "text/csv")},
        ).json()["id"]
        profile = request("GET", f"datasets/{dataset}/profile").json()
        task = request(
            "POST",
            f"datasets/{dataset}/tasks",
            json={
                "target_column": "Churn",
                "positive_label": "Yes",
                "id_column": "customerID",
                "feature_columns": ["tenure", "Contract", "MonthlyCharges", "TotalCharges"],
                "features_available_at_prediction": True,
            },
        ).json()["id"]
        request("GET", f"tasks/{task}/plan")
        print("Synthetic historical data uploaded; training four candidates...", flush=True)
        run_id = job("train", {"task_id": task, "search_trials": 0, "threshold": 0.5})
        diagnostics_id = job(
            "diagnostics",
            {
                "run_id": run_id,
                "segment_column": "Contract",
                "heuristic_column": "tenure",
                "heuristic_direction": "lower_risk",
            },
        )
        diagnostics = request("GET", f"analyses/{diagnostics_id}").json()
        if calibrate:
            run_id = job("calibrate", {"run_id": run_id})
        job("evaluate", {"run_id": run_id})
        final = request("GET", f"runs/{run_id}/evaluation").json()
        leaderboard = request("GET", f"runs/{run_id}").json()
        current_id = request(
            "POST",
            "datasets/upload",
            files={"file": ("synthetic-current.csv", current, "text/csv")},
        ).json()["id"]
        score_id = job(
            "score",
            {
                "run_id": run_id,
                "dataset_id": current_id,
                "contact_count": 5,
                "value_column": "Value",
                "value_unit": "synthetic annual units",
                "ranking": "risk_x_value",
            },
        )
        customers = request("GET", f"scores/{score_id}/customers?limit=5").json()
        explanation_id = job(
            "explain",
            {"score_id": score_id, "row_reference": customers["customers"][0]["row_reference"]},
        )
        explanation = request("GET", f"analyses/{explanation_id}").json()
        (output / "shortlist.csv").write_bytes(
            request("GET", f"scores/{score_id}/export?top_k=5").content
        )
        (output / "experiment.html").write_bytes(request("GET", f"runs/{run_id}/report").content)
        summary = {
            "data_notice": (
                "All rows and customer values are synthetic, not real business evidence."
            ),
            "dataset_id": dataset,
            "task_id": task,
            "run_id": run_id,
            "current_dataset_id": current_id,
            "score_id": score_id,
            "selected_model": leaderboard["report"]["best_validation_model"],
            "test_metrics": final["metrics"],
            "output_directory": str(output),
        }
        if with_agent:
            summary["assistant"] = request(
                "POST",
                "assistant/messages",
                json={
                    "dataset_id": dataset,
                    "task_id": task,
                    "run_id": run_id,
                    "score_id": score_id,
                    "idempotency_key": str(uuid4()),
                    "question": (
                        "Explain the selected model, separate validation from final test, "
                        "and explain the shortlist limits."
                    ),
                },
            ).json()
        for name, payload in [
            ("summary", summary),
            ("profile", profile),
            ("diagnostics", diagnostics),
            ("explanation", explanation),
            ("leaderboard", leaderboard),
            ("evaluation", final),
        ]:
            (output / f"{name}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/")
    parser.add_argument(
        "--output", type=Path, default=Path(__file__).resolve().parents[2] / ".data/demo-output"
    )
    parser.add_argument(
        "--with-agent", action="store_true", help="Call configured Nebius (uses API credits)."
    )
    parser.add_argument(
        "--calibrate", action="store_true", help="Calibrate before final evaluation."
    )
    args = parser.parse_args()
    run(args.base_url, args.output, args.with_agent, args.calibrate)
