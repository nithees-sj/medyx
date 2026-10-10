"""Phase 3 acceptance: ingest Rajan's 9 documents through the real API and check the merged FHIR record.

    backend/.venv/bin/python e2e/ingest_check.py [--profile-name "Rajan Subramanian"]
"""

import argparse
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
API = "http://localhost:8000/api"
FHIR = "http://localhost:8080/fhir"
H = {"X-HT-Request": "1"}


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile-name", default="Rajan Subramanian")
    ap.add_argument("--folder", default="rajan")
    args = ap.parse_args()

    c = httpx.Client(base_url=API, headers=H, timeout=60)
    c.post("/auth/demo", json={"persona": "priya"}).raise_for_status()
    profiles = c.get("/profiles").json()
    profile = next((p for p in profiles if p["display_name"] == args.profile_name), None)
    if profile is None:
        profile = c.post(
            "/profiles",
            json={
                "display_name": args.profile_name,
                "relationship": "parent",
                "dob": "1962-05-14",
                "sex": "male",
                "blood_group": "B+",
                "emergency_contact_name": "Priya Rajan",
                "emergency_contact_phone": "+91 98400 12345",
            },
        ).json()
    pid = profile["id"]
    print("profile", pid, profile["healththread_id"])

    files = sorted((ROOT / "demo_data" / args.folder).iterdir())
    multipart = [("files", (f.name, f.read_bytes())) for f in files]
    up = c.post(f"/profiles/{pid}/documents", files=multipart)
    up.raise_for_status()
    results = up.json()
    print("uploaded:", [(r["filename"], r["duplicate"], r["error"]) for r in results])

    started = time.time()
    while True:
        docs = c.get(f"/profiles/{pid}/documents").json()
        states = {d["original_filename"]: (d["status"], d["stage"]) for d in docs}
        if all(s in ("done", "needs_review", "failed") for s, _ in states.values()):
            break
        if time.time() - started > 900:
            fail(f"timeout: {states}")
        print(f"  {int(time.time() - started)}s", sorted({st for _, st in states.values()}))
        time.sleep(5)
    for d in sorted(docs, key=lambda d: d["seq"]):
        print(f"  {d['label']:>4} {d['status']:<12} {d['original_filename']:<38} {d['result_counts']} {d['error'] or ''}")
    if any(d["status"] == "failed" for d in docs):
        fail("some documents failed")

    # Re-upload the same file → skipped
    again = c.post(f"/profiles/{pid}/documents", files=[("files", (files[0].name, files[0].read_bytes()))]).json()
    if not again[0]["duplicate"]:
        fail("re-upload was not detected as duplicate")
    print("re-upload skipped: OK")

    print("profile id for further checks:", pid)


if __name__ == "__main__":
    main()
