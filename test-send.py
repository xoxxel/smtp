import os
import smtplib
from email.mime.text import MIMEText

HOST = os.getenv("SMTP_TEST_HOST", "127.0.0.1")
PORT = int(os.getenv("SMTP_TEST_PORT", "2525"))
USE_STARTTLS = os.getenv("SMTP_TEST_STARTTLS", "false").lower() == "true"
REQUIRE_AUTH = os.getenv("SMTP_TEST_REQUIRE_AUTH", "true").lower() == "true"
USER = os.getenv("SMTP_TEST_USER", "ghost")
PASS = os.getenv("SMTP_TEST_PASS", "verysecret")
FROM = os.getenv("SMTP_TEST_FROM", os.getenv("DEFAULT_FROM", "noreply@nons.ir"))
TO = os.getenv("SMTP_TEST_TO", "me@example.com")
SUBJ = os.getenv("SMTP_TEST_SUBJECT", "SMTP→Resend gateway test")
HTML = os.getenv("SMTP_TEST_HTML", "<h3>It works!</h3><p>via Python SMTP gateway</p>")

msg = MIMEText(HTML, "html", "utf-8")
msg["Subject"] = SUBJ
msg["From"] = FROM
msg["To"] = TO

print(f"Connecting to {HOST}:{PORT} ...")
with smtplib.SMTP(HOST, PORT, timeout=15) as s:
    s.ehlo()
    if USE_STARTTLS:
        print("Starting TLS ...")
        s.starttls()
        s.ehlo()
    if REQUIRE_AUTH:
        print("Logging in ...")
        s.login(USER, PASS)
    print(f"Sending mail: from={FROM} to={TO}")
    s.sendmail(FROM, [TO], msg.as_string())
    print("Sent.")
