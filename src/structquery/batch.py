"""Running many queries: :func:`batch_search`, :class:`Run`, and helpers for LLM-written queries."""
from __future__ import annotations

import os
import re
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Sequence, Tuple, Union

from ._structquery import IndriError, QuerySyntaxError
from .index import Hit, Index, escape

__all__ = ["batch_search", "Run", "bag_of_words", "extract_query"]



def trec_line(qid: str, hit: Hit, tag: str) -> str:
    """One TREC run line. Raises ``ValueError`` if an id contains whitespace (it would add a column)."""
    for what, value in (("query id", qid), ("docid", hit.docid)):
        if not value or any(c.isspace() for c in value):
            raise ValueError(f"cannot write a TREC run line: {what} {value!r} is empty or contains "
                             "whitespace. Use ids without spaces, or use Run.to_dict() instead.")
    return f"{qid} Q0 {hit.docid} {hit.rank} {hit.score:.6f} {tag}"


_QUERY_TAG = re.compile(r"<query>(.*?)</query>", re.S | re.I)


def extract_query(llm_output: str, tag: str = "query") -> Optional[str]:
    """Return the text inside the LAST ``<query>...</query>`` block of an LLM response, stripped.

    Returns ``None`` if there is no such block or it is empty. The last block is used because
    models often show a draft or an example before their final answer.
    """
    pattern = _QUERY_TAG if tag == "query" else re.compile(
        rf"<{re.escape(tag)}>(.*?)</{re.escape(tag)}>", re.S | re.I)
    found = pattern.findall(llm_output or "")
    if not found:
        return None
    q = found[-1].strip()
    return q or None


def bag_of_words(text: str) -> str:
    """``#combine(...)`` over the plain words of ``text``; always a valid query unless no words remain.

    Works on natural language and on a broken Indri query (operators and punctuation are dropped,
    the words are kept). Raises ``ValueError`` if ``text`` contains no letters or digits.
    """
    words = [w for w in escape(re.sub(r"#\w+", " ", text)).split() if w]
    if not words:
        raise ValueError("no query terms left after removing punctuation")
    return "#combine(" + " ".join(words) + ")"


@dataclass
class Run:
    """Result of :func:`batch_search`.

    ``results``   ``{qid: [Hit, ...]}`` for every query that ran (possibly an empty list).
    ``errors``    ``{qid: message}`` for queries that failed (syntax error or engine error).
    ``fallbacks`` ``{qid: query_actually_run}`` for queries replaced by a bag-of-words fallback
                  (only with ``on_error="fallback"``); these qids appear in both ``errors`` and ``results``.
    ``queries``   the queries as given.
    """

    results: Dict[str, List[Hit]] = field(default_factory=dict)
    errors: Dict[str, str] = field(default_factory=dict)
    fallbacks: Dict[str, str] = field(default_factory=dict)
    queries: Dict[str, str] = field(default_factory=dict)

    def to_trec(self, file: Union[str, os.PathLike], tag: str = "structquery") -> int:
        """Write a TREC run file (``qid Q0 docid rank score tag``). Returns lines written.

        Raises ``ValueError`` (and writes nothing) if a query id or docid contains whitespace.
        """
        lines = [trec_line(qid, h, tag) for qid, hits in self.results.items() for h in hits]
        tmp = f"{os.fspath(file)}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            for line in lines:
                fh.write(line + "\n")
        os.replace(tmp, file)
        return len(lines)

    def to_dict(self) -> Dict[str, Dict[str, float]]:
        """``{qid: {docid: score}}``, the format ``pytrec_eval`` and ``ir_measures`` accept."""
        return {qid: {h.docid: h.score for h in hits} for qid, hits in self.results.items()}


_worker_index: Optional[Index] = None


def _init_worker(path: str, rule) -> None:
    global _worker_index
    _worker_index = Index(path, rule=rule)


def _run_one(args: Tuple[str, str, int, str, bool]):
    qid, query, k, on_error, docs = args
    idx = _worker_index
    assert idx is not None
    try:
        return qid, idx.search(query, k=k, docs=docs), None, None
    except IndriError as e:  # includes QuerySyntaxError
        err = f"{type(e).__name__}: {e}"
        if on_error == "fallback":
            try:
                fb = bag_of_words(query)
                return qid, idx.search(fb, k=k, docs=docs), err, fb
            except (IndriError, ValueError) as e2:
                return qid, None, f"{err}; fallback failed: {e2}", None
        return qid, None, err, None


def batch_search(index: Union[str, os.PathLike, Index], queries: Union[Mapping[str, str], Sequence[Tuple[str, str]]],
                 k: int = 1000, workers: int = 1, rule: Union[str, Sequence[str], None] = None,
                 on_error: str = "skip", docs: bool = False) -> Run:
    """Run many Indri queries; one bad query never stops the others.

    Args:
        index:    index path (or an open :class:`Index`, only with ``workers=1``).
        queries:  ``{qid: query}`` or a list of ``(qid, query)``.
        k:        hits per query.
        workers:  number of processes. Each opens its own ``Index``. Keep it at or below the CPUs
                  you were allocated (e.g. ``$SLURM_CPUS_PER_TASK``).
        rule:     scoring rule(s), as for :class:`Index`.
        on_error: ``"skip"`` (default) record the error in ``Run.errors`` and continue;
                  ``"fallback"`` also retry as ``bag_of_words(query)`` and record it in
                  ``Run.fallbacks``; ``"raise"`` re-raise the first error.
        docs:     load document text into each ``Hit.text``.

    Returns a :class:`Run`.
    """
    if on_error not in ("skip", "fallback", "raise"):
        raise ValueError("on_error must be 'skip', 'fallback' or 'raise'")
    items = list(queries.items()) if isinstance(queries, Mapping) else list(queries)
    items = [(str(q), str(t)) for q, t in items]
    run = Run(queries=dict(items))
    tasks = [(qid, q, k, on_error, docs) for qid, q in items]

    global _worker_index
    if isinstance(index, Index):
        if workers != 1:
            raise ValueError("pass the index path (not an Index object) when workers > 1")
        _worker_index, own = index, False
        outputs = map(_run_one, tasks)
    elif workers <= 1:
        _init_worker(os.fspath(index), rule)
        own = True
        outputs = map(_run_one, tasks)
    else:
        own = False
        pool = ProcessPoolExecutor(max_workers=workers, initializer=_init_worker,
                                   initargs=(os.fspath(index), rule))
        outputs = pool.map(_run_one, tasks, chunksize=max(1, len(tasks) // (workers * 8) or 1))
    try:
        for qid, hits, err, fb in outputs:
            if err is not None:
                if on_error == "raise":
                    cls = QuerySyntaxError if err.startswith("QuerySyntaxError") else IndriError
                    raise cls(f"query {qid!r}: {err}")
                run.errors[qid] = err
            if hits is not None:
                run.results[qid] = hits
            if fb is not None:
                run.fallbacks[qid] = fb
    finally:
        if not isinstance(index, Index) and workers > 1:
            pool.shutdown(cancel_futures=True)
        elif own and _worker_index is not None:
            _worker_index.close()
        _worker_index = None
    return run
