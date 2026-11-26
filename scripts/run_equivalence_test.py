#!/usr/bin/env python3
"""汎用(仕様駆動)エンジンと取適法専用エンジン(applicability.py)の同値性試験: 事実関係の格子上で『適用断定の可否』が一致するか。
対象は製造委託の簡易仕様のみ。不一致は仕様(specs/*.json)またはエンジンの不備として報告する(自動的に合格にしない)。"""
import sys, os, json, itertools
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE); sys.path.insert(0, HERE)
import applicability as A, legal_toolkit as T
spec = json.load(open(os.path.join(ROOT, "specs", "torihiki_manufacturing.json"), encoding="utf-8"))
caps = [None, 5_000_000, 10_000_000, 10_000_001, 50_000_000, 300_000_000, 300_000_001]; emps = [None, 20, 100, 101, 300, 301]; forms = ["法人", "個人"]; matches = [None, True, False]; art14 = [None, False, True]
n = bad = 0; mism = []
for cc, ce, tc, te, cf, tf, m, a14 in itertools.product(caps, emps, caps, emps, ["法人"], forms, matches, art14):
    facts = {"reference_date": "2026-11-24", "contract_date": "2026-12-01", "entrustment": {"type": "製造委託", "matches_definition": m},
             "client": {"form": cf, "capital_yen": cc, "employees": ce, "is_state_or_art14_person": a14}, "contractor": {"form": tf, "capital_yen": tc, "employees": te}}
    e1 = A.judge(dict(facts)); e2 = T.applicability(spec, facts); n += 1
    if e1["asserted_applicable"] != e2["asserted_applicable"]:
        bad += 1
        if len(mism) < 8: mism.append({"facts": facts, "dedicated": e1["overall"], "generic": e2["overall"]})
print("同値性試験: 格子%d件 / 『適用断定』不一致%d件" % (n, bad))
for x in mism: print(json.dumps(x, ensure_ascii=False)[:420])
sys.exit(0 if bad == 0 else 1)
