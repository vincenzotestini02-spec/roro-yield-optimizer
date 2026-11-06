"""Time a deployed app.

    python -m benchmarks.measure_live https://user-space.hf.space --verdicts 10
"""

from __future__ import annotations

import argparse
import statistics
import time

import httpx

POLL_S = 0.2
TIMEOUT_S = 300


def wait_job(client: httpx.Client, job_id: str) -> dict:
    end = time.monotonic() + TIMEOUT_S
    while time.monotonic() < end:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "failed"):
            return job
        time.sleep(POLL_S)
    raise TimeoutError(job_id)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--verdicts", type=int, default=10)
    args = parser.parse_args()
    with httpx.Client(base_url=args.url.rstrip("/"), timeout=120, follow_redirects=True) as client:
        start = time.perf_counter()
        client.get("/api/health").raise_for_status()
        print(f"health: {time.perf_counter() - start:.2f} s")

        start = time.perf_counter()
        client.get("/").raise_for_status()
        print(f"first page: {time.perf_counter() - start:.2f} s")

        times = []
        for seed in range(9001, 9001 + args.verdicts):
            start = time.perf_counter()
            job = client.post("/api/game/verdict", json={"seed": seed, "decisions": []}).json()
            assert wait_job(client, job["job_id"])["status"] == "done"
            times.append(time.perf_counter() - start)
        print(f"verdict: median {statistics.median(times):.2f} s, max {max(times):.2f} s")

        values = client.get("/api/lab/defaults").json()["values"]
        start = time.perf_counter()
        job = client.post("/api/lab/plans", json={**values, "seed": 9100}).json()
        assert wait_job(client, job["job_id"])["status"] == "done"
        print(f"first plan (FCFS + optimizer): {time.perf_counter() - start:.2f} s")


if __name__ == "__main__":
    main()
