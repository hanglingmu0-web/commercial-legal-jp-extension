# legal_cache
動作確認用の法令キャッシュです。**一次資料ではありません。**
- 多くは AI による書き起こし・要約(`transcribed_by_model`)で、e-Gov の一次資料と照合していません。逐語性・現行性・附則の取得状況は各 JSON の項目を確認してください。
- 実利用では `pc/fetch_legal_sources.py` または `scripts/fetch_egov.py` で e-Gov 法令API から取得し、`transcribed_backup/` の内容を置き換えてください。照合前のデータでは「確定」を出さない設計です。
