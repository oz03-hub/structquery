# Troubleshooting

## Build and install failures

`pip install .` compiles the bundled Indri 5.21 source and the pybind11 binding with CMake,
through scikit-build-core. This takes roughly 2 to 4 minutes; a clean `pip install .` took
about 2 min 20 s on 2 cores. To see the compiler and CMake
output when something fails, run:

```bash
pip install -v .
```

What the build needs, from `CMakeLists.txt` and `pyproject.toml`:

| Requirement | Where the build stops without it | Fix |
|---|---|---|
| A C and C++ compiler (GCC or Clang) | at CMake's `project(structquery LANGUAGES C CXX)` step | Debian/Ubuntu: `apt install build-essential`. Fedora/RHEL: `dnf install gcc gcc-c++`. macOS: `xcode-select --install`. On a cluster: `module avail gcc`, then `module load ...` |
| CMake >= 3.18 | at `cmake_minimum_required(VERSION 3.18)` | Upgrade CMake with your package manager or `module load cmake`. Check the version with `cmake --version`. |
| zlib headers and library | at `find_package(ZLIB REQUIRED)` | Debian/Ubuntu: `apt install zlib1g-dev`. Fedora/RHEL: `dnf install zlib-devel`. macOS: included with the Xcode command-line tools. |
| Python >= 3.9 | pip refuses to install | use a newer Python |

Windows is not supported. Linux and macOS are.

Indri 5.21 is pre-C++11 code. `CMakeLists.txt` builds it as `gnu++11` and builds the binding
as C++14. Do not force `-std=c++17` through `CXXFLAGS`, because Indri's sources do not compile
as C++17.

**`ModuleNotFoundError: No module named 'structquery._structquery'`.** The Python files were found,
but the compiled extension was not. This happens when you import from a source checkout that
was never built, or when `src/` is on `PYTHONPATH` but the build put the extension somewhere
else. Install with `pip install .`, or put the directory that contains the built `_structquery*.so`
on the path.

## `FileExistsError` when building an index

```text
FileExistsError: 'my_index' already exists; pass overwrite=True to replace it or append=True to add documents to it
```

The target directory exists. Choose one of these:

- `IndexBuilder(path, overwrite=True)` (CLI `--overwrite`) deletes it and starts again.
  structquery deletes it only if it is an empty directory, or an Indri index that contains
  nothing else. For any other directory it raises `FileExistsError: refusing to overwrite
  '...': it is not an Indri index, or it contains files that are not part of one` and leaves
  the directory alone.
- `IndexBuilder(path, append=True)` (CLI `--append`) adds documents to the existing index.

**Long paths.** Indri cannot create an index whose path is longer than roughly 110
characters. The constructor raises `IndriError` ending in `file name too long`. Use a shorter
path, for example a symlink or a shorter scratch directory.

A build that failed partway also leaves an index behind. If an exception is raised inside the
`with IndexBuilder(...)` block, the builder is still closed, and the directory is a valid index
holding the documents added before the error. So after fixing the cause, rerun with
`overwrite=True`.

## `KeyError` from `Index.get`

```text
KeyError: "docid not in index: 'd9'"
```

- Check with `"d9" in idx`. Docids are exact strings and are case-sensitive.
- For TREC files, the docid is the `<DOCNO>` with surrounding whitespace removed.
- For `txt`, `html` and `xml` files added with `add_files`, the docid is the file path
  exactly as you passed it.
- If the index was built with `store_docs=False`, `get` raises `IndriError: ... Unable to
  find document N in the collection.` instead of `KeyError`, because the text was never
  stored. Rebuild without `--no-store`.

## A search returns nothing, or less than expected

Use the index to see what the terms became:

```python
import structquery

with structquery.IndexBuilder("ts_index", fields=["title"], overwrite=True) as b:
    b.add("d1", {"title": "U.S. economy", "body": "The e-mail said GDP fell."})

with structquery.Index("ts_index") as idx:
    print(idx.fields)                                    # fields you can use
    print(idx.stem("Economies"), idx.term_count("economies"))
    print(idx.term_count("us"), idx.term_count("email"))
    print(idx.expression_count("#1(e mail)"))
    print(len(idx.search("economy.Title")), len(idx.search("economy.title")))
```

```text
['title']
economy 1
1 0
1.0
0 1
```

Checklist:

1. **The term is not in the index.** Check `idx.term_count(word)`. The term is stemmed the
   same way as in a query.
2. **Unknown field, or a field name with the wrong case.** `word.nosuchfield` and
   `word.Title` silently match nothing. Compare with `idx.fields`. A dict key that was not
   listed in `fields=` at build time is searchable only as plain text, not as a field.
3. **Punctuation inside words.** Indri indexes "U.S." as `us`, "don't" as `dont`, and
   "e-mail" as `e` `mail`. Query `us`, `dont`, `e-mail` or `#1(e mail)`. `escape` produces
   `US` and `dont`. For "e-mail" it produces `e mail`, which is two separate terms and not the
   phrase, so write `#1(e mail)` yourself when the phrase matters. Do not query `U S` or
   `don t`. `U.S` without the final dot means term `u` in a field named `s`.
4. **Too strict an operator.** `#band`, `#filreq`, `#1` and small `#uwN` windows all drop
   documents. Try `#combine` over the same words.
5. **Stopwords.** If the index was built with `stopwords=`, a query made only of stopwords
   matches nothing.
6. **The builder was not closed.** If you open an index while its `IndexBuilder` is still open,
   the open fails with `IndriError: ... Couldn't open parameter file '.../manifest' for
   reading.` Close the builder first, or use `with`.

Full details: [query-language.md](query-language.md#not-errors-but-surprising).

## `QuerySyntaxError`

The query does not parse. The message is Indri's parser message, and it often names the token
*before* the real problem. Common causes are apostrophes, commas, `?`, quotes, `U.S.`,
uppercase operator names, `#and`, `#weight` without weights, and unbalanced parentheses. The
[table of failing queries](query-language.md#queries-that-fail-to-parse) gives the exact message
and fix for each one. For LLM-generated queries, call `structquery.validate` first and send the
message back to the model. If you need a query that always parses, `structquery.bag_of_words(text)`
gives you one.

## Slow indexing

- **Smoke-test first.** Use `add_jsonl(..., limit=1000)` or `structquery index --limit 1000` and
  time it before running the full corpus.
- **Storage.** Write the index to fast local or scratch storage, not to a slow network home
  or project directory. Indexing writes many temporary files.
- **Memory.** A larger `memory=` budget (for example `"4G"`) lets Indri buffer more before
  writing to disk. Keep it well below the memory your job was allocated. It bounds only that
  buffer: the whole process can use several times more (see
  [indexing.md](indexing.md#size-and-time)).
- **Stored text.** `store_docs=False` writes less data, but then `get`, `docs=True` and
  snippets stop working.
- **No parallel writers.** `IndexBuilder` is not thread-safe, and one index is built by one
  builder. Do not add documents to the same index from several threads or processes.

## Slow searching

- Use `batch_search(..., workers=N)`. Each worker process opens its own `Index`. Set `N` to
  the number of CPUs you have, and no more.
- Ask for fewer hits (`k`). Leave `docs` and `snippets` off unless you need them.
- An `Index` is not thread-safe. Do not share one across threads; use one per process.

## Running on a Slurm cluster

Compute belongs on compute nodes. On a shared cluster:

1. **Build inside an allocation.** Compiling Indri takes a few minutes of CPU, so do it in an
   interactive job (for example `salloc -c 4 --mem 8G -t 1:00:00`) or in a batch job, not on a
   login node. Load a compiler and CMake with `module load` first if needed.
2. **Index inside a batch job.** Write the index to scratch storage. On clusters that use HPC
   Workspace, create one with `ws_allocate` and write there. Do not write to `$HOME` or to
   slow project storage.
3. **Match workers to the allocation.** Set `workers` to the number of CPUs you were given,
   never to the number of cores on the node:

```python no-run
import os
run = structquery.batch_search(index_path, queries, k=1000,
                               workers=int(os.environ.get("SLURM_CPUS_PER_TASK", "1")))
```

A job script that indexes a JSONL corpus and runs a query set:

```bash
#!/bin/bash
#SBATCH --job-name=structquery_index
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
#SBATCH --time=02:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
set -euo pipefail
hostname; date; module list 2>&1 || true
source .venv/bin/activate
which python && python --version
WS=/path/to/your/scratch/workspace          # e.g. from: ws_allocate structquery 30
structquery index "$WS/index" corpus.jsonl --memory 4G --overwrite --json
structquery search "$WS/index" --queries queries.tsv -k 1000 \
    --workers "${SLURM_CPUS_PER_TASK:-1}" -o "$WS/run.trec" --json
```

Run a smoke test first: add `--limit 1000` to `structquery index`, and use a short `--time`.
Base `--mem` on the peak memory you measure (for example with
`sacct -j JOBID -o JobID,MaxRSS`), not on `--memory`; see
[indexing.md](indexing.md#size-and-time).
`scripts/browsecompplus.sbatch` in this repository is a complete example.
