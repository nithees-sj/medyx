# Doctor verification

HealthThread doesn't ask admins to eyeball certificates one by one. Every doctor application is checked automatically. Fixed rules (not AI) decide the clear-cut cases, and everything else reaches the admin queue with its evidence and a risk level.

## What is checked

| Check | Evidence | Needs |
|---|---|---|
| **Details** | The council is a recognised Indian council (`knowledge/medical_councils.json`), and the registration number looks like one | nothing |
| **Unique registration** | No other pending, verified or suspended account claims the same council and number. Register data is partly public, so a second claim is the classic impersonation signal. | nothing |
| **Medical register** | The register lists this number as **active** under a matching name. Names are compared with initials and transliteration allowed ("Dr. Meena Raghavan" ≈ "MEENA R", "Lakshmi" ≈ "Laxmi") | a register connection (below) |
| **Work identity** | Signed in with an email on an admin-trusted hospital domain. Google has already verified the user controls that address. | admins add domains under *Admin → Doctors* |
| **Certificate** | Gemini reads the uploaded registration certificate. Fixed rules compare the name, number and council with what was typed. This is evidence only: reading a document can't prove it's genuine. | the doctor uploads it |

## Decision rules (`services/verification/policy.py`, first match wins)

| Evidence | Outcome |
|---|---|
| Another account claims the number | review, **high** risk; admins notified |
| Register: not found or not active | **auto-reject** (`VERIFICATION_AUTO_REJECT`); the doctor sees why, fixes their details, and the checks run again |
| Register: different name, or the certificate conflicts | review, **high** risk |
| Register active **and** trusted work email, nothing conflicting | **auto-approve** (`VERIFICATION_AUTO_APPROVE`) |
| Register active, no work identity | review: low if the certificate matches, otherwise medium |
| No register answer, certificate **and** work email match | review, **low** risk (one-click approve) |
| Anything less | review, medium |

Verified doctors are re-checked against the register every `VERIFICATION_RECHECK_DAYS` (default 30). If a registration disappears or becomes inactive, the doctor is **suspended**: every active share they hold ends, the affected patients are notified, and admins are told. A register outage decides nothing; the check is simply retried the next day.

Admins can always approve, reject, re-run checks, suspend (with a reason) and reinstate. Every status change is a system event in *Admin → Activity*.

## Connecting a medical register

No register API is published openly. NMC/IMR verification is sold by vendors such as Surepass, Decentro and Meon, and ABDM's Healthcare Professionals Registry needs integrator onboarding. So HealthThread speaks one small JSON contract, and you point it at a vendor or a thin adapter in front of one.

```
REGISTRY_PROVIDER=http
REGISTRY_URL=https://your-adapter.example/lookup
REGISTRY_API_KEY=...            # sent as "Authorization: Bearer <key>"
```

**Request** `POST REGISTRY_URL`
```json
{ "council": "Tamil Nadu Medical Council", "council_id": "tamil_nadu",
  "registration_number": "TNMC-58213", "full_name": "Dr. Meena Raghavan" }
```

**Response** `200`
```json
{ "found": true, "name": "MEENA R", "registration_number": "58213",
  "council": "Tamil Nadu Medical Council", "status": "Active",
  "qualification": "MBBS, MD, DM", "registration_year": 2009 }
```
- `found` (boolean) is required. Return `{"found": false}` or HTTP 404 when there's no such registration.
- `status`: `active`, `valid`, `registered` or `current` count as active. Anything else (`suspended`, `cancelled`…) counts as not active.
- Any other HTTP error, a timeout or malformed JSON counts as a **register error**: nothing is decided and the check is retried later.

Until `REGISTRY_PROVIDER` is set, the register check reports "not configured" and nothing is approved on register grounds. Responses are never simulated.
