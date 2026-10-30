import json

import httpx
import pytest

from evals import cassette, graders
from evals.dataset import saas_accounts_csv

EVIDENCE = {
    "validation": {"precision": 0.6589147286821705, "recall": 0.3035, "row_count": 1056},
    "selected_candidate": "xgboost",
    "note": "Fixed threshold 0.6",
}


def test_grounding_accepts_rounded_and_percentage_forms():
    answer = (
        "Validation precision is 65.9% (0.659) on 1,056 rows; recall 0.30 at threshold 0.6. "
        "See run 3f2a9c1d-1111-2222-3333-444455556666 and the 3 candidates."
    )
    result = graders.numeric_grounding(answer, [EVIDENCE])
    assert result.passed, result.details
    assert "3" not in result.details["checked"]  # trivial counts are not graded


def test_grounding_flags_fabricated_numbers():
    answer = "Precision is 0.66, and contacting accounts will save 42,000 USD (a 12.5% uplift)."
    result = graders.numeric_grounding(answer, [EVIDENCE])
    assert not result.passed
    assert result.details["ungrounded"] == ["42,000", "12.5%"]
    assert result.score == pytest.approx(1 / 3)


def test_question_numbers_count_as_sources():
    question = "Budget 6000 USD, 20% save rate"
    result = graders.numeric_grounding("With 6000 USD and a 20% save rate…", [question])
    assert result.passed, result.details


def test_trajectory_language_and_budget():
    assert graders.trajectory(["inspect_dataset"], {"inspect_dataset"}, {"submit_training"}).passed
    failed = graders.trajectory(["submit_training"], {"read_run"}, {"submit_training"})
    assert failed.details == {
        "called": ["submit_training"],
        "missing": ["read_run"],
        "forbidden_called": ["submit_training"],
    }
    leak = graders.required_language(
        "Yes, add it — accuracy improves.", ["leak", "outcome"], [r"\byes,? (you should )?add\b"]
    )
    assert not leak.passed and leak.details["banned_matches"]
    assert graders.required_language("That is post-outcome leakage.", ["leak"], []).passed
    assert not graders.budget(9, 8).passed


def test_tool_outputs_decode_only_tool_messages():
    messages = [
        {"role": "system", "content": "x"},
        {"role": "tool", "tool_call_id": "a", "content": json.dumps({"rows": 1200})},
        {"role": "tool", "tool_call_id": "b", "content": "not json"},
    ]
    assert graders.tool_outputs(messages) == [{"rows": 1200}, "not json"]


def test_synthetic_dataset_is_deterministic_and_contains_leak_trap():
    first = saas_accounts_csv(rows=50)
    assert first == saas_accounts_csv(rows=50)
    header = first.splitlines()[0].split(",")
    assert header[0] == "account_id" and "cancellation_reason" in header


def test_cassette_records_without_secrets_and_replays_with_new_ids(tmp_path, monkeypatch):
    monkeypatch.setattr(cassette, "CASSETTE_DIRECTORY", tmp_path)
    body = {"choices": [{"message": {"content": "dataset OLD-ID has 1200 rows"}}]}
    inner = httpx.MockTransport(lambda request: httpx.Response(200, json=body))
    recorder = cassette.RecordingTransport(inner, {"OLD-ID": "{{dataset_id}}"})
    request_body = {"messages": [{"role": "user", "content": "hi"}], "tools": []}
    with httpx.Client(transport=recorder) as client:
        client.post(
            "https://example.invalid/v1/chat/completions",
            json=request_body,
            headers={"Authorization": "Bearer secret-key"},
        )
    saved = recorder.save("demo").read_text()
    assert "secret-key" not in saved and "OLD-ID" not in saved and "{{dataset_id}}" in saved

    replay = cassette.ReplayTransport("demo", {"NEW-ID": "{{dataset_id}}"})
    with httpx.Client(transport=replay) as client:
        response = client.post("https://replay.invalid/v1/chat/completions", json=request_body)
        assert "NEW-ID" in response.json()["choices"][0]["message"]["content"]
        with pytest.raises(cassette.CassetteMismatch):
            client.post("https://replay.invalid/v1/chat/completions", json=request_body)


def test_grounding_reads_space_grouped_thousands():
    answer = "Gross value ≈ $30 719 from 1 500 per account; contact 119 500-seat accounts."
    result = graders.numeric_grounding(answer, [{"benefit": 30719, "value": 1500}])
    assert result.details["checked"] == ["30 719", "1 500", "119", "500"]
    assert result.details["ungrounded"] == ["119", "500"]


def test_grounding_ignores_ids_written_with_unicode_hyphens():
    answer = "Dataset bde4c693‑df18‑4f09‑8886‑438a98366f50 shows −81.5 change."
    result = graders.numeric_grounding(answer, [{"low": -81.5}])
    assert result.passed and result.details["checked"] == ["-81.5"], result.details
