#!/usr/bin/env python3
"""検索インデックス(SQLite FTS5・trigram + 任意のローカルTF-IDFベクトル)。保存データ(JSON/JSONL/原本)から**いつでも再構築できる派生物**。
外部の埋め込みサービスへは何も送信しない。ベクトルはローカル計算の文字n-gram TF-IDF(埋め込みモデルを変えても元データから再構築可)。"""
import sys, os, json, sqlite3, pickle
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lk_common import *
def db_path(): return P("indexes", "fulltext", "kb.sqlite")
def jl(p): return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()] if os.path.isfile(p) else []
def rebuild(vectors=True):
    os.makedirs(os.path.dirname(db_path()), exist_ok=True); tmp = db_path() + ".new"
    if os.path.exists(tmp): os.remove(tmp)
    c = sqlite3.connect(tmp)
    c.executescript("""create table sources(source_id text primary key, title text, doc_type text, bibliographic_status text, sha256 text, json text);
create table knowledge(knowledge_id text primary key, source_id text, knowledge_type text, authority_class text, legal_field text, issue text, ocr_status text, structure_status text, suspicious int, json text);
create table cases(case_id text primary key, court text, bench text, decision_date text, case_number text, case_name text, existence_status text, fulltext_status text, original_verification text, suspicious int, json text);
create table passages(passage_id text primary key, parent_type text, parent_id text, page text, paragraph int, kind text, suspicious int, text text);
create table statute_refs(owner_type text, owner_id text, statute text);
create table links(link_id text primary key, from_type text, from_id text, to_type text, to_id text, unresolved_ref text, relation text, basis text, json text);
create virtual table fts_passages using fts5(text, content='', tokenize='trigram');
create virtual table fts_knowledge using fts5(body, tokenize='trigram');
create virtual table fts_cases using fts5(body, tokenize='trigram');""")
    n = {"sources": 0, "knowledge": 0, "cases": 0, "passages": 0, "links": 0}
    for sid in list_ids("knowledge/sources"):
        r = load_json(P("knowledge", "sources", sid + ".json")); c.execute("insert into sources values(?,?,?,?,?,?)", (sid, r["title"], r["doc_type"], r["bibliographic_status"], r.get("sha256"), json.dumps(r, ensure_ascii=False))); n["sources"] += 1
    vec_docs = []
    for kid in list_ids("knowledge/structured"):
        r = load_json(P("knowledge", "structured", kid + ".json")); body = " ".join(str(r.get(k) or "") for k in ("legal_field", "issue", "sub_issue", "problem_statement", "principle", "requirements", "effects", "exceptions", "interpretation", "scholarly_position", "practice_notes")) + " " + " ".join(r.get("keywords", []) + r.get("related_statutes", []) + r.get("related_articles", []))
        c.execute("insert into knowledge values(?,?,?,?,?,?,?,?,?,?)", (kid, r["source_id"], r["knowledge_type"], r["authority_class"], r["legal_field"], r["issue"], r["ocr_status"], r["structure_status"], int(bool(r.get("_suspicious_instruction"))), json.dumps(r, ensure_ascii=False)))
        c.execute("insert into fts_knowledge(rowid, body) values((select rowid from knowledge where knowledge_id=?), ?)", (kid, body)); n["knowledge"] += 1; vec_docs.append(("knowledge", kid, body))
        for s in r.get("related_statutes", []) + r.get("related_articles", []): c.execute("insert into statute_refs values('knowledge',?,?)", (kid, s))
    for cid in list_ids("cases/metadata"):
        m = load_json(P("cases", "metadata", cid + ".json")); st = load_json(P("cases", "structured", cid + ".json")) if os.path.isfile(P("cases", "structured", cid + ".json")) else {}
        r = dict(m); r.update({k: v for k, v in st.items() if k not in m})
        body = " ".join([str(r.get(k) or "") for k in ("case_name", "legal_field", "conclusion", "order_text", "applicability_conditions")] + r.get("issues", []) + [s["text"] for k in ("holdings", "court_reasoning", "key_facts") for s in r.get(k, [])] + r.get("cited_statutes", []))
        c.execute("insert into cases values(?,?,?,?,?,?,?,?,?,?,?)", (cid, m["court"], m.get("bench"), m["decision_date"], m["case_number"], m.get("case_name"), m["existence_status"], m["fulltext_status"], m["original_verification"], int(bool(m.get("_suspicious_instruction"))), json.dumps(r, ensure_ascii=False)))
        c.execute("insert into fts_cases(rowid, body) values((select rowid from cases where case_id=?), ?)", (cid, body)); n["cases"] += 1; vec_docs.append(("case", cid, body))
        for s in r.get("cited_statutes", []): c.execute("insert into statute_refs values('case',?,?)", (cid, s))
    for d in ("knowledge/passages", "cases/passages"):
        for f in sorted(os.listdir(P(*d.split("/")))) if os.path.isdir(P(*d.split("/"))) else []:
            if not f.endswith(".jsonl"): continue
            for r in jl(P(*d.split("/"), f)):
                c.execute("insert into passages values(?,?,?,?,?,?,?,?)", (r["passage_id"], r["parent_type"], r["parent_id"], str(r.get("page")), r.get("paragraph"), r["kind"], int(bool(r.get("_suspicious_instruction"))), r["text"]))
                c.execute("insert into fts_passages(rowid, text) values((select rowid from passages where passage_id=?), ?)", (r["passage_id"], r["text"])); n["passages"] += 1
                if r["kind"] != "ai_summary": vec_docs.append(("passage", r["passage_id"], r["text"]))
    for lid in list_ids("knowledge/links"):
        r = load_json(P("knowledge", "links", lid + ".json")); c.execute("insert into links values(?,?,?,?,?,?,?,?,?)", (lid, r["from_type"], r["from_id"], r.get("to_type"), r.get("to_id"), r.get("unresolved_ref"), r["relation"], r["basis"], json.dumps(r, ensure_ascii=False))); n["links"] += 1
    c.commit(); c.close()
    os.replace(tmp, db_path())   # 構築成功後に差し替え(破損したインデックスを残さない)
    if vectors: build_vectors(vec_docs)
    return n
def build_vectors(docs):
    try: from sklearn.feature_extraction.text import TfidfVectorizer
    except Exception: return False
    if not docs: return False
    os.makedirs(P("indexes", "vectors"), exist_ok=True); v = TfidfVectorizer(analyzer="char", ngram_range=(1, 2), min_df=1); m = v.fit_transform([d[2] for d in docs])
    pickle.dump({"model": "tfidf_char_1_2(local)", "ids": [(d[0], d[1]) for d in docs], "vectorizer": v, "matrix": m}, open(P("indexes", "vectors", "tfidf.pkl"), "wb")); return True
if __name__ == "__main__": print(rebuild())
