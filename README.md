# kopi-bell

公式API等に依存せず、非公式・最小構成で動作する草の根通知システムです。

現在は Raspberry Pi 上で以下を実装しています。

- SE（効果音）再生
- TTS音声再生（事前生成 wav）
- （次フェーズ）リレー連動によるパトライト制御

---

## 動作環境

- Raspberry Pi（Raspberry Pi OS）
- Python 3
- 音声出力環境（スピーカー、HDMI 等）

---

## 音声ファイルについて

本リポジトリには音声ファイル（wav）は含まれていません。

以下のディレクトリに配置してください。


```
/usr/local/share/sounds/kopi-bell/
```

使用しているファイル例（コードに合わせて調整してください）：

- se_notify.wav
- tts_live_start_adj.wav
- tts_live_soon_adj.wav

---

## 実行方法

```
python3 kopi_bell.py
```

---

## トラブルシュート

音が再生されない場合：

- 音量確認

  `alsamixer`

- デバイス確認

  `aplay -l`

- 手動再生テスト

  `aplay /usr/local/share/sounds/kopi-bell/se_notify.wav`

---

## Version

v0.2.0

SE + TTS 統合版（音声ファイルは除外）
