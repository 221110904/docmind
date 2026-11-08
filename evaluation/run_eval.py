"""DocMind evaluation: asks every question in questions.json through the local API and scores the results.

Usage (backend running with AUTH_BACKEND=none on port 8000):
    python run_eval.py
    python run_eval.py --base http://127.0.0.1:8000 --token <bearer>   # for a signed-in/live API
"""
import argparse, csv, json, re, statistics, sys, time, unicodedata, urllib.request, urllib.error
from pathlib import Path

HERE = Path(__file__).parent


def key(name: str) -> str:
    """Compare file names ignoring case, spaces, underscores and brackets."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def norm(text: str) -> str:
    """Lower-case and unify Arabic spelling variants so keyword checks are fair."""
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub("[ً-ٰٟـ]", "", text)          # diacritics, tatweel
    text = re.sub("[آأإ]", "ا", text)           # alef variants
    text = text.replace("ى", "ي").replace("ة", "ه")
    text = text.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
    text = re.sub(r"(?<=\d),(?=\d{3})", "", text)                    # 56,250 -> 56250
    return text


def hit(answer_n: str, kw: str) -> bool:
    if kw.startswith("re:"):
        return re.search(kw[3:], answer_n) is not None
    return norm(kw) in answer_n


def call(base, path, payload=None, token=None, method=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(base + path, data=data, method=method or ("POST" if data else "GET"))
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode(errors="replace")[:300]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--token", default=None)
    ap.add_argument("--scoped", action="store_true", help="limit each question to its own document, top_k 10")
    args = ap.parse_args()
    questions = json.loads((HERE / "questions.json").read_text(encoding="utf-8"))

    status, docs = call(args.base, "/documents", token=args.token)
    if status != 200:
        sys.exit(f"Cannot list documents ({status}): {docs}")
    print("Documents in the workspace:")
    for d in docs:
        print("  -", d.get("filename"), "|", d.get("status"))
    names = [d.get("filename", "") for d in docs]
    for needed in sorted({q["doc"] for q in questions if q["doc"]}):
        if not any(key(needed) in key(n) for n in names):
            print(f"WARNING: no uploaded file matches '{needed}'. Upload it, wait until indexed, and rerun.")

    def doc_id(needed):
        for d in docs:
            if key(needed) in key(d.get("filename", "")):
                return d.get("id") or d.get("document_id")
        return None

    suffix = "_scoped" if args.scoped else ""
    rows = []
    for q in questions:
        body = {"question": q["q"], "top_k": 5}
        if args.scoped and q["doc"]:
            scope = doc_id(q["doc"])
            if not scope:
                sys.exit(f"Cannot find the id of the document for {q['id']}")
            body.update(top_k=10, document_id=scope)
        t0 = time.perf_counter()
        status, out = call(args.base, "/ask", body, args.token)
        secs = time.perf_counter() - t0
        row = {"id": q["id"], "cat": q["cat"], "question": q["q"], "truth": q["truth"], "http": status,
               "seconds": round(secs, 2), "found": None, "answer": "", "sources": "", "correct": False,
               "citation_doc_ok": None, "citation_page_ok": None}
        if status == 200:
            row["found"] = out["found"]
            row["answer"] = out["answer"]
            row["sources"] = "; ".join(f'{s["filename"]} p{s["page_number"]}' for s in out["sources"])
            ans = norm(out["answer"])
            if q["cat"] == "Unanswerable":
                row["correct"] = out["found"] is False
            else:
                row["correct"] = out["found"] and all(any(hit(ans, k) for k in grp) for grp in q["must"])
                if out["found"]:
                    docs_ok = [s for s in out["sources"] if key(q["doc"]) in key(s["filename"])]
                    row["citation_doc_ok"] = bool(docs_ok)
                    if q.get("pages"):
                        row["citation_page_ok"] = any(s["page_number"] in q["pages"] for s in docs_ok)
        else:
            row["answer"] = str(out)[:200]
        rows.append(row)
        mark = "PASS" if row["correct"] else "FAIL"
        print(f'{q["id"]} {mark} {row["seconds"]:>5}s  {q["q"][:60]}')

    with open(HERE / f"results{suffix}.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
    (HERE / f"results{suffix}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

    def pct(a, b): return f"{a}/{b} ({100*a/b:.0f}%)" if b else "n/a"
    print("\n=== SUMMARY ===")
    for cat in dict.fromkeys(r["cat"] for r in rows):
        g = [r for r in rows if r["cat"] == cat]
        print(f"{cat:<13} correct {pct(sum(r['correct'] for r in g), len(g))}")
    ans = [r for r in rows if r["cat"] != "Unanswerable"]
    unans = [r for r in rows if r["cat"] == "Unanswerable"]
    cited = [r for r in ans if r["citation_doc_ok"] is not None]
    paged = [r for r in ans if r["citation_page_ok"] is not None]
    print(f"Overall answer accuracy      {pct(sum(r['correct'] for r in ans), len(ans))}")
    print(f"Correct 'not found'          {pct(sum(r['correct'] for r in unans), len(unans))}")
    print(f"Citation points to right doc {pct(sum(r['citation_doc_ok'] for r in cited), len(cited))}")
    print(f"Citation page correct (PDF)  {pct(sum(r['citation_page_ok'] for r in paged), len(paged))}")
    lat = sorted(r["seconds"] for r in rows if r["http"] == 200)
    if lat:
        print(f"Latency median {statistics.median(lat):.1f}s, p95 {lat[max(0, int(len(lat)*0.95)-1)]:.1f}s")
    print(f"\nResults saved to results{suffix}.csv and results{suffix}.json. Review FAIL rows by hand: the keyword check is strict.")


if __name__ == "__main__":
    main()
