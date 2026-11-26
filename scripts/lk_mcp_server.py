#!/usr/bin/env python3
"""法律知識・判例データのローカルMCPサーバー(stdio, 依存パッケージなし)。利用者のPC側で起動し、Claude Cowork/Claude等のMCPクライアントから使う。
このファイルを作成しただけでCoworkから利用可能になったとは扱わない。実際の接続は MCP クライアントでの `tools/list` `tools/call` の実動作で確認する(docs/法律知識基盤_接続手順.md)。
外部ネットワークへは一切接続しない。取込(import_*)は LK_ROOT/import/incoming 配下のファイルのみ受け付ける。"""
import sys, os, json, io, contextlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lk_common as C, lk_search as S, lk_verify as V, lk_import as I, lk_index as X
def _import(kind, path, update=False):
    base = os.path.realpath(C.P("import", "incoming")); p = C.safe_rel(base, path)
    if not p or not os.path.exists(p): return {"status": "rejected", "message": "取込は import/incoming 配下の相対パスのみ(絶対パス・..は不可)"}
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf): rc = I.main([kind, p, "--incoming", os.path.dirname(p) if os.path.isfile(p) else p] + (["--update"] if update else []))
    return {"status": "accepted" if rc == 0 else "rejected", "log": buf.getvalue()[-2000:]}
T = {}
def tool(name, desc, props, req, fn): T[name] = ({"name": name, "description": desc, "inputSchema": {"type": "object", "properties": props, "required": req}}, fn)
s = lambda d: {"type": "string", "description": d}; i_ = lambda d: {"type": "integer", "description": d}
tool("import_legal_knowledge", "法知識/出典/段落/関連付けのJSON・JSONLを取り込む(import/incoming配下)。検証に失敗した場合は全体を拒否し隔離する", {"kind": {"enum": ["source", "knowledge", "passages", "links"]}, "path": s("import/incoming 配下の相対パス"), "update": {"type": "boolean"}}, ["kind", "path"], lambda a: _import(a["kind"], a["path"], a.get("update", False)))
tool("import_case", "判例ディレクトリ(metadata.json structured.json judgment.pdf|txt passages.jsonl manifest.json)を取り込む", {"path": s("import/incoming 配下の判例ディレクトリ"), "update": {"type": "boolean"}}, ["path"], lambda a: _import("case", a["path"], a.get("update", False)))
tool("search_legal_knowledge", "法知識を論点・キーワード・関連条文・出典・法分野で検索(全文検索)。結果は確定的引用の可否と根拠の性質つき", {"query": s("検索語(空白区切りAND)"), "issue": s("論点"), "statute": s("関連条文"), "source_id": s("出典資料ID"), "legal_field": s("法分野"), "knowledge_type": s("知識の種類"), "limit": i_("件数")}, [], lambda a: S.search_legal_knowledge(a.get("query", ""), a.get("issue"), a.get("statute"), a.get("source_id"), a.get("legal_field"), a.get("knowledge_type"), int(a.get("limit", 10))))
tool("get_legal_knowledge", "知識IDで取得(出典・原文段落つき)", {"knowledge_id": s("知識ID")}, ["knowledge_id"], lambda a: S.get_legal_knowledge(a["knowledge_id"]))
tool("search_cases", "判例を論点・キーワード・事件番号・裁判所・裁判年月日・関連条文で検索", {"query": s("検索語"), "issue": s("争点"), "case_number": s("事件番号"), "court": s("裁判所"), "date_from": s("YYYY-MM-DD"), "date_to": s("YYYY-MM-DD"), "statute": s("関連条文"), "limit": i_("件数")}, [], lambda a: S.search_cases(a.get("query", ""), a.get("issue"), a.get("case_number"), a.get("court"), a.get("date_from"), a.get("date_to"), a.get("statute"), int(a.get("limit", 10))))
tool("get_case", "判例IDで取得(当事者の主張・裁判所の判断等を区別して返す)", {"case_id": s("判例ID")}, ["case_id"], lambda a: S.get_case(a["case_id"]))
tool("get_case_fulltext", "判決全文を取得(原本ハッシュで原本性を確認)", {"case_id": s("判例ID")}, ["case_id"], lambda a: S.get_case_fulltext(a["case_id"]))
tool("get_case_passages", "判決全文中の段落を取得", {"case_id": s("判例ID"), "query": s("語"), "passage_ids": {"type": "array", "items": {"type": "string"}}}, ["case_id"], lambda a: S.get_case_passages(a["case_id"], a.get("query"), a.get("passage_ids")))
tool("get_source_passages", "出典資料の原文段落を取得(ページ・語・段落ID指定)", {"source_id": s("出典資料ID"), "query": s("語"), "page": i_("ページ"), "passage_ids": {"type": "array", "items": {"type": "string"}}}, ["source_id"], lambda a: S.get_source_passages(a["source_id"], a.get("query"), a.get("page"), a.get("passage_ids")))
tool("search_legal_authorities", "法令・法知識・判例の横断検索(根拠の性質を区別して返す)", {"query": s("検索語"), "statute": s("条文"), "limit": i_("件数")}, ["query"], lambda a: S.search_legal_authorities(a["query"], a.get("statute"), int(a.get("limit", 5))))
tool("verify_case_citation", "判例の引用を検証(実在・事件番号・原本ハッシュ・段落・引用文言)。法律上の関連性・適用可能性は検証対象外", {"case_id": s("判例ID"), "court": s(""), "decision_date": s(""), "case_number": s(""), "quote": s("引用文言"), "passage_id": s(""), "page": s("")}, [], lambda a: V.verify_case_citation(a))
tool("verify_knowledge_citation", "法知識の引用を検証(出典・書誌・原資料ハッシュ・ページ・段落・引用文言・知識の種類)", {"knowledge_id": s("知識ID"), "quote": s("引用文言"), "passage_id": s(""), "page": s(""), "as_type": s("引用の性質(legal_principle等)")}, ["knowledge_id"], lambda a: V.verify_knowledge_citation(a))
tool("list_knowledge_sources", "登録済みの出典資料の一覧", {}, [], lambda a: S.list_knowledge_sources())
tool("get_related", "関連付け(原資料に明示/AI推定を区別)を取得", {"kind": {"enum": ["statute", "knowledge", "case"]}, "id": s("ID")}, ["kind", "id"], lambda a: S.related(a["kind"], a["id"]))
tool("verify_store", "保存データの整合性検証(原本ハッシュ・manifest・履歴)", {}, [], lambda a: V.verify_store())
tool("rebuild_index", "検索インデックスを保存データから再構築", {}, [], lambda a: {"status": "ok", "counts": X.rebuild()})
def handle(m):
    mid, meth, p = m.get("id"), m.get("method"), m.get("params") or {}
    if meth == "initialize": return {"protocolVersion": p.get("protocolVersion", "2024-11-05"), "capabilities": {"tools": {}}, "serverInfo": {"name": "legal-knowledge-local", "version": "0.5.0"}}
    if meth == "tools/list": return {"tools": [v[0] for v in T.values()]}
    if meth == "ping": return {}
    if meth == "tools/call":
        n = p.get("name")
        if n not in T: return {"content": [{"type": "text", "text": "unknown tool"}], "isError": True}
        try: r = T[n][1](p.get("arguments") or {}); return {"content": [{"type": "text", "text": json.dumps(r, ensure_ascii=False)}], "isError": False}
        except Exception as e: return {"content": [{"type": "text", "text": json.dumps({"status": "error", "message": "%s: %s" % (type(e).__name__, str(e)[:200])}, ensure_ascii=False)}], "isError": True}
    return None
def main():
    for line in sys.stdin:
        line = line.strip()
        if not line: continue
        try: m = json.loads(line)
        except Exception: continue
        if "id" not in m: continue   # notification
        r = handle(m)
        out = {"jsonrpc": "2.0", "id": m["id"]}
        if r is None: out["error"] = {"code": -32601, "message": "method not found"}
        else: out["result"] = r
        sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n"); sys.stdout.flush()
if __name__ == "__main__": main()
