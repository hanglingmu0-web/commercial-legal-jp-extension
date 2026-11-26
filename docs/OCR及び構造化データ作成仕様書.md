# OCR及び構造化データ作成仕様書
1. 原文は変更しない。`passages.kind` は `original_text`(原本の転記)/`extracted_text`(PDFからの機械抽出)/`ocr_text`/`correction`(人の訂正。原文と別段落)/`ai_summary`(AI要約。原文として引用不可)。
2. OCR結果は `ocr_status`(unchecked/checked/correction_confirmed)を持つ。未確認OCRは確定的引用不可。
3. 構造化(論点・原則・判断要旨)は `structure_status`(ai_generated/human_checked)。AI構造化は人の確認前は確定的引用不可。
4. 各構造化項目は `source_refs`/`passage_ids` で原文段落へ辿れること。辿れない項目は登録を拒否または警告。
5. 区別すべき種別: 原則/著者の見解/学説の対立/裁判所の判断/当事者の主張/事案の事実/実務上の注意。`author_view` を `court_decision` として登録することは拒否される。
6. 判決全文と構造化結果は別保存。誤りは `correction` で訂正を追記し、原文は不変。
