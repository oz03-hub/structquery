"""structquery quickstart: build a small index, search it, read documents, write a TREC run.

    python examples/quickstart.py                 # index goes to a new temp directory
    python examples/quickstart.py --index my_idx  # or to a directory you choose (must not exist)
"""
import argparse
import os
import tempfile

import structquery

DOCS = {
    "d1": {"title": "Indri search engine", "body": "Indri is a search engine from the Lemur Project."},
    "d2": {"title": "Lemur Project history", "body": "The Lemur Project was started by UMass and CMU."},
    "d3": {"title": "White House press briefing", "body": "The press secretary spoke at the White House."},
    "d4": {"title": "Housing market", "body": "House prices rose; the white paint on the house was new."},
}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--index", help="index directory to create (default: a new temp directory)")
    a = ap.parse_args()
    workdir = tempfile.mkdtemp(prefix="structquery_quickstart_")
    path = a.index or os.path.join(workdir, "index")

    # 1. Build. The index is searchable once the `with` block has closed the builder.
    with structquery.IndexBuilder(path, fields=["title", "body"]) as b:
        for docid, doc in DOCS.items():
            b.add(docid, doc)
        print(f"indexed {b.count} documents into {path}")

    with structquery.Index(path) as idx:
        print(idx.stats())

        # 2. Search. Scores are log-probabilities: negative, higher is better.
        for query in ["#combine(white house)", "#1(white house)", "#combine(lemur.title)",
                      "#filrej(press #combine(white house))"]:
            hits = idx.search(query, k=5)
            print(f"{query:40} -> {[(h.docid, round(h.score, 3)) for h in hits]}")

        # 3. Documents and snippets.
        hit = idx.search("#combine(press secretary)", k=1, snippets=True)[0]
        print("snippet:", repr(hit.snippet))
        print("d3 text:", repr(idx.get("d3").text))

        # 4. A bad query raises QuerySyntaxError; validate() checks without searching.
        try:
            idx.search("what's new?")
        except structquery.QuerySyntaxError as e:
            print("syntax error:", e)

    # 5. Many queries -> TREC run file. A failing query is recorded, not fatal.
    run = structquery.batch_search(path, {"q1": "#combine(lemur project)", "q2": "#combine(white"}, k=10)
    out = os.path.join(workdir, "run.trec")
    print(f"wrote {run.to_trec(out)} lines to {out}; errors: {run.errors}")


if __name__ == "__main__":
    main()
