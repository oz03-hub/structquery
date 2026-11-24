# structquery

structquery is a Python binding (pybind11) for the Indri 5.21 search engine. You can build Indri
indexes and run Indri structured queries (`#combine`, `#1`, `#uw8`, `#syn`, `#weight`, field
restriction, ...) from Python or from the `structquery` command line.

All tokenizing, parsing, stemming and scoring is done by Indri's own code, which is bundled
in `third_party/indri`.

## Install

There is no PyPI package. Install from source:

```bash
pip install .                      # from a checkout
pip install git+https://github.com/oz03-hub/structquery
```

To build it you need:

- a C++ compiler (GCC or Clang)
- CMake >= 3.18
- zlib headers
- Python >= 3.9

Linux is supported. macOS does not build yet, and Windows is not supported. The build compiles the bundled Indri source and
takes roughly 2 to 4 minutes. If it fails, see [docs/troubleshooting.md](docs/troubleshooting.md).

## Quickstart

```python
import structquery

with structquery.IndexBuilder("my_index", fields=["title"]) as b:   # the index is ready when the block exits
    b.add("d1", {"title": "White House", "body": "The press secretary spoke at the White House."})
    b.add("d2", {"title": "Housing", "body": "House prices rose; the white paint was new."})
    b.add("d3", "Cats chase dogs.")                                 # plain text works too

idx = structquery.Index("my_index")
for hit in idx.search("#combine(#1(white house) press)", k=10):
    print(hit.rank, hit.docid, round(hit.score, 3))                 # scores are negative; higher is better
print(idx.get("d3").text)
```

```text
1 d1 -2.74
Cats chase dogs.
```

## LLM query loop

A model writes an Indri query inside `<query>...</query>`. Your program extracts the query,
validates it and runs it. If the query does not parse, the program sends the parser error
back to the model.

```python
def call_llm(prompt):                       # replace with a real model call
    if "rejected" in prompt:
        return "Fixed: <query>#combine(#1(white house) press)</query>"
    return "My query: <query>#combine(white house's press)</query>"

prompt = "Write an Indri query for: press briefings at the White House"
for attempt in range(3):
    reply = call_llm(prompt)
    query = structquery.extract_query(reply)    # text of the last <query> block, or None
    if query is None:
        prompt += "\nAnswer with a <query>...</query> block."
        continue
    try:
        structquery.validate(query)             # raises QuerySyntaxError; no index needed
    except structquery.QuerySyntaxError as e:
        prompt += f"\nYour query {query!r} was rejected: {e}. Fix it."
        continue
    hits = idx.search(query, k=5)
    print(attempt, query, [h.docid for h in hits])
    break
```

```text
1 #combine(#1(white house) press) ['d1']
```

[docs/query-language.md](docs/query-language.md#prompt-for-an-llm) has a ready-made prompt
that teaches a model the operators. A runnable script is in
[examples/llm_query_loop.py](examples/llm_query_loop.py).

## API at a glance

| To do this | Use | Docs |
|---|---|---|
| Build an index | `IndexBuilder(path, stemmer=, stopwords=, fields=)` with `.add`, `.add_jsonl`, `.add_files` | [indexing](docs/indexing.md), [api](docs/api.md#indexbuilder) |
| Open an index and search | `Index(path).search(query, k, docs=, snippets=)` returns `[Hit]` | [api](docs/api.md#indexsearch) |
| Fetch documents | `Index.get(docid)`, `Index.get_many(docids)` return `Document` | [api](docs/api.md#indexget) |
| Collection and term statistics | `Index.stats()`, `term_count`, `doc_freq`, `expression_count`, `stem` | [api](docs/api.md#indexstats) |
| Run many queries, write a TREC run | `batch_search(path, queries, workers=)` returns `Run`, then `Run.to_trec(file)` | [quickstart](docs/quickstart.md#6-run-a-query-set-and-write-a-trec-run-file) |
| Check query syntax | `validate(q)` (raises `QuerySyntaxError`), `is_valid(q)` | [query language](docs/query-language.md#queries-that-fail-to-parse) |
| Use LLM output | `extract_query(text)`, `escape(text)`, `bag_of_words(text)` | [api](docs/api.md#extract_query) |
| Command line | `structquery index / search / validate / stats / doc` | [cli](docs/cli.md) |

More docs:

- [Quickstart](docs/quickstart.md)
- [Query language](docs/query-language.md)
- [Indexing](docs/indexing.md)
- [API reference](docs/api.md)
- [CLI](docs/cli.md)
- [Troubleshooting](docs/troubleshooting.md)
- [AGENTS.md](AGENTS.md), for coding agents
- [llms.txt](llms.txt)

## Things to know

- Scores from the default rule (Dirichlet, mu=2500) are log-probabilities: negative, and
  higher is better.
- An `Index` is not thread-safe. Use one per process. `batch_search(..., workers=N)` does this
  for you.
- structquery ships no stopword list. "the" and "of" are indexed unless you pass `stopwords=`.
- A field that does not exist in the index is not an error. The query returns no results.
- Rankings and scores match stock `IndriRunQuery` on the same index (`scripts/parity_check.py`).

## Licence and attribution

structquery is not an official Lemur Project product. It bundles the source of the Indri search
engine (Lemur Project, Copyright (c) 2000-2014 The Lemur Project), which is distributed under
the licence in [`third_party/indri/LICENSE.txt`](third_party/indri/LICENSE.txt). That source is
unmodified except for the patches in `third_party/patches/`:

- `0001-region-allocator-16-byte-alignment.patch`: `RegionAllocator` rounds allocations up
  to 16 bytes instead of 8, so objects placed there are correctly aligned.

structquery's own code is under the MIT licence ([`LICENSE`](LICENSE)). Notices for the bundled
code are in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md); both licences ship inside built wheels.
