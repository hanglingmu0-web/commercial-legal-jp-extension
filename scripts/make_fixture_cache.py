#!/usr/bin/env python3
"""試験専用: 既存キャッシュの条文から e-Gov形式の疑似rawを組み立て、ingest_egov.py の経路で『機械取得扱い・test_fixture=True』のキャッシュを生成する。
本番の法的判断には使えない(LEGAL_ALLOW_FIXTURE が無ければ reliability は『試験用フィクスチャ』)。ゲートの『確定』経路の動作試験にのみ使う。
  make_fixture_cache.py <out_cache_dir>
"""
import sys, os, json, subprocess, shutil
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
def build(out):
    os.makedirs(os.path.join(out, "raw"), exist_ok=True)
    for sid in ("act_331AC0000000120", "rule_507M60200000009"):
        src = json.load(open(os.path.join(ROOT, "legal_cache", sid + ".json"), encoding="utf-8")); prov = src["provisions"]; arts = {}
        if sid.startswith("rule"):   # ruleは本物のraw(ブラウザ取得)をそのまま複製
            shutil.copy(os.path.join(ROOT, "legal_cache", "raw", "raw_507M60200000009.json"), os.path.join(out, "raw", "raw_%s.json" % sid)); rawp = os.path.join(out, "raw", "raw_%s.json" % sid)
        else:
            for ref, text in prov.items():
                parts = ref.split("-")
                if parts[0] in ("MP", "SP", "enact"): continue
                a = arts.setdefault(parts[0], {}); p = a.setdefault(parts[1], {"text": "", "items": {}})
                if len(parts) == 2: p["text"] = text
                else: p["items"][parts[2]] = text
            S = lambda t, s: {"tag": t, "attr": {}, "children": [s]}
            children = []
            for an, ps in arts.items():
                pc = []
                for pn, p in ps.items():
                    items = [{"tag": "Item", "attr": {"Num": i}, "children": [S("ItemSentence", t)]} for i, t in p["items"].items()]
                    pc.append({"tag": "Paragraph", "attr": {"Num": pn}, "children": [S("ParagraphSentence", p["text"])] + items})
                children.append({"tag": "Article", "attr": {"Num": an}, "children": pc})
            raw = {"law_info": {"law_type": "Act", "law_id": src["law_id"], "law_num": src["law_num"], "promulgation_date": src.get("promulgation_date")},
                   "revision_info": {"law_revision_id": src["revision_id"], "law_title": src["law_title"], "abbrev": "", "amendment_enforcement_date": src["enforcement_date"], "current_revision_status": "CurrentEnforced",
                                     "repeal_status": "None", "repeal_date": None, "updated": src.get("api_updated"), "amendment_scheduled_enforcement_date": None},
                   "law_full_text": {"tag": "Law", "attr": {}, "children": [{"tag": "LawBody", "attr": {}, "children": [{"tag": "MainProvision", "attr": {}, "children": children}]}]}}
            rawp = os.path.join(out, "raw", "raw_%s.json" % sid); json.dump(raw, open(rawp, "w", encoding="utf-8"), ensure_ascii=False)
        env = dict(os.environ, LEGAL_CACHE_DIR=out)
        r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "ingest_egov.py"), rawp, sid, "--route", "試験用フィクスチャ(機械取得扱い)", "--retrieved-at", "2026-11-24T12:15:00+09:00", "--test-fixture", "--url", "fixture://" + sid]
                           + sum([["--alias", x] for x in (src.get("abbrev") or [])], []) + sum([["--former", x] for x in (src.get("former_titles") or [])], []), env=env, capture_output=True, text=True)
        if r.returncode: raise SystemExit("ingest失敗: " + r.stderr)
        d = json.load(open(os.path.join(out, sid + ".json"), encoding="utf-8")); d["transitional_provisions_retrieved"] = False; d["transitional_note"] = src.get("transitional_note")
        json.dump(d, open(os.path.join(out, sid + ".json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for f in ("guide_jftc_text_r7_11.json", "rule_337M50200000001_old.json"): shutil.copy(os.path.join(ROOT, "legal_cache", f), out)
if __name__ == "__main__": build(sys.argv[1]); print("OK", sys.argv[1])
