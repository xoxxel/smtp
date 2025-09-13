import asyncio
import base64
import email
import logging
import os
import threading
from email.policy import default as default_policy
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests
from aiosmtpd.controller import Controller
from aiosmtpd.smtp import AuthResult, LoginPassword, SMTP
from dotenv import load_dotenv

load_dotenv()

RESEND_API_KEY = os.getenv("RESEND_API_KEY")
DEFAULT_FROM = os.getenv("DEFAULT_FROM", "noreply@example.com")
SMTP_BIND = os.getenv("SMTP_BIND", "0.0.0.0")
SMTP_PORT = int(os.getenv("SMTP_PORT", "2525"))
REQUIRE_AUTH = os.getenv("SMTP_REQUIRE_AUTH", "false").lower() == "true"
SMTP_USER = os.getenv("SMTP_USER", "ghost")
SMTP_PASS = os.getenv("SMTP_PASS", "secret")
HTTP_PORT = int(os.getenv("HTTP_PORT", "8080"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(level=LOG_LEVEL,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("smtp-resend")

if not RESEND_API_KEY:
    raise SystemExit("RESEND_API_KEY is required")

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/healthz":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_response(404)
            self.end_headers()

def run_http_healthcheck():
    httpd = HTTPServer(("0.0.0.0", HTTP_PORT), HealthHandler)
    logger.info(f"HTTP healthcheck on :{HTTP_PORT}/healthz")
    httpd.serve_forever()

class ResendHandler:
    async def handle_DATA(self, server: SMTP, session, envelope):
        try:
            msg = email.message_from_bytes(envelope.content, policy=default_policy)
            subject = msg["subject"] or ""
            from_hdr = (msg["from"] or DEFAULT_FROM)
            to_rcpts = envelope.rcpt_tos or []

            text_body, html_body = None, None
            attachments = []

            if msg.is_multipart():
                for part in msg.walk():
                    ctype = part.get_content_type()
                    disp = (part.get("Content-Disposition") or "").lower()
                    if ctype == "text/plain" and text_body is None:
                        text_body = part.get_content()
                    elif ctype == "text/html" and html_body is None:
                        html_body = part.get_content()
                    elif disp.startswith("attachment"):
                        data = part.get_content()
                        if isinstance(data, str):
                            data = data.encode()
                        attachments.append({
                            "filename": part.get_filename() or "file.bin",
                            "content": base64.b64encode(data).decode(),
                        })
            else:
                # single part
                ctype = msg.get_content_type()
                if ctype == "text/html":
                    html_body = msg.get_content()
                else:
                    text_body = msg.get_content()

            payload = {
                "from": from_hdr,
                "to": to_rcpts,
                "subject": subject,
            }
            if html_body:
                payload["html"] = html_body
            if text_body:
                payload["text"] = text_body
            if attachments:
                payload["attachments"] = attachments

            logger.info(f"Sending via Resend → to={to_rcpts} subj={subject!r}")
            r = requests.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=30,
            )
            if r.status_code >= 300:
                logger.error("Resend error %s: %s", r.status_code, r.text)
                return b"451 Temporary failure\n"

            return b"250 Message accepted\n"
        except Exception as e:
            logger.exception("handle_DATA failed: %s", e)
            return b"451 Temporary failure\n"

    async def authenticate(self, server: SMTP, session, envelope, mechanism, auth_data):
        if not REQUIRE_AUTH:
            return AuthResult(success=True)
        if mechanism not in {"LOGIN", "PLAIN"}:
            return AuthResult(success=False)
        if isinstance(auth_data, LoginPassword):
            if auth_data.login == SMTP_USER and auth_data.password == SMTP_PASS:
                return AuthResult(success=True)
        return AuthResult(success=False)

class AuthController(Controller):
    def factory(self):
        return SMTP(self.handler, authenticator=self.handler.authenticate, auth_required=REQUIRE_AUTH)

if __name__ == "__main__":
    # healthcheck thread
    t = threading.Thread(target=run_http_healthcheck, daemon=True)
    t.start()

    handler = ResendHandler()
    controller = AuthController(handler, hostname=SMTP_BIND, port=SMTP_PORT)
    controller.start()
    logger.info(f"SMTP listening on {SMTP_BIND}:{SMTP_PORT} (auth={'ON' if REQUIRE_AUTH else 'OFF'})")
    try:
        asyncio.get_event_loop().run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        controller.stop()