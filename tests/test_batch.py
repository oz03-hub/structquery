"""batch_search and Run."""
from __future__ import annotations

import os

import pytest

import structquery
from conftest import docids

QUERIES = {
    "q1": "#combine(white house)",
    "q2": "#combine(zebra",            # syntax error, repairable by bag_of_words
    "q3": "#1(white house)",
    "q4": "xylophone",                 # valid, no hits
    "q5": "#prior(nosuchprior)",       # valid syntax, engine error
}


def _summary(run):
    return {qid: [(h.docid, h.rank, h.score) for h in hits] for qid, hits in run.results.items()}


def test_batch_skip(index_path, ix):
    run = structquery.batch_search(index_path, QUERIES, k=10)
    assert isinstance(run, structquery.Run)
    assert run.queries == QUERIES
    assert set(run.results) == {"q1", "q3", "q4"}
    assert set(run.errors) == {"q2", "q5"}
    assert run.errors["q2"].startswith("QuerySyntaxError:")
    assert run.errors["q5"].startswith("IndriError:")
    assert run.fallbacks == {}
    assert run.results["q4"] == []
    assert docids(run.results["q3"]) == ["d1"]
    # identical to searching one at a time
    assert run.results["q1"] == ix.search(QUERIES["q1"], k=10)


def test_batch_k(index_path):
    run = structquery.batch_search(index_path, {"q": "white"}, k=2)
    assert len(run.results["q"]) == 2


def test_batch_accepts_list_of_pairs(index_path):
    run = structquery.batch_search(index_path, [("a", "banana"), (7, "zebra")], k=5)
    assert docids(run.results["a"]) == ["doc ten"]
    assert docids(run.results["7"]) == ["d11"]       # qids are str()-ed


def test_batch_two_workers_matches_one(index_path):
    many = {f"q{i}": q for i, q in enumerate(
        ["white", "#1(white house)", "#combine(lemur)", "banana", "#syn(car automobile)",
         "#combine(oops", "zebra", "#uw7(white house)", "café", "#band(white barn)"])}
    one = structquery.batch_search(index_path, many, k=5, workers=1)
    two = structquery.batch_search(index_path, many, k=5, workers=2)
    assert _summary(one) == _summary(two)
    assert one.errors == two.errors and set(two.errors) == {"q5"}
    assert list(two.results) == [q for q in many if q != "q5"]     # input order preserved


def test_batch_fallback(index_path, ix):
    run = structquery.batch_search(index_path, QUERIES, k=10, on_error="fallback")
    # engine errors are retried too: "#prior(nosuchprior)" -> "#combine(nosuchprior)" (no hits)
    assert run.fallbacks == {"q2": "#combine(zebra)", "q5": "#combine(nosuchprior)"}
    assert set(run.errors) == {"q2", "q5"}
    assert set(run.results) == {"q1", "q2", "q3", "q4", "q5"}
    assert docids(run.results["q2"]) == ["d11"]
    assert run.results["q5"] == []
    assert run.results["q1"] == ix.search(QUERIES["q1"], k=10)


def test_batch_fallback_with_no_words(index_path):
    run = structquery.batch_search(index_path, {"q": "#combine(!!"}, on_error="fallback")
    assert "q" not in run.results
    assert "fallback failed" in run.errors["q"]


def test_batch_raise(index_path):
    with pytest.raises(structquery.QuerySyntaxError, match="q2"):
        structquery.batch_search(index_path, {"q1": "white", "q2": "#combine(a"}, on_error="raise")


def test_batch_raise_engine_error(index_path):
    with pytest.raises(structquery.IndriError) as ei:
        structquery.batch_search(index_path, {"q5": "#prior(nosuchprior)"}, on_error="raise")
    assert not isinstance(ei.value, structquery.QuerySyntaxError)


def test_batch_raise_two_workers(index_path):
    with pytest.raises(structquery.QuerySyntaxError):
        structquery.batch_search(index_path, {"q1": "white", "q2": "#combine(a"}, workers=2, on_error="raise")


def test_batch_bad_on_error(index_path):
    with pytest.raises(ValueError):
        structquery.batch_search(index_path, QUERIES, on_error="ignore")


def test_batch_with_index_object(ix):
    run = structquery.batch_search(ix, {"q": "banana"})
    assert docids(run.results["q"]) == ["doc ten"]
    # the caller's Index must remain open and usable
    assert docids(ix.search("banana")) == ["doc ten"]


def test_batch_with_index_object_rejects_workers(ix):
    with pytest.raises(ValueError):
        structquery.batch_search(ix, {"q": "banana"}, workers=2)


def test_batch_rule(index_path):
    d = structquery.batch_search(index_path, {"q": "white"})
    j = structquery.batch_search(index_path, {"q": "white"}, rule="method:jm,lambda:0.4")
    assert d.results["q"][0].score != pytest.approx(j.results["q"][0].score)


def test_batch_docs(index_path):
    run = structquery.batch_search(index_path, {"q": "banana"}, docs=True)
    assert run.results["q"][0].text == "apple banana cherry"


def test_batch_empty(index_path):
    run = structquery.batch_search(index_path, {})
    assert run.results == {} and run.errors == {}


# -- Run output ----------------------------------------------------------------------------

def test_to_trec(index_path, short_tmp):
    run = structquery.batch_search(index_path, {"q1": "#combine(white house)", "q2": "lemur", "bad": "#("})
    out = os.path.join(short_tmp, "run.trec")
    n = run.to_trec(out, tag="mytag")
    lines = open(out, encoding="utf-8").read().splitlines()
    assert n == len(lines) == 4 + 2
    assert not os.path.exists(out + ".tmp")
    for line in lines:
        cols = line.split()
        assert len(cols) == 6
        qid, q0, docid, rank, score, tag = cols
        assert q0 == "Q0" and tag == "mytag"
        assert int(rank) >= 1
        float(score)
    assert lines[0].split()[:4] == ["q1", "Q0", "d1", "1"]
    assert [l.split()[0] for l in lines] == ["q1"] * 4 + ["q2"] * 2


def test_to_trec_docid_with_space(index_path, short_tmp):
    run = structquery.batch_search(index_path, {"q": "banana"})
    out = os.path.join(short_tmp, "run.trec")
    try:
        run.to_trec(out)
    except ValueError:
        return
    for line in open(out, encoding="utf-8"):
        assert len(line.split()) == 6


def test_to_dict(index_path):
    run = structquery.batch_search(index_path, {"q1": "#combine(white house)", "q2": "banana", "bad": "#("})
    d = run.to_dict()
    assert set(d) == {"q1", "q2"}
    assert set(d["q1"]) == {"d1", "d2", "d3", "d12"}
    assert d["q2"] == {"doc ten": pytest.approx(run.results["q2"][0].score)}
    assert all(isinstance(v, float) for v in d["q1"].values())
