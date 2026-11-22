# 日記のサイト受け渡し — 契約と書き出しの結果

契約: `docs/DIARY_DELIVERY.md`、コード: `src/export_site.py`、検証: `sim/simulate_export.py`

## 決めたこと
- 渡すのは sweet-bits の `src/data/diary.json` 1ファイルだけ (flower.json と同じ流儀)
- latest = 最新1件の全文 (見出しごとの節+段落)、entries = 過去分の目次だけ (最大30件)
- seed・生ログ・メディアは渡さない。全体 64KB 上限は書き出し側が守る
- 経路は v1 では自動 push せず、ルナが sweet-bits の通常フロー (会話→PR) で届ける

## 検証結果
- 試作日記2件 (11-21 / 11-22) から diary.json を生成: **4,167 bytes**
- latest は 11-22 の全文、目次は新しい順、引用 (水やりみたい) も原文どおり
- seed がサイト側データに含まれていないことを確認

## 次 (ルナができること)
- sweet-bits 側に /diary ページとトップの日記カードを実装する
  (いつもの方式: 叩き台を会話で詰める → ブランチ + 下書き PR → マージ)
- 初期データとして、この export 済み diary.json (2件) をそのまま置く
