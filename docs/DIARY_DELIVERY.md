# 日記のサイト受け渡し契約 (v1)

sweet-home (日記を書く側) と sweet-bits (見せる側) の間の約束。
flower.json と同じ流儀: 小さな構造化テキストだけが国境を越える。

## 渡すもの
- ファイル1つ: sweet-bits の `src/data/diary.json`
- 中身:
  - `latest`: 最新の日記1件の全文 (date / writerName / title / excerpt /
    sections[{heading, topic, paragraphs[]}] / topics / thread)
  - `thread` (任意): 「いまの話」— premise / progress / question 各1文。
    リビングで続いている話の前提・今日の進み・残っている問い。
    サイトは /diary の頭に小さく出す
  - `entries`: 過去分の目次だけ (date / writerName / title / excerpt)、最大30件
- 渡さないもの: 動画・画像・Discord の生ログ・seed (翌朝の種は家の中のもの)

## 大きさの上限
- diary.json 全体で 64KB を超えない。entries は30件で頭打ち、
  それより古い分は月単位の要約に蒸留されてから落ちる (サイト側の責務ではなく
  書き出し側 = sweet-home の export が守る)

## 更新の経路 (v1)
- 実機の sweet-home が export した diary.json を、ルナが sweet-bits の
  通常フロー (会話で詰める → ブランチ + PR) で届ける。自動 push はしない
- 頻度は日記の頻度 (1日1回) 以下。サイトの他の更新と束ねてもよい

## サイト側の表示 (v1 の想定)
- トップ: 最新日記のカード (title + excerpt + 書き手) → /diary へ
- /diary: 最新の全文 (見出しごとに節) + 過去の目次
- dev-log とは別レーン (あちらは取り組みの区切り、こちらは毎日の暮らし)
