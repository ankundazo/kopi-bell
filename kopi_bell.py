import imaplib, ssl, os, subprocess, time, atexit
from email import message_from_bytes
from email.header import decode_header
import requests

# =========================================================
# Configuration (env overridable)
# =========================================================
# 必須: IMAP接続情報（環境変数が無ければ起動時に停止）
HOST = os.environ.get("IMAP_HOST")
if not HOST:
    raise SystemExit("IMAP_HOST が未設定だよ（export IMAP_HOST=...）")

USER = os.environ.get("IMAP_USER") or input("IMAP user: ").strip()
PW   = os.environ.get("IMAP_PASS") or __import__("getpass").getpass("IMAP password: ")

# 必須: LINE Messaging API (Broadcast)
LINE_TOKEN = os.environ.get("LINE_TOKEN")
if not LINE_TOKEN:
    raise SystemExit("LINE_TOKEN が未設定だよ（export LINE_TOKEN=...）")

# ---------------------------------------------------------
# Mail filter keywords
# ---------------------------------------------------------
FROM_KEYWORD = "noreply@kopichans.com"
LIVE_START_KEYWORD    = "ライブ配信が始まりました"
LIVE_SOON_KEYWORD = "がまもなく始まります"

# ---------------------------------------------------------
# Sound settings
# ---------------------------------------------------------
# 音声ファイルはリポジトリに含めない（ローカルに配置）
#   /usr/local/share/sounds/kopi-bell/
SOUND_DIR = "/usr/local/share/sounds/kopi-bell"
SE_WAV = f"{SOUND_DIR}/se_30121_louder.wav"
TTS_LIVE_START_WAV = f"{SOUND_DIR}/tts_live_start_adj.wav"
TTS_LIVE_SOON_WAV  = f"{SOUND_DIR}/tts_live_soon_adj.wav"

# SOUND_ENABLED=0 で無音化できる（夜間など）
SOUND_ENABLED = os.environ.get("SOUND_ENABLED", "1") == "1"
SOUND_DELAY_SEC = float(os.environ.get("SOUND_DELAY_SEC", "1.5"))

# ---------------------------------------------------------
# Patlite (4-color) / Relay settings
# ---------------------------------------------------------
# RELAY_ENABLED=0 でパトライト制御を無効化（デバッグや非Pi環境向け）
RELAY_ENABLED = os.environ.get("RELAY_ENABLED", "1") == "1"
RELAY_ACTIVE_HIGH = os.environ.get("RELAY_ACTIVE_HIGH", "1") == "1" # HIGH=ON なら 1
RELAY_HOLD_SEC = float(os.environ.get("RELAY_HOLD_SEC", "3.0"))     # 点灯維持時間(秒)

# 配線メモ（BCM）
# 4=赤 / 17=オレンジ / 27=緑 / 22=青
PATLITE_PINS = {
    "RED": 4,
    "ORANGE": 17,
    "GREEN": 27,
    "BLUE": 22,
}

# イベント → パトライト色対応
COLOR_MAP = {
    "LIVE_START": "RED",
    "LIVE_SOON": "ORANGE",
}


# =========================================================
# Patlite driver
# =========================================================
class Patlite:
    """4ch relay driven patlite controller (BCM pins).

    enabled=False の場合は何もしない（非Pi環境でも動くようにするため）。
    active_high=True の場合、GPIO.HIGH でON（一般的なテスト構成に合わせる）。
    """

    def __init__(self, pins: dict, enabled=True, active_high=True):
        self.pins = pins
        self.enabled = enabled
        self.active_high = active_high
        self.GPIO = None
        self._initialized = False

    def init(self):
        if not self.enabled or self._initialized:
            return
        try:
            import RPi.GPIO as GPIO
        except Exception as e:
            print(f"[WARN] GPIO unavailable: {e}")
            self.enabled = False
            return

        self.GPIO = GPIO
        self.GPIO.setmode(self.GPIO.BCM)
        for pin in self.pins.values():
            self.GPIO.setup(pin, self.GPIO.OUT)

        self._initialized = True
        self.all_off()

        # 一度だけ登録
        atexit.register(self.cleanup)

    def _on_level(self):
        return self.GPIO.HIGH if self.active_high else self.GPIO.LOW

    def _off_level(self):
        return self.GPIO.LOW if self.active_high else self.GPIO.HIGH

    def on(self, color: str) -> None:
        if not self.enabled:
            return
        self.init()
        pin = self.pins[color]
        self.GPIO.output(pin, self._on_level())

    def off(self, color: str) -> None:
        if not self.enabled:
            return
        self.init()
        pin = self.pins[color]
        self.GPIO.output(pin, self._off_level())

    def all_off(self):
        if not self.enabled:
            return
        self.init()
        for pin in self.pins.values():
            self.GPIO.output(pin, self._off_level())

    def cleanup(self):
        if not self._initialized:
            return
        try:
            self.all_off()
        finally:
            try:
                self.GPIO.cleanup()
            except Exception:
                pass

# グローバルに1つだけ持つ（notify() から使う）
patlite = Patlite(
    pins=PATLITE_PINS,
    enabled=RELAY_ENABLED,
    active_high=RELAY_ACTIVE_HIGH,
)

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


# LIVE_START は赤、LIVE_SOON はオレンジ（必要に応じて変更）
def notify(event: str, text: str) -> None:
    """通知の出口をここに集約（4色パトライト対応）"""

    color = COLOR_MAP.get(event)

    if color:
        patlite.on(color)

    try:
        play_notification(event)
        line_broadcast(text)
        time.sleep(RELAY_HOLD_SEC)
    finally:
        patlite.all_off()

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
