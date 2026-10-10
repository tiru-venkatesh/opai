# Resume Lab additions

New (all grounded in the student's own text; nothing is sent or submitted):

| Endpoint | What it does |
|---|---|
| `POST /v1/resume-lab/review` | ATS-readiness checklist for one version (contact, sections, length, bullets, tables/symbols, optional posting keywords). Rule-based; no real ATS is simulated. |
| `POST /v1/resume-lab/coach` | Diagnoses one bullet, asks for the missing TRUE details. An AI rewrite is returned only if it adds no number, tool or name that the student did not supply (`rewrite_is_grounded`). |
| `POST /v1/resume-lab/compare` | Two versions: common / unique / reworded bullets, skills, stat deltas, posting coverage. |
| `POST /v1/resume-lab/build` | Preview a tailored resume: base version with bullets reordered/removed + verbatim bullets from the student's other versions (422 if an "extra" is not in their library). |
| `POST /v1/resume-lab/export` | Same build as DOCX / PDF / TXT (single column, selectable text). Needs `python-docx` and `reportlab`. |
| `POST /v1/resume-lab/attach` | Saves the tailored resume as a library version and links it to one application (`resume_id`, `tailored_at`, `resume_bullets`). Re-attaching replaces the same tailored version instead of filling the library. |

Pure logic lives in `backend/resume_lab_core.py` (no FastAPI/DB), so it is testable anywhere:
`cd backend && python -m pytest tests/test_resume_lab_core.py -q`

Endpoint tests (need the full requirements installed): `python -m pytest tests/test_resume_lab_api.py -q`

Page: `frontend/resume-lab.html` (copied to `backend/static/`) has new tabs: Tailor & export, ATS review, Bullet coach, Compare.

## Verification status
* `resume_lab_core` tests: run and passing (including real DOCX round-trip and PDF text extraction).
* API module: compiles, static name check clean. **Endpoint tests were written but NOT run** (FastAPI/SQLAlchemy not installable where this was built). Run the two pytest commands above.
* Page JS: syntax-checked only, not exercised in a browser.
