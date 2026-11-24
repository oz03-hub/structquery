"""Command-line interface, driven through structquery.cli.main(argv)."""
from __future__ import annotations

import json
import os

import pytest

import structquery
from structquery.cli import main
from conftest import N_DOCS, N_TOKENS


def _jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return path


ROWS = [
    {"docid": "c1", "text": "red apple pie", "title": "dessert", "body": "red apple"},
    {"docid": "c2", "text": "green apple juice", "title": "drink", "body": "green apple"},
    {"docid": "c3", "text": "red wine", "title": "red drink", "body": "wine"},
]


# -- index ---------------------------------------------------------------------------------

def test_cli_index_text(short_tmp, capsys):
    src = _jsonl(os.path.join(short_tmp, "c.jsonl"), ROWS)
    out = os.path.join(short_tmp, "ix")
    assert main(["index", out, src]) == 0
    cap = capsys.readouterr()
    assert f"indexed 3 documents into {out}" in cap.out
    with structquery.Index(out) as idx:
        assert len(idx) == 3 and idx.get("c2").text == "green apple juice"


def test_cli_index_json(short_tmp, capsys):
    src = _jsonl(os.path.join(short_tmp, "c.jsonl"), ROWS)
    out = os.path.join(short_tmp, "ix")
    assert main(["index", out, src, "--json", "--limit", "2", "--stemmer", "none"]) == 0
    cap = capsys.readouterr()
    obj = json.loads(cap.out)
    assert obj["documents"] == 2 and obj["index"] == out
    assert isinstance(obj["seconds"], (int, float))
    assert cap.err == ""                                   # no progress noise in --json mode


def test_cli_index_fields_and_keys(short_tmp, capsys):
    src = _jsonl(os.path.join(short_tmp, "c.jsonl"),
                 [{"id": r["docid"], "title": r["title"], "body": r["body"]} for r in ROWS])
    out = os.path.join(short_tmp, "ix")
    assert main(["index", out, src, "--id-key", "id", "--text-key", "title", "body",
                 "--field", "title", "--json"]) == 0
    capsys.readouterr()
    with structquery.Index(out) as idx:
        assert idx.fields == ["title"]
        assert [h.docid for h in idx.search("red.title")] == ["c3"]


def test_cli_index_trectext(short_tmp, capsys):
    src = os.path.join(short_tmp, "d.trec")
    with open(src, "w") as fh:
        fh.write("<DOC>\n<DOCNO>t1</DOCNO>\n<TEXT>\nhello trec\n</TEXT>\n</DOC>\n")
    out = os.path.join(short_tmp, "ix")
    assert main(["index", out, src, "--format", "trectext", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["documents"] == 1


def test_cli_index_existing_path_fails(short_tmp, capsys):
    src = _jsonl(os.path.join(short_tmp, "c.jsonl"), ROWS)
    out = os.path.join(short_tmp, "ix")
    assert main(["index", out, src, "--json"]) == 0
    assert main(["index", out, src, "--json"]) == 1
    assert "already exists" in capsys.readouterr().err
    assert main(["index", out, src, "--json", "--overwrite"]) == 0
    assert main(["index", out, src, "--json", "--append", "--limit", "1"]) == 0
    capsys.readouterr()
    with structquery.Index(out) as idx:
        assert len(idx) == 4


def test_cli_index_missing_key(short_tmp, capsys):
    src = _jsonl(os.path.join(short_tmp, "c.jsonl"), ROWS)
    assert main(["index", os.path.join(short_tmp, "ix"), src, "--text-key", "contents", "--json"]) == 1
    assert "missing key 'contents'" in capsys.readouterr().err


# -- search --------------------------------------------------------------------------------

def test_cli_search_text(index_path, capsys):
    assert main(["search", index_path, "#1(white house)"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    rank, docid, score = lines[0].split("\t")
    assert (rank, docid) == ("1", "d1")
    float(score)


def test_cli_search_json(index_path, capsys):
    assert main(["search", index_path, "#combine(white house)", "--json", "-k", "3", "--docs",
                 "--snippets"]) == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["query"] == "#combine(white house)"
    hits = obj["hits"]
    assert len(hits) == 3 and hits[0]["docid"] == "d1" and hits[0]["rank"] == 1
    assert hits[0]["text"] == "the white house is in washington"
    assert "white" in hits[0]["snippet"].lower()
    assert set(hits[0]) == {"docid", "score", "rank", "text", "snippet", "internal_id"}


def test_cli_search_json_non_ascii(index_path, capsys):
    assert main(["search", index_path, "über", "--json", "--docs"]) == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["hits"][0]["text"] == "café naïve résumé über straße"


def test_cli_search_docs_text_mode(index_path, capsys):
    assert main(["search", index_path, "banana", "--docs", "--max-chars", "5"]) == 0
    out = capsys.readouterr().out
    assert "doc ten" in out and "apple..." in out


def test_cli_search_rule(index_path, capsys):
    assert main(["search", index_path, "white", "--json"]) == 0
    a = json.loads(capsys.readouterr().out)["hits"][0]["score"]
    assert main(["search", index_path, "white", "--json", "--rule", "method:jm,lambda:0.4"]) == 0
    b = json.loads(capsys.readouterr().out)["hits"][0]["score"]
    assert a != pytest.approx(b)


def test_cli_search_bad_syntax_exit_2(index_path, capsys):
    assert main(["search", index_path, "#combine(white"]) == 2
    assert "query syntax error" in capsys.readouterr().err


def test_cli_search_no_query_exit_1(index_path, capsys):
    assert main(["search", index_path]) == 1
    assert "QUERY" in capsys.readouterr().err


def test_cli_search_missing_index(short_tmp, capsys):
    assert main(["search", os.path.join(short_tmp, "nope"), "white"]) == 1
    assert "not found" in capsys.readouterr().err


def test_cli_search_queries_tsv(index_path, short_tmp, capsys):
    qf = os.path.join(short_tmp, "q.tsv")
    with open(qf, "w") as fh:
        fh.write("q1\t#1(white house)\nq2\t#combine(white\n\nq3\tzebra\n")
    assert main(["search", index_path, "--queries", qf, "--json", "--tag", "T"]) == 0
    cap = capsys.readouterr()
    lines = cap.out.splitlines()
    assert lines == [l for l in lines if len(l.split()) == 6]
    assert [l.split()[:3] for l in lines] == [["q1", "Q0", "d1"], ["q3", "Q0", "d11"]]
    assert all(l.endswith(" T") for l in lines)
    summary = json.loads(cap.err)
    assert summary["queries"] == 3 and summary["ran"] == 2
    assert set(summary["errors"]) == {"q2"}


def test_cli_search_queries_docid_with_space(index_path, short_tmp, capsys):
    qf = os.path.join(short_tmp, "q.tsv")
    with open(qf, "w") as fh:
        fh.write("q\tbanana\n")
    rc = main(["search", index_path, "--queries", qf])
    lines = capsys.readouterr().out.splitlines()
    assert rc != 0 or (lines and all(len(l.split()) == 6 for l in lines))


def test_cli_search_queries_jsonl_to_file(index_path, short_tmp, capsys):
    qf = _jsonl(os.path.join(short_tmp, "q.jsonl"),
                [{"id": "a", "q": "#combine(white house)"}, {"id": "b", "q": "#combine(zebra"}])
    out = os.path.join(short_tmp, "run.trec")
    assert main(["search", index_path, "--queries", qf, "--qid-key", "id", "--query-key", "q",
                 "--on-error", "fallback", "--workers", "2", "-o", out, "-k", "2"]) == 0
    cap = capsys.readouterr()
    assert cap.out == ""
    assert "2/2 queries ran, 1 errors" in cap.err
    lines = open(out).read().splitlines()
    assert [l.split()[0] for l in lines] == ["a", "a", "b"]
    assert lines[2].split()[2] == "d11"


def test_cli_search_queries_on_error_raise(index_path, short_tmp, capsys):
    qf = os.path.join(short_tmp, "q.tsv")
    with open(qf, "w") as fh:
        fh.write("q1\twhite\nq2\t#combine(white\n")
    assert main(["search", index_path, "--queries", qf, "--on-error", "raise"]) == 2


# -- validate ------------------------------------------------------------------------------

def test_cli_validate_ok(capsys):
    assert main(["validate", "#combine(white #1(a b))"]) == 0
    assert capsys.readouterr().out.strip() == "valid"


def test_cli_validate_bad(capsys):
    assert main(["validate", "#combine(white"]) == 2
    assert capsys.readouterr().out.startswith("INVALID: Couldn't understand this query")


def test_cli_validate_json(capsys):
    assert main(["validate", "#combine(white", "--json"]) == 2
    obj = json.loads(capsys.readouterr().out)
    assert obj["valid"] is False and obj["query"] == "#combine(white" and "C_PAREN" in obj["error"]
    assert main(["validate", "white house", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"valid": True, "query": "white house"}


def test_cli_validate_stdin(monkeypatch, capsys):
    import io
    monkeypatch.setattr("sys.stdin", io.StringIO("#uw8(a b)\n"))
    assert main(["validate"]) == 0
    monkeypatch.setattr("sys.stdin", io.StringIO("#uw8(a b\n"))
    assert main(["validate"]) == 2
    capsys.readouterr()


# -- stats ---------------------------------------------------------------------------------

def test_cli_stats_text(index_path, capsys):
    assert main(["stats", index_path]) == 0
    out = capsys.readouterr().out
    assert f"doc_count: {N_DOCS}" in out and f"term_count: {N_TOKENS}" in out
    assert "Indri release 5.21" in out


def test_cli_stats_json(index_path, capsys):
    assert main(["stats", index_path, "--json", "--term", "houses", "--term", "zebra"]) == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["doc_count"] == N_DOCS and obj["term_count"] == N_TOKENS
    assert obj["fields"] == ["title"] and obj["indri_version"] == structquery.INDRI_VERSION
    assert obj["terms"]["houses"] == {"stem": "house", "term_count": 3, "doc_freq": 3}
    assert obj["terms"]["zebra"] == {"stem": "zebra", "term_count": 3, "doc_freq": 1}


# -- doc -----------------------------------------------------------------------------------

def test_cli_doc_text(index_path, capsys):
    assert main(["doc", index_path, "d1", "doc ten"]) == 0
    assert capsys.readouterr().out.splitlines() == ["the white house is in washington", "apple banana cherry"]


def test_cli_doc_json(index_path, capsys):
    assert main(["doc", index_path, "d9", "doc ten", "--json"]) == 0
    objs = [json.loads(l) for l in capsys.readouterr().out.splitlines()]
    assert [o["docid"] for o in objs] == ["d9", "doc ten"]
    assert objs[0]["text"] == "café naïve résumé über straße"
    assert objs[1]["metadata"] == {"docno": "doc ten"}


def test_cli_doc_missing(index_path, capsys):
    assert main(["doc", index_path, "d1", "nope"]) == 1
    cap = capsys.readouterr()
    assert cap.out == "" and "nope" in cap.err


# -- misc ----------------------------------------------------------------------------------

def test_cli_requires_command(capsys):
    with pytest.raises(SystemExit) as ei:
        main([])
    assert ei.value.code == 1      # usage errors exit 1; 2 is reserved for query syntax errors


def test_cli_version(capsys):
    with pytest.raises(SystemExit) as ei:
        main(["--version"])
    assert ei.value.code == 0
    assert structquery.__version__ in capsys.readouterr().out
