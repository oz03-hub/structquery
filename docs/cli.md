# Command-line interface

Installing structquery installs the `structquery` command. From a source checkout without installing,
run `PYTHONPATH=src python -m structquery` instead; it is the same program.

```text
structquery [-h] [--version] {index,search,validate,stats,doc} ...
```

| Command | Does |
|---|---|
| [`index`](#structquery-index) | build an index from JSONL or from native Indri formats |
| [`search`](#structquery-search) | run one query, or a file of queries (TREC run output) |
| [`validate`](#structquery-validate) | check Indri query syntax (exit 2 if invalid) |
| [`stats`](#structquery-stats) | index statistics |
| [`doc`](#structquery-doc) | print stored documents by id |

Every command takes `--json` for machine-readable output. Errors are always printed as plain
text on stderr, even with `--json`.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success. A batch `search --queries` also exits 0 when some queries failed (unless `--on-error raise`); the failures are in the summary. |
| 1 | An engine, file, input or usage error: index not found, input file missing, missing JSONL key, unknown docid, `FileExistsError`, `search` with neither QUERY nor `--queries`, an unknown flag, or a missing required argument. |
| 2 | Invalid query syntax (`search`, `validate`), and nothing else. |

```console
$ structquery --version
structquery 0.1.0 (Indri release 5.21)
$ structquery search; echo "exit code: $?"
usage: structquery search [-h] [--queries QUERIES] [--qid-key QID_KEY]
                      [--query-key QUERY_KEY] [-k K] [--rule RULE] [--docs]
                      [--snippets] [--max-chars MAX_CHARS] [--workers WORKERS]
                      [--on-error {skip,fallback,raise}] [--output OUTPUT]
                      [--tag TAG] [--json]
                      index [query]
structquery search: error: the following arguments are required: index
exit code: 1
```

## Example files

The examples below use these files in the current directory.

<!-- file: corpus.jsonl -->
```json
{"docid": "d1", "title": "Indri search engine", "text": "Indri is a search engine from the Lemur Project."}
{"docid": "d2", "title": "Lemur Project history", "text": "The Lemur Project was started by UMass Amherst and Carnegie Mellon."}
{"docid": "d3", "title": "White House press briefing", "text": "The press secretary spoke at the White House about the economy."}
{"docid": "d4", "title": "Housing market", "text": "House prices rose and the housing market cooled."}
```

`queries.tsv` has one query per line as `qid<TAB>query`. q2 is broken on purpose:

<!-- file: queries.tsv -->
```text
q1	#combine(lemur project)
q2	#combine(white house
q3	what's new?
```

<!-- file: queries.jsonl -->
```json
{"id": "a", "q": "#1(lemur project)"}
{"id": "b", "q": "#combine(economy)"}
```

<!-- file: stopwords.txt -->
```text
the
of
```

## structquery index

```text
structquery index [-h] [--format {jsonl,txt,trectext,trecweb,trecalt,trecchar,html,xml,warc,warcchar,mbox,pdf,doc,ppt}]
              [--id-key ID_KEY] [--text-key TEXT_KEY [TEXT_KEY ...]]
              [--field FIELD] [--stemmer {krovetz,porter,none}]
              [--stopwords STOPWORDS] [--memory MEMORY] [--limit LIMIT]
              [--no-store] [--overwrite] [--append] [--json]
              index input [input ...]
```

| Argument | Default | Meaning |
|---|---|---|
| `index` | | index directory to create |
| `input ...` | | one or more input files |
| `--format` | `jsonl` | `jsonl`, or an Indri file class (`trectext`, `trecweb`, `html`, ...) |
| `--id-key` | `docid` | JSONL key of the document id |
| `--text-key K [K ...]` | `text` | JSONL key(s) of the text. Two or more keys make a fielded document. |
| `--field F` | none | make field `F` searchable as a field (repeat the flag for several fields) |
| `--stemmer` | `krovetz` | `krovetz`, `porter` or `none` |
| `--stopwords FILE` | none | file with one stopword per line |
| `--memory` | `1G` | indexing memory budget, e.g. `512M`, `4G` |
| `--limit N` | none | only the first N documents of each JSONL file (the `--help` text still says "lines"; blank lines are not counted) |
| `--no-store` | off | do not store document text (`doc`, `--docs` and `--snippets` will fail) |
| `--overwrite` | off | replace an existing index |
| `--append` | off | add to an existing index |
| `--json` | off | print a JSON summary |

In text mode, a running document count goes to stderr and a summary line goes to stdout:

```console
$ structquery index my_index corpus.jsonl --text-key title text --field title
4 documents
indexed 4 documents into my_index in ...s
$ structquery index my_index corpus.jsonl; echo "exit code: $?"
error: 'my_index' already exists; pass overwrite=True to replace it or append=True to add documents to it
exit code: 1
$ structquery index my_index corpus.jsonl --text-key title text --field title --overwrite --json
{"index": "my_index", "documents": 4, "seconds": ...}
```

`--json` shape: `{"index": str, "documents": int, "seconds": float}`.

More examples:

```console
$ structquery index plain_index corpus.jsonl --stemmer porter --stopwords stopwords.txt --limit 2 --json
{"index": "plain_index", "documents": 2, "seconds": ...}
$ structquery index plain_index corpus.jsonl --append --json
{"index": "plain_index", "documents": 4, "seconds": ...}
$ structquery index bad_index corpus.jsonl --id-key id; echo "exit code: $?"
error: "corpus.jsonl:1: missing key 'id'; available keys: ['docid', 'text', 'title']"
exit code: 1
```

For TREC files, use `--format trectext corpus/*.trec`. If a build fails, the index directory
is still created. Rerun with `--overwrite`.

## structquery search

```text
structquery search [-h] [--queries QUERIES] [--qid-key QID_KEY]
               [--query-key QUERY_KEY] [-k K] [--rule RULE] [--docs]
               [--snippets] [--max-chars MAX_CHARS] [--workers WORKERS]
               [--on-error {skip,fallback,raise}] [--output OUTPUT]
               [--tag TAG] [--json]
               index [query]
```

| Argument | Default | Meaning |
|---|---|---|
| `index` | | index directory |
| `query` | | one Indri query (quote it in the shell) |
| `--queries FILE` | | query file: `qid<TAB>query` lines, or a `.jsonl` file |
| `--qid-key` | `qid` | JSONL key of the query id (only for `.jsonl` files) |
| `--query-key` | `query` | JSONL key of the query text (only for `.jsonl` files) |
| `-k` | `10` | hits per query |
| `--rule` | Indri default | scoring rule, e.g. `method:dirichlet,mu:1000`, `method:jm,lambda:0.4` |
| `--docs` | off | single query only: print document text |
| `--snippets` | off | single query only: print query-biased snippets |
| `--max-chars` | `500` | text mode only: truncate printed document text |
| `--workers` | `1` | batch only: number of processes |
| `--on-error` | `skip` | batch only: `skip`, `fallback` (retry as bag of words) or `raise` |
| `--output`, `-o` | stdout | batch only: write the TREC run file here |
| `--tag` | `structquery` | batch only: run tag (last column of the run file) |
| `--json` | off | JSON output (see below) |

### One query

Text mode prints `rank<TAB>docid<TAB>score`:

```console
$ structquery search my_index '#combine(white house)' -k 2
1	d3	-3.0251
2	d4	-3.0365
$ structquery search my_index '#combine(white house)' -k 1 --docs --snippets --max-chars 40
1	d3	-3.0251	'WHITE HOUSE press briefing The press secretary spoke\nat the WHITE HOUSE about the economy...'
<title>
White House press briefing
</tit...
$ structquery search my_index '#combine(white house)' -k 1 --json
{"query": "#combine(white house)", "hits": [{"docid": "d3", "score": -3.02507644113269, "rank": 1, "text": null, "snippet": null, "internal_id": 3}]}
$ structquery search my_index '#combine(white house'; echo "exit code: $?"
query syntax error: Couldn't understand this query: expecting C_PAREN, found ''
exit code: 2
```

`--json` shape for one query:
`{"query": str, "hits": [{"docid": str, "score": float, "rank": int, "text": str|null, "snippet": str|null, "internal_id": int}]}`.
`text` is filled only with `--docs`, and `snippet` only with `--snippets`.

### A file of queries (batch)

The TREC run lines go to **stdout**, or to the file given by `-o`. A summary goes to
**stderr**, as text, or as JSON with `--json`.

```console
$ structquery search my_index --queries queries.tsv -k 2
q1 Q0 d2 1 -2.825289 structquery
q1 Q0 d1 2 -2.831225 structquery
1/3 queries ran, 2 errors
$ structquery search my_index --queries queries.tsv -k 2 --on-error fallback -o run.trec --tag bm --json
{"queries": 3, "ran": 3, "errors": {"q2": "QuerySyntaxError: Couldn't understand this query: expecting C_PAREN, found ''", "q3": "QuerySyntaxError: Couldn't understand this query: unexpected token: what"}, "fallbacks": {"q2": "#combine(white house)", "q3": "#combine(whats new)"}, "output": "run.trec"}
$ cat run.trec
q1 Q0 d2 1 -2.825289 bm
q1 Q0 d1 2 -2.831225 bm
q2 Q0 d3 1 -3.025076 bm
q2 Q0 d4 2 -3.036549 bm
$ structquery search my_index --queries queries.jsonl --qid-key id --query-key q -k 1 --workers 2
a Q0 d2 1 -2.825289 structquery
b Q0 d3 1 -3.917613 structquery
2/2 queries ran, 0 errors
$ structquery search my_index --queries queries.tsv --on-error raise; echo "exit code: $?"
query syntax error: query 'q2': QuerySyntaxError: Couldn't understand this query: expecting C_PAREN, found ''
exit code: 2
```

In the fallback run, q3 ran as `#combine(whats new)` and matched nothing, so the run file
has no lines for q3.

`--json` shape for batch (on stderr):
`{"queries": int, "ran": int, "errors": {qid: message}, "fallbacks": {qid: query_that_ran}, "output": str|null}`.
A query listed in `fallbacks` also appears in `errors`. `ran` counts the queries that
produced a result list, including empty lists.

Files whose names end in `.jsonl` are read as JSON lines. Any other file is read as
`qid<TAB>query`. In batch mode the TREC run lines are written in the same format with or
without `--json`. A qid or docid that is empty or contains whitespace cannot be written to a
run file, so the command fails with exit code 1.

## structquery validate

```text
structquery validate [-h] [--json] [query]
```

This checks syntax only. It does not open an index. If you leave out QUERY, the query is read
from stdin. Exit code 0 means valid and 2 means invalid.

```console
$ structquery validate '#combine(white house)'
valid
$ structquery validate "what's up"; echo "exit code: $?"
INVALID: Couldn't understand this query: unexpected token: what
exit code: 2
$ structquery validate "what's up" --json
{"valid": false, "error": "Couldn't understand this query: unexpected token: what", "query": "what's up"}
$ echo '#1(white house)' | structquery validate --json
{"valid": true, "query": "#1(white house)\n"}
```

`--json` shape: `{"valid": true, "query": str}` or
`{"valid": false, "error": str, "query": str}`.

## structquery stats

```text
structquery stats [-h] [--term TERM] [--json] index
```

`--term T` adds counts for term `T`. The term is stemmed the way query terms are. Repeat the
flag for several terms.

```console
$ structquery stats my_index
doc_count: 4
term_count: 51
unique_terms: 32
fields: ['title']
avg_doc_length: 12.75
path: my_index
indri_version: Indri release 5.21
$ structquery stats my_index --term houses --term the --json
{"doc_count": 4, "term_count": 51, "unique_terms": 32, "fields": ["title"], "avg_doc_length": 12.75, "path": "my_index", "indri_version": "Indri release 5.21", "terms": {"houses": {"stem": "house", "term_count": 3, "doc_freq": 2}, "the": {"stem": "the", "term_count": 6, "doc_freq": 4}}}
```

`--json` shape: `{"doc_count": int, "term_count": int, "unique_terms": int, "fields": [str], "avg_doc_length": float, "path": str, "indri_version": str}`.
With `--term` it also has `"terms": {term: {"stem": str, "term_count": int, "doc_freq": int}}`.
`term_count` is the total number of tokens, and `unique_terms` is the vocabulary size.

## structquery doc

```text
structquery doc [-h] [--json] index docid [docid ...]
```

Text mode prints each document's stored text. `--json` prints **one JSON object per line**,
one per document, not a list.

```console
$ structquery doc my_index d2 --json
{"docid": "d2", "text": "<title>\nLemur Project history\n</title>\n<text>\nThe Lemur Project was started by UMass Amherst and Carnegie Mellon.\n</text>\n", "metadata": {"docno": "d2"}}
$ structquery doc plain_index d1 d4
Indri is a search engine from the Lemur Project.
House prices rose and the housing market cooled.
$ structquery doc my_index d2 d9; echo "exit code: $?"
error: docid not in index: 'd9'
exit code: 1
```

`--json` shape, one line per docid: `{"docid": str, "text": str, "metadata": {str: str}}`.
If any docid is missing, nothing is printed and the exit code is 1.
