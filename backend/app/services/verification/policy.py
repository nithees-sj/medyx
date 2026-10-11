"""Turning evidence into a decision. Pure and ordered: the first matching rule wins.

approve  — only when an official register confirms an active licence under this name AND the
           person is bound to an organisation (trusted work email), with no conflicting evidence.
reject   — only when the register itself says the registration doesn't exist or isn't active.
           The doctor sees why and can correct their details, which re-runs the checks.
review   — everything else, with a risk level so admins can work the queue efficiently:
           low = strong evidence, one-click approval; high = conflicting evidence.
"""

from dataclasses import dataclass, field
from typing import Literal

from app.services.verification.checks import CheckResult

Action = Literal["approve", "reject", "review"]
Risk = Literal["low", "medium", "high"]


@dataclass
class Decision:
    action: Action
    risk: Risk
    reasons: list[str] = field(default_factory=list)
    doctor_message: str | None = None  # shown to the doctor on rejection


def decide(checks: list[CheckResult], *, auto_approve: bool, auto_reject: bool) -> Decision:
    by = {c.kind: c for c in checks}

    def st(kind: str) -> str:
        return by[kind].status if kind in by else "missing"

    registry, identity, document = st("registry"), st("identity"), st("document")
    reg_reason = by["registry"].details.get("reason") if "registry" in by else None

    if st("duplicate") == "failed":
        return Decision("review", "high", ["Another account already claims this registration number."])
    if registry == "failed" and reg_reason in ("not_found", "inactive"):
        why = (
            "The medical register has no record of this registration."
            if reg_reason == "not_found"
            else "The medical register lists this registration as not active."
        )
        if auto_reject:
            return Decision(
                "reject",
                "high",
                [why],
                doctor_message=f"{why} Please check your council and registration number and resubmit.",
            )
        return Decision("review", "high", [why])
    if registry == "failed":
        return Decision("review", "high", ["The register lists this number under a different name."])
    if document == "failed":
        return Decision("review", "high", ["The uploaded certificate doesn't match the details entered."])

    if registry == "passed" and identity == "passed":
        reasons = ["Active licence confirmed by the medical register.", "Signed in with a trusted hospital email."]
        if document == "warning" or st("format") == "warning":
            return Decision("review", "low", reasons + ["Minor inconsistencies to glance at."])
        return Decision("approve" if auto_approve else "review", "low", reasons)
    if registry == "passed":  # identity is missing or a warning here
        return Decision(
            "review",
            "low" if document == "passed" else "medium",
            [
                "Active licence confirmed by the medical register.",
                "Identity not bound to a hospital — confirm by video call or a work email.",
            ],
        )
    if registry == "warning":
        return Decision("review", "medium", [by["registry"].summary])

    # No register answer (not configured or unreachable): only document + identity evidence.
    strong = [k for k, v in (("certificate", document), ("work email", identity)) if v == "passed"]
    if len(strong) == 2:
        return Decision(
            "review", "low", ["Certificate matches and work email is trusted; register not checked automatically."]
        )
    if strong:
        return Decision("review", "medium", [f"Only the {strong[0]} supports this application; register not checked."])
    return Decision("review", "medium", ["Only self-declared details so far; register not checked automatically."])
