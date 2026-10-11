# Resume Lab v3: review, coach, compare, builder, export, attach

## What is new
| Piece | Endpoint | Notes |
|---|---|---|
| ATS / quality review | `POST /v1/resume-lab/review` | Deterministic checks on extracted text (structure, formatting, content, keywords vs a posting). Not a vendor ATS score, and says so. |
| Bullet coach | `POST /v1/resume-lab/coach` | Weakest bullets first, with the questions only the student can answer. Optional `rewrite:true` asks Groq; every rewrite is checked by `verify_rewrite` and dropped if it adds a number, tool or name not in the original bullet. |
| Compare | `POST /v1/resume-lab/compare` | Bullets (identical / reworded / only in one), skills, sections, stats, posting coverage. |
| Builder | `POST /v1/resume-lab/builds/suggest`, `POST/GET/PUT/DELETE /v1/resume-lab/builds[/{id}]` | Draft only reorders and trims the base resume. Saving requires every bullet/skill to come from the student's own resumes or be explicitly marked "I wrote this". Provenance is set server-side. |
| Export | `GET /v1/resume-lab/resumes/{id}/export?format=docx\|pdf\|txt` | Single column, real text, no tables or images. Reference resumes can never be exported. |
| Attach | `POST /v1/resume-lab/attach`, `DELETE /v1/resume-lab/attach/{application_id}`, `GET /v1/resume-lab/attachments` | Records which version goes with an application. Submits nothing. |

Tailored builds are stored as `resumes` rows with `kind="tailored"` (new `resumes.build` JSON column, added by the startup migration). They do not count toward the 10-version limit and are kept out of match, the bullet bank and insights.

## Other changes
* `resume_lab_tools.py` (new): all pure logic, no FastAPI/DB. `resume_lab_api.py` re-exports the old parsing names.
* **Parser fix:** a bullet without a trailing period used to swallow the next project title line (`CivicIQ | React, Node.js`). Titles and dated role lines are no longer merged. Affects Match/Insights numbers slightly (more accurate).
* `PATCH /v1/opp/applications/{id}` now rejects a `resume_id` that is not the caller's own/tailored resume (it previously accepted any id).
* CORS exposes `Content-Disposition` and `X-Export-Warnings` so downloads get proper names.
* `requirements.txt`: added `reportlab` (PDF export). The PDF font cannot show non-Latin scripts; the response sets `X-Export-Warnings` and the page tells the user.
* `frontend/sw.js` cache `opai-v16`; the page exists in `frontend/` and `backend/static/` (kept identical).

## How it was tested (be aware)
* `tests/test_resume_lab_tools.py`: 24 tests of the pure logic, all pass (run with `python tests/test_resume_lab_tools.py` or pytest). Includes real DOCX/PDF generation and re-parsing the exported PDF.
* The page was driven in headless Chromium against a **stub server** that serves the same contracts from the same pure functions: review, coach, compare, draft, rejection of invented bullets, save, re-save, DOCX/PDF download, attach, delete and detach, mobile width. No JS errors.
* **Not run:** the FastAPI endpoints themselves, and `tests/test_resume_lab_api.py` (new tests appended, 11). The sandbox had no FastAPI/SQLAlchemy/pytest and no network. Run `cd backend && python -m pytest tests/test_resume_lab_api.py tests/test_resume_lab_tools.py -q` before deploying. If something fails it will most likely be in the endpoint glue.
