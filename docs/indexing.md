# Building indexes

`structquery.IndexBuilder` creates an Indri index (a directory, also called a repository), or adds
documents to one. All text processing is done by Indri itself: tokenizing, markup parsing,
stemming and stopping. structquery does no tokenization of its own and ships no stopword list.

Every example on this page was run, and its output is shown under it.

## Options

```python no-run
structquery.IndexBuilder(path, stemmer="krovetz", stopwords=None, fields=None, memory="1G",
                         store_docs=True, overwrite=False, append=False)
```

| Option | Default | Meaning |
|---|---|---|
| `path` | required | Directory to create. Parent directories are created too. |
| `stemmer` | `"krovetz"` | `"krovetz"`, `"porter"` or `None`. Queries are stemmed the same way automatically. |
| `stopwords` | `None` | An iterable of words to drop. They are dropped at index time and from queries. |
| `fields` | `None` | Field names to make searchable as fields (`term.title`, `#combine[title](...)`). Names are lowercased. |
| `memory` | `"1G"` | Indexing memory budget: `"512M"`, `"2G"`, `"1.5g"` or an int of bytes. |
| `store_docs` | `True` | Store document text so that `Index.get`, `Hit.text` and snippets work. |
| `overwrite` | `False` | Delete an existing *Indri index* at `path` first. |
| `append` | `False` | Open an existing index and add documents to it. |

You must call `close()` before the index can be searched. A `with` block calls it for you.
`IndexBuilder` is not thread-safe.

```python
import structquery

with structquery.IndexBuilder("demo_index") as b:
    b.add("d1", "Indri is a search engine from the Lemur Project.")
    b.add("d2", "Query likelihood with Dirichlet smoothing.")
    print(b.count)

with structquery.Index("demo_index") as idx:
    print(len(idx), [h.docid for h in idx.search("#combine(lemur)")])
```

```text
2
2 ['d1']
```

## Plain documents and fielded documents

`add(docid, doc)` takes either a string or a dict.

- **A string** is indexed as plain text, with Indri's `txt` file class. Markup in the string
  is not parsed: `<b>` is indexed as the word `b`.
- **A dict** `{field_name: text}` becomes a small XML document. Each value is wrapped in
  `<field_name>` tags, and the result is parsed with Indri's `xml` file class.
  - Every value is searchable as ordinary text.
  - The keys you also list in `fields=` are searchable as fields.
  - A value of `None` is skipped.
  - Keys must match `[A-Za-z][A-Za-z0-9_]*`, otherwise `add` raises `ValueError`.

In dict values, **every `<` and `>` is replaced by a space** before indexing, so text cannot
be mistaken for markup. Nothing else is changed. The stored text keeps those spaces, and it
includes the `<field>` wrapper tags.

```python
with structquery.IndexBuilder("fielded_index", fields=["title"]) as b:
    b.add("p1", "Plain text with <b>bold</b> markup.")
    b.add("p2", {"title": "a <b>bold</b> title", "body": "x > y and y < z"})
    b.add("p3", {"title": "Only a title", "body": None})

with structquery.Index("fielded_index") as idx:
    print(idx.fields)
    print(repr(idx.get("p1").text))
    print(repr(idx.get("p2").text))
    print([h.docid for h in idx.search("#combine(bold)")])        # both documents
    print([h.docid for h in idx.search("#combine(bold.title)")])  # only the title field
    print([h.docid for h in idx.search("#combine(y.body)")])      # body is not in fields=
```

```text
['title']
'Plain text with <b>bold</b> markup.'
'<title>\na  b bold /b  title\n</title>\n<body>\nx   y and y   z\n</body>\n'
['p1', 'p2']
['p2']
[]
```

Other notes:

- **Field-name case.** Field names are lowercased when the index is built, and a dict key
  like `"Title"` is indexed as the field `title`. In queries, field names must be lowercase:
  `zebra.title` works, `zebra.Title` returns nothing.
- **HTML entities.** Indri's tokenizer drops entity-like sequences such as `&amp;` and
  `&lt;`. They are not decoded, and they are not searchable. A bare `&` splits words: `AT&T`
  is indexed as `at` `t`.
- **Duplicate docids.** These are not rejected. Adding the same docid twice creates two
  documents. Both can be returned by a search, and `Index.get` returns the first one.

```python
with structquery.IndexBuilder("dup_index") as b:
    b.add("x", "first apple")
    b.add("x", "second banana")
with structquery.Index("dup_index") as idx:
    print(len(idx), idx.get("x").text)
```

```text
2 first apple
```

## JSON lines

`add_jsonl(file, id_key="docid", text_key="text", limit=None, progress=None, progress_every=1000)`
streams a JSONL file and uses constant memory.

- If `text_key` is a single key, its value is indexed as plain text.
- If `text_key` is a list of keys, each document is a fielded dict made of those keys. Keys
  that are missing or `null` in a record are skipped, but a record that has none of the keys
  raises `KeyError`.
- A missing `id_key`, or a missing single `text_key`, raises `KeyError`. The message names the
  file, the line and the available keys.

<!-- file: corpus.jsonl -->
```json
{"docid": "j1", "title": "Cats", "text": "Cats chase mice."}
{"docid": "j2", "title": "Dogs", "text": "Dogs chase cats."}
{"docid": "j3", "text": "No title here."}
```

```python
with structquery.IndexBuilder("jsonl_index", fields=["title"]) as b:
    n = b.add_jsonl("corpus.jsonl", text_key=["title", "text"])
    print(n)

with structquery.Index("jsonl_index") as idx:
    print([h.docid for h in idx.search("#combine(cat.title)")])
    print(repr(idx.get("j3").text))

try:
    with structquery.IndexBuilder("bad_index") as b:
        b.add_jsonl("corpus.jsonl", id_key="id")
except KeyError as e:
    print(e)
```

```text
3
['j1']
'<text>\nNo title here.\n</text>\n'
"corpus.jsonl:1: missing key 'id'; available keys: ['docid', 'text', 'title']"
```

`limit=N` stops after N documents. Blank lines do not count.

The `progress` callback receives the running document count every `progress_every`
documents, and once more at the end. `add_many(pairs)` takes any iterable of `(docid, doc)`
pairs and has the same `progress` arguments:

```python
seen = []
with structquery.IndexBuilder("many_index") as b:
    b.add_many(((f"x{i}", f"word{i} common") for i in range(5)), progress=seen.append, progress_every=2)
print(seen)
```

```text
[2, 4, 5]
```

## Files in Indri's own formats

`add_files(paths, file_class="trectext")` hands files to Indri's own parsers. `paths` can be
one path or a list of paths. `structquery.FILE_CLASSES` lists the classes:

```python
print(structquery.FILE_CLASSES)
```

```text
('txt', 'trectext', 'trecweb', 'trecalt', 'trecchar', 'html', 'xml', 'warc', 'warcchar', 'mbox', 'pdf', 'doc', 'ppt')
```

With `trectext` and `trecweb`, a file holds many `<DOC>` records and each record's docid is
its `<DOCNO>`. With one-document-per-file classes (`txt`, `html`, `xml`), the docid is the
file path as you passed it. TREC tags such as `<TITLE>` and `<TEXT>` become fields when you
list them in `fields=`.

<!-- file: sample.trec -->
```xml
<DOC>
<DOCNO> T1 </DOCNO>
<TEXT>
The white house is in Washington.
</TEXT>
</DOC>
<DOC>
<DOCNO>T2</DOCNO>
<TITLE>Cats</TITLE>
<TEXT>
Cats are not dogs.
</TEXT>
</DOC>
```

```python
with structquery.IndexBuilder("trec_index", fields=["title", "text"]) as b:
    b.add_files("sample.trec", file_class="trectext")
    print(b.count)

with structquery.Index("trec_index") as idx:
    print(idx.fields, [h.docid for h in idx.search("#combine(cat.title)")])
    doc = idx.get("T2")
    print(repr(doc.text))
    print(repr(doc.raw))
```

```text
2
['text', 'title'] ['T2']
'<DOCNO>T2</DOCNO>\n<TITLE>Cats</TITLE>\n<TEXT>\nCats are not dogs.\n</TEXT>\n'
'<DOC>\n<DOCNO>T2</DOCNO>\n<TITLE>Cats</TITLE>\n<TEXT>\nCats are not dogs.\n</TEXT>\n</DOC>\n'
```

The whitespace around `T1` in `<DOCNO> T1 </DOCNO>` is stripped, so the docid is `T1`.
`Document.text` still contains the inner tags. `Document.raw` also contains `<DOC>`.

The classes `txt`, `trectext`, `trecweb`, `html` and `xml` were tested with structquery. The other
classes are passed to Indri unchanged and were not tested here.

## Stemmers

| `stemmer=` | running | runners | universities | houses | housing |
|---|---|---|---|---|---|
| `"krovetz"` (default) | running | runner | university | house | housing |
| `"porter"` | run | runner | univers | hous | hous |
| `None` | running | runners | universities | houses | housing |

```python
words = ["running", "runners", "universities", "houses", "housing"]
for stemmer in ["krovetz", "porter", None]:
    with structquery.IndexBuilder("stem_index", stemmer=stemmer, overwrite=True) as b:
        b.add("s", " ".join(words))
    with structquery.Index("stem_index") as idx:
        print(stemmer, [idx.stem(w) for w in words])
```

```text
krovetz ['running', 'runner', 'university', 'house', 'housing']
porter ['run', 'runner', 'univers', 'hous', 'hous']
None ['running', 'runners', 'universities', 'houses', 'housing']
```

The stemmer is stored in the index. `Index.stem(word)` applies it, and query terms are
stemmed with it automatically. When you append, the documents you add are stemmed with the
stemmer the index already has.

## Stopwords

There is no default list. Pass your own words. Matching is case-insensitive. Stopped words
are not searchable, and they are dropped from queries too. They keep their positions, so they
still count toward document length, and they still occupy a slot inside phrases:

```python
with structquery.IndexBuilder("stop_index", stopwords=["the", "of"], overwrite=True) as b:
    b.add("a", "The running of the bulls")
with structquery.Index("stop_index") as idx:
    print(repr(idx.stem("The")), idx.doc_length("a"))
    print([h.docid for h in idx.search("#combine(the)")])
    print([h.docid for h in idx.search("#1(running of the bulls)")])
    print([h.docid for h in idx.search("#1(running bulls)")])
```

```text
'' 5
[]
['a']
[]
```

The CLI reads stopwords from a file with one word per line: `structquery index ... --stopwords FILE`.

## Storing documents

When `store_docs=True` (the default), the index keeps each document's text. When
`store_docs=False` the index is smaller, but `Index.get`, `search(docs=True)` and
`search(snippets=True)` raise `structquery.IndriError`. They do not raise `KeyError`.

```python
with structquery.IndexBuilder("nostore_index", store_docs=False) as b:
    b.add("n1", "giraffe neck")
with structquery.Index("nostore_index") as idx:
    print([h.docid for h in idx.search("giraffe")])
    try:
        idx.get("n1")
    except structquery.IndriError as e:
        print("IndriError:", str(e).split(": ", 1)[1])
```

```text
['n1']
IndriError: Unable to find document 1 in the collection.
```

## Overwrite and append

- If `path` exists and you pass neither option, the constructor raises `FileExistsError`.
- `overwrite=True` deletes `path` only if it is an empty directory, or an Indri index
  (`manifest`, `index/`, `collection/`) that contains nothing else. Otherwise it raises
  `FileExistsError` ("refusing to overwrite ...") and deletes nothing.
- `append=True` requires an existing index, otherwise it raises `FileNotFoundError`. The
  `stemmer`, `stopwords`, `fields` and `store_docs` arguments are ignored. The index keeps the
  settings it was built with.
- `overwrite=True` together with `append=True` raises `ValueError`.

```python
try:
    structquery.IndexBuilder("demo_index")
except FileExistsError as e:
    print(e)

with structquery.IndexBuilder("demo_index", append=True) as b:
    b.add("d3", "An appended document about elephants.")
with structquery.Index("demo_index") as idx:
    print(len(idx), [h.docid for h in idx.search("elephants")])
```

```text
'demo_index' already exists; pass overwrite=True to replace it or append=True to add documents to it
3 ['d3']
```

**A failed build still leaves an index.** If an exception is raised inside the `with` block
(for example a `KeyError` from `add_jsonl`), the builder is closed on the way out. The
directory is then a valid index that holds whatever was added before the error, possibly
nothing. A retry with the same path raises `FileExistsError` unless you pass `overwrite=True`.
The CLI `structquery index` behaves the same way.

## Memory

`memory` is passed to Indri's `IndexEnvironment::setMemory`, which is documented as "the
amount of memory to use for internal structures" while indexing. The default is `"1G"`. Accepted forms: `1024` (bytes),
`"512M"`, `"2G"`, `"1.5g"`. Units are binary, so `"1G"` is 2^30 bytes. On a cluster, keep it
well below the memory of your job allocation.

`memory` bounds only that in-memory index buffer, not the whole process. Large documents in
particular need memory of their own, so the process can use several times more than
`memory`; see the measurement in [Size and time](#size-and-time).

## Size and time

Indexing speed and index size depend on the corpus. Measure them on yours:
`structquery index --json` reports `"seconds"`, and `du -sh INDEX_DIR` gives the size.
The 8-document examples on these pages each index in well under a second.

One larger data point, from a single run, is below. Treat it as an example, not a guarantee.
The corpus was BrowseComp-Plus: 100,195 web documents, 3.3 GB of JSONL, 523 million tokens and
3.85 million unique terms.

| Measure | Result |
|---|---|
| Indexing time | 464 s on one core of a shared cluster node, with `memory="4G"` and Krovetz stemming |
| Index size on disk | 3.6 GB |
| Peak process memory while indexing | about 15.6 GB |
| Searching | 830 long natural-language questions (bag-of-words `#combine`, `k=1000`) in 540 s with 4 worker processes |

Peak memory was far above the `memory="4G"` setting. That setting bounds only Indri's
in-memory index buffer, and this corpus contains single documents of up to 10 MB. Smoke-test
on your own corpus and request job memory based on the peak you measure, not on `memory=`.
