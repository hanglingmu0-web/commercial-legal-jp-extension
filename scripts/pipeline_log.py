#!/usr/bin/env python3
"""パイプライン実行ログ(JSONL)。各工程の実行・時間・成果物ハッシュを記録し、『呼出指示の記載』と『実際の実行』を区別できるようにする。
  pipeline_log.py run <log.jsonl> <step> [--artifact f ...] -- <command...>     コマンドを実行し所要時間・終了コード・成果物ハッシュを記録
  pipeline_log.py mark <log.jsonl> <step> --status ok|fail|skipped [--duration-ms N] [--artifact f ...] [--note 文]   外部実行(AIエージェント等)の記録
  pipeline_log.py summary <log.jsonl>
"""
import sys, os, json, time, subprocess, hashlib, datetime
def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()[:16] if os.path.isfile(p) else None
def append(log, rec):
    rec["ts"] = datetime.datetime.now().astimezone().isoformat(timespec="seconds"); open(log, "a", encoding="utf-8").write(json.dumps(rec, ensure_ascii=False) + "\n")
def arts(args):
    out, i = [], 0
    while i < len(args):
        if args[i] == "--artifact": out.append(args[i + 1]); i += 2
        else: i += 1
    return out
if __name__ == "__main__":
    a = sys.argv[1:]; cmd = a[0]
    if cmd == "run":
        log, step = a[1], a[2]; sep = a.index("--"); ar = arts(a[3:sep]); t = time.time()
        p = subprocess.run(a[sep + 1:], capture_output=True, text=True); ms = int((time.time() - t) * 1000)
        append(log, {"step": step, "kind": "executed", "status": "ok" if p.returncode == 0 else "fail", "exit": p.returncode, "duration_ms": ms, "artifacts": {f: sha(f) for f in ar}, "stdout_tail": p.stdout[-300:], "stderr_tail": p.stderr[-200:]})
        sys.stdout.write(p.stdout); sys.stderr.write(p.stderr); sys.exit(p.returncode)
    elif cmd == "mark":
        log, step = a[1], a[2]; kv = {a[i]: a[i + 1] for i in range(3, len(a) - 1, 2)}
        append(log, {"step": step, "kind": "external", "status": kv.get("--status", "ok"), "duration_ms": int(kv["--duration-ms"]) if "--duration-ms" in kv else None, "artifacts": {f: sha(f) for f in arts(a[3:])}, "note": kv.get("--note")})
    elif cmd == "summary":
        tot = 0
        for l in open(a[1], encoding="utf-8"):
            r = json.loads(l); tot += r.get("duration_ms") or 0
            print("%-28s %-9s %-7s %8s ms  %s" % (r["step"], r["kind"], r["status"], r.get("duration_ms"), list((r.get("artifacts") or {}).values())))
        print("合計(記録された所要時間): %.1f 秒" % (tot / 1000))
