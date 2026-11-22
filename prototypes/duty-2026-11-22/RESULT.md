# Step 4 第一弾 — 当番テキストの配線結果

コード: `src/config.py` / `src/personas.py` / `src/duty.py`、検証: `sim/simulate_duty.py`
まだ offline のみ。生成は決定的な組み立て (LLM なし) で、配線の検証が目的。
Ollama 生成は同じ compose インターフェースの後ろに実機で差し替える。

## 通ったこと
- .env.example の仮値を7件検出し、live モードの起動を正しく拒否した
  (未設定: DISCORD_BOT_TOKEN / GUILD_ID / LUNACHANNEL_ID / OLLAMA_MODEL)
- 当番ローテーション: 日付から決定的に決まる (2026-11-23 朝=こはく、夜=ステラ)
- 朝当番が前日の日記の種 (天職感の話) を実際に含んだ — 「記憶が使われる」の配線が通った
- 当番2件がスケジューラで実行され、出来事プールに記録される

## 見つけた粗さ
- 種の文が「昨日の夜の〜」で始まるため、本文の「昨日の日記からひとつ。」と重なった。
  種は全文ではなく断片 (話題+接続の一言) で持つ形に寄せる方がよい。
  diary.json の nextMorningSeed の書き方ルールとして仕様に足す候補
