"""Deterministic matching used by doctor verification. No AI decides a match.

Indian registers and certificates write names in many shapes ("Dr. R. Meena", "MEENA R",
"Meena Raghavan", "Ragavan Meena"), so names are compared as token sets with initials
and small transliteration differences allowed.
"""

import functools
import re
from dataclasses import dataclass
from typing import Literal

from rapidfuzz import fuzz

from app.knowledge import load, norm_text

NameMatch = Literal["exact", "compatible", "conflict"]
RegMatch = Literal["exact", "digits", "conflict"]

_HONORIFICS = {
    "dr", "doctor", "prof", "professor", "mr", "mrs", "ms", "miss", "smt", "shri", "sri", "selvi", "thiru",
    "mbbs", "md", "dnb", "mrcp", "frcs", "dm", "mch", "phd",
}  # fmt: skip

PUBLIC_EMAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.in", "yahoo.in", "outlook.com", "hotmail.com",
    "live.com", "msn.com", "icloud.com", "me.com", "aol.com", "rediffmail.com", "proton.me", "protonmail.com",
    "zoho.com", "zohomail.in", "yandex.com", "gmx.com", "mail.com",
}  # fmt: skip


def name_tokens(name: str) -> tuple[list[str], list[str]]:
    """(full tokens, initials). "Dr. R.K. Meena Raghavan" → (["meena", "raghavan"], ["r", "k"])."""
    text = re.sub(r"([a-z])\.([a-z])", r"\1 \2", name.lower())  # "r.k." → "r k"
    toks = [t for t in re.split(r"[^a-z]+", text) if t and t not in _HONORIFICS]
    return [t for t in toks if len(t) > 1], [t for t in toks if len(t) == 1]


# Common Indian-name transliteration variants, folded before comparing (order matters).
_PHONETIC = [("ksh", "x"), ("ks", "x"), ("kh", "k"), ("gh", "g"), ("th", "t"), ("dh", "d"), ("bh", "b"),
             ("ph", "f"), ("sh", "s"), ("ee", "i"), ("oo", "u"), ("aa", "a"), ("w", "v"), ("y", "i")]  # fmt: skip


def _phonetic(t: str) -> str:
    for a, b in _PHONETIC:
        t = t.replace(a, b)
    return re.sub(r"(.)\1+", r"\1", t)  # collapse doubled letters: Ramanna / Ramana


def _token_match(a: str, b: str) -> int:
    """2 = same name (incl. transliteration variants), 1 = probably a typo, 0 = different."""
    if a == b or _phonetic(a) == _phonetic(b):
        return 2
    # Remaining slack for longer names (one-letter typos and vowel shifts).
    return 1 if min(len(a), len(b)) >= 5 and fuzz.ratio(_phonetic(a), _phonetic(b)) >= 85 else 0


def name_match(a: str, b: str) -> NameMatch:
    """exact: the same names. compatible: the same person written differently — initials for
    some names, or one name part (often the father's name or surname) left out.
    conflict: a full name on the shorter side has no counterpart on the other."""
    fa, ia = name_tokens(a)
    fb, ib = name_tokens(b)
    if not fa or not fb:
        return "conflict"
    short, short_init, long_, long_init = (fa, ia, fb, ib) if len(fa) <= len(fb) else (fb, ib, fa, ia)
    leftover = list(long_)
    fuzzy = False
    for t in short:
        scored = sorted(((_token_match(t, u), u) for u in leftover), reverse=True)
        if not scored or scored[0][0] == 0:
            return "conflict"
        fuzzy = fuzzy or scored[0][0] == 1
        leftover.remove(scored[0][1])
    if not leftover and not fuzzy and sorted(short_init) == sorted(long_init):
        return "exact"
    # Initials on the shorter side stand for leftover full names, or match the other side's initials.
    uncovered, other_inits = list(leftover), list(long_init)
    for i in short_init:
        hit = next((u for u in uncovered if u[0] == i), None)
        if hit is not None:
            uncovered.remove(hit)
        elif i in other_inits:
            other_inits.remove(i)
        else:
            return "conflict"
    return "compatible" if len(uncovered) <= 1 else "conflict"


def normalize_registration(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", s.upper())


def registration_match(a: str, b: str) -> RegMatch:
    """exact: same characters ignoring separators. digits: only the digits agree (prefix differs,
    e.g. "TNMC-58213" vs "58213"). conflict: different numbers."""
    na, nb = normalize_registration(a), normalize_registration(b)
    if na and na == nb:
        return "exact"
    da, db = re.sub(r"\D", "", na), re.sub(r"\D", "", nb)
    if da and da == db:
        return "digits"
    return "conflict"


@dataclass(frozen=True)
class Council:
    id: str
    name: str


@functools.cache
def councils() -> list[Council]:
    return [Council(c["id"], c["name"]) for c in load("medical_councils")["councils"]]


@functools.cache
def _council_index() -> tuple[dict[str, str], list[tuple[str, str]]]:
    exact: dict[str, str] = {}
    states: list[tuple[str, str]] = []
    for c in load("medical_councils")["councils"]:
        exact[norm_text(c["name"])] = c["id"]
        for a in c["aliases"]:
            exact[norm_text(a)] = c["id"]
        if c["state"]:
            states.append((c["state"], c["id"]))
    # Longer state names first so "arunachal pradesh" wins over a bare substring match.
    states.sort(key=lambda s: -len(s[0]))
    return exact, states


def council_id(text: str) -> str | None:
    """Canonical council id for free text, or None if not recognised."""
    t = norm_text(text)
    if not t:
        return None
    exact, states = _council_index()
    if t in exact:
        return exact[t]
    padded = f" {t} "
    for state, cid in states:
        if f" {state} " in padded:
            return cid
    for alias, cid in exact.items():
        if f" {alias} " in padded and len(alias) >= 3:
            return cid
    return None


def council_name(cid: str | None) -> str | None:
    return next((c.name for c in councils() if c.id == cid), None)


def email_domain(email: str) -> str:
    return email.rsplit("@", 1)[-1].strip().lower()


def domain_candidates(domain: str) -> list[str]:
    """mail.kaveri.in → [mail.kaveri.in, kaveri.in] (a trusted parent domain covers subdomains)."""
    parts = domain.split(".")
    return [".".join(parts[i:]) for i in range(len(parts) - 1)]


_ORG_STOPWORDS = {
    "hospital", "hospitals", "clinic", "clinics", "care", "centre", "center", "the", "and", "of", "pvt", "ltd",
    "institute", "medical", "health", "healthcare", "multispeciality", "multispecialty", "speciality",
}  # fmt: skip


def org_overlap(a: str, b: str) -> bool:
    """Do two organisation names plausibly refer to the same place?"""
    ta = {t for t in norm_text(a).split() if t not in _ORG_STOPWORDS and len(t) > 2}
    tb = {t for t in norm_text(b).split() if t not in _ORG_STOPWORDS and len(t) > 2}
    return bool(ta & tb) or fuzz.token_set_ratio(norm_text(a), norm_text(b)) >= 80
