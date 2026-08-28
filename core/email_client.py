"""
IMAP/SMTP email client for per-character email integration.

Gmail setup:
  1. Enable IMAP in Gmail Settings → See all settings → Forwarding and POP/IMAP
  2. Use an App Password (Google Account → Security → App passwords) — not your regular password
  3. IMAP host: imap.gmail.com port 993 / SMTP host: smtp.gmail.com port 587
"""

from __future__ import annotations

import imaplib
import smtplib
import socket
import email as _email_mod
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import decode_header as _raw_decode
from email.utils import parseaddr, parsedate_to_datetime, formataddr
from typing import Optional

_TIMEOUT = 20  # seconds


def _decode_str(value) -> str:
    if not value:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    parts = _raw_decode(str(value))
    result = []
    for part, charset in parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(str(part))
    return "".join(result).strip()


def _get_body(msg) -> tuple[str, str]:
    """Return (text_plain, text_html) from a parsed email message."""
    text_body = ""
    html_body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition", ""))
            if "attachment" in cd:
                continue
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            charset = part.get_content_charset() or "utf-8"
            decoded = payload.decode(charset, errors="replace")
            if ct == "text/plain" and not text_body:
                text_body = decoded
            elif ct == "text/html" and not html_body:
                html_body = decoded
    else:
        ct = msg.get_content_type()
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            decoded = payload.decode(charset, errors="replace")
            if ct == "text/html":
                html_body = decoded
            else:
                text_body = decoded
    return text_body, html_body


def _imap_connect(char: dict) -> imaplib.IMAP4_SSL:
    host = (char.get("email_imap_host") or "imap.gmail.com").strip()
    port = int(char.get("email_imap_port") or 993)
    addr = (char.get("email_address") or "").strip()
    # App Passwords are displayed with spaces (xxxx xxxx xxxx xxxx) — remove them
    pwd = (char.get("email_password") or "").replace(" ", "").strip()
    if not addr or not pwd:
        raise RuntimeError("Email not configured for this character. Add credentials in Character → Email tab.")
    imap = imaplib.IMAP4_SSL(host, port)
    imap.sock.settimeout(_TIMEOUT)
    try:
        imap.login(addr, pwd)
    except imaplib.IMAP4.error as e:
        err = str(e)
        if "AUTHENTICATIONFAILED" in err or "Invalid credentials" in err:
            raise RuntimeError(
                "Gmail authentication failed. Check:\n"
                "1. IMAP is enabled in Gmail → Settings → See all settings → Forwarding and POP/IMAP\n"
                "2. You're using a Gmail App Password (not your regular password)\n"
                "3. App Password is from Google Account → Security → App passwords (requires 2-Step Verification ON)\n"
                "4. The email address matches the Google account"
            )
        raise RuntimeError(f"IMAP login error: {err}")
    return imap


def fetch_inbox(char: dict, folder: str = "INBOX", limit: int = 50) -> list[dict]:
    imap = _imap_connect(char)
    try:
        status, _ = imap.select(folder, readonly=True)
        if status != "OK":
            raise RuntimeError(f"Could not select folder '{folder}'")

        _, data = imap.search(None, "ALL")
        uids = data[0].split()
        uids = list(reversed(uids[-limit:]))  # newest first

        if not uids:
            return []

        uid_list = b",".join(uids)
        _, msg_data = imap.fetch(uid_list, "(RFC822.HEADER FLAGS UID)")

        result = []
        i = 0
        while i < len(msg_data):
            item = msg_data[i]
            if not isinstance(item, tuple):
                i += 1
                continue
            meta_str = item[0].decode()
            raw_headers = item[1]

            seen = "\\Seen" in meta_str
            uid_match = [p for p in meta_str.split() if p.isdigit()]
            uid = uid_match[0] if uid_match else str(i)

            msg = _email_mod.message_from_bytes(raw_headers)
            from_raw = msg.get("From", "")
            from_name, from_addr = parseaddr(from_raw)

            date_str = msg.get("Date", "")
            try:
                dt = parsedate_to_datetime(date_str).isoformat()
            except Exception:
                dt = date_str

            result.append({
                "uid": uid,
                "from_name": _decode_str(from_name) or from_addr,
                "from_addr": from_addr,
                "to": _decode_str(msg.get("To", "")),
                "subject": _decode_str(msg.get("Subject", "(no subject)")),
                "date": dt,
                "read": seen,
                "message_id": msg.get("Message-ID", ""),
            })
            i += 2  # IMAP fetch returns (header, b')') pairs

        return result
    finally:
        try:
            imap.logout()
        except Exception:
            pass


def fetch_message(char: dict, uid: str, folder: str = "INBOX") -> dict:
    imap = _imap_connect(char)
    try:
        imap.select(folder, readonly=False)
        _, msg_data = imap.fetch(uid.encode(), "(RFC822)")

        raw = None
        for item in msg_data:
            if isinstance(item, tuple):
                raw = item[1]
                break
        if not raw:
            raise RuntimeError("Message not found")

        # Mark as read
        try:
            imap.store(uid.encode(), "+FLAGS", "\\Seen")
        except Exception:
            pass

        msg = _email_mod.message_from_bytes(raw)
        from_raw = msg.get("From", "")
        from_name, from_addr = parseaddr(from_raw)

        date_str = msg.get("Date", "")
        try:
            dt = parsedate_to_datetime(date_str).isoformat()
        except Exception:
            dt = date_str

        text_body, html_body = _get_body(msg)

        return {
            "uid": uid,
            "from_name": _decode_str(from_name) or from_addr,
            "from_addr": from_addr,
            "to": _decode_str(msg.get("To", "")),
            "cc": _decode_str(msg.get("Cc", "")),
            "subject": _decode_str(msg.get("Subject", "(no subject)")),
            "date": dt,
            "message_id": msg.get("Message-ID", ""),
            "references": msg.get("References", ""),
            "body_text": text_body,
            "body_html": html_body,
        }
    finally:
        try:
            imap.logout()
        except Exception:
            pass


def send_email(
    char: dict,
    to: str,
    subject: str,
    body: str,
    reply_to_message_id: Optional[str] = None,
    references: Optional[str] = None,
) -> None:
    host = (char.get("email_smtp_host") or "smtp.gmail.com").strip()
    port = int(char.get("email_smtp_port") or 587)
    addr = (char.get("email_address") or "").strip()
    pwd = (char.get("email_password") or "").replace(" ", "").strip()

    if not addr or not pwd:
        raise RuntimeError("SMTP credentials not configured for this character.")

    msg = MIMEText(body, "plain", "utf-8")
    msg["From"] = addr
    msg["To"] = to
    msg["Subject"] = subject
    if reply_to_message_id:
        msg["In-Reply-To"] = reply_to_message_id
        refs = ((references or "") + " " + reply_to_message_id).strip()
        msg["References"] = refs

    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=_TIMEOUT) as smtp:
            smtp.login(addr, pwd)
            smtp.sendmail(addr, [to], msg.as_string())
    else:
        with smtplib.SMTP(host, port, timeout=_TIMEOUT) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(addr, pwd)
            smtp.sendmail(addr, [to], msg.as_string())


def list_folders(char: dict) -> list[str]:
    imap = _imap_connect(char)
    try:
        _, folders = imap.list()
        result = []
        for f in folders:
            if isinstance(f, bytes):
                parts = f.decode().split('"/"')
                name = parts[-1].strip().strip('"')
                result.append(name)
        return result
    finally:
        try:
            imap.logout()
        except Exception:
            pass
