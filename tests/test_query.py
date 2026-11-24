"""Indri query operators against the fixture corpus (see conftest.py for the documents).

Scores under the default rule (Dirichlet, mu=2500) differ only slightly on such a tiny
collection, so tests assert exact ranking only where the documents make the order
unambiguous, and otherwise assert the *set* of matching docids.
"""
from __future__ import annotations

import pytest

import structquery
from conftest import docids


def ids(ix, q, k=20):
    return docids(ix.search(q, k=k))


def idset(ix, q, k=20):
    return set(ids(ix, q, k))


WHITE_DOCS = {"d1", "d2", "d3", "d12"}
HOUSE_DOCS = {"d1", "d2", "d3"}


# -- belief operators ----------------------------------------------------------------------

def test_bare_words_are_combine(ix):
    assert ix.search("white house") == ix.search("#combine(white house)")


def test_combine_matches_any_term(ix):
    assert idset(ix, "#combine(white house)") == WHITE_DOCS


def test_combine_ranks_doc_with_all_terms_first(ix):
    # only d2 has both "white" and "barn"
    hits = ids(ix, "#combine(white barn)")
    assert hits[0] == "d2"
    assert set(hits) == WHITE_DOCS


def test_combine_prefers_shorter_doc_with_same_tf(ix):
    # d1 (6 tokens), d2/d3 (7 tokens) all contain white+house once; d12 lacks house
    hits = ix.search("#combine(white house)")
    assert hits[0].docid == "d1"
    assert hits[-1].docid == "d12"
    assert {h.docid for h in hits[1:3]} == {"d2", "d3"}
    assert hits[1].score == pytest.approx(hits[2].score)   # d2/d3 tie: order not asserted


def test_weight_changes_ranking(ix):
    assert ids(ix, "#weight(0.9 zebra 0.1 apple)") == ["d11", "doc ten"]
    assert ids(ix, "#weight(0.1 zebra 0.9 apple)") == ["doc ten", "d11"]


def test_max_uses_best_child(ix):
    # #combine averages beliefs: "doc ten" (banana, 3 tokens) edges out d11.
    # #max takes the best single belief: d11 (zebra x3) wins.
    assert ids(ix, "#combine(banana zebra)") == ["doc ten", "d11"]
    assert ids(ix, "#max(banana zebra)") == ["d11", "doc ten"]


def test_or_matches_any(ix):
    assert idset(ix, "#or(zebra apple)") == {"d11", "doc ten"}


def test_not_penalises_docs_with_term(ix):
    hits = ids(ix, "#combine(white #not(barn))")
    assert set(hits) == WHITE_DOCS
    assert hits[-1] == "d2"   # the only white doc containing "barn"


def test_not_alone_selects_no_candidates(ix):
    # Indri only scores documents that contain a positive query term
    assert ix.search("#not(barn)") == []


# -- proximity / extent operators ----------------------------------------------------------

def test_exact_phrase_hash1(ix):
    assert ids(ix, "#1(white house)") == ["d1"]
    assert ids(ix, "#1(house white)") == ["d2"]


@pytest.mark.parametrize("q", ["#1(white house)", "#od1(white house)"])
def test_od1_is_hash1(ix, q):
    assert ids(ix, q) == ["d1"]


def test_ordered_window(ix):
    # d3: "white cat sat near the big house" -> 5 words between white and house
    assert ids(ix, "#od3(white house)") == ["d1"]
    assert ids(ix, "#od5(white house)") == ["d1"]
    assert idset(ix, "#od6(white house)") == {"d1", "d3"}
    assert idset(ix, "#od(white house)") == {"d1", "d3"}       # unlimited ordered


def test_unordered_window(ix):
    # d2 has "house white" (reversed, adjacent) -> matches unordered window 2
    assert idset(ix, "#uw2(white house)") == {"d1", "d2"}
    assert idset(ix, "#uw6(white house)") == {"d1", "d2"}
    assert idset(ix, "#uw7(white house)") == HOUSE_DOCS
    assert idset(ix, "#uw(white house)") == HOUSE_DOCS          # unlimited unordered


def test_proximity_inside_combine(ix):
    hits = ids(ix, "#combine(#1(white house) cat)")
    assert set(hits) == {"d1", "d3"}


def test_syn_merges_terms(ix):
    assert ids(ix, "#combine(car)") == ["d4"]
    # as one term: d5 (automobile x2 in 3 tokens) beats d4 (car x1 in 4 tokens)
    assert ids(ix, "#syn(car automobile)") == ["d5", "d4"]


def test_wsyn_weights_matter(ix):
    assert ids(ix, "#wsyn(1.0 car 0.1 automobile)") == ["d4", "d5"]
    assert ids(ix, "#wsyn(0.1 car 1.0 automobile)") == ["d5", "d4"]


def test_band_requires_all_terms(ix):
    assert ids(ix, "#band(white barn)") == ["d2"]
    assert idset(ix, "#band(white house)") == HOUSE_DOCS


@pytest.mark.parametrize("op", ["#filreq", "#scoreif"])
def test_filreq(ix, op):
    assert ids(ix, f"{op}(barn #combine(white))") == ["d2"]


@pytest.mark.parametrize("op", ["#filrej", "#scoreifnot"])
def test_filrej(ix, op):
    assert idset(ix, f"{op}(barn #combine(white))") == {"d1", "d3", "d12"}


def test_filreq_keeps_inner_scores(ix):
    full = {h.docid: h.score for h in ix.search("#combine(white)")}
    filt = ix.search("#filreq(barn #combine(white))")
    assert filt[0].score == pytest.approx(full["d2"])


# -- fields --------------------------------------------------------------------------------

def test_fields_listed(ix):
    assert ix.fields == ["title"]


def test_field_restricted_term(ix):
    # "lemur" is in d7's title and d8's body
    assert idset(ix, "#combine(lemur)") == {"d7", "d8"}
    assert ids(ix, "lemur.title") == ["d7"]
    assert ids(ix, "#combine(lemur.title)") == ["d7"]
    assert ids(ix, "#combine(lemur.(title))") == ["d7"]
    # "search" is in d8's title and d7's body
    assert ids(ix, "search.title") == ["d8"]
    # "indri" never appears in a title
    assert ix.search("indri.title") == []


def test_extent_retrieval(ix):
    assert ids(ix, "#combine[title](lemur)") == ["d7"]
    assert ids(ix, "#combine[title](search)") == ["d8"]


def test_any_field(ix):
    assert idset(ix, "#combine(#any:title)") == {"d7", "d8"}


def test_field_text_is_searchable_without_restriction(ix):
    assert idset(ix, "#combine(toolkit)") == {"d7", "d8"}


@pytest.mark.parametrize("q", ["white.nofield", "#combine[nofield](white)"])
def test_unknown_field_returns_nothing(ix, q):
    assert ix.search(q) == []          # documented: Indri does not treat this as an error


def test_unknown_prior_raises_indri_error_not_syntax_error(ix):
    with pytest.raises(structquery.IndriError) as ei:
        ix.search("#prior(nosuchprior)")
    assert not isinstance(ei.value, structquery.QuerySyntaxError)


# -- terms: stemming, case, unicode --------------------------------------------------------

def test_stemming_on(ix):
    assert ids(ix, "#combine(park)") == ["d6"]           # indexed as "parks"
    assert ids(ix, "#combine(parks)") == ["d6"]
    assert idset(ix, "#combine(houses)") == HOUSE_DOCS
    assert ix.stem("parks") == "park"
    assert ix.stem("houses") == "house"


def test_stemming_off(ix_nostem):
    assert ix_nostem.search("#combine(park)") == []
    assert docids(ix_nostem.search("#combine(parks)")) == ["d6"]
    assert ix_nostem.search("#combine(houses)") == []
    assert ix_nostem.stem("parks") == "parks"


def test_krovetz_is_dictionary_based(ix):
    # "dogs" and "running" are Krovetz dictionary headwords, so they are left alone
    assert ix.stem("dogs") == "dogs"
    assert ix.stem("quickly") == "quick"


def test_query_terms_are_case_folded(ix):
    assert ix.search("WHITE HOUSE") == ix.search("white house")


@pytest.mark.parametrize("q", ["#combine(über)", "#combine(café)", "#combine(CAFÉ)", "straße", "naïve"])
def test_non_ascii_terms(ix, q):
    assert ids(ix, q) == ["d9"]


def test_docid_with_space_is_returned(ix):
    assert ids(ix, "banana") == ["doc ten"]


def test_docid_is_not_indexed_text(ix):
    assert ix.search("#combine(ten)") == []


def test_out_of_vocabulary_term(ix):
    assert ix.search("#combine(xylophone)") == []


# -- syntax errors -------------------------------------------------------------------------

def test_exception_hierarchy():
    assert issubclass(structquery.QuerySyntaxError, structquery.IndriError)
    assert issubclass(structquery.IndriError, RuntimeError)
    from structquery import errors
    assert errors.QuerySyntaxError is structquery.QuerySyntaxError
    assert errors.IndriError is structquery.IndriError


BAD_QUERIES = [
    "#combine(a b",
    "#combine()",
    "#combine(a b))",
    "#1(a",
    "a)",
    "#foo(a)",
    "#and(a b)",
    "#weight(a b)",
    "#weight(0.5 a 0.5)",
    "#wsyn(a b)",
    "#filreq(a)",
    "#not(a b)",
    "#max()",
    '"white house"',
    "U.S.",
    "what's",
    "a,b",
    "@#$",
    "",
    "   ",
]


@pytest.mark.parametrize("q", BAD_QUERIES)
def test_invalid_query_raises_syntax_error_in_search(ix, q):
    with pytest.raises(structquery.QuerySyntaxError) as ei:
        ix.search(q)
    assert "Couldn't understand this query" in str(ei.value)
    assert isinstance(ei.value, structquery.IndriError)
    assert isinstance(ei.value, RuntimeError)


@pytest.mark.parametrize("q", BAD_QUERIES)
def test_validate_and_is_valid_reject(q):
    assert structquery.is_valid(q) is False
    with pytest.raises(structquery.QuerySyntaxError):
        structquery.validate(q)


GOOD_QUERIES = [
    "white", "white house", "#combine(white house)", "#weight(0.3 a 0.7 b)", "#1(a b)", "#od4(a b)",
    "#uw8(a b)", "#uw(a b)", "#syn(a b)", "#wsyn(1 a 0.5 b)", "#band(a b)", "#max(a b)", "#or(a b)",
    "#filreq(a #combine(b))", "#filrej(a #combine(b))", "#combine(a #not(b))", "a.title",
    "#combine[title](a b)", "#combine(#any:title)", "#combine(über straße)",
]


@pytest.mark.parametrize("q", GOOD_QUERIES)
def test_validate_and_is_valid_accept(q):
    assert structquery.validate(q) is None
    assert structquery.is_valid(q) is True


def test_index_validate_methods(ix):
    assert ix.is_valid("#combine(a)") and not ix.is_valid("#combine(a")
    with pytest.raises(structquery.QuerySyntaxError):
        ix.validate("#combine(a")


def test_validate_non_str():
    with pytest.raises(TypeError):
        structquery.validate(123)
    with pytest.raises(TypeError):
        structquery.validate(None)


def test_syntax_error_message_is_parser_message():
    with pytest.raises(structquery.QuerySyntaxError, match="C_PAREN"):
        structquery.validate("#combine(a b")


# -- helpers for untrusted / LLM text ------------------------------------------------------

def test_escape_doc_example():
    assert structquery.escape("What's the U.S. GDP (2020)?") == "Whats the US GDP 2020"


def test_escape_keeps_unicode_letters_and_drops_underscore():
    assert structquery.escape("Café über_straße!") == "Café über straße"


@pytest.mark.parametrize("text", [
    "What's the U.S. GDP (2020)?", '#combine(a b', "a.title", '"quoted" text', "x)y(z", "C++ & C#",
    "e-mail: foo@bar.com", "100% #1 [title]", "tab\tand\nnewline", "naïve café",
])
def test_escaped_text_is_always_a_valid_query(text):
    assert structquery.is_valid(f"#combine({structquery.escape(text)})")


def test_escaped_query_runs(ix):
    hits = ix.search(f"#combine({structquery.escape('The White-House?')})")
    assert hits and hits[0].docid == "d1"


def test_bag_of_words_repairs_broken_query():
    assert structquery.bag_of_words("#combine(white house") == "#combine(white house)"
    assert structquery.bag_of_words("#1(white house) #uw8(red car)") == "#combine(white house red car)"
    assert structquery.bag_of_words("What's up?") == "#combine(Whats up)"
    assert structquery.is_valid(structquery.bag_of_words("#weight(0.5 a"))


def test_bag_of_words_no_words():
    with pytest.raises(ValueError):
        structquery.bag_of_words("#combine( ) !!! ???")


def test_extract_query():
    out = "Draft: <query>#combine(a)</query>\nFinal answer:\n<query>\n  #combine(b c)\n</query>\n"
    assert structquery.extract_query(out) == "#combine(b c)"
    assert structquery.extract_query("<QUERY>x</QUERY>") == "x"
    assert structquery.extract_query("no tags here") is None
    assert structquery.extract_query("<query>   </query>") is None
    assert structquery.extract_query("") is None
    assert structquery.extract_query(None) is None
    assert structquery.extract_query("<q>one</q><q>two</q>", tag="q") == "two"
    assert structquery.extract_query("<query>x</query>", tag="q") is None
