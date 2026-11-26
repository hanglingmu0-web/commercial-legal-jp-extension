#!/usr/bin/env python3
"""【PC(Windows)で実行】法令の一次資料を公式サイトから取得し、応答を一切加工せず保存する(標準ライブラリのみ。追加インストール不要)。
使い方:  python fetch_legal_sources.py <出力フォルダ>
  例:    python fetch_legal_sources.py C:\\Users\\<user>\\Documents\\CL-Extension-Work\\legal_fetch
出力(出力フォルダ\\YYYYMMDD_HHMMSS\\): raw_*.json / raw_*.pdf(応答そのまま) / manifest.json(URL・取得日時・HTTPステータス・バイト数・SHA-256) / SHA256SUMS.txt / fetch_log.txt
終了コード: 0=必須資料すべて取得 / 2=必須資料に取得失敗あり(失敗はmanifestとfetch_log.txtに記録。成功扱いにしない)
通信先(HTTPSのみ): laws.e-gov.go.jp(法令API v2) / www.jftc.go.jp(公正取引委員会)。認証・ログイン不要。アクセス制限の迂回は行わない。
"""
import sys, os, json, hashlib, datetime, urllib.request, urllib.error, time
BASE = os.environ.get("LEGAL_API_BASE", "https://laws.e-gov.go.jp")           # 試験時のみ差し替え(本番は既定のまま)
JFTC = os.environ.get("LEGAL_JFTC_BASE", "https://www.jftc.go.jp")
ITEMS = [
 # id, 必須か, URL, ファイル名, 種別
 ("act_331AC0000000120", True,  BASE + "/api/2/law_data/331AC0000000120?response_format=json", "raw_act_331AC0000000120.json", "egov_law_data"),
 ("rule_507M60200000009", True, BASE + "/api/2/law_data/507M60200000009?response_format=json", "raw_rule_507M60200000009.json", "egov_law_data"),
 ("revisions_331AC0000000120", True, BASE + "/api/2/law_revisions/331AC0000000120?response_format=json", "raw_revisions_331AC0000000120.json", "egov_law_revisions"),
 ("amending_act_507AC0000000041", False, BASE + "/api/2/law_data/507AC0000000041?response_format=json", "raw_amending_act_507AC0000000041.json", "egov_law_data_amending"),
 ("jftc_kaiseihou_jyobun", False, JFTC + "/partnership_package/toritekihou-jyobun.pdf", "raw_jftc_kaiseihou_jyobun.pdf", "official_pdf_suppl"),
 ("jftc_shinkyu", False, JFTC + "/partnership_package/toritekihou-sinkyu.pdf", "raw_jftc_shinkyu.pdf", "official_pdf"),
 ("jftc_text_r7", False, JFTC + "/toriteki/r7text.pdf", "raw_jftc_text_r7.pdf", "official_pdf_guide"),
]
def main():
    if len(sys.argv) < 2: print(__doc__); sys.exit(1)
    ts = datetime.datetime.now().astimezone(); out = os.path.join(sys.argv[1], ts.strftime("%Y%m%d_%H%M%S")); os.makedirs(out, exist_ok=True)
    man = {"fetched_by": "pc/fetch_legal_sources.py", "started_at": ts.isoformat(timespec="seconds"), "host": os.environ.get("COMPUTERNAME", ""), "python": sys.version.split()[0], "items": {}}
    log = open(os.path.join(out, "fetch_log.txt"), "w", encoding="utf-8"); sums = []; bad = 0
    def L(m): print(m); log.write(m + "\n"); log.flush()
    for sid, required, url, fn, kind in ITEMS:
        rec = {"url": url, "kind": kind, "required": required, "retrieved_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds")}
        t0 = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "legal-extension-fetch/1.0", "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read(); rec.update(status=r.status, content_type=r.headers.get("Content-Type"), server_date=r.headers.get("Date"))
            open(os.path.join(out, fn), "wb").write(body)
            rec.update(file=fn, bytes=len(body), sha256=hashlib.sha256(body).hexdigest(), result="OK"); sums.append("%s *%s" % (rec["sha256"], fn))
            L("OK   %-32s %s bytes  sha256=%s" % (sid, len(body), rec["sha256"][:16]))
        except urllib.error.HTTPError as e:
            rec.update(status=e.code, result="HTTP_ERROR", error=str(e)); L("FAIL %-32s HTTP %s (%s)" % (sid, e.code, "必須" if required else "任意"))
        except Exception as e:
            rec.update(status=None, result="ERROR", error=repr(e)); L("FAIL %-32s %r (%s)" % (sid, e, "必須" if required else "任意"))
        rec["seconds"] = round(time.time() - t0, 2)
        if rec["result"] != "OK" and required: bad += 1
        man["items"][sid] = rec
    man["finished_at"] = datetime.datetime.now().astimezone().isoformat(timespec="seconds"); man["required_failures"] = bad
    json.dump(man, open(os.path.join(out, "manifest.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    open(os.path.join(out, "SHA256SUMS.txt"), "w", encoding="utf-8").write("\n".join(sums) + "\n")
    L("---\n保存先: " + out); L("結果: " + ("正常終了(必須資料すべて取得)" if bad == 0 else "異常終了(必須資料の取得失敗 %d 件。manifest.json と fetch_log.txt を確認)" % bad))
    sys.exit(0 if bad == 0 else 2)
if __name__ == "__main__": main()
