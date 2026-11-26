#!/usr/bin/env python3
"""e-Gov法令API v2 から法令を機械取得し、応答そのまま(raw)を保存してキャッシュ化する(利用者PC等、外部通信が許可された環境で実行)。
  fetch_egov.py <law_id|法令番号> <source_id> [--elm 'MainProvision-Article[2]'] [--alias 略称] [--former 旧名称]
応答バイト列のSHA-256を保存し、verbatim=true / transcribed_by_model=false として取り込む。
【検証状況】この作業領域のシェルは e-Gov への CONNECT が 403 で拒否されるため、本スクリプトのネットワーク動作は未検証
(取り込み部 ingest_egov.py のみ、実際の応答JSONで検証済み)。
"""
import sys, os, urllib.request, urllib.parse, datetime, subprocess, argparse
HERE = os.path.dirname(os.path.abspath(__file__)); RAW = os.path.join(os.path.dirname(HERE), "legal_cache", "raw")
ap = argparse.ArgumentParser(); ap.add_argument("law"); ap.add_argument("source_id"); ap.add_argument("--elm"); ap.add_argument("--alias", action="append", default=[]); ap.add_argument("--former", action="append", default=[])
a = ap.parse_args()
q = {"response_format": "json"}
if a.elm: q["elm"] = a.elm
url = "https://laws.e-gov.go.jp/api/2/law_data/%s?%s" % (urllib.parse.quote(a.law), urllib.parse.urlencode(q, safe="[]-"))
try:
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "legal-extension/1"}), timeout=30) as r: body = r.read()
except Exception as e:
    print("FAIL: 取得失敗(キャッシュは更新しない。一次資料未確認として扱うこと): %s" % e, file=sys.stderr); sys.exit(2)
os.makedirs(RAW, exist_ok=True); path = os.path.join(RAW, a.source_id + ".json"); open(path, "wb").write(body)
cmd = [sys.executable, "-I", os.path.join(HERE, "ingest_egov.py"), path, a.source_id, "--route", "機械取得 " + url, "--url", url, "--retrieved-at", datetime.datetime.now().astimezone().isoformat(timespec="seconds")]
for x in a.alias: cmd += ["--alias", x]
for x in a.former: cmd += ["--former", x]
sys.exit(subprocess.call(cmd))
