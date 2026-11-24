# Quickstart

This page walks through indexing, searching, reading documents, running a query set to a TREC
run file, and scoring that run against relevance judgments. Run the code blocks in order in
one Python session, in an empty directory. Each block that prints something is followed by
the output it produced when these docs were checked.

Install first ([README](../README.md#install)). Then:

```python
import structquery
print(structquery.__version__, "/", structquery.INDRI_VERSION)
```

```text
0.1.0 / Indri release 5.21
```

## 1. Build an index from Python objects

An index is a directory. `IndexBuilder` creates it. The index is complete and searchable only
after the builder is closed, which the `with` block does for you.

```python
docs = {
    "d1": "Indri is a search engine from the Lemur Project.",
    "d2": "The Lemur Project was started by UMass Amherst and Carnegie Mellon.",
    "d3": "The press secretary spoke at the White House about the economy.",
    "d4": "House prices rose and the housing market cooled.",
}
with structquery.IndexBuilder("my_index") as b:
    for docid, text in docs.items():
        b.add(docid, text)
```

A document can also be a dict of fields. List the field names in `fields=` so queries can
restrict to them. See [indexing.md](indexing.md#plain-documents-and-fielded-documents).

```python
with structquery.IndexBuilder("fielded_index", fields=["title", "body"]) as b:
    b.add("a1", {"title": "Indri", "body": "A search engine from the Lemur Project."})
    b.add("a2", {"title": "Lemur", "body": "A toolkit for language modeling and retrieval."})
```

If the directory already exists, `IndexBuilder` raises `FileExistsError`. Pass
`overwrite=True` to replace it, or `append=True` to add documents to it.

## 2. Build an index from a JSONL file

One JSON object per line. By default the id is read from `"docid"` and the text from `"text"`.

<!-- file: corpus.jsonl -->
```json
{"docid": "j1", "title": "Cats", "text": "Cats chase mice in the barn."}
{"docid": "j2", "title": "Dogs", "text": "Dogs chase cats in the yard."}
{"docid": "j3", "title": "Mice", "text": "Mice eat grain."}
```

```python
with structquery.IndexBuilder("jsonl_index") as b:
    n = b.add_jsonl("corpus.jsonl", id_key="docid", text_key="text")
print(n)
```

```text
3
```

Pass a list as `text_key` to get a fielded document:
`add_jsonl("corpus.jsonl", text_key=["title", "text"])`, together with
`fields=["title", "text"]` on the builder.

## 3. Build an index from TREC files

`add_files` uses Indri's own parsers. Each `<DOCNO>` becomes a docid.

<!-- file: news.trec -->
```xml
<DOC>
<DOCNO>N1</DOCNO>
<TEXT>
The central bank raised interest rates again.
</TEXT>
</DOC>
<DOC>
<DOCNO>N2</DOCNO>
<TEXT>
Interest in electric cars keeps growing.
</TEXT>
</DOC>
```

```python
with structquery.IndexBuilder("trec_index") as b:
    b.add_files(["news.trec"], file_class="trectext")
    print(b.count)
```

```text
2
```

Other formats: `structquery.FILE_CLASSES` (`trecweb`, `html`, `xml`, `warc`, ...).

## 4. Search

Queries are written in the Indri query language. Plain words work as they are. Operators give
you phrases, proximity, weights, synonyms and fields; see
[query-language.md](query-language.md).

```python
idx = structquery.Index("my_index")
for hit in idx.search("#combine(lemur project)", k=10):
    print(hit.rank, hit.docid, round(hit.score, 4))
```

```text
1 d1 -2.9662
2 d2 -2.967
```

Scores are log-probabilities. They are negative, and higher (closer to 0) is better. Only
documents that contain at least one query term are returned, so you can get fewer than `k`
hits.

```python
print([h.docid for h in idx.search("#1(white house)")])    # exact phrase
print([h.docid for h in idx.search("house")])              # bare word, case-insensitive
print([h.docid for h in idx.search("#combine(zebra)")])    # no match: empty list
```

```text
['d3']
['d4', 'd3']
[]
```

A malformed query raises `structquery.QuerySyntaxError`. You can check a query first with
`structquery.validate` (which raises) or `structquery.is_valid` (which returns a bool):

```python
print(structquery.is_valid("#combine(white house"))
try:
    idx.search("what's new?")
except structquery.QuerySyntaxError as e:
    print(e)
```

```text
False
Couldn't understand this query: unexpected token: what
```

## 5. Read documents and snippets

```python
hits = idx.search("#combine(white house)", k=1, docs=True, snippets=True)
print(hits[0].docid)
print(hits[0].text)
print(hits[0].snippet)

doc = idx.get("d2")
print(doc.docid, "|", doc.text)
print("d9" in idx, len(idx))
```

```text
d3
The press secretary spoke at the White House about the economy.
The press secretary spoke at the WHITE HOUSE about
the economy...
d2 | The Lemur Project was started by UMass Amherst and Carnegie Mellon.
False 4
```

- `Index.get(docid)` raises `KeyError` when the docid is not in the index.
- `Index.get_many([...])` fetches several documents in order.
- Indri builds the snippet, and query terms appear in upper case in it.
- For fielded documents, `Document.text` includes the `<field>` tags, and `Document.fields`
  gives back the `{name: text}` dict.

```python
idx.close()
```

## 6. Run a query set and write a TREC run file

`batch_search` runs many queries. A query that fails never stops the others. Its error is
recorded in `run.errors`. `workers=N` starts N processes, and each one opens its own `Index`.

```python
queries = {
    "q1": "#combine(lemur project)",
    "q2": "#combine(white house",       # broken on purpose
    "q3": "#combine(housing market)",
}
run = structquery.batch_search("my_index", queries, k=100, workers=1)
print(sorted(run.results))
print(run.errors)
print(run.to_trec("run.trec", tag="my-run"))
print(open("run.trec").read(), end="")
```

```text
['q1', 'q3']
{'q2': "QuerySyntaxError: Couldn't understand this query: expecting C_PAREN, found ''"}
3
q1 Q0 d1 1 -2.966238 my-run
q1 Q0 d2 2 -2.967035 my-run
q3 Q0 d4 1 -3.651277 my-run
```

With `on_error="fallback"`, a query that fails is retried as `bag_of_words(query)`, which
keeps its plain words. The query that actually ran is recorded in `run.fallbacks`:

```python
run = structquery.batch_search("my_index", queries, k=100, on_error="fallback")
print(run.fallbacks, [h.docid for h in run.results["q2"]])
```

```text
{'q2': '#combine(white house)'} ['d3', 'd4']
```

`on_error="raise"` re-raises the first error instead. `run.to_dict()` returns
`{qid: {docid: score}}`.

## 7. Evaluate against qrels

A TREC qrels file has one judgment per line: `qid 0 docid relevance`. structquery does not include
evaluation code. Below is a small pure-Python recall and nDCG@10. For full metrics, pass the
run file to `trec_eval`, or pass `run.to_dict()` to an evaluation library such as
`pytrec_eval` or `ir_measures`. Neither library is a dependency of structquery, and neither was
tested here.

<!-- file: qrels.txt -->
```text
q1 0 d1 1
q1 0 d2 1
q3 0 d4 2
q3 0 d3 0
```

```python
import math

qrels = {}
with open("qrels.txt") as fh:
    for line in fh:
        qid, _, docid, rel = line.split()
        if int(rel) > 0:
            qrels.setdefault(qid, {})[docid] = int(rel)

run = structquery.batch_search("my_index", queries, k=100, on_error="fallback")
for qid, rel in sorted(qrels.items()):
    ranked = [h.docid for h in run.results.get(qid, [])]
    recall = len(set(ranked) & set(rel)) / len(rel)
    dcg = sum((2 ** rel.get(d, 0) - 1) / math.log2(i + 2) for i, d in enumerate(ranked[:10]))
    ideal = sorted(rel.values(), reverse=True)[:10]
    idcg = sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(ideal))
    print(qid, f"recall@100={recall:.3f}", f"ndcg@10={dcg / idcg:.3f}")
```

```text
q1 recall@100=1.000 ndcg@10=1.000
q3 recall@100=1.000 ndcg@10=1.000
```

## The same thing from the shell

```bash
structquery index cli_index corpus.jsonl
structquery search cli_index '#combine(cats chase)' -k 5 --docs
structquery search cli_index --queries queries.tsv -k 1000 -o run.trec
```

All commands and flags are in [cli.md](cli.md).

## Next

- [query-language.md](query-language.md): every operator, the parse errors, and a prompt for LLMs.
- [indexing.md](indexing.md): builder options, fields, stemmers, stopwords.
- [api.md](api.md): the full Python reference.
