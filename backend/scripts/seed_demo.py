"""Seed the demo world (requires DEMO_MODE=true).

    python -m scripts.seed_demo [--reset] [--stage full|live]

--stage full (default): Priya's father Rajan has all 9 documents ingested through the real
    pipeline (AI extraction → normalise → merge → FHIR → safety), the review item confirmed
    by Priya, and an active 7-day share to Dr. Meena (all scopes except mental health,
    can_write). Lakshmi (control patient) is ingested and shared with Dr. Meena too.
--stage live: same people, but Rajan's profile is empty and not shared, so the on-stage
    demo can upload his documents and share by QR live. Lakshmi is fully seeded.
--reset: first wipes all app data and the FHIR data of every health profile.

Documents go through the same code path as the upload API. When the AI call fails
(e.g. quota exhausted) and DEMO_CACHE=true, the pipeline uses demo_cache/<sha256>.json,
which holds the real extraction recorded for that exact file.
"""

import argparse
import asyncio
import sys
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import select, text

from app.config import get_settings
from app.db import Base, SessionLocal, engine, utcnow
from app.models import Alert, Consent, ExtractionItem, HealthProfile, User
from app.routers.review import apply_review
from app.services import record as record_service
from app.services.demo import ensure_persona
from app.services.documents import find_duplicate, next_seq, store_document, validate_upload
from app.services.ingest import pipeline
from app.services.profiles import create_profile
from app.services.purge import purge_profile
from app.services.safety import engine as safety

ALL_BUT_MENTAL = ["allergies", "conditions", "documents", "labs", "medications", "notes"]


def say(msg: str) -> None:
    print(msg, flush=True)


async def reset() -> None:
    say("• Resetting: purging FHIR data of every health profile and clearing app tables…")
    async with SessionLocal() as db:
        for p in (await db.scalars(select(HealthProfile))).all():
            await purge_profile(db, p, delete_profile=True)
    names = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {names} CASCADE"))
    record_service.invalidate()


async def ensure_user(db, sub: str, email: str, name: str, role: str) -> User:
    u = await db.scalar(select(User).where(User.google_sub == sub))
    if u is None:
        u = User(google_sub=sub, email=email, name=name, role=role)
        db.add(u)
        await db.commit()
        await db.refresh(u)
    return u


async def ensure_profile(db, owner: User, **fields) -> HealthProfile:
    p = await db.scalar(
        select(HealthProfile).where(
            HealthProfile.owner_user_id == owner.id, HealthProfile.display_name == fields["display_name"]
        )
    )
    if p is None:
        p = await create_profile(db, owner_user_id=owner.id, **fields)
        await db.commit()
    return p


async def ingest(owner: User, profile: HealthProfile, folder: Path) -> None:
    async with SessionLocal() as db:
        seq = await next_seq(db, profile.id)
        docs = []
        for f in sorted(folder.iterdir()):
            data = f.read_bytes()
            mime = validate_upload(data, f.name)
            if await find_duplicate(db, profile.id, data):
                say(f"    {f.name}: already in the record")
                continue
            doc = await store_document(
                db,
                profile_id=profile.id,
                user_id=owner.id,
                uploader_role="owner",
                filename=f.name,
                data=data,
                mime=mime,
                seq=seq,
            )
            seq += 1
            docs.append((doc.id, f.name))
        await db.commit()
    for doc_id, name in docs:
        await pipeline.process_document(doc_id)
        async with SessionLocal() as db:
            from app.models import Document

            d = await db.get(Document, doc_id)
            assert d is not None
            source = (d.result_counts or {}).get("meta", {}).get("extraction_source", "?")
            say(f"    {name:<38} {d.status:<13} via {source:<5} {d.error or ''}")


async def confirm_pending(owner: User, profile: HealthProfile) -> None:
    async with SessionLocal() as db:
        from app.models import Document

        items = (
            await db.scalars(
                select(ExtractionItem)
                .join(Document, Document.id == ExtractionItem.document_id)
                .where(Document.profile_id == profile.id, ExtractionItem.review_status == "pending")
            )
        ).all()
        user = await db.get(User, owner.id)
        assert user is not None
        for item in items:
            await apply_review(db, item, user, "confirm", None, None)
            say(f"    confirmed pending {item.resource_type} (as {owner.name}, like the review queue)")


async def grant(
    owner: User, profile: HealthProfile, doctor: User, scopes: list[str], can_write: bool, days: int = 7
) -> None:
    async with SessionLocal() as db:
        existing = await db.scalar(
            select(Consent).where(
                Consent.profile_id == profile.id, Consent.doctor_user_id == doctor.id, Consent.status == "active"
            )
        )
        if existing:
            return
        db.add(
            Consent(
                profile_id=profile.id,
                granted_by_user_id=owner.id,
                doctor_user_id=doctor.id,
                scopes=sorted(scopes),
                can_write=can_write,
                purpose="Demo share",
                status="active",
                duration_hours=days * 24,
                expires_at=utcnow() + timedelta(days=days),
            )
        )
        await db.commit()


async def run_safety(profile: HealthProfile) -> list[Alert]:
    async with SessionLocal() as db:
        p = await db.get(HealthProfile, profile.id)
        assert p is not None
        await safety.run_for_profile(db, p)
    await safety.explain_pending(profile.id)
    async with SessionLocal() as db:
        return [
            a
            for a in (
                await db.scalars(select(Alert).where(Alert.profile_id == profile.id, Alert.status == "active"))
            ).all()
            if not (a.details or {}).get("superseded_by")
        ]


async def main(stage: str, do_reset: bool) -> int:
    s = get_settings()
    if not s.demo_mode:
        say("DEMO_MODE must be true to seed demo data.")
        return 2
    if safety.safety_hook not in pipeline.post_write_hooks:
        pipeline.post_write_hooks.append(safety.safety_hook)
    if do_reset:
        await reset()

    say("• People")
    async with SessionLocal() as db:
        priya = await ensure_persona(db, "priya")
        meena = await ensure_persona(db, "meena")
        await ensure_persona(db, "arjun")
        await ensure_persona(db, "admin")
        lakshmi_user = await ensure_user(
            db, "demo:lakshmi", "lakshmi.iyer@demo.healththread.app", "Lakshmi Iyer", "patient"
        )
        await db.commit()
        for u in (priya, meena, lakshmi_user):
            await db.refresh(u)
        me = await ensure_profile(
            db,
            priya,
            display_name="Priya Rajan",
            relationship="self",
            dob=date(1991, 8, 22),
            sex="female",
            blood_group="O+",
            emergency_contact_name="Karthik Rajan",
            emergency_contact_phone="+91 98410 55667",
        )
        rajan = await ensure_profile(
            db,
            priya,
            display_name="Rajan Subramanian",
            relationship="parent",
            dob=date(1962, 5, 14),
            sex="male",
            blood_group="B+",
            emergency_contact_name="Priya Rajan",
            emergency_contact_phone="+91 98400 12345",
        )
        lakshmi = await ensure_profile(
            db,
            lakshmi_user,
            display_name="Lakshmi Iyer",
            relationship="self",
            dob=date(1968, 3, 9),
            sex="female",
            blood_group="A+",
            emergency_contact_name="Ravi Iyer",
            emergency_contact_phone="+91 94470 12345",
        )
    managed = f"{me.display_name} {me.healththread_id}, {rajan.display_name} {rajan.healththread_id}"
    say(f"    Priya ({priya.email}) manages: {managed}")
    say(f"    Lakshmi Iyer {lakshmi.healththread_id}; Dr. Meena (verified), Dr. Arjun (pending), Admin")

    data = s.demo_data_dir
    if not (data / "rajan").exists():
        say("• Generating synthetic documents")
        from scripts.generate_demo_docs import generate

        generate()

    say("• Lakshmi (control patient): ingesting 3 documents")
    await ingest(lakshmi_user, lakshmi, data / "lakshmi")
    await confirm_pending(lakshmi_user, lakshmi)
    lakshmi_alerts = await run_safety(lakshmi)
    await grant(lakshmi_user, lakshmi, meena, ["conditions", "medications", "allergies", "labs"], can_write=False)

    rajan_alerts: list[Alert] = []
    if stage == "full":
        say("• Rajan: ingesting 9 documents from 5 sources")
        await ingest(priya, rajan, data / "rajan")
        await confirm_pending(priya, rajan)
        rajan_alerts = await run_safety(rajan)
        await grant(priya, rajan, meena, ALL_BUT_MENTAL, can_write=True)
    else:
        say("• Rajan: left empty for the live upload (stage=live)")

    # Let background mirroring (FHIR Consent/AuditEvent) finish before exiting.
    pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if pending:
        await asyncio.wait(pending, timeout=20)

    say("\n• Result")
    say(f"    Lakshmi: {len(lakshmi_alerts)} alerts (expected 0)")
    ok = len(lakshmi_alerts) == 0
    if stage == "full":
        types = sorted(a.type for a in rajan_alerts)
        say(f"    Rajan:   {len(rajan_alerts)} alerts → {', '.join(types)}")
        expected = ["allergy_conflict", "duplicate_therapy", "lab_drift", "prescribing_cascade"]
        ok = ok and types == expected
        say(f"    Shared with Dr. Meena for 7 days: {', '.join(ALL_BUT_MENTAL)} (can add & prescribe)")
    say("\n    Sign in at http://localhost:3000/login → Demo accounts (Priya, Dr. Meena, Dr. Arjun, Admin)")
    say("    ✅ Demo data ready." if ok else "    ⚠️  Unexpected alert set — check the extraction output above.")
    await engine.dispose()
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reset", action="store_true", help="wipe app data and FHIR data of all profiles first")
    ap.add_argument("--stage", choices=["full", "live"], default="full")
    args = ap.parse_args()
    sys.exit(asyncio.run(main(args.stage, args.reset)))
