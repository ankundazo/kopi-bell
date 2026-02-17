import imaplib, ssl, os, subprocess, time
from email import message_from_bytes
from email.header import decode_header
import requests

HOST = os.environ.get("IMAP_HOST")
if not HOST:
    raise SystemExit("IMAP_HOST が未設定だよ（export IMAP_HOST=...）")

USER = os.environ.get("IMAP_USER") or input("IMAP user: ").strip()
PW   = os.environ.get("IMAP_PASS") or __import__("getpass").getpass("IMAP password: ")

LINE_TOKEN = os.environ.get("LINE_TOKEN")
if not LINE_TOKEN:
    raise SystemExit("LINE_TOKEN が未設定だよ（export LINE_TOKEN=...）")

FROM_KEYWORD = "noreply@kopichans.com"
LIVE_START_KEYWORD    = "ライブ配信が始まりました"
LIVE_SOON_KEYWORD = "がまもなく始まります"

# ===== Sound settings =====
SOUND_DIR = "/usr/local/share/sounds/kopi-bell"
SE_WAV = f"{SOUND_DIR}/se_30121_louder.wav"
TTS_LIVE_START_WAV = f"{SOUND_DIR}/tts_live_start_adj.wav"
TTS_LIVE_SOON_WAV  = f"{SOUND_DIR}/tts_live_soon_adj.wav"

SOUND_ENABLED = os.environ.get("SOUND_ENABLED", "1") == "1"
SOUND_DELAY_SEC = float(os.environ.get("SOUND_DELAY_SEC", "1.5"))


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


def _aplay(path: str, async_play: bool = False) -> None:
    """path が存在するときだけ aplay。"""
    if not os.path.exists(path):
        print(f"[WARN] sound not found: {path}")
        return
    if async_play:
        subprocess.Popen(["aplay", path])
    else:
        subprocess.run(["aplay", path], check=False)


def play_notification(event: str) -> None:
    """SE → TTS の順で鳴らす。"""
    if not SOUND_ENABLED:
        return

    if event == "LIVE_START":
        tts = TTS_LIVE_START_WAV
    elif event == "LIVE_SOON":
        tts = TTS_LIVE_SOON_WAV
    else:
        return

    _aplay(SE_WAV, async_play=True)
    time.sleep(SOUND_DELAY_SEC)
    _aplay(tts, async_play=False)


def notify(event: str, text: str) -> None:
    """通知の出口をここに集約（今後パトライトもここに足す）"""
    # まずローカルで気づけるように音 → その後にLINE
    play_notification(event)
    line_broadcast(text)


def main() -> None:
    ctx = ssl.create_default_context()
    M = imaplib.IMAP4_SSL(HOST, 993, ssl_context=ctx)
    M.login(USER, PW)
    M.select("INBOX")

    typ, data = M.search(None, '(UNSEEN FROM "noreply@kopichans.com")')
    ids = data[0].split() if data and data[0] else []

    sent = 0
    for msgid in ids:
        typ, msgdata = M.fetch(msgid, "(RFC822)")
        raw = msgdata[0][1]
        msg = message_from_bytes(raw)

        subj = decode_mime(msg.get("Subject", ""))
        frm  = decode_mime(msg.get("From", ""))

        if FROM_KEYWORD in frm:
            if LIVE_START_KEYWORD in subj:
                text = "\U0001F514 こぴちゃんず LIVE 開始！\n今すぐチェックだよ？\u2728"
                notify("LIVE_START", text)
                sent += 1
                M.store(msgid, "+FLAGS", "\\Seen")

            elif LIVE_SOON_KEYWORD in subj:
                text = "\u23F0 こぴちゃんず LIVE まもなく！\nスタンバイしよ？\u2728"
                notify("LIVE_SOON", text)
                sent += 1
                M.store(msgid, "+FLAGS", "\\Seen")

    from datetime import datetime
    print(f"{datetime.now().isoformat()} Done. sent={sent}, unseen={len(ids)}")


if __name__ == "__main__":
    main()
