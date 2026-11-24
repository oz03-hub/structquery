"""Searching an Indri index: :class:`Index`, :class:`Hit`, :class:`Document`, :class:`IndexStats`."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Union

from . import _structquery
from ._structquery import IndriError, QuerySyntaxError

__all__ = ["Index", "Hit", "Document", "IndexStats", "escape", "validate", "is_valid", "DEFAULT_RULE"]

#: Indri's own default retrieval model (query likelihood, Dirichlet smoothing, mu=2500).
DEFAULT_RULE = "method:dirichlet,mu:2500"

_NOT_WORD = re.compile(r"[^\w\s]|_", re.UNICODE)
_SPACE = re.compile(r"\s+")
# Indri's tokenizer indexes "U.S." as "us" and "don't" as "dont"; mirror that so escaped text matches.
_ACRONYM = re.compile(r"\b(?:[A-Za-z]\.){2,}|\b(?:[A-Za-z]\.)+[A-Za-z]\b")
_APOSTROPHE = re.compile(r"(?<=\w)['\u2019](?=\w)")


def _s(b: Union[bytes, str, None]) -> str:
    if b is None:
        return ""
    return b.decode("utf-8", "replace") if isinstance(b, bytes) else b


def escape(text: str) -> str:
    """Turn arbitrary text into plain query terms that Indri's query parser always accepts.

    Dotted acronyms and contractions are joined the way Indri's tokenizer indexes them
    (``U.S.`` -> ``US``, ``don't`` -> ``dont``); every other character that is not a letter,
    digit or whitespace becomes a space (punctuation such as ``. , ? " # ( ) -`` has syntactic
    meaning in the Indri query language or makes it fail to parse). Use it for natural-language
    text you want to put inside an operator::

        >>> structquery.escape("What's the U.S. GDP (2020)?")
        'Whats the US GDP 2020'
        >>> query = f"#combine({structquery.escape(question)})"

    Do NOT call it on a full Indri query: it would strip the operators.
    """
    text = _ACRONYM.sub(lambda m: m.group(0).replace(".", ""), text)
    text = _APOSTROPHE.sub("", text)
    return _SPACE.sub(" ", _NOT_WORD.sub(" ", text)).strip()


def validate(query: str) -> None:
    """Check that ``query`` is syntactically valid Indri query language. No index is needed.

    Returns ``None`` when valid, raises :class:`QuerySyntaxError` (with Indri's parser message)
    when not. This only checks syntax: a query naming a field that does not exist in an index
    passes here, and :meth:`Index.search` then simply returns no results for it (Indri does not
    treat an unknown field as an error; compare against :attr:`Index.fields` if you need to know).
    """
    if not isinstance(query, str):
        raise TypeError(f"query must be str, got {type(query).__name__}")
    if not query.strip():
        raise QuerySyntaxError("Couldn't understand this query: the query is empty")
    _structquery.Index.validate(query)


def is_valid(query: str) -> bool:
    """``True`` if :func:`validate` accepts ``query``, else ``False``. Never raises for str input."""
    try:
        validate(query)
        return True
    except QuerySyntaxError:
        return False


@dataclass(frozen=True)
class Document:
    """A stored document.

    ``docid``    external id (the ``docno`` given at indexing time).
    ``text``     the text exactly as Indri stored it; structquery does not alter it. For a document
                 added as a plain string this is that string. For a document added as a mapping it
                 is the tagged form that was indexed (``<title>\n...\n</title>\n<body>...``), and
                 for TREC/HTML/XML files it includes that format's markup.
    ``fields``   for a document added as a mapping: the ``{name: text}`` mapping back again
                 (with ``<`` and ``>`` as spaces, as they were indexed). Empty for every other
                 kind of document.
    ``metadata`` all stored metadata, including ``docno``.
    ``raw``      the complete stored record: the same as ``text`` for documents added with
                 ``add``; for TREC files it also has the ``<DOC>`` wrapper.
    """

    docid: str
    text: str
    metadata: Dict[str, str] = field(default_factory=dict)
    raw: str = ""
    fields: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Hit:
    """One search result.

    ``docid``    external document id.
    ``score``    Indri score: a log-probability for the default language-model rules, so it is
                 negative and *higher (closer to 0) is better*.
    ``rank``     1-based rank.
    ``text``     document text as Indri stored it (see :class:`Document`), only when
                 ``search(..., docs=True)`` (else ``None``).
    ``snippet``  query-biased snippet built by Indri, only when ``search(..., snippets=True)``.
    ``internal_id`` Indri's internal integer document id (rarely needed).
    """

    docid: str
    score: float
    rank: int
    text: Optional[str] = None
    snippet: Optional[str] = None
    internal_id: int = 0


@dataclass(frozen=True)
class IndexStats:
    """Collection statistics. ``term_count`` is total tokens; ``unique_terms`` is vocabulary size."""

    doc_count: int
    term_count: int
    unique_terms: int
    fields: List[str]
    avg_doc_length: float
    path: str


# Exactly the layout IndexBuilder.add writes for mapping documents. Values never contain
# "<" or ">" (add replaces them), so this parse cannot be confused by the text itself.
_FIELD_BLOCK = re.compile(r"<([A-Za-z][A-Za-z0-9_]*)>\n([^<>]*)\n</\1>\n")


def _parse_fields(text: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    pos = 0
    for m in _FIELD_BLOCK.finditer(text):
        if m.start() != pos:
            return {}
        out[m.group(1)] = m.group(2)
        pos = m.end()
    return out if pos == len(text) and pos > 0 else {}


def _doc_from_raw(d: dict) -> Document:
    # keys like #TEXT# / #POSITIONS# are Indri's internal storage records, not user metadata
    meta = {str(k): _s(v) for k, v in d["metadata"].items() if not str(k).startswith("#")}
    text = _s(d["content"])
    return Document(docid=meta.get("docno", ""), text=text, metadata=meta, raw=_s(d["raw"]),
                    fields=_parse_fields(text))


class Index:
    """A read-only handle on an Indri index (repository directory) for searching.

    Example::

        import structquery
        with structquery.Index("/path/to/index") as idx:
            for hit in idx.search("#combine(neural #1(information retrieval))", k=5):
                print(hit.rank, hit.docid, hit.score)

    Args:
        path:   index directory created by :class:`structquery.IndexBuilder` or ``IndriBuildIndex``.
        rule:   Indri scoring rule(s), e.g. ``"method:dirichlet,mu:2500"`` (default),
                ``"method:jm,lambda:0.4"``, ``"method:twostage,mu:2500,lambda:0.4"``,
                or a list of rule strings (to set per-field smoothing).
        memory: optional query-time memory budget, bytes or a string like ``"1G"``.

    Not thread-safe: use one ``Index`` per thread/process (see :func:`structquery.batch_search`).
    Raises :class:`IndriError` if ``path`` is not an Indri index.
    """

    def __init__(self, path: Union[str, os.PathLike], rule: Union[str, Sequence[str], None] = None,
                 memory: Union[int, str, None] = None):
        from .indexer import parse_memory

        path = os.fspath(path)
        if not os.path.isdir(path):
            raise FileNotFoundError(f"Indri index directory not found: {path!r}. "
                                    "Build one with structquery.IndexBuilder or `structquery index`.")
        if rule is None:
            rules: List[str] = []
        elif isinstance(rule, str):
            rules = [rule]
        else:
            rules = list(rule)
        self.path = path
        self.rules = rules
        self._ix = _structquery.Index(path, rules, parse_memory(memory) if memory else 0)

    # -- lifecycle -------------------------------------------------------------------------
    def close(self) -> None:
        """Release the index. Safe to call twice."""
        self._ix.close()

    def __enter__(self) -> "Index":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"Index({self.path!r}, rule={self.rules or DEFAULT_RULE!r})"

    # -- query syntax ----------------------------------------------------------------------
    def validate(self, query: str) -> None:
        """Same as :func:`structquery.validate`: raise :class:`QuerySyntaxError` if ``query`` is malformed."""
        validate(query)

    def is_valid(self, query: str) -> bool:
        """Same as :func:`structquery.is_valid`."""
        return is_valid(query)

    # -- search ----------------------------------------------------------------------------
    def search(self, query: str, k: int = 10, docs: bool = False, snippets: bool = False) -> List[Hit]:
        """Run an Indri query and return the top ``k`` hits, best first.

        Args:
            query:    Indri query language string, e.g. ``"#combine(white house)"``. Bare words
                      (``"white house"``) are treated as ``#combine``. See docs/query-language.md.
            k:        number of results.
            docs:     also load each hit's stored text into ``Hit.text`` (slower).
            snippets: also build a query-biased snippet into ``Hit.snippet`` (implies loading docs).

        Raises:
            QuerySyntaxError: the query does not parse. ``str(e)`` is Indri's parser message.
            IndriError: any other engine failure (e.g. an unknown ``#prior``).

        A field name that is not in :attr:`fields` is not an error: the query returns ``[]``.
        An unknown ``rule`` is not an error either: Indri silently uses its default.
        """
        validate(query)
        if k <= 0:
            return []
        if docs or snippets:
            rows = self._ix.search_docs(query, int(k), bool(snippets))
            out = []
            for rank, (name, score, iid, _b, _e, doc, snip) in enumerate(rows, 1):
                text = _s(doc["content"]) if (docs and doc is not None) else None
                out.append(Hit(_s(name), score, rank, text, _s(snip) if snip is not None else None, iid))
            return out
        rows = self._ix.search(query, int(k))
        return [Hit(_s(name), score, rank, None, None, iid)
                for rank, (name, score, iid, _b, _e) in enumerate(rows, 1)]

    # -- documents -------------------------------------------------------------------------
    def get(self, docid: str) -> Document:
        """Fetch one stored document by external id. Raises ``KeyError`` if it is not in the index."""
        return self.get_many([docid])[0]

    def get_many(self, docids: Sequence[str]) -> List[Document]:
        """Fetch several stored documents, in the given order. Raises ``KeyError`` on a missing id."""
        docids = [str(d) for d in docids]
        ids = self._ix.internal_ids(docids)
        missing = [d for d, i in zip(docids, ids) if i == 0]
        if missing:
            raise KeyError(f"docid not in index: {missing[0]!r}")
        raws = self._ix.documents(ids)
        out = []
        for d, raw in zip(docids, raws):
            if raw is None:
                raise KeyError(f"docid not in index: {d!r}")
            out.append(_doc_from_raw(raw))
        return out

    def __contains__(self, docid: str) -> bool:
        return self._ix.internal_ids([str(docid)])[0] != 0

    def __len__(self) -> int:
        return self._ix.document_count()

    # -- statistics ------------------------------------------------------------------------
    def stats(self) -> IndexStats:
        """Collection statistics (document count, token count, vocabulary size, fields)."""
        n = self._ix.document_count()
        t = self._ix.term_count()
        return IndexStats(doc_count=n, term_count=t, unique_terms=self._ix.term_count_unique(),
                          fields=list(self._ix.field_list()), avg_doc_length=(t / n if n else 0.0),
                          path=self.path)

    def term_count(self, term: str, field: Optional[str] = None) -> int:
        """Total occurrences of ``term`` in the collection (the term is stemmed like a query term).
        With ``field``, only occurrences inside that field."""
        if field:
            return self._ix.term_field_count(term, field)
        return self._ix.term_count_term(term)

    def doc_freq(self, term: str) -> int:
        """Number of documents containing ``term`` (stemmed like a query term)."""
        return self._ix.document_count_term(term)

    def expression_count(self, expression: str) -> float:
        """Total occurrences of an Indri expression, e.g. ``"#1(white house)"`` or ``"#uw8(a b)"``."""
        validate(expression)
        return self._ix.expression_count(expression)

    def expression_doc_freq(self, expression: str) -> float:
        """Number of documents matching an Indri expression, e.g. ``"#1(white house)"``.

        Caveat (Indri behaviour, not corrected here): for field-restricted expressions such as
        ``"lemur.title"`` Indri can report more documents than actually match in that field.
        """
        validate(expression)
        return self._ix.document_expression_count(expression)

    def doc_length(self, docid: str) -> int:
        """Length of a document in indexed tokens. Raises ``KeyError`` if missing."""
        iid = self._ix.internal_ids([str(docid)])[0]
        if iid == 0:
            raise KeyError(f"docid not in index: {docid!r}")
        return self._ix.document_length(iid)

    def stem(self, term: str) -> str:
        """Apply the index's stemmer (the one chosen at build time) to ``term``."""
        return _s(self._ix.stem_term(term))

    @property
    def fields(self) -> List[str]:
        """Names of the fields that were indexed (usable as ``term.field`` in queries)."""
        return list(self._ix.field_list())
