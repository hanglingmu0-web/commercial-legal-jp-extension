#!/usr/bin/env python3
"""PCで取得した一次資料フォルダ(manifest.json+raw_*)をキャッシュへ取り込む。取得経路の連鎖(PCでのSHA-256 → ここで再計算)を検証し、一致した場合のみ machine_fetch として登録する。
  ingest_manifest.py <取得フォルダ> [--cache-dir D]
成功条件: 必須資料(法律・規則)のSHA-256一致、JSON解釈可能、条文を原文から再生成してキャッシュと一致(trace)。附則(改正法条文PDF)は取得の有無と抽出結果を記録する(経過措置の内容解釈は行わない)。"""
import sys, os, json, hashlib, shutil, subprocess, argparse, datetime
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
ap = argparse.ArgumentParser(); ap.add_argument("folder"); ap.add_argument("--cache-dir"); a = ap.parse_args()
cache = a.cache_dir or os.path.join(ROOT, "legal_cache"); os.makedirs(os.path.join(cache, "raw"), exist_ok=True)
man = json.load(open(os.path.join(a.folder, "manifest.json"), encoding="utf-8")); res = []; fatal = 0
def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()
for sid, it in man["items"].items():
    if it.get("result") != "OK": res.append((sid, "SKIP", "取得されていない(%s)" % it.get("error") or it.get("status"))); fatal += it.get("required", False); continue
    p = os.path.join(a.folder, it["file"])
    if not os.path.isfile(p) or sha(p) != it["sha256"]: res.append((sid, "REJECT", "SHA-256がmanifestと不一致または欠落(転送中の改変/破損の疑い)")); fatal += it.get("required", False); continue
    dst = os.path.join(cache, "raw", it["file"]); shutil.copy(p, dst)
    if it["kind"] == "egov_law_data":
        try: json.loads(open(p, encoding="utf-8").read())
        except Exception as e: res.append((sid, "REJECT", "JSON解釈不能 %r" % e)); fatal += 1; continue
        env = dict(os.environ, LEGAL_CACHE_DIR=cache)
        r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "ingest_egov.py"), dst, sid, "--route", "機械取得(PC: %s)" % man.get("fetched_by"), "--url", it["url"], "--retrieved-at", it["retrieved_at"]], env=env, capture_output=True, text=True)
        res.append((sid, "INGEST" if r.returncode == 0 else "REJECT", (r.stdout + r.stderr).strip()[-200:])); fatal += (r.returncode != 0)
    else:
        res.append((sid, "STORED", "原文を保存(%s)" % it["kind"]))
# 附加情報の反映(改正履歴・附則の取得状況)。キャッシュJSONは取得事実のみ更新する(内容の解釈・補完はしない)
actp = os.path.join(cache, "act_331AC0000000120.json")
if os.path.isfile(actp):
    d = json.load(open(actp, encoding="utf-8")); rv = man["items"].get("revisions_331AC0000000120", {})
    if rv.get("result") == "OK" and os.path.isfile(os.path.join(a.folder, rv["file"])):
        try: json.loads(open(os.path.join(a.folder, rv["file"]), encoding="utf-8").read()); d["amendment_history_retrieved"] = True; d["amendment_history_raw"] = "raw/" + rv["file"]
        except Exception: pass
    sp = man["items"].get("jftc_kaiseihou_jyobun", {}); am = man["items"].get("amending_act_507AC0000000041", {})
    d["suppl_sources"] = {"amending_act_api": am.get("result"), "jftc_kaiseihou_jyobun_pdf": sp.get("result"), "jftc_pdf_sha256": sp.get("sha256")}
    d["transitional_provisions_retrieved"] = False   # 取得しただけでは True にしない。附則の抽出・確認(下記)後、検証者が根拠付きで更新する
    if sp.get("result") == "OK" or am.get("result") == "OK": d["transitional_note"] = "改正法の附則の原文(公式PDF/API)を取得済み。経過措置の内容の抽出と適用関係の確認は未了。確認完了までは transitional_provisions_retrieved=false のまま扱う。"
    json.dump(d, open(actp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
sys.path.insert(0, HERE); os.environ["LEGAL_CACHE_DIR"] = cache
import legal_sources as L; L.CACHE_DIR = cache
for sid in ("act_331AC0000000120", "rule_507M60200000009"):
    s = L.load(sid, cache)
    if s: res.append((sid, "RELIABILITY", L.reliability(s, cache)))
for r in res: print("%-10s %-30s %s" % (r[1], r[0], r[2]))
print("RESULT:", "FAIL(必須資料の取り込み失敗 %d)" % fatal if fatal else "OK"); sys.exit(2 if fatal else 0)
