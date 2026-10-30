from fastapi.testclient import TestClient

from customer_intelligence.core.config import Settings
from customer_intelligence.main import create_app


def client_with(tmp_path, **limits) -> TestClient:
    settings = Settings(_env_file=None, auth_mode="private", data_directory=tmp_path, **limits)
    return TestClient(create_app(settings))


def csv_rows(count: int, width: int = 3) -> bytes:
    header = ",".join(f"c{i}" for i in range(width)) + ",churn\n"
    body = "".join(
        ",".join(str(r * i) for i in range(width)) + f",{'Yes' if r % 3 else 'No'}\n"
        for r in range(count)
    )
    return (header + body).encode()


def test_files_above_the_old_limits_are_accepted(tmp_path):
    # Beyond the former 50,000-row cap, well inside the new default.
    with client_with(tmp_path) as client:
        response = client.post(
            "/api/v1/datasets/upload", files={"file": ("big.csv", csv_rows(60_000))}
        )
        assert response.status_code == 201, response.text
        assert response.json()["row_count"] == 60_000
        limits = client.get("/api/v1/capabilities").json()["limits"]
        assert limits["upload_mib"] == 200 and limits["rows"] == 1_000_000
        # No partial files are left behind.
        assert not [p for p in (tmp_path / "uploads").iterdir() if p.name.endswith(".part")]


def test_configured_limits_are_enforced(tmp_path):
    with client_with(tmp_path, max_upload_mb=1, max_rows=100, max_columns=5) as client:
        rows = client.post("/api/v1/datasets/upload", files={"file": ("r.csv", csv_rows(101))})
        assert rows.status_code == 413 and "100" in rows.json()["message"]
        wide = client.post(
            "/api/v1/datasets/upload", files={"file": ("w.csv", csv_rows(5, width=6))}
        )
        assert wide.status_code == 413
        huge = client.post(
            "/api/v1/datasets/upload",
            files={"file": ("h.csv", b"a,b\n" + b"1,2\n" * 400_000)},
        )
        assert huge.status_code == 413
        small_json = client.post("/api/v1/assistant/messages", content=b"x" * (3 * 1024 * 1024))
        assert small_json.status_code == 413, "ordinary requests keep a small cap"
        assert not [p for p in (tmp_path / "uploads").iterdir() if p.name.endswith(".part")]


def test_bad_encoding_is_still_rejected(tmp_path):
    with client_with(tmp_path) as client:
        response = client.post(
            "/api/v1/datasets/upload", files={"file": ("bad.csv", b"a,b\n\xff\xfe,1\n")}
        )
        assert response.status_code == 400 and "UTF-8" in response.json()["message"]


def test_fast_loader_matches_the_exact_reader():
    import csv
    from io import StringIO
    from uuid import uuid4

    import pandas as pd

    from customer_intelligence.models.dataset import Dataset
    from customer_intelligence.services.datasets import validate_csv
    from customer_intelligence.services.profiling import _fast_frame, blank_to_missing

    content = (
        "﻿id,note,amount,flag\n"
        '1,"comma, inside",10.5,Yes\n'
        '2,"line\nbreak",  ,No\n'
        '3,"quote ""here""",007, \n'
        "4, ,1e3,Yes\n"
        "\n"
        "5,plain, -2 ,No\n"
    ).encode()
    rows, cols = validate_csv(content)
    dataset = Dataset(
        id=uuid4(),
        original_filename="x.csv",
        storage_key="x.csv",
        row_count=rows,
        column_count=cols,
    )
    reader = csv.reader(StringIO(content.decode("utf-8-sig"), newline=""), strict=True)
    headers = next(reader)
    exact = pd.DataFrame([r for r in reader if r], columns=headers, dtype="string")
    exact = exact.replace(r"^\s*$", pd.NA, regex=True)
    fast = _fast_frame(content, dataset)
    assert fast is not None
    pd.testing.assert_frame_equal(blank_to_missing(fast), exact)
