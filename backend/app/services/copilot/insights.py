"""Panel insights: questions across a doctor's consented patients, answered through tools only.

The model never sees raw records or writes queries. It calls four tools, executed here over
this doctor's actively consented profiles, each filtered by that consent's scopes.
"""

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np
from google.genai import types
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import knowledge as kb
from app.ai import client as ai
from app.db import utcnow
from app.models import Alert, Consent, HealthProfile, User
from app.services.consent import filter_record
from app.services.profiles import age_on
from app.services.record import PatientRecord, load_record

log = logging.getLogger(__name__)
MAX_STEPS = 6


@dataclass
class PanelPatient:
    profile: HealthProfile
    record: PatientRecord
    scopes: frozenset[str]


async def load_panel(db: AsyncSession, doctor: User) -> list[PanelPatient]:
    consents = (
        await db.scalars(
            select(Consent).where(
                Consent.doctor_user_id == doctor.id, Consent.status == "active", Consent.expires_at > utcnow()
            )
        )
    ).all()
    panel = []
    latest: dict[uuid.UUID, Consent] = {}
    for c in consents:  # defensively one entry per patient (the latest consent wins)
        if c.profile_id not in latest or (c.expires_at or utcnow()) > (latest[c.profile_id].expires_at or utcnow()):
            latest[c.profile_id] = c
    for c in latest.values():
        profile = await db.get(HealthProfile, c.profile_id)
        if profile is None:
            continue
        scopes = frozenset(c.scopes)
        record = filter_record(await load_record(db, profile), scopes)
        panel.append(PanelPatient(profile, record, scopes))
    return panel


def _loinc(code_or_name: str) -> tuple[str | None, str]:
    lab = kb.lab_by_code(code_or_name) or kb.match_lab(code_or_name)
    return (lab.code, lab.short) if lab else (None, code_or_name)


def _series(record: PatientRecord, loinc: str) -> list[dict[str, Any]]:
    return [
        {"date": o.effective.isoformat(), "value": o.value, "org": o.org, "ref": o.ref}
        for o in record.series(loinc)
        if o.effective and o.value is not None
    ]


def _base(p: PanelPatient) -> dict[str, Any]:
    return {
        "profile_id": str(p.profile.id),
        "name": p.profile.display_name,
        "age": age_on(p.profile.dob),
        "sex": p.profile.sex,
    }


class Tools:
    def __init__(self, panel: list[PanelPatient], alerts: dict[uuid.UUID, list[Alert]]):
        self.panel = panel
        self.alerts = alerts
        self.rows: list[dict[str, Any]] = []  # what the UI shows (last tool that returned patients)
        self.table_kind = ""

    def list_patients_with_lab_trend(self, loinc: str, direction: str = "down", min_points: int = 3) -> dict:
        code, name = _loinc(loinc)
        if not code:
            return {"error": f"Unknown lab test '{loinc}'"}
        out = []
        for p in self.panel:
            pts = _series(p.record, code)
            if len(pts) < max(2, min_points):
                continue
            t0 = date.fromisoformat(pts[0]["date"])
            t = np.array([(date.fromisoformat(x["date"]) - t0).days / 365.25 for x in pts])
            v = np.array([x["value"] for x in pts], dtype=float)
            if t[-1] == 0:
                continue
            slope = float(np.polyfit(t, v, 1)[0])
            if (direction == "down" and slope < 0) or (direction == "up" and slope > 0):
                out.append(
                    {
                        **_base(p),
                        "metric": f"{name} {pts[0]['value']:g} → {pts[-1]['value']:g}",
                        "slope_per_year": round(slope, 2),
                        "latest": pts[-1],
                        "points": len(pts),
                        "sparkline": pts,
                        "sources": len({x["org"] for x in pts}),
                    }
                )
        out.sort(key=lambda r: r["slope_per_year"] if direction == "down" else -r["slope_per_year"])
        self._show(out, f"{name} trending {direction}")
        return {"lab": name, "loinc": code, "direction": direction, "patients": [_brief(r) for r in out]}

    def list_patients_on_drug(self, molecule_or_class: str) -> dict:
        q = molecule_or_class.strip().lower()
        generic = kb.canonical_generic(q)
        out = []
        for p in self.panel:
            meds = [
                m
                for m in p.record.medications
                if m.active_on(date.today()) and (generic in m.generic.split(" + ") or q in m.classes or q == m.generic)
            ]
            if meds:
                out.append(
                    {
                        **_base(p),
                        "metric": ", ".join(m.display + (f" ({m.brand})" if m.brand else "") for m in meds),
                        "medicines": [
                            {"name": m.display, "brand": m.brand, "org": m.org, "since": str(m.start)} for m in meds
                        ],
                    }
                )
        self._show(out, f"on {molecule_or_class}")
        return {"query": molecule_or_class, "patients": [_brief(r) for r in out]}

    def list_patients_with_alert(self, type: str = "any", severity: str = "any") -> dict:
        out = []
        for p in self.panel:
            hits = [
                a
                for a in self.alerts.get(p.profile.id, [])
                if (type in ("any", a.type)) and (severity in ("any", a.severity))
            ]
            if hits:
                out.append(
                    {
                        **_base(p),
                        "metric": "; ".join(a.title for a in hits),
                        "alerts": [{"title": a.title, "severity": a.severity, "type": a.type} for a in hits],
                    }
                )
        out.sort(key=lambda r: min({"critical": 0, "warning": 1}.get(a["severity"], 2) for a in r["alerts"]))
        self._show(out, "with safety alerts")
        return {"type": type, "severity": severity, "patients": [_brief(r) for r in out]}

    def get_latest_lab(self, loinc: str) -> dict:
        code, name = _loinc(loinc)
        if not code:
            return {"error": f"Unknown lab test '{loinc}'"}
        out = []
        for p in self.panel:
            pts = _series(p.record, code)
            if pts:
                out.append(
                    {
                        **_base(p),
                        "metric": f"{name} {pts[-1]['value']:g} on {pts[-1]['date']}",
                        "latest": pts[-1],
                        "sparkline": pts,
                    }
                )
        out.sort(key=lambda r: r["latest"]["value"])
        self._show(out, f"latest {name}")
        return {"lab": name, "loinc": code, "patients": [_brief(r) for r in out]}

    def _show(self, rows: list[dict[str, Any]], kind: str) -> None:
        if rows or not self.rows:
            self.rows, self.table_kind = rows, kind

    def call(self, name: str, args: dict[str, Any]) -> dict:
        fn: Any = {
            "list_patients_with_lab_trend": self.list_patients_with_lab_trend,
            "list_patients_on_drug": self.list_patients_on_drug,
            "list_patients_with_alert": self.list_patients_with_alert,
            "get_latest_lab": self.get_latest_lab,
        }.get(name)
        if fn is None:
            return {"error": f"Unknown tool {name}"}
        try:
            return fn(**args)
        except TypeError as e:
            return {"error": f"Bad arguments: {e}"}


def _brief(row: dict[str, Any]) -> dict[str, Any]:
    """What the model sees: enough to answer, without document snippets."""
    keep = {"name", "age", "sex", "metric", "slope_per_year", "latest", "points", "sources", "medicines", "alerts"}
    return {k: v for k, v in row.items() if k in keep}


DECLARATIONS = [
    types.FunctionDeclaration(
        name="list_patients_with_lab_trend",
        description="Patients whose lab values move in a direction over time (linear trend), most extreme first.",
        parameters_json_schema={
            "type": "object",
            "properties": {
                "loinc": {"type": "string", "description": "LOINC code or test name, e.g. 33914-3 or eGFR"},
                "direction": {"type": "string", "enum": ["down", "up"]},
                "min_points": {"type": "integer", "description": "Minimum number of results (default 3)"},
            },
            "required": ["loinc", "direction"],
        },
    ),
    types.FunctionDeclaration(
        name="list_patients_on_drug",
        description="Patients currently taking a generic molecule ('metformin') or a class ('ace_inhibitor').",
        parameters_json_schema={
            "type": "object",
            "properties": {"molecule_or_class": {"type": "string"}},
            "required": ["molecule_or_class"],
        },
    ),
    types.FunctionDeclaration(
        name="list_patients_with_alert",
        description="Patients with active safety alerts, optionally filtered by type and severity.",
        parameters_json_schema={
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": [
                        "any",
                        "duplicate_therapy",
                        "allergy_conflict",
                        "prescribing_cascade",
                        "lab_drift",
                        "interaction",
                    ],
                },
                "severity": {"type": "string", "enum": ["any", "critical", "warning", "info"]},
            },
        },
    ),
    types.FunctionDeclaration(
        name="get_latest_lab",
        description="Each patient's most recent value for a lab test, lowest first.",
        parameters_json_schema={
            "type": "object",
            "properties": {"loinc": {"type": "string", "description": "LOINC code or test name"}},
            "required": ["loinc"],
        },
    ),
]


async def answer(db: AsyncSession, doctor: User, question: str) -> dict[str, Any]:
    panel = await load_panel(db, doctor)
    alerts: dict[uuid.UUID, list[Alert]] = {}
    for p in panel:
        rows = (await db.scalars(select(Alert).where(Alert.profile_id == p.profile.id, Alert.status == "active"))).all()
        refs = {
            x.ref
            for coll in (p.record.conditions, p.record.medications, p.record.allergies, p.record.observations)
            for x in coll
        }
        alerts[p.profile.id] = [
            a for a in rows if not (a.details or {}).get("superseded_by") and all(e["ref"] in refs for e in a.evidence)
        ]
    tools = Tools(panel, alerts)
    contents: list[types.Content] = [types.Content(role="user", parts=[types.Part.from_text(text=question)])]
    used: list[dict[str, Any]] = []
    text = ""
    for _ in range(MAX_STEPS):
        resp = await ai.generate_with_tools(
            purpose="insights",
            system=ai.load_prompt("insights") + f"\n\nThe doctor's panel has {len(panel)} consented patient(s).",
            contents=contents,
            tools=[types.Tool(function_declarations=DECLARATIONS)],
        )
        calls = resp.function_calls or []
        if not calls:
            text = resp.text or ""
            break
        model_turn = resp.candidates[0].content if resp.candidates else None
        if model_turn is not None:
            contents.append(model_turn)  # keep the model turn as-is (thought signatures)
        parts = []
        for call in calls:
            result = tools.call(call.name or "", dict(call.args or {}))
            used.append({"tool": call.name, "args": dict(call.args or {}), "patients": len(result.get("patients", []))})
            parts.append(
                types.Part.from_function_response(
                    name=call.name or "", response={"result": json.loads(json.dumps(result, default=str))}
                )
            )
        contents.append(types.Content(role="user", parts=parts))
    else:
        text = "I couldn't finish answering within the allowed number of steps."
    return {
        "answer": text.strip(),
        "table": {"kind": tools.table_kind, "rows": tools.rows},
        "tools_used": used,
        "panel_size": len(panel),
        "touched_profiles": [r["profile_id"] for r in tools.rows],
    }
