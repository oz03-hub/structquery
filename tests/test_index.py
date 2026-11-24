"""Index: documents, statistics, search options, rules, lifecycle."""
from __future__ import annotations

import os

import pytest

import structquery
from conftest import CORPUS, DOCIDS, N_DOCS, N_TOKENS, N_UNIQUE, docids


# -- opening -------------------------------------------------------------------------------

def test_open_missing_dir(short_tmp):
    with pytest.raises(FileNotFoundError):
        structquery.Index(os.path.join(short_tmp, "nope"))


def test_open_non_index_dir(short_tmp):
    with pytest.raises(structquery.IndriError):
        structquery.Index(short_tmp)


def test_open_accepts_pathlike(index_path):
    import pathlib
    with structquery.Index(pathlib.Path(index_path)) as idx:
        assert len(idx) == N_DOCS


def test_repr(ix, index_path):
    assert repr(ix) == f"Index({index_path!r}, rule={structquery.DEFAULT_RULE!r})"


# -- documents -----------------------------------------------------------------------------

def test_len_and_contains(ix):
    assert len(ix) == N_DOCS
    for d in DOCIDS:
        assert d in ix
    assert "nope" not in ix
    assert "doc" not in ix and "ten" not in ix
    assert "D1" not in ix                      # docids are case-sensitive


def test_get_plain_text(ix):
    doc = ix.get("d1")
    assert isinstance(doc, structquery.Document)
    assert doc.docid == "d1"
    assert doc.text == "the white house is in washington"
    assert doc.raw == doc.text
    assert doc.metadata == {"docno": "d1"}


def test_get_docid_with_space(ix):
    doc = ix.get("doc ten")
    assert doc.docid == "doc ten"
    assert doc.text == "apple banana cherry"


def test_get_non_ascii(ix):
    assert ix.get("d9").text == "café naïve résumé über straße"


def test_get_fielded_doc_contains_field_text(ix):
    doc = ix.get("d7")
    assert "lemur project overview" in doc.text
    assert "indri search engine toolkit" in doc.text
    assert "<title>" in doc.text


def test_get_many_preserves_order(ix):
    want = ["d12", "doc ten", "d1", "d9"]
    got = ix.get_many(want)
    assert [d.docid for d in got] == want


def test_get_missing_raises_keyerror(ix):
    with pytest.raises(KeyError) as ei:
        ix.get("nope")
    assert ei.value.args[0] == "docid not in index: 'nope'"


def test_get_many_with_one_missing_raises(ix):
    with pytest.raises(KeyError) as ei:
        ix.get_many(["d1", "missing", "d2"])
    assert "'missing'" in ei.value.args[0]


# -- statistics ----------------------------------------------------------------------------

def test_stats(ix, index_path):
    st = ix.stats()
    assert isinstance(st, structquery.IndexStats)
    assert st.doc_count == N_DOCS
    assert st.term_count == N_TOKENS
    assert st.unique_terms == N_UNIQUE
    assert st.fields == ["title"]
    assert st.avg_doc_length == pytest.approx(N_TOKENS / N_DOCS)
    assert st.path == index_path


@pytest.mark.parametrize("term,count,df", [
    ("white", 4, 4),          # d1 d2 d3 d12
    ("house", 3, 3),
    ("houses", 3, 3),         # stemmed like a query term
    ("HOUSE", 3, 3),
    ("the", 4, 4),            # d1 d2 d3 + d8 body
    ("zebra", 3, 1),
    ("automobile", 2, 1),
    ("lemur", 2, 2),
    ("parks", 1, 1),
    ("park", 1, 1),
    ("café", 1, 1),
    ("xylophone", 0, 0),
])
def test_term_count_and_doc_freq(ix, term, count, df):
    assert ix.term_count(term) == count
    assert ix.doc_freq(term) == df


@pytest.mark.parametrize("term,count", [("lemur", 1), ("search", 1), ("basics", 1), ("indri", 0), ("white", 0)])
def test_term_count_in_field(ix, term, count):
    assert ix.term_count(term, field="title") == count


def test_term_count_nostem(ix_nostem):
    assert ix_nostem.term_count("houses") == 0
    assert ix_nostem.term_count("house") == 3
    assert ix_nostem.term_count("parks") == 1


@pytest.mark.parametrize("expr,count,df", [
    ("#1(white house)", 1, 1),
    ("#1(house white)", 1, 1),
    ("#uw2(white house)", 2, 2),
    ("#uw7(white house)", 3, 3),
    ("#od(white house)", 2, 2),
    ("#syn(car automobile)", 3, 2),
    ("#band(white barn)", 1, 1),
    ("white", 4, 4),
    ("zebra", 3, 1),
])
def test_expression_count_and_doc_freq(ix, expr, count, df):
    assert ix.expression_count(expr) == count
    assert ix.expression_doc_freq(expr) == df


def test_field_expression_count(ix):
    assert ix.expression_count("lemur.title") == 1


@pytest.mark.xfail(strict=True, reason=(
    "expression_doc_freq('lemur.title') returns 2 although only d7 has 'lemur' in its title "
    "(search returns only d7 and expression_count is 1). Comes from Indri's "
    "QueryEnvironment::documentExpressionCount; contradicts the wrapper docstring"))
def test_field_expression_doc_freq(ix):
    assert ix.expression_doc_freq("lemur.title") == 1


def test_expression_count_rejects_belief_operator(ix):
    with pytest.raises(structquery.IndriError):
        ix.expression_count("#combine(white house)")


def test_expression_count_validates_syntax(ix):
    with pytest.raises(structquery.QuerySyntaxError):
        ix.expression_count("#1(white house")
    with pytest.raises(structquery.QuerySyntaxError):
        ix.expression_doc_freq("#1(white house")


@pytest.mark.parametrize("docid,length", [
    ("d1", 6), ("d2", 7), ("d5", 3), ("d7", 7), ("d8", 8), ("d9", 5), ("doc ten", 3), ("d12", 2),
])
def test_doc_length(ix, docid, length):
    assert ix.doc_length(docid) == length


def test_doc_lengths_sum_to_term_count(ix):
    assert sum(ix.doc_length(d) for d in DOCIDS) == N_TOKENS


def test_doc_length_missing(ix):
    with pytest.raises(KeyError):
        ix.doc_length("nope")


@pytest.mark.parametrize("term,stem", [("houses", "house"), ("parks", "park"), ("played", "play"),
                                       ("Quickly", "quick"), ("CAFÉ", "café"), ("white", "white")])
def test_stem(ix, term, stem):
    assert ix.stem(term) == stem


# -- search results ------------------------------------------------------------------------

def test_hits_sorted_and_ranked(ix):
    for q in ["#combine(white house)", "#combine(the lemur toolkit)", "white", "#syn(car automobile)"]:
        hits = ix.search(q, k=20)
        assert hits
        assert [h.rank for h in hits] == list(range(1, len(hits) + 1))
        scores = [h.score for h in hits]
        assert scores == sorted(scores, reverse=True)
        assert all(s < 0 for s in scores)     # log-probabilities
        assert len({h.docid for h in hits}) == len(hits)


def test_hit_fields_default(ix):
    h = ix.search("banana")[0]
    assert isinstance(h, structquery.Hit)
    assert h.text is None and h.snippet is None
    assert h.internal_id > 0


def test_k_limits_results(ix):
    assert len(ix.search("white", k=2)) == 2
    assert len(ix.search("white", k=1)) == 1
    assert ix.search("white", k=0) == []
    assert ix.search("white", k=-5) == []
    assert ix.search("white", k=2) == ix.search("white", k=20)[:2]


def test_search_docs_and_snippets(ix):
    plain = ix.search("#combine(white house)")
    hits = ix.search("#combine(white house)", docs=True, snippets=True)
    assert [(h.docid, h.score) for h in hits] == [(h.docid, h.score) for h in plain]
    texts = dict(CORPUS)
    for h in hits:
        assert h.text == texts[h.docid]
        assert isinstance(h.snippet, str) and h.snippet
        assert "white" in h.snippet.lower()


def test_search_docs_without_snippets(ix):
    hits = ix.search("banana", docs=True)
    assert hits[0].text == "apple banana cherry"
    assert hits[0].snippet is None


def test_search_snippets_without_docs(ix):
    hits = ix.search("banana", snippets=True)
    assert hits[0].text is None
    assert "banana" in hits[0].snippet.lower()


def test_search_docs_non_ascii(ix):
    h = ix.search("über", docs=True, snippets=True)[0]
    assert h.text == "café naïve résumé über straße"
    assert "über" in h.snippet.lower()


def test_search_docs_extent_query(ix):
    h = ix.search("#combine[title](lemur)", docs=True, snippets=True)[0]
    assert h.docid == "d7"
    assert "lemur" in h.text


# -- retrieval rules -----------------------------------------------------------------------

def test_default_rule_equals_explicit_dirichlet(index_path, ix):
    with structquery.Index(index_path, rule=structquery.DEFAULT_RULE) as idx:
        assert idx.search("#combine(white house)") == ix.search("#combine(white house)")


def test_jm_rule_gives_different_scores(index_path, ix):
    q = "#combine(white house)"
    with structquery.Index(index_path, rule="method:jm,lambda:0.4") as jm:
        a = jm.search(q)
    b = ix.search(q)
    assert {h.docid for h in a} == {h.docid for h in b}
    assert a[0].docid == "d1"
    da, db = {h.docid: h.score for h in a}, {h.docid: h.score for h in b}
    assert all(da[d] != pytest.approx(db[d]) for d in da)


def test_dirichlet_mu_changes_scores(index_path, ix):
    with structquery.Index(index_path, rule="method:dirichlet,mu:10") as small:
        s = small.search("white")[0].score
    assert s != pytest.approx(ix.search("white")[0].score)


def test_rule_list(index_path):
    with structquery.Index(index_path, rule=["method:dirichlet,mu:100"]) as a, \
            structquery.Index(index_path, rule="method:dirichlet,mu:100") as b:
        assert a.search("white") == b.search("white")


def test_memory_option(index_path):
    with structquery.Index(index_path, memory="64M") as idx:
        assert len(idx) == N_DOCS


# -- lifecycle -----------------------------------------------------------------------------

def test_close_twice(index_path):
    idx = structquery.Index(index_path)
    idx.close()
    idx.close()


def test_context_manager_closes(index_path):
    with structquery.Index(index_path) as idx:
        assert len(idx) == N_DOCS
    with pytest.raises(RuntimeError):
        idx.search("white")


@pytest.mark.parametrize("op", [
    lambda i: i.search("white"),
    lambda i: i.search("white", docs=True, snippets=True),
    lambda i: len(i),
    lambda i: "d1" in i,
    lambda i: i.get("d1"),
    lambda i: i.get_many(["d1"]),
    lambda i: i.stats(),
    lambda i: i.term_count("white"),
    lambda i: i.term_count("lemur", field="title"),
    lambda i: i.doc_freq("white"),
    lambda i: i.expression_count("#1(white house)"),
    lambda i: i.expression_doc_freq("#1(white house)"),
    lambda i: i.doc_length("d1"),
    lambda i: i.stem("houses"),
    lambda i: i.fields,
], ids=["search", "search_docs", "len", "contains", "get", "get_many", "stats", "term_count",
        "term_field_count", "doc_freq", "expression_count", "expression_doc_freq", "doc_length",
        "stem", "fields"])
def test_closed_index_raises(index_path, op):
    idx = structquery.Index(index_path)
    idx.close()
    with pytest.raises(RuntimeError, match="closed"):
        op(idx)


def test_validation_works_on_closed_index(index_path):
    idx = structquery.Index(index_path)
    idx.close()
    assert idx.is_valid("#combine(a)")


def test_many_indexes_open_at_once(index_path, nostem_path):
    handles = [structquery.Index(p) for p in (index_path, nostem_path, index_path)]
    assert [len(h) for h in handles] == [N_DOCS] * 3
    for h in handles:
        h.close()


def test_closing_one_handle_leaves_others_usable(index_path, ix):
    other = structquery.Index(index_path)
    other.close()
    assert docids(ix.search("banana")) == ["doc ten"]


# -- Document.fields ------------------------------------------------------------------------

def test_document_fields_roundtrip(short_tmp):
    import os
    p = os.path.join(short_tmp, "fx")
    with structquery.IndexBuilder(p, fields=["title"]) as b:
        b.add("f1", {"title": "White House", "body": "a < b and c > d\nsecond line"})
        b.add("p1", "plain text with <b>markup</b> inside")
        b.add("p2", "<title>\nlooks tagged but has trailing text\n</title>\nextra")
    with structquery.Index(p) as ix:
        d = ix.get("f1")
        assert d.fields == {"title": "White House", "body": "a   b and c   d\nsecond line"}
        assert d.text.startswith("<title>\nWhite House\n</title>")      # Indri's stored text, untouched
        assert ix.get("p1").fields == {}
        assert ix.get("p1").text == "plain text with <b>markup</b> inside"
        assert ix.get("p2").fields == {}


def test_cli_usage_error_exits_1():
    from structquery.cli import main
    import pytest as _pt
    with _pt.raises(SystemExit) as ei:
        main(["search", "--no-such-flag"])
    assert ei.value.code == 1
