# HealthThread — 3-minute demo script

**Story:** Priya manages her father Rajan's health. His records are scattered across five hospitals, clinics and labs. HealthThread threads them into one record, catches four problems no single hospital could see, and lets Priya share it safely with a nephrologist.

## Before the demo (10 minutes ahead)

```bash
docker compose up -d                          # Postgres + HAPI FHIR
cd backend && .venv/bin/uvicorn app.main:app --port 8000      # terminal 1
cd frontend && npm run dev                                     # terminal 2
cd backend && .venv/bin/python -m scripts.seed_demo --reset --stage live
```

- `--stage live` creates everyone (Priya, Dr. Meena, Dr. Arjun, Admin, and Lakshmi as the control patient, already shared with Dr. Meena). **Rajan's profile is left empty** so you can upload live. Use `--stage full` instead if you want everything preloaded (no live upload).
- Open two windows:
  - **Phone window** (or DevTools at 390 px) for Priya: <http://localhost:3000/login> → *Demo accounts* → **Priya (caregiver)**.
  - **Laptop window** (a different browser profile or incognito) for the doctor. Keep it signed out.
- Keep `demo_data/rajan/` open in a file manager for drag-and-drop.
- Check <http://localhost:3000>: the status pill should say *API ok · Database · FHIR 4.0.1*.
- On the free Gemini tier, uploads queue at 5 requests a minute, so 9 documents take about 2 minutes. On a paid key, set `AI_REQUESTS_PER_MINUTE=60` and it takes about 20 s. If the AI is unavailable, extraction falls back to `DEMO_CACHE` (real recorded outputs for these exact files), so the upload still completes.

## The 3 minutes

**1. Patient, phone (0:00–0:45).** Priya opens **Appa — Rajan** and taps **Upload**. Drag all 9 files from `demo_data/rajan` (5 sources: typed letterheads, a table-style lab report, an SI-unit report and phone photos of handwritten prescriptions).
- *Say:* "Every hospital formats differently. Watch each file go through extraction, codes and units, merging, and saving to FHIR."
- If a **Review** badge appears (the penicillin allergy only says "2022"), tap **Review → Looks right**. That shows the human-in-the-loop confidence gate.
- Tap **Timeline**: one thread, colour-coded by hospital.

**2. Safety (0:45–1:15).** Tap **Alerts (4)**:
- **Critical:** penicillin allergy (Sunrise, 2022) vs Novamox → amoxicillin (Anand clinic, 2026).
- Metformin twice: Glycomet (Sunrise) + Glucophage (Anand). Two brands, same molecule.
- Ramipril → dry cough → dextromethorphan: a prescribing cascade.
- eGFR 72 → 61 → 52 → 47 across **four labs, three test names, one in SI units**, while on metformin.

Then open **Lab trends → eGFR**: the regression line, the dashed projection to 45, and a reference band. Each point is coloured by its lab; tap a point to open the original report.

**3. Share (1:15–1:35).** Open **Sharing**. The defaults are conditions, medicines, allergies and labs, with mental health off and 7 days. Switch on **Allow doctor to add documents and prescriptions** (step 5 needs it), then tap **Create QR code**.

**4. Doctor, laptop (1:35–2:20).** Open the QR link (or scan it).
- You're redirected to login. Choose **Dr. Meena Raghavan**, and you land back on the claim page. Tap **Open Rajan's record**.
- Rajan is at the top of the dashboard with **1 critical · 3 warnings**.
- The **Summary** tab is already set to *Nephrology*: key problems, medicines, labs with trend arrows, alerts and open questions, every line cited.
- In **Ask the record**, type: *"When did kidney function start declining and what was he taking then?"* The answer streams with citation chips.
- Click an **eGFR … D8 p1** chip. The **original 2024 Sunrise lab report** opens with the value highlighted.

**5. Prevention (2:20–2:40).** Tap **Prescribe** and type **Novamox 500**.
- A red **Critical: Penicillin allergy vs amoxicillin** alert appears before saving, and the button is blocked until an override reason is given.
- Switch to **Azithral**, pick **1-0-0**, enter 3 days: *No conflicts found*. Tap **Prescribe**, then **Print prescription**.

**6. Control (2:40–2:55).**
- Priya opens **Access log**: "Dr. Meena Raghavan (Nephrology) opened the shared record (QR) … viewed lab results & vitals …".
- She opens **Sharing → Revoke → Revoke access**.
- Dr. Meena refreshes the workspace: *"You no longer have access to this record."*

**7. Emergency (2:55–3:00).**
- Priya opens **Emergency card → Turn on**.
- Open the card link in another tab (or scan the QR) as a responder. **Penicillin** is shown in red, plus blood group **B+**, current medicines and a tap-to-call contact. No labs and no documents.
- Priya's bell shows *"Emergency access to Rajan's card at 9:14 PM."*

## Extra moments if there's time
- **Panel insights** on Dr. Meena's dashboard: *"Which of my patients have declining kidney function?"* returns Rajan with a sparkline, not Lakshmi (the control patient, zero alerts).
- **Documents → Explain simply → Tamil**: a grounded, cited explanation of the lab report in Tamil.
- **Settings → Export as FHIR Bundle**: the whole record as a standard FHIR R4 `collection` Bundle, with Provenance.
- **Admin** demo account: the doctor verification queue (Dr. Arjun is pending). Admins can't open any patient record.

## Reset between runs
```bash
cd backend && .venv/bin/python -m scripts.seed_demo --reset --stage live
```

## Rehearse it automatically
`backend/.venv/bin/python e2e/demo.py` runs this whole script headless (a phone for Priya, a laptop for Dr. Meena, a responder phone) and saves screenshots to `e2e/screenshots/demo_*.png`.
