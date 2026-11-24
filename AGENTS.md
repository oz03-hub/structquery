# AGENTS.md

## What this repo is

`structquery` is a Python (pybind11) binding for the Indri 5.21 search engine. It builds indexes
and runs Indri structured queries. Indri's source is vendored in `third_party/indri`, unmodified
except for `third_party/patches/`. All tokenizing, stemming, stopping and scoring is Indri's;
structquery adds no text processing of its own.

## To do X, call Y

| Task | Call |
|---|---|
| build an index | `with structquery.IndexBuilder(path, fields=[...]) as b: b.add(docid, str_or_dict)` |
| index a JSONL file | `b.add_jsonl(file, id_key="docid", text_key="text")`. A list, e.g. `text_key=["title", "body"]`, gives a fielded document: every key is searchable as plain text, and the keys also listed in `fields=` are searchable as fields |
| index TREC/HTML/... files | `b.add_files(paths, file_class="trectext")`, with classes from `structquery.FILE_CLASSES` |
| add to an existing index | `IndexBuilder(path, append=True)` |
| rebuild | `IndexBuilder(path, overwrite=True)` |
| search | `structquery.Index(path).search(query, k=10)` returns `[Hit(docid, score, rank, ...)]` |
| read a hit | `Hit` has `docid`, `score`, `rank`, `text`, `snippet`, `internal_id`. `snippet` is multi-line with matched words in upper case |
| get text with the hits | `search(q, docs=True)` fills `Hit.text`; `snippets=True` fills `Hit.snippet` |
| fetch a document | `idx.get(docid)` returns a `Document` (`docid`, `text`, `fields`, `metadata`), or raises `KeyError`. `text` is what Indri stored, so a document added as a dict comes back tagged (`<title>...`); use `doc.fields` for the `{name: text}` mapping |
| many queries, TREC run | `run = structquery.batch_search(path, {qid: q}, k=1000, workers=N)`, then `run.to_trec(file)` |
| see which queries failed | `run.errors` is `{qid: "QuerySyntaxError: ..."}`; bad queries never raise in a batch. `run.results` is `{qid: [Hit]}` (failed qids are absent, also from the TREC file). `on_error="fallback"` retries as bag of words and records it in `run.fallbacks` |
| check query syntax | `structquery.validate(q)` raises `QuerySyntaxError`; `structquery.is_valid(q)` returns a bool |
| query from LLM output | `structquery.extract_query(text)` returns the last `<query>...</query>` block, or `None` |
| natural-language text into terms | `structquery.escape(text)`, or `structquery.bag_of_words(text)` for a whole `#combine(...)` query. Pass the question or the extracted query body, not a raw LLM response (tag words like `query` would become terms) |
| term statistics | `idx.term_count(t)`, `idx.doc_freq(t)` (both stem `t` like a query term), `idx.stem(t)`, `idx.fields`; `idx.stats()` has `doc_count`, `term_count`, `unique_terms`, `fields`, `avg_doc_length`, `path` |
| scoring model | `Index(path, rule="method:jm,lambda:0.4")`; the default is `structquery.DEFAULT_RULE` |
| shell | `structquery index`, `search`, `validate`, `stats`, `doc` (see `docs/cli.md`) |

## Rules that prevent the common mistakes

1. **Validate before you search.** Call `structquery.validate(query)` on any query you did not
   write yourself. Feed `str(e)` from `QuerySyntaxError` back to the LLM. `search` raises the
   same exception. The message names the token where the parser gave up (for example
   `Couldn't understand this query: unexpected token: tariffs` for a missing `)`), which is not
   always where the mistake is, so send the query back along with it.
2. **Escape natural-language text before you put it in an operator.** For example,
   `f"#combine({structquery.escape(question)})"`. Apostrophes, commas, `?`, quotes, `:`, `+` and
   `U.S.` break parsing. `escape` joins dotted acronyms and contractions the way Indri indexes
   them ("U.S." becomes `US`, "don't" becomes `dont`) and turns all other punctuation into spaces.
3. **Never call `escape` on a full Indri query.** It deletes `#` and the parentheses.
4. **Use one `Index` per process, and never share one across threads.** For parallel search
   use `batch_search(path, ..., workers=N)`, passing the *path*, not an `Index` object.
5. **Close the builder before searching.** Use `with IndexBuilder(...)`. Opening an index whose
   builder is still open raises `IndriError` (it cannot read `manifest`).
6. **Scores are negative log-probabilities under the default rule. Higher is better.** Never
   sort ascending. Under `okapi` or `tfidf` the scores are positive.
7. **Operators are lowercase. There is no `#and`.** Use `#band` to require every term and
   `#combine` to rank. `#not` does not exclude documents; use `#filrej(term #combine(...))`.
8. **Fields must be declared at build time** (`fields=[...]`). Field names in queries are
   lowercase. An unknown field returns `[]` with no error, so check `idx.fields`.
   Restrict a term with `tariffs.title`, a phrase with `#1(trade policy).title`, or score only
   the field text with `#combine[title](trade policy)`.
9. **Phrase and window operators (`#1`, `#odN`, `#uwN`, `#syn`) take only terms** or other
   `#1/#odN/#uwN/#syn`, never `#combine` or `#weight`. Every `#weight` item needs a number in
   front of it.
10. **`IndexBuilder(path)` raises `FileExistsError` if `path` exists.** Pass `overwrite=True`
    or `append=True`. Put indexes in scratch or temp storage, never inside the repo.

## Build, test, run (this repo)

Shared HPC machine: do heavy work inside a Slurm allocation and keep to at most a few
processes.

```bash
source .venv/bin/activate                          # from the repo root
PYTHONPATH=src python your_script.py               # use the in-place build in src/structquery
PYTHONPATH=src python -m structquery --help        # the CLI (installed name: structquery)
PYTHONPATH=src python -m pytest tests              # tests (needs pytest; see note below)
PYTHONPATH=src python scripts/check_docs.py        # run every example in the docs, compare output
pip install .                                      # full build+install, ~2-4 min; only when asked
```

Build the C++ extension without pip (a CMake build; needs `pybind11` importable for
`find_package(pybind11 CONFIG)`):

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -Dpybind11_DIR="$(python -m pybind11 --cmakedir)"
cmake --build build -j "${SLURM_CPUS_PER_TASK:-1}"
```

pytest is installed in `.venv`; `pyproject.toml` lists it as the `test` extra for other environments.

## Repo map

| Path | What |
|---|---|
| `src/structquery/index.py` | `Index`, `Hit`, `Document`, `IndexStats`, `validate`, `is_valid`, `escape` |
| `src/structquery/indexer.py` | `IndexBuilder`, `FILE_CLASSES`, `STEMMERS` |
| `src/structquery/batch.py` | `batch_search`, `Run`, `extract_query`, `bag_of_words` |
| `src/structquery/cli.py` | the `structquery` command |
| `src/_structquery.cpp` | pybind11 binding (thin wrapper over Indri's `QueryEnvironment`/`IndexEnvironment`) |
| `CMakeLists.txt`, `pyproject.toml` | build (scikit-build-core + CMake) |
| `LICENSE`, `THIRD_PARTY_NOTICES.md` | MIT licence for structquery's own code; notices for bundled code |
| `third_party/indri/` | vendored Indri 5.21 source and its `LICENSE.txt` |
| `third_party/patches/` | the only changes made to the Indri source |
| `tests/` | pytest suite |
| `scripts/` | Slurm job scripts, `parity_check.py` (comparison with stock IndriRunQuery), `check_docs.py` (runs the doc examples) |
| `examples/` | `quickstart.py`, `llm_query_loop.py`, `browsecompplus_eval.py` |
| `docs/` | quickstart, query-language, indexing, api, cli, troubleshooting |
