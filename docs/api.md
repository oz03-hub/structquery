# API reference

This page covers every public name in `structquery.__all__`. The signatures were generated with
`inspect.signature` and were not typed by hand. To regenerate them, run the block in
[Signature index](#signature-index) and compare its output with this page. Each example on this
page was run against the small index built in [Setup](#setup).

- Searching: [`Index`](#index), [`Hit`](#hit), [`Document`](#document), [`IndexStats`](#indexstats)
- Indexing: [`IndexBuilder`](#indexbuilder)
- Many queries: [`batch_search`](#batch_search), [`Run`](#run)
- Query helpers: [`validate`](#validate), [`is_valid`](#is_valid), [`escape`](#escape), [`bag_of_words`](#bag_of_words), [`extract_query`](#extract_query)
- Exceptions: [`IndriError`](#indrierror), [`QuerySyntaxError`](#querysyntaxerror)
- Constants: [`DEFAULT_RULE`, `FILE_CLASSES`, `STEMMERS`, `INDRI_VERSION`, `__version__`](#constants)

## Setup

```python
import structquery

with structquery.IndexBuilder("api_index", fields=["title"], overwrite=True) as b:
    b.add("d1", {"title": "White House", "body": "The press secretary spoke at the White House."})
    b.add("d2", {"title": "Housing", "body": "House prices rose; the white paint was new."})
    b.add("d3", "Cats chase dogs.")
idx = structquery.Index("api_index")
```

## Index

```python no-run
class Index(path: Union[str, os.PathLike], rule: Union[str, Sequence[str], None] = None, memory: Union[int, str, None] = None)
```

A read-only handle on an index directory, used for searching.

- `path`: an index directory created by `IndexBuilder`, `structquery index` or Indri's
  `IndriBuildIndex`.
- `rule`: Indri scoring rule(s). The default is Indri's own default, `DEFAULT_RULE`
  (Dirichlet, mu=2500). Other examples: `"method:jm,lambda:0.4"`,
  `"method:twostage,mu:2500,lambda:0.4"`, `"method:okapi,k1:1.2,b:0.75,k3:7"`. A list of
  rules sets per-field smoothing, e.g. `["method:dirichlet,mu:2500", "method:jm,lambda:0.1,field:title"]`.
  An invalid rule string raises no error; the default rule is used instead.
- `memory`: an optional query-time memory budget, in bytes or as a string like `"1G"`.

Raises `FileNotFoundError` if `path` is not a directory. Raises `IndriError` if `path` is a
directory but not an Indri index. Not thread-safe: use one `Index` per process (as
`batch_search` does). It is a context manager, and `with` closes it.

```python
with structquery.Index("api_index", rule="method:jm,lambda:0.4") as jm:
    print(jm, len(jm))
```

```text
Index('api_index', rule=['method:jm,lambda:0.4']) 3
```

### Index.search

```python no-run
Index.search(query: str, k: int = 10, docs: bool = False, snippets: bool = False) -> List[Hit]
```

Runs one Indri query and returns the top `k` hits, best first, as a `list[Hit]`.

- A query of bare words is treated as `#combine`.
- Only documents that match at least one query term are returned, so the list can be shorter
  than `k`.
- `k <= 0` returns `[]`.
- `docs=True` fills `Hit.text` with the stored text.
- `snippets=True` fills `Hit.snippet` with a query-biased snippet built by Indri.

Raises `QuerySyntaxError` if the query does not parse, and `IndriError` for other engine
failures (for example an unknown `#prior`). Raises `TypeError` if `query` is not a `str`. An
unknown *field* is not an error: it gives no matches. Calling `search` after `close()` raises
`RuntimeError("index is closed")`.

```python
print(idx.search("#combine(white house)", k=5))
```

```text
[Hit(docid='d1', score=-1.990572661170852, rank=1, text=None, snippet=None, internal_id=1), Hit(docid='d2', score=-1.9930946606944566, rank=2, text=None, snippet=None, internal_id=2)]
```

### Index.get

```python no-run
Index.get(docid: str) -> Document
```

Fetches one stored document by its external id. Raises `KeyError` if the docid is not in the
index. Raises `IndriError` if the index was built with `store_docs=False`.

```python
print(idx.get("d3"))
```

```text
Document(docid='d3', text='Cats chase dogs.', metadata={'docno': 'd3'}, raw='Cats chase dogs.', fields={})
```

### Index.get_many

```python no-run
Index.get_many(docids: Sequence[str]) -> List[Document]
```

Fetches several documents, returned in the order given. Raises `KeyError` naming the first
missing docid.

```python
print([d.docid for d in idx.get_many(["d3", "d1"])])
```

```text
['d3', 'd1']
```

### Index.\_\_contains\_\_, Index.\_\_len\_\_

```python no-run
Index.__contains__(docid: str) -> bool
Index.__len__() -> int
```

`docid in idx` tests whether a docid exists. `len(idx)` is the number of documents.

```python
print("d1" in idx, "d9" in idx, len(idx))
```

```text
True False 3
```

### Index.stats

```python no-run
Index.stats() -> IndexStats
```

Returns collection statistics as an [`IndexStats`](#indexstats).

```python
print(idx.stats())
```

```text
IndexStats(doc_count=3, term_count=22, unique_terms=16, fields=['title'], avg_doc_length=7.333333333333333, path='api_index')
```

### Index.term_count, Index.doc_freq

```python no-run
Index.term_count(term: str, field: Optional[str] = None) -> int
Index.doc_freq(term: str) -> int
```

`term_count` gives the total number of occurrences of `term` in the collection. With `field`,
it counts only the occurrences inside that field. An unknown field gives 0. `doc_freq` gives
the number of documents that contain `term`. The term is stemmed like a query term, so
`"houses"` counts `house`.

```python
print(idx.term_count("houses"), idx.term_count("house", field="title"), idx.doc_freq("house"))
```

```text
3 1 2
```

### Index.expression_count, Index.expression_doc_freq

```python no-run
Index.expression_count(expression: str) -> float
Index.expression_doc_freq(expression: str) -> float
```

These give the total number of matches of an Indri expression, such as `#1(white house)`, and
the number of documents that match it. Both return a `float`. Both raise `QuerySyntaxError`
for a malformed expression.

```python
print(idx.expression_count("#1(white house)"), idx.expression_doc_freq("#uw8(white house)"))
```

```text
2.0 2.0
```

### Index.doc_length

```python no-run
Index.doc_length(docid: str) -> int
```

Returns the document length in indexed tokens. Stopped words are counted too. Raises
`KeyError` for an unknown docid.

```python
print(idx.doc_length("d3"))
```

```text
3
```

### Index.stem

```python no-run
Index.stem(term: str) -> str
```

Applies the index's stemmer, the one chosen at build time. It returns `''` for a stopword.

```python
print(idx.stem("Houses"), idx.stem("running"))
```

```text
house running
```

### Index.fields

```python no-run
Index.fields: List[str]  (property)
```

A property: the names of the indexed fields, usable as `term.field` and `#combine[field](...)`.

```python
print(idx.fields)
```

```text
['title']
```

### Index.validate, Index.is_valid

```python no-run
Index.validate(query: str) -> None
Index.is_valid(query: str) -> bool
```

These are the same as the module-level [`validate`](#validate) and [`is_valid`](#is_valid).

### Index.close

```python no-run
Index.close() -> None
```

Releases the index. It is safe to call twice. `with structquery.Index(...) as idx:` calls it for
you.

## Hit

```python no-run
class Hit(docid: str, score: float, rank: int, text: Optional[str] = None, snippet: Optional[str] = None, internal_id: int = 0)
```

One search result. It is a frozen dataclass.

| Field | Meaning |
|---|---|
| `docid` | external document id |
| `score` | Indri score. With the language-model rules (the default `dirichlet`, `jm`, `twostage`) it is a log-probability: negative, and higher is better. `okapi` and `tfidf` give positive scores. |
| `rank` | 1-based rank |
| `text` | stored text, only with `search(..., docs=True)`; otherwise `None` |
| `snippet` | query-biased snippet, only with `search(..., snippets=True)`; otherwise `None` |
| `internal_id` | Indri's internal integer document id |

```python
hit = idx.search("#1(white house)", docs=True, snippets=True)[0]
print(hit.docid, round(hit.score, 3), hit.rank)
print(repr(hit.snippet))
```

```text
d1 -2.393 1
'WHITE HOUSE The press secretary spoke at the WHITE\nHOUSE...'
```

## Document

```python no-run
class Document(docid: str, text: str, metadata: Dict[str, str] = <factory>, raw: str = '', fields: Dict[str, str] = <factory>)
```

A stored document, returned by `Index.get` and `Index.get_many`. It is a frozen dataclass.

| Field | Meaning |
|---|---|
| `docid` | external id (`metadata["docno"]`) |
| `text` | the content exactly as Indri stored it. For a dict document it includes the `<field>` tags; for a TREC document it includes the inner tags such as `<TEXT>`. |
| `fields` | for a document added as a dict: the `{name: text}` mapping back again (with `<` and `>` as spaces, as indexed). `{}` for every other document. |
| `metadata` | stored metadata, always including `docno` |
| `raw` | the complete stored record. It is the same as `text` for documents added with `add`; for TREC files it also has the `<DOC>` wrapper. |

```python
d1 = idx.get("d1")
print(repr(d1.text))
print(d1.fields, idx.get("d3").fields)
```

```text
'<title>\nWhite House\n</title>\n<body>\nThe press secretary spoke at the White House.\n</body>\n'
{'title': 'White House', 'body': 'The press secretary spoke at the White House.'} {}
```

## IndexStats

```python no-run
class IndexStats(doc_count: int, term_count: int, unique_terms: int, fields: List[str], avg_doc_length: float, path: str)
```

`term_count` is the total number of tokens, `unique_terms` is the vocabulary size, and
`avg_doc_length` is `term_count / doc_count`. See [`Index.stats`](#indexstats) for an example.

## IndexBuilder

```python no-run
class IndexBuilder(path: Union[str, os.PathLike], stemmer: Optional[str] = 'krovetz', stopwords: Optional[Iterable[str]] = None, fields: Optional[Sequence[str]] = None, memory: Union[int, str] = '1G', store_docs: bool = True, overwrite: bool = False, append: bool = False)
```

Creates an index, or appends to one. See [indexing.md](indexing.md) for details and examples.

| Argument | Meaning |
|---|---|
| `path` | directory to create. It must not exist, unless `overwrite` or `append` is set. |
| `stemmer` | `"krovetz"`, `"porter"` or `None`. Anything else raises `ValueError`. |
| `stopwords` | iterable of words to drop. The default `None` keeps every word. |
| `fields` | field names to make searchable as fields. Names are lowercased. An invalid name raises `ValueError`. |
| `memory` | indexing memory: `"1G"`, `"512M"` or an int of bytes. An unparsable value raises `ValueError`. |
| `store_docs` | keep document text (needed for `get`, `docs=True`, `snippets=True`) |
| `overwrite` | replace an empty directory or an Indri index that contains nothing else. Any other directory raises `FileExistsError`. |
| `append` | add to an existing index. If there is none, raises `FileNotFoundError`. `stemmer`, `stopwords`, `fields` and `store_docs` are then ignored. |

Raises `FileExistsError` if `path` exists and neither flag is set. Raises `ValueError` if both
flags are set. The index is searchable only after `close()`; the `with` block calls it. Not
thread-safe.

```python
with structquery.IndexBuilder("tiny_index", overwrite=True) as b:
    b.add("x1", "hello world")
print(len(structquery.Index("tiny_index")))
```

```text
1
```

### IndexBuilder.add

```python no-run
IndexBuilder.add(docid: str, doc: Union[str, Mapping[str, str]]) -> None
```

Adds one document.

- `doc` as a `str` is indexed as plain text.
- `doc` as a `dict` `{field: text}` becomes a fielded document: each value is wrapped in
  `<field>` tags, `<` and `>` in values become spaces, and `None` values are skipped.
- An empty `docid` raises `ValueError`. Any other `doc` type raises `TypeError`. A dict key
  that is not `[A-Za-z][A-Za-z0-9_]*` raises `ValueError`.
- A non-`str` docid is converted with `str()`.
- Duplicate docids are *not* detected.

```python no-run
b.add("d1", "plain text")
b.add("d2", {"title": "A title", "body": "The body."})
```

### IndexBuilder.add_many

```python no-run
IndexBuilder.add_many(docs: Iterable, progress: Optional[Callable[[int], None]] = None, progress_every: int = 1000) -> int
```

Adds `(docid, doc)` pairs from any iterable and returns the number added. `progress(n)` is
called every `progress_every` documents and once at the end.

```python no-run
n = b.add_many(((row.id, row.text) for row in rows), progress=print, progress_every=10000)
```

### IndexBuilder.add_jsonl

```python no-run
IndexBuilder.add_jsonl(file: Union[str, os.PathLike], id_key: str = 'docid', text_key: Union[str, Sequence[str]] = 'text', limit: Optional[int] = None, progress: Optional[Callable[[int], None]] = None, progress_every: int = 1000) -> int
```

Streams a JSON-lines file and returns the number of documents added.

- `text_key` as a `str` indexes that key's value as plain text.
- `text_key` as a list builds a fielded document from those keys.
- `limit` stops after that many documents; blank lines do not count.
- A missing id key, a missing single text key, or a record with none of the listed keys raises
  `KeyError` naming the file and line.

```python no-run
n = b.add_jsonl("corpus.jsonl", id_key="docid", text_key=["title", "text"], limit=1000)
```

### IndexBuilder.add_files

```python no-run
IndexBuilder.add_files(paths: Union[str, os.PathLike, Iterable[Union[str, os.PathLike]]], file_class: str = 'trectext') -> None
```

Indexes files with Indri's own parser for `file_class`, which must be one of
[`FILE_CLASSES`](#constants). For `trectext` and `trecweb` the docid is each `<DOCNO>`. For
one-document-per-file classes the docid is the path as passed. Raises `ValueError` for an
unknown class and `FileNotFoundError` for a missing file.

```python no-run
b.add_files(["a.trec", "b.trec"], file_class="trectext")
```

### IndexBuilder.count

```python no-run
IndexBuilder.count: int  (property)
```

A property: the number of documents added so far, through this builder.

### IndexBuilder.close

```python no-run
IndexBuilder.close() -> None
```

Flushes and finishes the index. It is required before searching, and it is safe to call
twice. When an exception leaves a `with` block, `close()` still runs, so a partial index is
left on disk.

## batch_search

```python no-run
batch_search(index: Union[str, os.PathLike, Index], queries: Union[Mapping[str, str], Sequence[Tuple[str, str]]], k: int = 1000, workers: int = 1, rule: Union[str, Sequence[str], None] = None, on_error: str = 'skip', docs: bool = False) -> Run
```

Runs many queries. A query that fails never stops the others.

| Argument | Meaning |
|---|---|
| `index` | index path, or an open `Index` (only with `workers=1`; otherwise raises `ValueError`) |
| `queries` | `{qid: query}` or a list of `(qid, query)` pairs. qids and queries are converted with `str()`. |
| `k` | hits per query (default 1000) |
| `workers` | number of processes. Each one opens its own `Index`. Use at most the number of CPUs you were allocated. |
| `rule` | scoring rule(s), as for `Index` |
| `on_error` | `"skip"`: record the error in `Run.errors`. `"fallback"`: also rerun the query as `bag_of_words(query)` and record that in `Run.fallbacks`. `"raise"`: raise the first error, as `QuerySyntaxError` or `IndriError`, with the qid in the message. Any other value raises `ValueError`. |
| `docs` | fill `Hit.text` |

Returns a [`Run`](#run).

```python
run = structquery.batch_search("api_index", {"q1": "#combine(white house)", "q2": "#combine(white"}, k=10)
print({q: [h.docid for h in hs] for q, hs in run.results.items()}, run.errors)
```

```text
{'q1': ['d1', 'd2']} {'q2': "QuerySyntaxError: Couldn't understand this query: expecting C_PAREN, found ''"}
```

## Run

```python no-run
class Run(results: Dict[str, List[Hit]] = <factory>, errors: Dict[str, str] = <factory>, fallbacks: Dict[str, str] = <factory>, queries: Dict[str, str] = <factory>)
Run.to_trec(file: Union[str, os.PathLike], tag: str = 'structquery') -> int
Run.to_dict() -> Dict[str, Dict[str, float]]
```

The result of `batch_search`.

| Field | Meaning |
|---|---|
| `results` | `{qid: [Hit, ...]}` for every query that ran. The list can be empty. |
| `errors` | `{qid: "ExceptionName: message"}` for every query that failed |
| `fallbacks` | `{qid: query_that_ran}` (only with `on_error="fallback"`). These qids are also in `errors` and in `results`. |
| `queries` | `{qid: query}` as given |

- `to_trec(file, tag)` writes a TREC run file (`qid Q0 docid rank score tag`) and returns the
  number of lines written. It writes a temporary file and then renames it. A query with no
  hits writes no lines. A qid or docid that is empty or contains whitespace raises
  `ValueError`; use `to_dict()` for such ids.
- `to_dict()` returns `{qid: {docid: score}}`.

```python
print(run.to_trec("api.run", tag="demo"), run.to_dict())
```

```text
2 {'q1': {'d1': -1.990572661170852, 'd2': -1.9930946606944566}}
```

## validate

```python no-run
validate(query: str) -> None
```

Checks Indri query syntax without needing an index. It returns `None` if the query is valid.
Otherwise it raises `QuerySyntaxError`, and `str(e)` is Indri's message. An empty or
whitespace-only query is invalid. A non-`str` argument raises `TypeError`. This checks syntax
only: unknown fields and missing priors are not detected.

```python
try:
    structquery.validate("#combine(white, house)")
except structquery.QuerySyntaxError as e:
    print(e)
```

```text
Couldn't understand this query: unexpected token: white
```

## is_valid

```python no-run
is_valid(query: str) -> bool
```

`True` if `validate` accepts the query, otherwise `False`. It still raises `TypeError` for a
non-`str` argument.

```python
print(structquery.is_valid("#1(white house)"), structquery.is_valid("#combine(white house"))
```

```text
True False
```

## escape

```python no-run
escape(text: str) -> str
```

Joins dotted acronyms and contractions the way Indri indexes them (`U.S.` becomes `US`,
`don't` becomes `dont`), replaces every other character that is not a letter, digit or
whitespace (and also `_`) with a space, then collapses the spaces. The result always parses
inside an operator. Use it on natural-language text, never on a whole query
(see [query-language.md](query-language.md#apostrophes-and-dots-in-documents)).

```python
print(structquery.escape("What's the U.S. GDP (2020)?"))
```

```text
Whats the US GDP 2020
```

## bag_of_words

```python no-run
bag_of_words(text: str) -> str
```

Returns `#combine(...)` over the plain words of `text`, after removing `#operator` names and
punctuation. It works on natural language and on a broken Indri query. Raises `ValueError` if
no letters or digits are left.

```python
print(structquery.bag_of_words("#combine(#1(white house) economy"))
```

```text
#combine(white house economy)
```

## extract_query

```python no-run
extract_query(llm_output: str, tag: str = 'query') -> Optional[str]
```

Returns the stripped text inside the **last** `<query>...</query>` block of an LLM response.
The tag match is case-insensitive and can span several lines. Returns `None` if there is no
complete block, or if the block is empty. `tag="q"` looks for `<q>...</q>` instead.

```python
reply = "Draft: <query>#combine(a b)</query>\nFinal:\n<query>\n#1(white house)\n</query>"
print(structquery.extract_query(reply), structquery.extract_query("no tags here"))
```

```text
#1(white house) None
```

## IndriError

```python no-run
class IndriError(RuntimeError)
```

Any failure reported by the Indri engine, for example opening a directory that is not an
index, using an unknown `#prior`, or `get` on an index built with `store_docs=False`. It is a
subclass of `RuntimeError`.

## QuerySyntaxError

```python no-run
class QuerySyntaxError(IndriError)
```

The query is not valid Indri query language. It is a subclass of `IndriError`, so
`except structquery.IndriError` also catches it. The message starts with
`Couldn't understand this query: `.

```python
print(issubclass(structquery.QuerySyntaxError, structquery.IndriError), issubclass(structquery.IndriError, RuntimeError))
```

```text
True True
```

## Constants

```python
for name in ["DEFAULT_RULE", "FILE_CLASSES", "STEMMERS", "INDRI_VERSION", "__version__"]:
    print(name, "=", repr(getattr(structquery, name)))
```

```text
DEFAULT_RULE = 'method:dirichlet,mu:2500'
FILE_CLASSES = ('txt', 'trectext', 'trecweb', 'trecalt', 'trecchar', 'html', 'xml', 'warc', 'warcchar', 'mbox', 'pdf', 'doc', 'ppt')
STEMMERS = ('krovetz', 'porter')
INDRI_VERSION = 'Indri release 5.21'
__version__ = '0.1.1'
```

## Signature index

This block generates every signature on this page.

```python
import inspect

import structquery


def signature(obj, name, is_class=False):
    s = inspect.signature(obj)
    params = []
    for p in s.parameters.values():
        if p.name == "self":
            continue
        item = ("*" if p.kind is p.VAR_POSITIONAL else "") + p.name
        if p.annotation is not p.empty:
            item += f": {p.annotation}"
        if p.default is not p.empty:
            item += f" = {p.default!r}"
        params.append(item)
    ret = "" if is_class or s.return_annotation is s.empty else f" -> {s.return_annotation}"
    return f"{name}({', '.join(params)}){ret}"


for name in structquery.__all__:
    obj = getattr(structquery, name)
    if inspect.isclass(obj) and issubclass(obj, BaseException):
        print(f"class {name}({obj.__mro__[1].__name__})")
    elif inspect.isclass(obj):
        print("class " + signature(obj, name, is_class=True))
        for attr in sorted(vars(obj)):
            if attr.startswith("_") and attr not in ("__contains__", "__len__"):
                continue
            member = inspect.getattr_static(obj, attr)
            if isinstance(member, property):
                ret = inspect.signature(member.fget).return_annotation
                print(f"    {name}.{attr}: {ret}  (property)")
            elif inspect.isfunction(member):
                print("    " + signature(member, f"{name}.{attr}"))
    elif callable(obj):
        print(signature(obj, name))
    else:
        print(f"{name} = {obj!r}")
```

```text
class Index(path: Union[str, os.PathLike], rule: Union[str, Sequence[str], None] = None, memory: Union[int, str, None] = None)
    Index.__contains__(docid: str) -> bool
    Index.__len__() -> int
    Index.close() -> None
    Index.doc_freq(term: str) -> int
    Index.doc_length(docid: str) -> int
    Index.expression_count(expression: str) -> float
    Index.expression_doc_freq(expression: str) -> float
    Index.fields: List[str]  (property)
    Index.get(docid: str) -> Document
    Index.get_many(docids: Sequence[str]) -> List[Document]
    Index.is_valid(query: str) -> bool
    Index.search(query: str, k: int = 10, docs: bool = False, snippets: bool = False) -> List[Hit]
    Index.stats() -> IndexStats
    Index.stem(term: str) -> str
    Index.term_count(term: str, field: Optional[str] = None) -> int
    Index.validate(query: str) -> None
class IndexBuilder(path: Union[str, os.PathLike], stemmer: Optional[str] = 'krovetz', stopwords: Optional[Iterable[str]] = None, fields: Optional[Sequence[str]] = None, memory: Union[int, str] = '1G', store_docs: bool = True, overwrite: bool = False, append: bool = False)
    IndexBuilder.add(docid: str, doc: Union[str, Mapping[str, str]]) -> None
    IndexBuilder.add_files(paths: Union[str, os.PathLike, Iterable[Union[str, os.PathLike]]], file_class: str = 'trectext') -> None
    IndexBuilder.add_jsonl(file: Union[str, os.PathLike], id_key: str = 'docid', text_key: Union[str, Sequence[str]] = 'text', limit: Optional[int] = None, progress: Optional[Callable[[int], None]] = None, progress_every: int = 1000) -> int
    IndexBuilder.add_many(docs: Iterable, progress: Optional[Callable[[int], None]] = None, progress_every: int = 1000) -> int
    IndexBuilder.close() -> None
    IndexBuilder.count: int  (property)
class Hit(docid: str, score: float, rank: int, text: Optional[str] = None, snippet: Optional[str] = None, internal_id: int = 0)
class Document(docid: str, text: str, metadata: Dict[str, str] = <factory>, raw: str = '', fields: Dict[str, str] = <factory>)
class IndexStats(doc_count: int, term_count: int, unique_terms: int, fields: List[str], avg_doc_length: float, path: str)
class Run(results: Dict[str, List[Hit]] = <factory>, errors: Dict[str, str] = <factory>, fallbacks: Dict[str, str] = <factory>, queries: Dict[str, str] = <factory>)
    Run.to_dict() -> Dict[str, Dict[str, float]]
    Run.to_trec(file: Union[str, os.PathLike], tag: str = 'structquery') -> int
batch_search(index: Union[str, os.PathLike, Index], queries: Union[Mapping[str, str], Sequence[Tuple[str, str]]], k: int = 1000, workers: int = 1, rule: Union[str, Sequence[str], None] = None, on_error: str = 'skip', docs: bool = False) -> Run
validate(query: str) -> None
is_valid(query: str) -> bool
escape(text: str) -> str
bag_of_words(text: str) -> str
extract_query(llm_output: str, tag: str = 'query') -> Optional[str]
class IndriError(RuntimeError)
class QuerySyntaxError(IndriError)
DEFAULT_RULE = 'method:dirichlet,mu:2500'
FILE_CLASSES = ('txt', 'trectext', 'trecweb', 'trecalt', 'trecchar', 'html', 'xml', 'warc', 'warcchar', 'mbox', 'pdf', 'doc', 'ppt')
STEMMERS = ('krovetz', 'porter')
INDRI_VERSION = 'Indri release 5.21'
__version__ = '0.1.1'
```
