"""IndexBuilder: creating, overwriting, appending, add_jsonl, add_files."""
from __future__ import annotations

import json
import os

import pytest

import structquery
from conftest import CORPUS, N_DOCS, docids


def _small(path, docs=(("a1", "alpha beta"), ("a2", "beta gamma")), **kw):
    with structquery.IndexBuilder(path, **kw) as b:
        for d, t in docs:
            b.add(d, t)
        n = b.count
    return n


# -- the session fixture ------------------------------------------------------------------

def test_fixture_index_has_all_docs(ix):
    assert len(ix) == N_DOCS
    for d, _ in CORPUS:
        assert d in ix


def test_builder_count_tracks_added_documents(short_tmp):
    with structquery.IndexBuilder(os.path.join(short_tmp, "c")) as b:
        assert b.count == 0
        for i, (d, t) in enumerate(CORPUS, 1):
            b.add(d, t)
            assert b.count == i


def test_add_many_returns_count_and_reports_progress(short_tmp):
    seen = []
    with structquery.IndexBuilder(os.path.join(short_tmp, "m")) as b:
        n = b.add_many(CORPUS, progress=seen.append, progress_every=5)
    assert n == N_DOCS
    assert seen == [5, 10, 12]
    assert len(structquery.Index(os.path.join(short_tmp, "m"))) == N_DOCS


def test_builder_close_twice_is_safe(short_tmp):
    b = structquery.IndexBuilder(os.path.join(short_tmp, "x"))
    b.add("a", "alpha")
    b.close()
    b.close()


def test_builder_add_after_close_raises(short_tmp):
    b = structquery.IndexBuilder(os.path.join(short_tmp, "x"))
    b.close()
    with pytest.raises(RuntimeError):
        b.add("a", "alpha")


# -- overwrite / append / refusing ---------------------------------------------------------

def test_existing_path_without_flags_raises_file_exists(short_tmp):
    p = os.path.join(short_tmp, "ix")
    _small(p)
    with pytest.raises(FileExistsError, match="overwrite=True"):
        structquery.IndexBuilder(p)


def test_overwrite_replaces_existing_index(short_tmp):
    p = os.path.join(short_tmp, "ix")
    _small(p)
    _small(p, docs=[("z1", "zeta")], overwrite=True)
    with structquery.Index(p) as idx:
        assert len(idx) == 1
        assert "z1" in idx and "a1" not in idx


def test_overwrite_accepts_empty_directory(short_tmp):
    p = os.path.join(short_tmp, "empty")
    os.mkdir(p)
    assert _small(p, overwrite=True) == 2


def test_overwrite_refuses_non_index_directory(short_tmp):
    p = os.path.join(short_tmp, "precious")
    os.mkdir(p)
    keep = os.path.join(p, "data.txt")
    with open(keep, "w") as fh:
        fh.write("do not delete")
    with pytest.raises(FileExistsError, match="not an Indri index"):
        structquery.IndexBuilder(p, overwrite=True)
    assert open(keep).read() == "do not delete"


def test_overwrite_refuses_lookalike_non_index_directory(short_tmp):
    p = os.path.join(short_tmp, "lookalike")
    os.makedirs(os.path.join(p, "index"))
    open(os.path.join(p, "manifest"), "w").close()
    keep = os.path.join(p, "results.csv")
    with open(keep, "w") as fh:
        fh.write("irreplaceable")
    with pytest.raises(structquery.IndriError):
        structquery.Index(p)                       # Indri agrees: not an index
    try:
        structquery.IndexBuilder(p, overwrite=True).close()
    except FileExistsError:
        pass
    assert os.path.exists(keep)


def test_overwrite_refuses_regular_file(short_tmp):
    p = os.path.join(short_tmp, "afile")
    with open(p, "w") as fh:
        fh.write("x")
    with pytest.raises(FileExistsError, match="not an Indri index"):
        structquery.IndexBuilder(p, overwrite=True)
    assert os.path.isfile(p)


def test_append_adds_documents(short_tmp):
    p = os.path.join(short_tmp, "ix")
    _small(p)
    with structquery.IndexBuilder(p, append=True) as b:
        b.add("a3", "gamma delta")
        assert b.count == 1          # count is per builder session
    with structquery.Index(p) as idx:
        assert len(idx) == 3
        assert set(docids(idx.search("gamma"))) == {"a2", "a3"}


def test_append_to_missing_index_raises(short_tmp):
    with pytest.raises(FileNotFoundError):
        structquery.IndexBuilder(os.path.join(short_tmp, "nope"), append=True)


def test_append_to_non_index_directory_raises(short_tmp):
    p = os.path.join(short_tmp, "plain")
    os.mkdir(p)
    with pytest.raises(FileNotFoundError):
        structquery.IndexBuilder(p, append=True)


def test_overwrite_and_append_are_exclusive(short_tmp):
    with pytest.raises(ValueError, match="mutually exclusive"):
        structquery.IndexBuilder(os.path.join(short_tmp, "x"), overwrite=True, append=True)


# -- argument validation -------------------------------------------------------------------

@pytest.mark.parametrize("stemmer", ["snowball", "Krovetz", "", "none"])
def test_bad_stemmer_raises(short_tmp, stemmer):
    with pytest.raises(ValueError, match="stemmer"):
        structquery.IndexBuilder(os.path.join(short_tmp, "x"), stemmer=stemmer)
    assert not os.path.exists(os.path.join(short_tmp, "x"))


def test_known_stemmers_constant():
    assert set(structquery.STEMMERS) == {"krovetz", "porter"}


@pytest.mark.parametrize("field", ["1title", "ti-tle", "ti tle", "_x", ""])
def test_bad_field_name_raises(short_tmp, field):
    with pytest.raises(ValueError, match="field name"):
        structquery.IndexBuilder(os.path.join(short_tmp, "x"), fields=[field])


def test_field_names_are_lowercased(short_tmp):
    b = structquery.IndexBuilder(os.path.join(short_tmp, "x"), fields=["Title"])
    assert b.fields == ["title"]
    b.close()


def test_bad_dict_key_raises(short_tmp):
    with structquery.IndexBuilder(os.path.join(short_tmp, "x")) as b:
        with pytest.raises(ValueError, match="field name"):
            b.add("d", {"bad key": "text"})


@pytest.mark.parametrize("docid", ["", "   "])
def test_empty_docid_raises(short_tmp, docid):
    with structquery.IndexBuilder(os.path.join(short_tmp, "x")) as b:
        with pytest.raises(ValueError, match="docid"):
            b.add(docid, "text")


def test_non_text_document_raises(short_tmp):
    with structquery.IndexBuilder(os.path.join(short_tmp, "x")) as b:
        with pytest.raises(TypeError):
            b.add("d", 12345)


def test_angle_brackets_in_dict_values_are_not_markup(short_tmp):
    p = os.path.join(short_tmp, "x")
    with structquery.IndexBuilder(p, fields=["title"]) as b:
        b.add("d", {"title": "a <b>bold</b> claim", "body": "x</body><title>injected"})
    with structquery.Index(p) as idx:
        assert docids(idx.search("bold.title")) == ["d"]
        assert idx.search("injected.title") == []


def test_porter_stemmer(short_tmp):
    p = os.path.join(short_tmp, "porter")
    _small(p, docs=[("p1", "dogs running fast")], stemmer="porter")
    with structquery.Index(p) as idx:
        assert idx.stem("running") == "run"
        assert docids(idx.search("#combine(run dog)")) == ["p1"]


def test_stopwords_are_dropped(short_tmp):
    p = os.path.join(short_tmp, "stop")
    _small(p, docs=[("s1", "the cat and the hat")], stopwords=["the", "and"])
    with structquery.Index(p) as idx:
        # stopped words are not indexed (Indri still reserves their positions, so doc_length
        # and stats().term_count include them; that is upstream behaviour and not asserted here)
        assert idx.term_count("the") == 0 and idx.doc_freq("and") == 0
        assert idx.term_count("cat") == 1
        assert idx.stats().unique_terms == 2
        assert idx.search("the") == []
        assert docids(idx.search("#combine(the cat)")) == ["s1"]


def test_store_docs_false_still_searchable(short_tmp):
    p = os.path.join(short_tmp, "nostore")
    _small(p, store_docs=False)
    with structquery.Index(p) as idx:
        assert docids(idx.search("alpha")) == ["a1"]
        assert "a1" in idx


def test_failed_create_does_not_crash(short_tmp):
    long_dir = os.path.join(short_tmp, "x" * 130)
    with pytest.raises(structquery.IndriError):
        structquery.IndexBuilder(os.path.join(long_dir, "ix"))
    # reaching this line without SIGSEGV is the assertion


# -- add_jsonl -----------------------------------------------------------------------------

def _write_jsonl(path, rows, blank_after=None):
    with open(path, "w", encoding="utf-8") as fh:
        for i, r in enumerate(rows):
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            if blank_after is not None and i == blank_after:
                fh.write("\n")
    return path


ROWS = [
    {"id": "j1", "text": "solar panel efficiency", "title": "energy", "body": "solar panel"},
    {"id": "j2", "text": "wind turbine design", "title": "wind power", "body": "turbine blade"},
    {"id": "j3", "text": "solar wind interaction", "title": "space weather", "body": "solar wind"},
]


def test_add_jsonl_single_key(short_tmp):
    src = _write_jsonl(os.path.join(short_tmp, "c.jsonl"), ROWS)
    p = os.path.join(short_tmp, "ix")
    with structquery.IndexBuilder(p) as b:
        assert b.add_jsonl(src, id_key="id", text_key="text") == 3
    with structquery.Index(p) as idx:
        assert len(idx) == 3
        assert idx.get("j2").text == "wind turbine design"
        assert set(docids(idx.search("solar"))) == {"j1", "j3"}


def test_add_jsonl_multiple_keys_makes_fields(short_tmp):
    src = _write_jsonl(os.path.join(short_tmp, "c.jsonl"), ROWS)
    p = os.path.join(short_tmp, "ix")
    with structquery.IndexBuilder(p, fields=["title"]) as b:
        assert b.add_jsonl(src, id_key="id", text_key=["title", "body"]) == 3
    with structquery.Index(p) as idx:
        # "wind" is in j2's title and j3's body: field restriction picks only j2
        assert set(docids(idx.search("wind"))) == {"j2", "j3"}
        assert docids(idx.search("wind.title")) == ["j2"]
        # keys not listed in text_key are not indexed
        assert idx.search("efficiency") == []


def test_add_jsonl_limit(short_tmp):
    src = _write_jsonl(os.path.join(short_tmp, "c.jsonl"), ROWS)
    p = os.path.join(short_tmp, "ix")
    with structquery.IndexBuilder(p) as b:
        assert b.add_jsonl(src, id_key="id", limit=2) == 2
    with structquery.Index(p) as idx:
        assert len(idx) == 2 and "j3" not in idx


def test_add_jsonl_limit_counts_documents_not_lines(short_tmp):
    src = _write_jsonl(os.path.join(short_tmp, "c.jsonl"), ROWS, blank_after=0)
    with structquery.IndexBuilder(os.path.join(short_tmp, "ix")) as b:
        assert b.add_jsonl(src, id_key="id", limit=2) == 2


def test_add_jsonl_skips_blank_lines(short_tmp):
    src = _write_jsonl(os.path.join(short_tmp, "c.jsonl"), ROWS, blank_after=0)
    with structquery.IndexBuilder(os.path.join(short_tmp, "ix")) as b:
        assert b.add_jsonl(src, id_key="id") == 3


def test_add_jsonl_missing_text_key_message(short_tmp):
    src = _write_jsonl(os.path.join(short_tmp, "c.jsonl"), [ROWS[0], {"id": "bad", "contents": "x"}])
    with structquery.IndexBuilder(os.path.join(short_tmp, "ix")) as b:
        with pytest.raises(KeyError) as ei:
            b.add_jsonl(src, id_key="id", text_key="text")
    msg = ei.value.args[0]
    assert f"{src}:2" in msg
    assert "missing key 'text'" in msg
    assert "['contents', 'id']" in msg


def test_add_jsonl_multi_key_missing_key_raises(short_tmp):
    src = _write_jsonl(os.path.join(short_tmp, "c.jsonl"), [ROWS[0], {"id": "bad", "contents": "x"}])
    with structquery.IndexBuilder(os.path.join(short_tmp, "ix"), fields=["title"]) as b:
        with pytest.raises(KeyError, match="missing key"):
            b.add_jsonl(src, id_key="id", text_key=["title", "body"])


def test_add_jsonl_missing_id_key_message(short_tmp):
    src = _write_jsonl(os.path.join(short_tmp, "c.jsonl"), ROWS)
    with structquery.IndexBuilder(os.path.join(short_tmp, "ix")) as b:
        with pytest.raises(KeyError) as ei:
            b.add_jsonl(src, id_key="docid")
    msg = ei.value.args[0]
    assert f"{src}:1" in msg and "missing key 'docid'" in msg


def test_add_jsonl_progress_callback(short_tmp):
    src = _write_jsonl(os.path.join(short_tmp, "c.jsonl"), ROWS)
    seen = []
    with structquery.IndexBuilder(os.path.join(short_tmp, "ix")) as b:
        b.add_jsonl(src, id_key="id", progress=seen.append, progress_every=2)
    assert seen == [2, 3]


# -- add_files -----------------------------------------------------------------------------

TRECTEXT = """<DOC>
<DOCNO> t1 </DOCNO>
<TEXT>
quantum entanglement experiment
</TEXT>
</DOC>
<DOC>
<DOCNO>t2</DOCNO>
<TEXT>
classical mechanics lecture
</TEXT>
</DOC>
"""


@pytest.fixture
def trec_file(short_tmp):
    p = os.path.join(short_tmp, "docs.trec")
    with open(p, "w") as fh:
        fh.write(TRECTEXT)
    return p


def test_add_files_trectext(short_tmp, trec_file):
    p = os.path.join(short_tmp, "ix")
    with structquery.IndexBuilder(p) as b:
        b.add_files(trec_file, file_class="trectext")
        assert b.count == 2
    with structquery.Index(p) as idx:
        assert len(idx) == 2
        assert "t1" in idx and "t2" in idx          # DOCNO whitespace is trimmed
        assert docids(idx.search("quantum")) == ["t1"]
        assert docids(idx.search("mechanics")) == ["t2"]
        doc = idx.get("t1")
        assert "quantum entanglement experiment" in doc.text
        assert doc.raw.startswith("<DOC>")


def test_add_files_accepts_list_of_paths(short_tmp, trec_file):
    p = os.path.join(short_tmp, "ix")
    with structquery.IndexBuilder(p) as b:
        b.add_files([trec_file])
        assert b.count == 2


def test_add_files_missing_file(short_tmp):
    with structquery.IndexBuilder(os.path.join(short_tmp, "ix")) as b:
        with pytest.raises(FileNotFoundError):
            b.add_files(os.path.join(short_tmp, "nope.trec"))


def test_add_files_bad_file_class(short_tmp, trec_file):
    with structquery.IndexBuilder(os.path.join(short_tmp, "ix")) as b:
        with pytest.raises(ValueError, match="file_class"):
            b.add_files(trec_file, file_class="bogus")
