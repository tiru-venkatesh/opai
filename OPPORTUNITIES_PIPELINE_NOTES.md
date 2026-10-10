# OPAI Opportunities pipeline changes

## Included
- `backend/database.py`: adds `content_hash`, `approved_hash`, and `send_state` to Outbox items. Existing installations receive the new columns through the existing idempotent auto-migration.
- `backend/main.py`: hashes the canonical JSON payload when an Outbox item is created; approval checks the current payload against that hash and stores the approved hash. Approval no longer records a professor email as sent. `POST /v1/outbox/{id}/mark-sent` records confirmed delivery only if the sender supplies the exact approved SHA-256 hash. On a mismatch, the item returns to pending approval.
- `backend/schemas.py`: exposes Outbox hash and send-state fields.
- `backend/static/opportunities.html` and `frontend/opportunities.html`: responsive Opportunities workspace connected to existing FastAPI endpoints for opportunity intake/matching, applications/follow-ups, professor contacts, and Outbox approval.

## Important delivery boundary
The backend `mark-sent` endpoint is a delivery-confirmation endpoint, not a Gmail sender. A Gmail delivery client must send the exact approved payload and call `mark-sent` with the matching `content_hash` only after Gmail confirms success. The current legacy browser app has a separate local-storage Outbox/Gmail flow, so it is not automatically wired to this backend hash protocol by these changes. Do not treat a backend approval as proof that Gmail sent a message.

## Verification
- Python syntax compilation passed for backend modules.
- JavaScript syntax check passed for the new Opportunities page.
- Full pytest suite could not be collected in this environment because the installed Python environment is missing the declared `groq` dependency (`ModuleNotFoundError: No module named 'groq'`). Install `backend/requirements.txt` before running the full test suite.

## Open the page
After starting the FastAPI backend, open `/static/opportunities.html`. Enter the API base URL and the existing OPAI user UUID. The API must be reachable from the browser and configured with the appropriate CORS origin.

## Gmail send integration (added)
- `POST /v1/outbox/{id}/send-gmail` accepts `user_id`, a short-lived Google OAuth `access_token`, and the approved SHA-256 hash. It verifies ownership, approval state, and exact content hash before calling Gmail's `users/me/messages/send` endpoint.
- The access token is never persisted or logged. The Opportunities page requests the `gmail.send` scope only after the user clicks Connect Gmail, keeps the token in memory, asks for final confirmation before sending, and clears it after the send attempt.
- The Outbox displays Send only for approved email items awaiting delivery. A successful Gmail response must include a message ID before delivery is marked sent.
- If the network result is ambiguous, the item is frozen as `failed` instead of offering a blind retry that could send a duplicate. Check Gmail Sent and reconcile before resetting it.
- This uses the existing Firebase web config in the project. The Firebase authorized domains, Google OAuth consent screen, Gmail API, and account permissions must be configured in Google/Firebase consoles. Sensitive Gmail scope approval may be required for production use.
