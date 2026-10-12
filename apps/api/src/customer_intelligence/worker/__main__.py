import argparse
import fcntl
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from time import monotonic

from sqlmodel import Session

from customer_intelligence.core.config import get_settings
from customer_intelligence.core.database import engine, init_database
from customer_intelligence.services.jobs import (
    claim_job,
    finish_job,
    get_job,
    recover_interrupted_jobs,
)


def run_once() -> bool:
    settings = get_settings()
    with Session(engine) as session:
        job = claim_job(session)
        if job is None:
            return False
        job_id = job.id
    try:
        child = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "customer_intelligence.worker.execute",
                str(job_id),
                "--parent-pid",
                str(os.getpid()),
            ],
            env={**os.environ, "CI_DATA_DIRECTORY": str(settings.data_directory)},
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        with Session(engine) as session:
            finish_job(session, job_id, None, "Could not start the job process.")
        return True
    started = monotonic()
    last_heartbeat = 0.0
    reason = None
    try:
        while child.poll() is None:
            with Session(engine) as session:
                job = get_job(session, job_id)
                if job.cancel_requested:
                    reason = "Cancellation requested."
                    break
                if monotonic() - started > settings.worker_timeout_seconds:
                    reason = "Job exceeded the configured worker time budget."
                    break
                if monotonic() - last_heartbeat > 2:
                    job.heartbeat_at = datetime.now(UTC)
                    session.add(job)
                    session.commit()
                    last_heartbeat = monotonic()
            time.sleep(0.2)
    except BaseException:
        reason = "Worker interrupted. Retry with a new idempotency key."
        raise
    finally:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        with Session(engine) as session:
            job = get_job(session, job_id)
            if job.state == "running":
                finish_job(
                    session, job_id, None, reason or "Job process exited before recording a result."
                )
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="One local CPU worker (macOS/Linux).")
    parser.add_argument("--once", action="store_true", help="Process at most one queued job.")
    args = parser.parse_args()
    settings = get_settings()
    settings.data_directory.mkdir(parents=True, exist_ok=True)
    with (settings.data_directory / "worker.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("Another worker owns this data directory.") from None
        init_database()
        with Session(engine) as session:
            recover_interrupted_jobs(session)
        try:
            while True:
                worked = run_once()
                if args.once:
                    break
                if not worked:
                    time.sleep(0.5)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
