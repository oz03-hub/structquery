"""structquery: Python API for the Indri search engine (Lemur Project).

Build an index::

    import structquery
    with structquery.IndexBuilder("my_index") as b:
        b.add("d1", "Indri is a search engine from the Lemur Project.")

Search it with the Indri query language::

    idx = structquery.Index("my_index")
    hits = idx.search("#combine(search #1(lemur project))", k=10)
    hits[0].docid, hits[0].score

Check LLM-written queries before running them::

    structquery.is_valid("#combine(a b")        # False
    structquery.validate("#combine(a b")        # raises structquery.QuerySyntaxError

See docs/ (quickstart.md, query-language.md, api.md) and AGENTS.md.
"""
from ._structquery import INDRI_VERSION, IndriError, QuerySyntaxError
from .batch import Run, batch_search, bag_of_words, extract_query
from .index import DEFAULT_RULE, Document, Hit, Index, IndexStats, escape, is_valid, validate
from .indexer import FILE_CLASSES, STEMMERS, IndexBuilder

__version__ = "0.1.0"

__all__ = [
    "Index", "IndexBuilder", "Hit", "Document", "IndexStats", "Run",
    "batch_search", "validate", "is_valid", "escape", "bag_of_words", "extract_query",
    "IndriError", "QuerySyntaxError",
    "DEFAULT_RULE", "FILE_CLASSES", "STEMMERS", "INDRI_VERSION", "__version__",
]
