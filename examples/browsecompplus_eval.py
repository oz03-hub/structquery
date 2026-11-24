"""Index a JSONL corpus with structquery, run a query set as bag-of-words, and score against qrels.

Resumable: an existing index is reused (pass --rebuild to redo it); the run file is written
atomically. Example (see scripts/browsecompplus.sbatch):

    python examples/browsecompplus_eval.py --data scratchspace/data/browsecompplus \
        --index scratchspace/indripy/indexes/browsecompplus --out scratchspace/indripy/runs/bcp
"""
import argparse
import json
import math
import os
import time

import structquery


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True, help="dir with indexes/bm25/docids.jsonl, queries/, qrels/")
    ap.add_argument("--corpus", help="JSONL corpus (default: DATA/indexes/bm25/docids.jsonl)")
    ap.add_argument("--queries", help="default: DATA/queries/test.jsonl")
    ap.add_argument("--qrels", help="default: DATA/qrels/test.tsv")
    ap.add_argument("--index", required=True)
    ap.add_argument("--out", required=True, help="output directory for run + metrics")
    ap.add_argument("--limit", type=int, help="index only the first N documents (smoke test)")
    ap.add_argument("--stemmer", default="krovetz", choices=["krovetz", "porter", "none"])
    ap.add_argument("--memory", default="4G")
    ap.add_argument("--k", type=int, default=1000)
    ap.add_argument("--workers", type=int, default=int(os.environ.get("SLURM_CPUS_PER_TASK", "1")))
    ap.add_argument("--rule", default=None)
    ap.add_argument("--rebuild", action="store_true")
    a = ap.parse_args()

    corpus = a.corpus or os.path.join(a.data, "indexes/bm25/docids.jsonl")
    queries_f = a.queries or os.path.join(a.data, "queries/test.jsonl")
    qrels_f = a.qrels or os.path.join(a.data, "qrels/test.tsv")
    os.makedirs(a.out, exist_ok=True)
    print(f"structquery {structquery.__version__} / {structquery.INDRI_VERSION}", flush=True)
    metrics = {"args": vars(a)}

    done_marker = os.path.join(a.index, ".structquery_complete")
    if a.rebuild or not os.path.exists(done_marker):
        t0 = time.time()
        with structquery.IndexBuilder(a.index, stemmer=None if a.stemmer == "none" else a.stemmer,
                                  memory=a.memory, overwrite=os.path.exists(a.index)) as b:
            n = b.add_jsonl(corpus, id_key="docid", text_key="text", limit=a.limit,
                            progress=lambda n: print(f"  indexed {n} docs, {time.time()-t0:.0f}s", flush=True),
                            progress_every=10000)
        open(done_marker, "w").write(f"{n}\n")
        metrics["index_seconds"] = round(time.time() - t0, 1)
        print(f"indexed {n} docs in {metrics['index_seconds']}s", flush=True)
    else:
        print("reusing existing index", flush=True)

    with structquery.Index(a.index) as idx:
        st = idx.stats()
    metrics["stats"] = {"doc_count": st.doc_count, "term_count": st.term_count,
                        "unique_terms": st.unique_terms, "avg_doc_length": round(st.avg_doc_length, 1)}
    print(metrics["stats"], flush=True)

    queries = {}
    with open(queries_f, encoding="utf-8") as fh:
        for line in fh:
            o = json.loads(line)
            queries[str(o["query_id"])] = structquery.bag_of_words(o.get("question") or o["query"])
    t0 = time.time()
    run = structquery.batch_search(a.index, queries, k=a.k, workers=a.workers, rule=a.rule)
    metrics["search_seconds"] = round(time.time() - t0, 1)
    metrics["n_queries"] = len(queries)
    metrics["n_errors"] = len(run.errors)
    run.to_trec(os.path.join(a.out, "run.trec"))
    if run.errors:
        json.dump(run.errors, open(os.path.join(a.out, "errors.json"), "w"), indent=1)

    qrels = {}
    with open(qrels_f) as fh:
        for line in fh:
            p = line.split()
            if len(p) >= 3 and int(p[-1]) > 0:
                qrels.setdefault(p[0], {})[p[-2]] = int(p[-1])
    r100 = r1000 = ndcg = 0.0
    n = 0
    for qid, rel in qrels.items():
        if qid not in queries:
            continue
        n += 1
        ranked = [h.docid for h in run.results.get(qid, [])]
        r100 += len(set(ranked[:100]) & set(rel)) / len(rel)
        r1000 += len(set(ranked[:1000]) & set(rel)) / len(rel)
        dcg = sum((2 ** rel.get(d, 0) - 1) / math.log2(i + 2) for i, d in enumerate(ranked[:10]))
        idcg = sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(sorted(rel.values(), reverse=True)[:10]))
        ndcg += dcg / idcg if idcg else 0.0
    metrics.update({"n_judged_queries": n, "recall@100": round(r100 / max(n, 1), 4),
                    "recall@1000": round(r1000 / max(n, 1), 4), "ndcg@10": round(ndcg / max(n, 1), 4)})
    tmp = os.path.join(a.out, "metrics.json.tmp")
    json.dump(metrics, open(tmp, "w"), indent=1)
    os.replace(tmp, os.path.join(a.out, "metrics.json"))
    print(json.dumps({k: v for k, v in metrics.items() if k != "args"}, indent=1))


if __name__ == "__main__":
    main()
