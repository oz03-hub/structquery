"""Building an Indri index: :class:`IndexBuilder`.

All text processing is Indri's own: its tokenizers and parsers (chosen by *file class*), its
Krovetz/Porter stemmers and its stopword mechanism. structquery does no tokenization of its own and
ships no stopword list.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from typing import Callable, Iterable, Mapping, Optional, Sequence, Union

from . import _structquery

__all__ = ["IndexBuilder", "FILE_CLASSES", "STEMMERS", "parse_memory"]

#: Document formats Indri can parse natively (argument ``file_class`` of ``add_files``).
FILE_CLASSES = ("txt", "trectext", "trecweb", "trecalt", "trecchar", "html", "xml", "warc",
                "warcchar", "mbox", "pdf", "doc", "ppt")
#: Stemmers that ship with Indri.
STEMMERS = ("krovetz", "porter")

_UNITS = {"": 1, "b": 1, "k": 1 << 10, "kb": 1 << 10, "m": 1 << 20, "mb": 1 << 20,
          "g": 1 << 30, "gb": 1 << 30}
_FIELD_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_MARKUP = str.maketrans({"<": " ", ">": " "})


def parse_memory(value: Union[int, str]) -> int:
    """``"2G"``/``"512M"``/``1024`` -> bytes."""
    if isinstance(value, int):
        return value
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([a-zA-Z]*)\s*", str(value))
    if not m or m.group(2).lower() not in _UNITS:
        raise ValueError(f"cannot parse memory size {value!r}; use e.g. '2G', '512M' or an int of bytes")
    return int(float(m.group(1)) * _UNITS[m.group(2).lower()])


#: Everything an Indri repository directory may contain at top level (plus structquery's marker).
_INDEX_ENTRIES = {"manifest", "index", "collection", "deleted", "prior", ".structquery_complete"}


def _looks_like_index(path: str) -> bool:
    """True only if ``path`` has the layout of an Indri repository and nothing else in it."""
    try:
        entries = set(os.listdir(path))
    except OSError:
        return False
    return ({"manifest", "index", "collection"} <= entries and entries <= _INDEX_ENTRIES
            and os.path.isfile(os.path.join(path, "manifest"))
            and os.path.isdir(os.path.join(path, "index"))
            and os.path.isdir(os.path.join(path, "collection")))


class IndexBuilder:
    """Create (or append to) an Indri index.

    Example::

        import structquery
        with structquery.IndexBuilder("my_index", stemmer="krovetz") as b:
            b.add("d1", "Indri is a search engine from the Lemur Project.")
            b.add("d2", {"title": "Query language", "body": "Indri supports #combine and #uw."})
            b.add_jsonl("corpus.jsonl", id_key="docid", text_key="text")
        # the index is complete and searchable once the `with` block exits

    Args:
        path:       directory to create. Must not exist unless ``overwrite`` or ``append``.
        stemmer:    ``"krovetz"`` (default, Indri's usual choice), ``"porter"`` or ``None``.
                    Queries are stemmed the same way automatically.
        stopwords:  optional iterable of words to drop at index time (Indri's stopper). structquery
                    ships no list; the default ``None`` indexes every word.
        fields:     names of fields to index, so queries can use ``term.title`` or
                    ``#combine[title](...)``. Required for dict documents whose keys should be
                    searchable as fields.
        memory:     indexing memory budget (``"2G"``, ``"512M"`` or bytes).
        store_docs: keep document text in the index so ``Index.get`` / ``Hit.text`` work.
        overwrite:  delete an existing Indri index at ``path`` first. Refuses (``FileExistsError``)
                    unless the directory contains an Indri repository and no other files.
        append:     open an existing index and add documents to it.

    Call :meth:`close` (or use ``with``) to finish; an index is not searchable before that.
    Not thread-safe. Raises :class:`structquery.IndriError` on engine failures.
    """

    def __init__(self, path: Union[str, os.PathLike], stemmer: Optional[str] = "krovetz",
                 stopwords: Optional[Iterable[str]] = None, fields: Optional[Sequence[str]] = None,
                 memory: Union[int, str] = "1G", store_docs: bool = True, overwrite: bool = False,
                 append: bool = False):
        path = os.fspath(path)
        if stemmer is not None and stemmer not in STEMMERS:
            raise ValueError(f"stemmer must be one of {STEMMERS} or None, got {stemmer!r}")
        if overwrite and append:
            raise ValueError("overwrite and append are mutually exclusive")
        fields = [str(f).lower() for f in (fields or [])]   # Indri field names are lower-case
        for f in fields:
            if not _FIELD_NAME.match(f):
                raise ValueError(f"invalid field name {f!r}: use letters, digits, underscore; start with a letter")
        self.path = path
        self.fields = fields
        self._closed = False
        exists = os.path.exists(path)
        if exists and not append:
            if not overwrite:
                raise FileExistsError(f"{path!r} already exists; pass overwrite=True to replace it "
                                      "or append=True to add documents to it")
            if os.path.isdir(path) and (_looks_like_index(path) or not os.listdir(path)):
                shutil.rmtree(path)
            else:
                raise FileExistsError(f"refusing to overwrite {path!r}: it is not an Indri index, "
                                      "or it contains files that are not part of one")
        if append and not (exists and _looks_like_index(path)):
            raise FileNotFoundError(f"append=True but {path!r} is not an existing Indri index")
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, exist_ok=True)

        b = _structquery.Builder()
        b.set_memory(parse_memory(memory))
        if not append:
            if stemmer:
                b.set_stemmer(stemmer)
            if stopwords is not None:
                b.set_stopwords([str(w) for w in stopwords])
            if fields:
                b.set_indexed_fields(fields, list(FILE_CLASSES))
            # Same default as IndriBuildIndex: docno is retrievable in both directions
            # (internal id -> docno for results, docno -> internal id for Index.get).
            b.set_metadata_indexed_fields(["docno"], ["docno"])
            b.set_store_docs(bool(store_docs))
            b.create(path)
        else:
            b.open(path)
        self._b = b

    # -- adding documents ------------------------------------------------------------------
    def add(self, docid: str, doc: Union[str, Mapping[str, str]]) -> None:
        """Add one document.

        ``doc`` is either a string (indexed as plain text with Indri's ``txt`` file class) or a
        mapping ``{field_name: text}`` (each value is wrapped in ``<field_name>`` tags and parsed
        with Indri's ``xml`` file class; all values are searchable, and the keys listed in
        ``fields=`` are additionally searchable as fields). In mapping values the characters
        ``<`` and ``>`` are replaced by spaces so text cannot be mistaken for markup; nothing
        else is changed. :attr:`Document.fields` returns the mapping when the document is read back.

        ``docid`` must be non-empty; it is what ``Hit.docid`` returns. Uniqueness is your
        responsibility: like Indri itself, the builder does not check for duplicates. Adding the
        same ``docid`` twice stores two documents; both can appear in search results under that
        id, and :meth:`Index.get` returns the first one.
        """
        docid = str(docid)
        if not docid.strip():
            raise ValueError("docid must be a non-empty string")
        if isinstance(doc, str):
            self._b.add_string(doc, "txt", [("docno", docid)])
            return
        if not isinstance(doc, Mapping):
            raise TypeError(f"doc must be str or a mapping of field -> text, got {type(doc).__name__}")
        parts = []
        for name, value in doc.items():
            if not _FIELD_NAME.match(str(name)):
                raise ValueError(f"invalid field name {name!r}")
            if value is None:
                continue
            parts.append(f"<{name}>\n{str(value).translate(_MARKUP)}\n</{name}>")
        self._b.add_string("\n".join(parts) + "\n", "xml", [("docno", docid)])

    def add_many(self, docs: Iterable, progress: Optional[Callable[[int], None]] = None,
                 progress_every: int = 1000) -> int:
        """Add ``(docid, doc)`` pairs from any iterable. Returns how many were added."""
        n = 0
        for docid, doc in docs:
            self.add(docid, doc)
            n += 1
            if progress and n % progress_every == 0:
                progress(n)
        if progress:
            progress(n)
        return n

    def add_jsonl(self, file: Union[str, os.PathLike], id_key: str = "docid",
                  text_key: Union[str, Sequence[str]] = "text", limit: Optional[int] = None,
                  progress: Optional[Callable[[int], None]] = None, progress_every: int = 1000) -> int:
        """Add documents from a JSON-lines file, streaming (constant memory).

        Args:
            id_key:   JSON key holding the document id.
            text_key: one key -> its value is indexed as plain text; a list of keys -> a fielded
                      document with those keys (see :meth:`add`). With a list, keys that are
                      absent or null in a row are skipped; a row with none of them is an error.
            limit:    stop after this many documents (blank lines do not count).
            progress: callback ``progress(n_added)`` every ``progress_every`` documents.

        Returns the number of documents added. Raises ``KeyError`` naming the line if a key is missing.
        """
        keys = None if isinstance(text_key, str) else list(text_key)

        def rows():
            with open(file, "r", encoding="utf-8") as fh:
                emitted = 0
                for lineno, line in enumerate(fh, 1):
                    if limit is not None and emitted >= limit:
                        return
                    if not line.strip():
                        continue
                    obj = json.loads(line)
                    try:
                        if keys is None:
                            yield obj[id_key], str(obj[text_key])
                        else:
                            doc = {k: obj[k] for k in keys if obj.get(k) is not None}
                            if not doc:
                                raise KeyError(" / ".join(keys))
                            yield obj[id_key], doc
                        emitted += 1
                    except KeyError as e:
                        raise KeyError(f"{file}:{lineno}: missing key {e}; available keys: {sorted(obj)}") from None

        return self.add_many(rows(), progress, progress_every)

    def add_files(self, paths: Union[str, os.PathLike, Iterable[Union[str, os.PathLike]]],
                  file_class: str = "trectext") -> None:
        """Index files in a format Indri parses natively (see :data:`FILE_CLASSES`).

        For ``trectext``/``trecweb`` the document id comes from each ``<DOCNO>``.
        """
        if file_class not in FILE_CLASSES:
            raise ValueError(f"file_class must be one of {FILE_CLASSES}, got {file_class!r}")
        if isinstance(paths, (str, os.PathLike)):
            paths = [paths]
        for p in paths:
            p = os.fspath(p)
            if not os.path.isfile(p):
                raise FileNotFoundError(p)
            self._b.add_file(p, file_class)

    # -- lifecycle -------------------------------------------------------------------------
    @property
    def count(self) -> int:
        """Documents added so far."""
        return self._b.documents_indexed()

    def close(self) -> None:
        """Flush and finish the index. Required before searching. Safe to call twice."""
        if not self._closed:
            self._closed = True
            self._b.close()

    def __enter__(self) -> "IndexBuilder":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
