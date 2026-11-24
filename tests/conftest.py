"""Shared fixtures for the structquery test suite.

The corpus below is small enough that every count used in the tests can be checked by hand.
Token counts (Indri lower-cases; dict documents are wrapped in <field> tags which are NOT tokens):

    d1       the white house is in washington              6 tokens
    d2       house white paint for the old barn            7
    d3       white cat sat near the big house              7
    d4       car repair shop downtown                      4
    d5       automobile automobile dealer                  3
    d6       children played in sunny parks                5
    d7       title: lemur project overview                 3 + 4 = 7
             body:  indri search engine toolkit
    d8       title: search engine basics                   3 + 5 = 8
             body:  the lemur toolkit includes indri
    d9       café naïve résumé über straße                 5
    doc ten  apple banana cherry                           3   (docid contains a space)
    d11      zebra zebra zebra giraffe                     4
    d12      white snow                                    2
                                                   total  61 tokens, 12 documents

Distinct terms: 44 (no two distinct surface words above collapse to the same Krovetz stem).
"""
from __future__ import annotations

import os

import pytest

import structquery

CORPUS = [
    ("d1", "the white house is in washington"),
    ("d2", "house white paint for the old barn"),
    ("d3", "white cat sat near the big house"),
    ("d4", "car repair shop downtown"),
    ("d5", "automobile automobile dealer"),
    ("d6", "children played in sunny parks"),
    ("d7", {"title": "lemur project overview", "body": "indri search engine toolkit"}),
    ("d8", {"title": "search engine basics", "body": "the lemur toolkit includes indri"}),
    ("d9", "café naïve résumé über straße"),
    ("doc ten", "apple banana cherry"),
    ("d11", "zebra zebra zebra giraffe"),
    ("d12", "white snow"),
]
DOCIDS = [d for d, _ in CORPUS]
N_DOCS = 12
N_TOKENS = 61
N_UNIQUE = 44

# Indri's keyfile layer rejects file names of 128+ characters ("file name too long") and the
# repository files sit a few levels below the index root, so keep index roots short.
MAX_ROOT_LEN = 80


def _build(path: str, **kwargs) -> str:
    with structquery.IndexBuilder(path, **kwargs) as b:
        for docid, doc in CORPUS:
            b.add(docid, doc)
    return path


@pytest.fixture(scope="session")
def index_root(tmp_path_factory) -> str:
    root = str(tmp_path_factory.mktemp("ix"))
    assert len(root) < MAX_ROOT_LEN, (
        f"temporary directory {root!r} is too long for Indri's 128-character file-name limit; "
        "run pytest with a short --basetemp")
    return root


@pytest.fixture(scope="session")
def index_path(index_root) -> str:
    """Krovetz-stemmed index of CORPUS with ``title`` indexed as a field."""
    return _build(os.path.join(index_root, "main"), fields=["title"])


@pytest.fixture(scope="session")
def nostem_path(index_root) -> str:
    """Same CORPUS indexed with ``stemmer=None``."""
    return _build(os.path.join(index_root, "nostem"), stemmer=None, fields=["title"])


@pytest.fixture(scope="session")
def ix(index_path):
    idx = structquery.Index(index_path)
    yield idx
    idx.close()


@pytest.fixture(scope="session")
def ix_nostem(nostem_path):
    idx = structquery.Index(nostem_path)
    yield idx
    idx.close()


@pytest.fixture
def short_tmp(tmp_path) -> str:
    """Function-scoped temp dir, checked to be short enough for Indri."""
    p = str(tmp_path)
    assert len(p) < MAX_ROOT_LEN, f"temporary directory {p!r} is too long for Indri"
    return p


def docids(hits):
    return [h.docid for h in hits]
