# commercial-legal-jp-extension

Claude for Legal の **Commercial Legal** プラグインに重ねて使う、**日本法の契約レビュー向け検証拡張**です(非公式。Anthropic とは無関係)。
Commercial Legal 本体は改変せず、後段で「法的判断の検証」と「Word 変更履歴の検証」を行います。

> **重要:** 本ツールは法的助言ではありません。出力は機械的な整合確認と AI による検討結果であり、法的正確性を保証しません。契約の締結・送付・最終的な法的判断は、必ず人間(弁護士・法務担当者)が行ってください。

## できること
- 契約書原文・事実関係・法令の一次資料に基づく初回レビュー(`review.json`)の機械検証(引用照合、条番号、数値、適用要件)
- 結論を伏せた独立再検証、不一致の分類(客観/解釈/取引判断)、反証レビュー
- 修正案の分類(検証済みの修正 / 交渉上の提案 / 確認事項 / 反映禁止)と、条件を満たすものだけの Word 変更履歴・コメント反映
- Word の整合検証(変更履歴・コメント件数、本文の差分が意図した範囲に限られるか)
- 法律知識基盤(SQLite FTS5 + TF-IDF の検索、台帳のハッシュ連鎖、MCP サーバ)

## 構成
| ディレクトリ | 内容 |
|---|---|
| `scripts/` | ゲート・検証・Word 反映・知識基盤のスクリプト(Python 標準ライブラリ中心。`python3 -I` で実行) |
| `agents/`, `skills/` | 独立再検証・反証レビュー用エージェント定義、レビュー手順スキル |
| `schemas/`, `specs/`, `config/`, `playbooks/` | JSON スキーマ、類型別仕様、リスク方針、分岐プレイブック |
| `docs/` | 審査基準・出力形式・操作手順・知識基盤の仕様書 |
| `examples/` | サンプル契約書とレビュー例(下記) |
| `profile/` | 実務プロファイルの**テンプレート**(各自の情報を記入) |
| `legal_cache/` | 動作確認用の法令キャッシュ(**一次資料ではありません**。実利用では取得スクリプトで更新) |
| `tests/` | 架空データによるテスト |

## サンプル(`examples/`)
会社名等はすべて架空(株式会社A・株式会社B)です。
- `contracts/` レビュー対象のサンプル契約書: `01_manufacturing`(金型及び樹脂成形部品製造委託基本契約書)、`02_joint_research`(共同研究開発契約書)、`03_cloud_service`(クラウドサービス利用契約書)
- `reviews/<契約名>/custom_ai_internal.docx` 本システムによる内部検討用レビュー(変更履歴・コメント付き)
- `reviews/<契約名>/custom_ai_external.docx` 同・相手方提示用(理由を相手方向けの表現にしたもの)
- `reviews/02_joint_research/genspark_review.docx` 比較用の他AIによるレビュー例

レビュー例は、実際の試験で得た出力から会社名等を匿名化したものです(試験時点の版であり、現行版の出力とは異なる場合があります)。

## 前提(Claude の利用)
本拡張は Claude(Claude for Legal の Commercial Legal プラグインを含む)上で動かす前提です。Claude の有料プランは、利用者各自で契約してください(本リポジトリには含まれません)。

## 使い方(概要)
1. `profile/` のテンプレートを埋め、`scripts/check_config.py` で読込を確認する(未読込のまま一般基準に切り替えない設計)。
2. 法令の一次資料を取得する(`pc/fetch_legal_sources.py` または `scripts/fetch_egov.py`。e-Gov 法令API)。**キャッシュは必ず一次資料と照合**してから使うこと。
3. `docs/操作手順書.md` と `docs/review_schema.md` に従って `review.json` を作成し、`review_gate.py` → `blind_packet.py`(独立再検証)→ `compare_judgments.py` → `integrated_gate.py` → `revision_state.py` → `apply_revisions.py` → `validate_docx.py` の順に実行する。

## 既知の限界
- 検証が PASS しても、法的な正しさ・実務上の妥当性は証明されません。独立再検証は同一系統のモデルによる確認になり得ます。
- 一部スクリプトには、類型や契約書の書式への依存による既知の不具合があります(例: レポート生成の `judgment_label` 依存、外部法令条番号の誤検出、既存コメントを含む docx の件数検証)。
- Word は Microsoft Word 実機での開封確認を前提としていません。

## ライセンス
MIT License(`LICENSE` 参照)。法令キャッシュ(`legal_cache/`)は一次資料ではなく、無保証です。

## 環境ごとの検証結果

[English](README.md)

関連文書・コメント・サンプル契約の多くは日本語です。日本語ファイル名を含め、UTF-8を維持してください。

一部のスクリプトには `lxml`、`python-docx`、`reportlab` が必要です。知識基盤のスキーマ検証では `jsonschema` も使用します。依存パッケージの自動インストール設定は含まれていません。

### 著者環境での合格実績

著者から、標準ライブラリのみの環境で以下の試験が合格したとの報告があります。

| 試験 | 著者環境での結果 |
|---|---|
| `python3 -I scripts/run_tests.py` | **46/46 合格** |
| `python3 -I scripts/run_v5_tests.py` | **31/31 合格** |
| `python3 -I scripts/run_pipeline_tests.py` | **37/37 合格** |
| `python3 -I tests/kb/run_kb_tests.py` | **80/80 合格** |

これらは著者環境での結果です。利用可能なパッケージや実行設定は環境によって異なり、上記の依存関係は提供スクリプト内で使用するインポートを示しています。

### Codex環境での再実行結果

公開準備時のWindows / Python 3.10.11環境では、最初の3試験は `lxml` 不足で停止しました。知識基盤試験は取込試験の失敗後に `reportlab` 不足で停止し、このCodex環境では合格件数を確認できませんでした。

その後、別のCodex Windows / Python 3.12環境に追加の依存ライブラリを用意して確認した結果は以下のとおりです。

| 試験 | Codexでの確認結果 |
|---|---|
| `scripts/run_tests.py` | 自動試験45/45合格。手動の永続化確認1件は未実施 |
| `scripts/run_v5_tests.py` | 30/31合格。内部で呼び出すv4試験に失敗あり |
| `scripts/run_pipeline_tests.py` | WindowsのCP932文字コードによる読み取りエラーで停止 |
| `tests/kb/run_kb_tests.py` | SQLiteデータベースを開く際のエラーで停止 |

著者環境の合格実績とCodex環境の結果は、それぞれの環境で得られた別個の結果です。Codex側の結果が著者環境の合格実績を置き換えるものではありません。試験のためのコード変更は行っていません。試験合格は実装された検査の動作確認であり、法的正確性やすべての例外条件を保証するものではありません。

サンプルDOCX 10件はコンテナーと内部XMLの読み取りを確認しました。CodexによるMicrosoft Wordでの表示確認は未実施です。
