"""Gmail send via the Gmail REST API (users.messages.send).

Design choices:
  * The browser performs Google OAuth (Google Identity Services, scope gmail.send ONLY) and passes the
    short-lived access token with the single send request. OPAI never stores the token, never logs it and
    has no read/search access. Reply detection would need a separate, opt-in scope - it is not built here.
  * `send` is the ONLY network call and it is injectable, so tests never touch the network.
"""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from email.message import EmailMessage
from typing import Optional

GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"


class GmailError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


def client_id() -> Optional[str]:
    return os.getenv("GOOGLE_CLIENT_ID", "").strip() or None


def build_raw(to: str, subject: str, body: str, from_addr: Optional[str] = None) -> str:
    m = EmailMessage()
    m["To"], m["Subject"] = to, subject
    if from_addr:
        m["From"] = from_addr
    m.set_content(body)
    return base64.urlsafe_b64encode(m.as_bytes()).decode()


def send(access_token: str, to: str, subject: str, body: str, from_addr: Optional[str] = None) -> str:
    """Returns the Gmail message id. Raises GmailError (never leaks the token)."""
    if not access_token:
        raise GmailError(401, "No Gmail access token supplied. Connect Gmail (send-only) or use manual mode.")
    req = urllib.request.Request(SEND_URL, method="POST",
                                 data=json.dumps({"raw": build_raw(to, subject, body, from_addr)}).encode(),
                                 headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode()).get("id", "")
    except urllib.error.HTTPError as e:
        msg = {401: "Gmail rejected the token (expired or wrong scope). Reconnect Gmail.",
               403: "Gmail refused: the token lacks the gmail.send scope.",
               429: "Gmail rate limit reached. Try again later."}.get(e.code, f"Gmail returned HTTP {e.code}.")
        raise GmailError(e.code if e.code in (401, 403, 429) else 502, msg)
    except Exception:
        raise GmailError(502, "Could not reach Gmail. Nothing was sent.")
