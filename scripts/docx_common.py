"""共通ユーティリティ: DOCXの読み書き(標準ライブラリ+lxml)。"""
import zipfile, hashlib, copy
from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W}
def q(tag): return "{%s}%s" % (W, tag)

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(65536), b""):
            h.update(b)
    return h.hexdigest()

def read_parts(path):
    with zipfile.ZipFile(path) as z:
        return {i.filename: z.read(i.filename) for i in z.infolist()}, [i.filename for i in z.infolist()]

def write_parts(path, parts, order):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        names = list(order) + [n for n in parts if n not in order]
        for n in names:
            if n in parts:
                z.writestr(n, parts[n])

def para_text(p, include_deleted=False):
    out = []
    for el in p.iter():
        if el.tag == q("t"): out.append(el.text or "")
        elif el.tag == q("delText") and include_deleted: out.append(el.text or "")
        elif el.tag == q("tab"): out.append("\t")
    return "".join(out)
