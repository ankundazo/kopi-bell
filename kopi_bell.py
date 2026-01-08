import imaplib, ssl, os
from email import message_from_bytes
from email.header import decode_header
import requests

HOST = "haruka-a.sakura.ne.jp"
USER = os.environ.get("IMAP_USER") or input("IMAP user: ").strip()
PW   = os.environ.get("IMAP_PASS") or __import__("getpass").getpass("IMAP password: ")

LINE_TOKEN = os.environ.get("LINE_TOKEN")
if not LINE_TOKEN:
    raise SystemExit("LINE_TOKEN が未設定だよ（export LINE_TOKEN=...）")

FROM_KEYWORD = "noreply@kopichans.com"
SUBJECT_KEYWORD = "ライブ配信が始まりました"

def decode_mime(value: str) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    out = []
    for txt, enc in parts:
        if isinstance(txt, bytes):
            out.append(txt.decode(enc or "utf-8", errors="replace"))
        else:
            out.append(txt)
    return "".join(out)

def line_broadcast(text: str) -> None:
    url = "https://api.line.me/v2/bot/message/broadcast"
    payload = {"messages":[{"type":"text","text": text}]}
    r = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {LINE_TOKEN}",
            "Content-Type": "application/json; charset=utf-8",
        },
        json=payload,
        timeout=10,
    )
    r.raise_for_status()

ctx = ssl.create_default_context()
M = imaplib.IMAP4_SSL(HOST, 993, ssl_context=ctx)
M.login(USER, PW)
M.select("INBOX")

typ, data = M.search(None, "UNSEEN")
ids = data[0].split() if data and data[0] else []

sent = 0
for msgid in ids:
    typ, msgdata = M.fetch(msgid, "(RFC822)")
    raw = msgdata[0][1]
    msg = message_from_bytes(raw)

    subj = decode_mime(msg.get("Subject", ""))
    frm  = decode_mime(msg.get("From", ""))

    if (FROM_KEYWORD in frm) and (SUBJECT_KEYWORD in subj):
        text = "\uD83D\uDD14 こぴちゃんず LIVE 開始！\n今すぐチェックだよ?\u2728"
        line_broadcast(text)
        sent += 1
        M.store(msgid, "+FLAGS", "\\Seen")

from datetime import datetime
print(f"{datetime.now().isoformat()} Done. sent={sent}, unseen={len(ids)}")
