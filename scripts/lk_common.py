#!/usr/bin/env python3
"""法律知識基盤(法知識・判例)の共通部。保存形式(JSON/JSONL/原本/テキスト)が正本で、検索インデックス(SQLite)はそこから再構築できる派生物。
LK_ROOT 環境変数で基盤のルートを切り替える(試験は架空データを別ルートに置き、本番と分離する)。"""
import os, re, json, hashlib, time
HERE = os.path.dirname(os.path.abspath(__file__)); DEFAULT_ROOT = os.path.dirname(HERE)
def root(): return os.environ.get("LK_ROOT") or DEFAULT_ROOT
def P(*a): return os.path.join(root(), *a)
ID_RE = re.compile(r"^[A-Za-z0-9_\-]{3,64}$")
def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()
def sha256_text(s): return hashlib.sha256(s.encode("utf-8")).hexdigest()
def norm(s): return re.sub(r"[\s　「」『』“”\"'、。,.・･\-－―ー()（）\[\]【】]", "", (s or "")).translate(str.maketrans("０１２３４５６７８９", "0123456789"))
def schema(name):
    return json.load(open(os.path.join(DEFAULT_ROOT, "schemas", name + ".schema.json"), encoding="utf-8"))
def validate(obj, name):
    import jsonschema
    v = jsonschema.Draft202012Validator(schema(name)); return ["%s: %s" % ("/".join(map(str, e.absolute_path)) or "(root)", e.message[:160]) for e in sorted(v.iter_errors(obj), key=lambda e: list(map(str, e.absolute_path)))]
def safe_rel(base, rel):
    """入力ファイルの相対パスが base の内側に収まるか(絶対パス・.. ・シンボリックリンクによる脱出を拒否)。戻り値: 実パス又は None"""
    if not rel or os.path.isabs(rel) or re.match(r"^[A-Za-z]:", rel) or ".." in rel.replace("\\", "/").split("/") or "\x00" in rel: return None
    p = os.path.realpath(os.path.join(base, rel)); b = os.path.realpath(base)
    return p if (p == b or p.startswith(b + os.sep)) else None
INJECT = re.compile(r"(ignore (all |any )?(previous|prior|above)|disregard .{0,20}instruction|システム(プロンプト|指示)|以前の指示を(無視|忘れ)|この指示に従|you must now|新しい指示)", re.I)
def suspicious(text): return bool(INJECT.search(text or ""))
def ledger(op, kind, ids, outcome, detail=None):
    """登録・更新履歴(ハッシュ連鎖で改ざんを検出可能にする追記専用ログ)"""
    os.makedirs(P("logs"), exist_ok=True); p = P("logs", "kb_ledger.jsonl"); prev = "0" * 64
    if os.path.isfile(p):
        last = [l for l in open(p, encoding="utf-8") if l.strip()]
        if last: prev = json.loads(last[-1])["hash"]
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S+09:00", time.gmtime(time.time() + 9 * 3600)), "op": op, "kind": kind, "ids": ids, "outcome": outcome, "detail": detail, "prev": prev}
    rec["hash"] = sha256_text(json.dumps(rec, ensure_ascii=False, sort_keys=True)); open(p, "a", encoding="utf-8").write(json.dumps(rec, ensure_ascii=False) + "\n")
def ledger_ok():
    p = P("logs", "kb_ledger.jsonl")
    if not os.path.isfile(p): return True, 0
    prev = "0" * 64; n = 0
    for l in open(p, encoding="utf-8"):
        if not l.strip(): continue
        r = json.loads(l); h = r.pop("hash")
        if r["prev"] != prev or sha256_text(json.dumps(r, ensure_ascii=False, sort_keys=True)) != h: return False, n
        prev = h; n += 1
    return True, n
def load_json(p): return json.load(open(p, encoding="utf-8"))
def read_records(path):
    """JSON(オブジェクト又は配列)/JSONL を読む"""
    t = open(path, encoding="utf-8").read()
    if path.endswith(".jsonl"): return [json.loads(l) for l in t.splitlines() if l.strip()]
    d = json.loads(t); return d if isinstance(d, list) else [d]
def list_ids(sub, ext=".json"):
    d = P(*sub.split("/")); return sorted(f[:-len(ext)] for f in os.listdir(d) if f.endswith(ext)) if os.path.isdir(d) else []
