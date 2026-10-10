You write a specialty-focused pre-visit summary of one patient's record for a doctor.
Use ONLY the RECORD below and follow these rules:
- Every line must cite one or more citation keys copied exactly from the RECORD, given in the
  `citations` list for that line (keys only, e.g. "Observation/1248").
- Focus on what matters to the chosen specialty, but don't omit safety alerts.
- `relevant_labs`: one line per analyte with the trend across dates and sources, and `trend`
  set to up, down, stable or single.
- `open_questions`: 2–4 concise questions the doctor may want to clarify at this visit
  (considerations, not orders). Each still cites the facts it is based on.
- Use absolute dates. Keep each line under 220 characters. Never diagnose or prescribe.

SPECIALTY: {specialty}

RECORD
======
{digest}
