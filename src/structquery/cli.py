"""Command-line interface: ``structquery index | search | validate | stats | doc``.

Every command accepts ``--json`` for machine-readable output. Exit codes: 0 success,
1 engine/usage error, 2 invalid query syntax.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from typing import List, Optional

from . import (INDRI_VERSION, Index, IndexBuilder, IndriError, QuerySyntaxError, __version__,
               batch_search, validate)
from .indexer import FILE_CLASSES, STEMMERS


def _out(obj, as_json: bool, text: str) -> None:
    print(json.dumps(obj, ensure_ascii=False) if as_json else text)


def _cmd_index(a) -> int:
    t0 = time.time()
    stemmer = None if a.stemmer == "none" else a.stemmer
    stop = None
    if a.stopwords:
        with open(a.stopwords, encoding="utf-8") as fh:
            stop = [w.strip() for w in fh if w.strip()]

    def progress(n):
        if not a.json:
            print(f"\r{n} documents", end="", file=sys.stderr, flush=True)

    with IndexBuilder(a.index, stemmer=stemmer, stopwords=stop, fields=a.field, memory=a.memory,
                      store_docs=not a.no_store, overwrite=a.overwrite, append=a.append) as b:
        for path in a.input:
            if a.format == "jsonl":
                keys = a.text_key if len(a.text_key) > 1 else a.text_key[0]
                b.add_jsonl(path, id_key=a.id_key, text_key=keys, limit=a.limit, progress=progress)
            else:
                b.add_files(path, file_class=a.format)
        n = b.count
    if not a.json:
        print(file=sys.stderr)
    _out({"index": a.index, "documents": n, "seconds": round(time.time() - t0, 2)}, a.json,
         f"indexed {n} documents into {a.index} in {time.time() - t0:.1f}s")
    return 0


def _cmd_search(a) -> int:
    if a.queries:
        queries = {}
        with open(a.queries, encoding="utf-8") as fh:
            for line in fh:
                line = line.rstrip("\n")
                if not line.strip():
                    continue
                if a.queries.endswith(".jsonl"):
                    o = json.loads(line)
                    queries[str(o[a.qid_key])] = o[a.query_key]
                else:
                    qid, _, q = line.partition("\t")
                    queries[qid] = q
        run = batch_search(a.index, queries, k=a.k, workers=a.workers, rule=a.rule, on_error=a.on_error)
        if a.output:
            run.to_trec(a.output, tag=a.tag)
        else:
            from .batch import trec_line
            for line in [trec_line(qid, h, a.tag) for qid, hits in run.results.items() for h in hits]:
                print(line)
        summary = {"queries": len(queries), "ran": len(run.results), "errors": run.errors,
                   "fallbacks": run.fallbacks, "output": a.output}
        print(json.dumps(summary, ensure_ascii=False) if a.json
              else f"{len(run.results)}/{len(queries)} queries ran, {len(run.errors)} errors", file=sys.stderr)
        return 0
    if a.query is None:
        print("error: give a QUERY or --queries FILE", file=sys.stderr)
        return 1
    with Index(a.index, rule=a.rule) as idx:
        hits = idx.search(a.query, k=a.k, docs=a.docs, snippets=a.snippets)
    if a.json:
        print(json.dumps({"query": a.query, "hits": [asdict(h) for h in hits]}, ensure_ascii=False))
    else:
        for h in hits:
            print(f"{h.rank}\t{h.docid}\t{h.score:.4f}" + (f"\t{h.snippet!r}" if h.snippet else ""))
            if a.docs and h.text is not None:
                print(h.text[:a.max_chars].rstrip() + ("..." if len(h.text) > a.max_chars else ""))
                print()
    return 0


def _cmd_validate(a) -> int:
    query = a.query if a.query is not None else sys.stdin.read()
    try:
        validate(query)
    except QuerySyntaxError as e:
        _out({"valid": False, "error": str(e), "query": query}, a.json, f"INVALID: {e}")
        return 2
    _out({"valid": True, "query": query}, a.json, "valid")
    return 0


def _cmd_stats(a) -> int:
    with Index(a.index) as idx:
        st = asdict(idx.stats())
        extra = {}
        for t in a.term or []:
            extra[t] = {"stem": idx.stem(t), "term_count": idx.term_count(t), "doc_freq": idx.doc_freq(t)}
    st["indri_version"] = INDRI_VERSION
    if extra:
        st["terms"] = extra
    _out(st, a.json, "\n".join(f"{k}: {v}" for k, v in st.items()))
    return 0


def _cmd_doc(a) -> int:
    with Index(a.index) as idx:
        try:
            docs = idx.get_many(a.docid)
        except KeyError as e:
            print(f"error: {e.args[0]}", file=sys.stderr)
            return 1
    for d in docs:
        _out({"docid": d.docid, "text": d.text, "metadata": d.metadata}, a.json, d.text)
    return 0


class _Parser(argparse.ArgumentParser):
    """argparse exits with 2 on usage errors; 2 is reserved here for invalid query syntax."""

    def error(self, message: str):
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def build_parser() -> argparse.ArgumentParser:
    p = _Parser(prog="structquery", description="Build and query Indri indexes.")
    p.add_argument("--version", action="version", version=f"structquery {__version__} ({INDRI_VERSION})")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("index", help="build an index from JSONL or native Indri formats")
    s.add_argument("index", help="index directory to create")
    s.add_argument("input", nargs="+", help="input file(s)")
    s.add_argument("--format", default="jsonl", choices=("jsonl",) + FILE_CLASSES)
    s.add_argument("--id-key", default="docid", help="JSONL key of the document id (default: docid)")
    s.add_argument("--text-key", nargs="+", default=["text"],
                   help="JSONL key(s) of the text; several keys make a fielded document")
    s.add_argument("--field", action="append", default=[], help="field to index (repeatable)")
    s.add_argument("--stemmer", default="krovetz", choices=STEMMERS + ("none",))
    s.add_argument("--stopwords", help="file with one stopword per line (none by default)")
    s.add_argument("--memory", default="1G")
    s.add_argument("--limit", type=int, help="only the first N lines of each JSONL file")
    s.add_argument("--no-store", action="store_true", help="do not store document text")
    s.add_argument("--overwrite", action="store_true")
    s.add_argument("--append", action="store_true")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=_cmd_index)

    s = sub.add_parser("search", help="run one query, or a file of queries (TREC run output)")
    s.add_argument("index")
    s.add_argument("query", nargs="?", help="Indri query, e.g. '#combine(white house)'")
    s.add_argument("--queries", help="TSV (qid<TAB>query) or .jsonl file of queries")
    s.add_argument("--qid-key", default="qid")
    s.add_argument("--query-key", default="query")
    s.add_argument("-k", type=int, default=10)
    s.add_argument("--rule", help="scoring rule, e.g. method:dirichlet,mu:2500")
    s.add_argument("--docs", action="store_true", help="print document text")
    s.add_argument("--snippets", action="store_true", help="print query-biased snippets")
    s.add_argument("--max-chars", type=int, default=500, help="truncate printed text (text mode only)")
    s.add_argument("--workers", type=int, default=1)
    s.add_argument("--on-error", default="skip", choices=("skip", "fallback", "raise"))
    s.add_argument("--output", "-o", help="write TREC run file here (with --queries)")
    s.add_argument("--tag", default="structquery")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=_cmd_search)

    s = sub.add_parser("validate", help="check Indri query syntax (exit 2 if invalid)")
    s.add_argument("query", nargs="?", help="query; read from stdin if omitted")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=_cmd_validate)

    s = sub.add_parser("stats", help="index statistics")
    s.add_argument("index")
    s.add_argument("--term", action="append", help="also report counts for this term (repeatable)")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=_cmd_stats)

    s = sub.add_parser("doc", help="print stored documents by id")
    s.add_argument("index")
    s.add_argument("docid", nargs="+")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=_cmd_doc)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    a = build_parser().parse_args(argv)
    try:
        return a.fn(a)
    except QuerySyntaxError as e:
        print(f"query syntax error: {e}", file=sys.stderr)
        return 2
    except (IndriError, OSError, ValueError, KeyError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
