---
name: jp-contract-review-extension
description: 日本法の契約レビュー時、commercial-legal:reviewの前後で実行する検証工程(設定読込確認・一次資料照合・適用要件判定・独立再検証・Word決定論的編集・機械検証)。
---
# 日本法契約レビュー拡張(標準 /commercial-legal:review に追加して実行)
1. 設定確認: `python3 scripts/check_config.py <既存CLAUDE.md> <追補>` が FAIL なら停止し「設定未読込」を報告。
2. 原本保全: SHA-256記録、原本は上書きせずコピーで作業。
3. 契約類型・当社立場・事実関係を確定/仮定に分けて記録。不明事実は補完しない。
4. 法令: 適用要件ごとに 充足/不充足/事実関係不明/法的解釈未確定/該当なし を判定(根拠付き)。正式名称・法令番号・条項・施行日・経過措置・基準日を一次資料(e-Gov等)の本文取得で確認。取得不能は「一次資料未確認」。契約書記載の旧法令名だけで適用法令を決めない。
5. 初回レビュー結果は review.json(judgments/evidence/revisions)に構造化。`python3 scripts/check_review_output.py review.json` が FAIL なら後続に進まない。
6. 独立再検証: 別サブエージェント(初回の結論を渡さない)で第10章の14項目を再検証。不一致は一次資料に戻る。解決不能は判断保留。
7. 修正指示: 判断保留でない修正のみ revisions.json 化 → `apply_revisions.py 原本 revisions.json 出力`(失敗時は成功と報告しない)。
8. 検証: `validate_docx.py 出力 --expect-ins N --expect-del N --expect-comments N` と `compare_documents.py 原本 出力 --revisions revisions.json` が共にPASS。Word実機での開封確認は別途(未実施なら未実施と明記)。
9. 日付: 報告書の年月日は `verify_dates.py scan` で曜日検算。数値は計算スクリプトで。
10. 実行記録(日時・モデル・版・ハッシュ・判定・エラー)を logs/ に保存。契約書本文・取引先名をWeb検索に送らない。
最終判断は人間。
