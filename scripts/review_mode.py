#!/usr/bin/env python3
"""レビュー方式の必須/省略可能工程を表示し、省略が許されない工程の省略を拒否する。  review_mode.py <簡易|標準|重点|規制対応> [--skip 工程名 ...]"""
import sys, os, json
cfg = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "review_modes.json"), encoding="utf-8"))
if len(sys.argv) < 2 or sys.argv[1] not in cfg["modes"]: print("方式:", list(cfg["modes"])); sys.exit(1)
m = cfg["modes"][sys.argv[1]]; skips = sys.argv[sys.argv.index("--skip") + 1:] if "--skip" in sys.argv else []
bad = [s for s in skips if any(s in x for x in cfg["always_required"] + m.get("required", []))]
print(json.dumps({"mode": sys.argv[1], "always_required": cfg["always_required"], **m}, ensure_ascii=False, indent=1))
if bad: print("ERROR: 省略不可の工程を省略しようとしています:", bad); sys.exit(2)
