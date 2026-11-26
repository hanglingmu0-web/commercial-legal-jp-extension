#!/usr/bin/env python3
"""独立オラクル(条文のみから別エージェントが実装・期待値を手作成した72境界ケース)と、専用/汎用エンジンの比較。
期待値(boundary_cases.json)は本プログラムの出力から生成していない。条文はAI転記(機械取得原文との照合は未実施)のため、法的正確性の検証ではない。"""
import sys, os, json, copy
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.dirname(HERE); sys.path.insert(0,HERE)
import importlib.util as u, applicability as A, legal_toolkit as T
s=u.spec_from_file_location("oracle",os.path.join(ROOT,"tests/equivalence/oracle_agent.py")); O=u.module_from_spec(s); s.loader.exec_module(O)
spec=json.load(open(os.path.join(ROOT,"specs/torihiki_manufacturing.json"),encoding="utf-8")); cases=json.load(open(os.path.join(ROOT,"tests/equivalence/boundary_cases.json"),encoding="utf-8"))
def cls(x):
    x=str(x); return "未施行" if "未施行" in x else "適用あり" if x.startswith("適用あり") else "適用なし" if x.startswith("適用なし") else "判断保留"
r={"oracle_exact":0,"ded_exact":0,"gen_exact":0,"ded_assert_ok":0,"gen_assert_ok":0}; diff=[]; unsafe=0
for c in cases:
    f=copy.deepcopy(c["facts"]); f.setdefault("entrustment",{})["type"]="製造委託"; f["contract_date"]=f.get("reference_date") or "2026-12-01"; e=c["expected"]
    o=O.judge(copy.deepcopy(c["facts"])); o=cls(o if isinstance(o,str) else o.get("overall"))
    d=cls(A.judge(copy.deepcopy(f))["overall"]); g=cls(T.applicability(spec,copy.deepcopy(f))["overall"])
    for k,v in (("oracle",o),("ded",d),("gen",g)): r[k+"_exact"]+=v==e
    for k,v in (("ded",d),("gen",g)):
        ok=(v=="適用あり")==(e=="適用あり"); r[k+"_assert_ok"]+=ok; unsafe+= (not ok)
    if d!=e or g!=e: diff.append({"id":c["id"],"desc":c["desc"],"expected":e,"dedicated":d,"generic":g})
print(json.dumps({"cases":len(cases),**r,"unsafe_assert_diffs":unsafe,"diffs":diff},ensure_ascii=False,indent=1))
sys.exit(1 if unsafe else 0)
