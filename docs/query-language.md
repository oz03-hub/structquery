# The Indri query language, as structquery runs it

This page shows the Indri 5.21 query operators that were tested with structquery. Each example's
output was captured from a real run on the small corpus below. You can paste the code blocks
into one Python session, in order, and get the same output.

All query parsing, tokenization and stemming is done by Indri. structquery only passes your
string to Indri. Use `structquery.validate(query)` to check syntax without an index.

Contents:

- [Example corpus](#example-corpus)
- [Operators](#operators)
- [Fields](#fields)
- [Other operators that work](#other-operators-that-work)
- [Operators not covered](#operators-not-covered)
- [Queries that fail to parse](#queries-that-fail-to-parse)
- [Not errors, but surprising](#not-errors-but-surprising)
- [Prompt for an LLM](#prompt-for-an-llm)

## Example corpus

Eight short documents. Each one has two fields, `title` and `body`.

```python
import structquery

DOCS = {
    "d1": {"title": "Indri search engine",
           "body": "Indri is a search engine from the Lemur Project. It supports structured queries."},
    "d2": {"title": "Lemur Project history",
           "body": "The Lemur Project was started by the University of Massachusetts and Carnegie Mellon University."},
    "d3": {"title": "White House press briefing",
           "body": "The press secretary spoke at the White House about the economy."},
    "d4": {"title": "Housing market",
           "body": "House prices rose. The white paint on the old house was new. Economists studied the housing market."},
    "d5": {"title": "Neural information retrieval",
           "body": "Neural models for information retrieval rank documents with dense vectors."},
    "d6": {"title": "Classic retrieval models",
           "body": "Query likelihood and BM25 are classic retrieval models. Information is retrieved by matching terms."},
    "d7": {"title": "U.S. economy in 2020",
           "body": "The U.S. GDP fell in 2020 and recovered in 2021. Analysts used e-mail and state-of-the-art models."},
    "d8": {"title": "Cats and dogs",
           "body": "Dogs chase cats. A cat sleeps while the dog runs."},
}

with structquery.IndexBuilder("ql_index", fields=["title", "body"], overwrite=True) as b:
    for docid, doc in DOCS.items():
        b.add(docid, doc)

idx = structquery.Index("ql_index")


def show(query, k=10):
    """Print docid(score) for each hit, best first."""
    hits = idx.search(query, k=k)
    print(" ".join(f"{h.docid}({h.score:.3f})" for h in hits) or "(no results)")
```

The index uses the defaults: Krovetz stemming, no stopwords, and Dirichlet smoothing with
mu=2500. Scores are log-probabilities, so they are negative and higher (closer to 0) is better.

A query returns only documents that match at least one of its terms. In the example below,
`d8` is not returned at all because it contains neither "white" nor "house".

## Operators

Operator names are lowercase. `#COMBINE` and `#Combine` do not parse.

### Bare words and `#combine`

`#combine(a b c)` scores documents by all of the terms together, with equal weight. A query
made of bare words is treated as `#combine` over those words.

```python
show("#combine(white house)")
show("white house")
```

```text
d3(-3.631) d4(-3.641)
d3(-3.631) d4(-3.641)
```

Top-level items that are not wrapped in an operator are combined too:

```python
show("#combine(white house) economy")
```

```text
d3(-3.907) d7(-3.926) d4(-3.927)
```

### `#weight`

`#weight(w1 q1 w2 q2 ...)` is like `#combine`, but each item gets the weight written before
it. Every item needs a number in front of it.

```python
show("#weight(3.0 economy 1.0 house)")
show("#weight(1.0 economy 3.0 house)")
```

```text
d3(-4.011) d7(-4.021) d4(-4.032)
d3(-3.664) d4(-3.673) d7(-3.688)
```

### `#1(...)` and `#odN(...)`: ordered windows (phrases)

`#odN(a b)` matches when the terms appear in this order with at most N-1 words between
consecutive terms. `#1(a b)` is an exact phrase. `#N(...)` is the same as `#odN(...)`.

```python
show("#1(white house)")
show("#od5(white house)")
show("#5(white house)")
```

```text
d3(-4.158)
d3(-3.770) d4(-3.789)
d3(-3.770) d4(-3.789)
```

`d4` matches `#od5` because "white paint on the old house" has "house" five words after
"white".

### `#uwN(...)`: unordered windows

`#uwN(a b)` matches when all the terms appear, in any order, inside a window of N words.

```python
show("#od8(house white)")
show("#uw8(house white)")
show("#uw3(white house)")
```

```text
d4(-4.853)
d3(-3.770) d4(-3.789)
d3(-4.158)
```

Window operators accept terms, other window operators and `#syn`. They do not accept
`#combine` (see [Queries that fail to parse](#queries-that-fail-to-parse)).

```python
show("#uw8(#1(white house) economy)")
show("#1(white #syn(house houses))")
```

```text
d3(-4.852)
d3(-4.158)
```

### `#syn(...)`: synonyms

`#syn(a b)` treats all the terms as one term. Their counts are added together.

```python
show("#combine(cat)")
show("#combine(dog)")
show("#syn(cat dog)")
show("#combine(#syn(cat dog) chase)")
```

```text
d8(-3.752)
d8(-4.851)
d8(-3.465)
d8(-4.158)
```

### `#wsyn(...)`: weighted synonyms

`#wsyn(w1 a w2 b)` is `#syn` where each term's count is multiplied by its weight.

```python
show("#wsyn(1.0 cat 0.5 dog)")
```

```text
d8(-4.004)
```

### `#band(...)`: require every term

`#band(a b)` returns only documents that contain all of its terms. Compare it with `#combine`,
which also returns documents that contain only some of the terms:

```python
show("#combine(white economy)")
show("#band(white economy)")
```

```text
d3(-3.977) d7(-3.998) d4(-4.001)
d3(-4.852)
```

There is no `#and` operator; see [Queries that fail to parse](#queries-that-fail-to-parse).

### `#or(...)` and `#max(...)`

`#or(a b)` is a probabilistic OR. `#max(a b)` scores each document by its best-scoring item.
Neither one requires all of the terms.

```python
show("#or(white economy)")
show("#max(white economy)")
show("#max(#1(white house) #1(lemur project))")
```

```text
d3(-3.272) d4(-3.294) d7(-3.296)
d3(-3.770) d4(-3.789) d7(-3.809)
d2(-3.771) d1(-3.788) d3(-3.805)
```

### `#filreq(...)` and `#filrej(...)`: filters

`#filreq(F Q)` returns the documents that match `F` and ranks them by `Q`. `#filrej(F Q)`
returns the documents that do *not* match `F` and ranks them by `Q`. Use `#filrej` to exclude
documents.

```python
show("#filreq(economy #combine(white house))")
show("#filrej(economy #combine(white house))")
show("#filreq(#1(white house) #combine(economy))")
```

```text
d3(-3.631)
d4(-3.641)
d3(-4.184)
```

### `#not(...)`: soft negation, which does not exclude

`#not(q)` scores a document higher when `q` is *less* likely in it. It does **not** remove
documents that contain `q`. In the next example `d3` contains "white" and still ranks first.
To exclude documents, use `#filrej`.

```python
show("#combine(economy)")
show("#combine(economy #not(white))")
show("#not(white)")
```

```text
d3(-4.184) d7(-4.188)
d3(-2.104) d7(-2.105)
(no results)
```

## Fields

Fields exist only if they were listed in `fields=` when the index was built (see
[indexing.md](indexing.md)). `idx.fields` lists them. Field names in queries are lowercase.

```python
print(idx.fields)
```

```text
['body', 'title']
```

### Field restriction: `term.field`

`term.field` counts only the occurrences of the term that are inside that field. It also
works on a phrase, as `#1(a b).field`.

```python
show("#combine(economy)")
show("#combine(economy.title)")
show("#combine(economy.body)")
show("#1(white house).title")
```

```text
d3(-4.184) d7(-4.188)
d7(-4.855)
d3(-4.852)
d3(-4.852)
```

To accept a term in either of two fields, put both restrictions in `#syn`:

```python
show("#combine(#syn(retrieval.title retrieval.body))")
```

```text
d5(-3.490) d6(-3.492)
```

Do not write `term.title,body`. It parses, but on this corpus it returned nothing even
though "cat" is in both fields of `d8`:

```python
show("#combine(cat.title,body)")
```

```text
(no results)
```

### Extent retrieval: `#combine[field](...)`

`#combine[field](...)` scores each `field` extent on its own, as if it were a small document.
The hit's `docid` is the document that contains the extent.

```python
show("#combine[title](economy)")
show("#combine[body](economy)")
show("#combine[title](white house)")
```

```text
d7(-3.211)
d3(-4.653)
d3(-3.211)
```

`term.(field)` gave the same scores as `#combine[field](term)` on this corpus:

```python
show("#combine(economy.(title))")
```

```text
d7(-3.211)
```

A document that has several extents of the field can appear more than once in the results.
Passage retrieval, `#combine[passageN:M](...)` (windows of N words, every M words), shows
this. `Hit` does not include the passage offsets, and `Run.to_trec` writes the repeated
docids as they are.

```python
show("#combine[passage5:3](white house)")
```

```text
d3(-3.642) d3(-3.642) d4(-3.649) d4(-3.649) d3(-3.649) d4(-3.651) d4(-3.651)
```

## Other operators that work

These operators also parse and run. They are shown here with one example each, but they are
not described in detail.

```python
show("#wsum(1.0 cat 1.0 economy)")      # weighted sum of beliefs
show("#wand(1.0 cat 1.0 economy)")      # like #weight; every item needs a weight
show("#scoreif(economy #combine(white house))")     # same results as #filreq here
show("#scoreifnot(economy #combine(white house))")  # same results as #filrej here
show("#combine(retriev*)")              # wildcard over indexed (stemmed) terms
show("#any:title")                      # documents that have a title field
```

```text
d8(-3.955) d3(-3.977) d7(-3.980)
d8(-3.981) d3(-3.995) d7(-3.998)
d3(-3.631)
d4(-3.641)
d6(-3.264) d5(-3.272)
d8(-2.817) d5(-2.817) d3(-2.818) d1(-2.818) d6(-2.818) d2(-2.818) d4(-2.819) d7(-2.821)
```

## Operators not covered

- **Priors (`#prior(name)`)**: the query parses, but structquery has no way to create a prior,
  so it fails at search time with `IndriError` ("named prior: ... not found in Repository").
- **Numeric and date operators (`#less`, `#greater`, `#between`, `#equals`, `#date:...`)**:
  these need numeric fields. `IndexBuilder` cannot create them. On a normal index,
  `#less(year 2021)` returns nothing and raises no error.
- **`#and`** does not exist in Indri's query language. Use `#band` (all terms required) or
  `#combine` (ranked).

## Queries that fail to parse

`structquery.validate(query)` raises `structquery.QuerySyntaxError` and `Index.search` raises the
same exception. `str(e)` is Indri's parser message. Indri's message often names the token
*before* the real problem. For example, in `#combine(what's new)` it reports `what`, but the
problem is the apostrophe.

| Input | Message (after `Couldn't understand this query: `) | Fix |
|---|---|---|
| `#combine(what's new)` | `unexpected token: what` | `#combine(whats new)` |
| `#combine(white, house)` | `unexpected token: white` | `#combine(white house)` |
| `#combine(white house?)` | `unexpected char: '?'` | `#combine(white house)` |
| `What is the capital of France?` | `unexpected char: '?'` | `What is the capital of France` |
| `#combine(U.S. economy)` | `expecting O_PAREN, found 'economy'` | `#combine(us economy)` |
| `#combine(white house` | `expecting C_PAREN, found ''` | `#combine(white house)` |
| `#combine(white house))` | `unexpected token: )` | `#combine(white house)` |
| *(empty string, or only spaces)* | `the query is empty` | at least one term |
| `#combine()` | `unexpected token: )` | at least one term |
| `#and(cat dog)` | `expecting NUMBER, found '('` | `#band(cat dog)` |
| `#foo(cat dog)` | `expecting NUMBER, found '('` | a [listed operator](#operators) |
| `#COMBINE(white house)` | `expecting NUMBER, found '('` | `#combine(white house)` |
| `#combine("white house")` | `expecting DBL_QUOTE, found 'house'` | `#combine(#1(white house))` |
| `'white house'` | `unexpected token: '` | `#1(white house)` |
| `#weight(white house)` | `unexpected token: white` | `#weight(1.0 white 1.0 house)` |
| `#wand(cat dog)` | `unexpected token: cat` | `#wand(1.0 cat 1.0 dog)` |
| `#1(white #combine(house))` | `expecting C_PAREN, found '#combine'` | `#1(white house)` |
| `#combine(cat -dog)` | `unexpected token:  -` | `#filrej(dog #combine(cat))` |
| `#combine(c++)` | `unexpected char: '+'` | `#combine(c)` |
| `#combine(1,000)` | `unexpected token: 1` | `#1(1 000)` |
| `#combine(cat:dog)` | `unexpected token: cat` | `#combine(cat dog)` |
| `#combine(white/house)` | `unexpected token: white` | `#combine(white house)` |

Any operator name Indri does not know produces `expecting NUMBER, found '('`. This includes
an uppercase spelling of a real operator.

This block reproduces the table: every input fails, and every fix is valid.

```python
FAILING = {
    "#combine(what's new)": "#combine(whats new)",
    "#combine(white, house)": "#combine(white house)",
    "#combine(white house?)": "#combine(white house)",
    "What is the capital of France?": "What is the capital of France",
    "#combine(U.S. economy)": "#combine(us economy)",
    "#combine(white house": "#combine(white house)",
    "#combine(white house))": "#combine(white house)",
    "": "white",
    "#combine()": "#combine(white)",
    "#and(cat dog)": "#band(cat dog)",
    "#foo(cat dog)": "#combine(cat dog)",
    "#COMBINE(white house)": "#combine(white house)",
    '#combine("white house")': "#combine(#1(white house))",
    "'white house'": "#1(white house)",
    "#weight(white house)": "#weight(1.0 white 1.0 house)",
    "#wand(cat dog)": "#wand(1.0 cat 1.0 dog)",
    "#1(white #combine(house))": "#1(white house)",
    "#combine(cat -dog)": "#filrej(dog #combine(cat))",
    "#combine(c++)": "#combine(c)",
    "#combine(1,000)": "#1(1 000)",
    "#combine(cat:dog)": "#combine(cat dog)",
    "#combine(white/house)": "#combine(white house)",
}
for bad, fixed in FAILING.items():
    try:
        structquery.validate(bad)
        print("UNEXPECTEDLY VALID:", bad)
    except structquery.QuerySyntaxError as e:
        assert str(e).startswith("Couldn't understand this query: ")
    assert structquery.is_valid(fixed), fixed
print(len(FAILING), "failing inputs checked")

try:
    idx.search("#combine(white house")
except structquery.QuerySyntaxError as e:
    print(e)
```

```text
22 failing inputs checked
Couldn't understand this query: expecting C_PAREN, found ''
```

`validate` checks syntax only. A query can pass `validate` and still fail in `search`:

```python
print(structquery.is_valid("#prior(date)"))
try:
    idx.search("#prior(date)")
except structquery.IndriError as e:
    print(type(e).__name__, "...", str(e).split(": ", 1)[1])
```

```text
True
IndriError ... named prior: date not found in Repository. Unable to process query.
```

### Turning text into safe terms

`structquery.escape(text)` joins dotted acronyms and contractions ("U.S." becomes `US`,
"what's" becomes `whats`), then replaces every other character that is not a letter, digit or
whitespace with a space. The result always parses inside an operator. `structquery.bag_of_words(text)`
returns `#combine(...)` over those words, after dropping `#operator` names. It is useful as a
fallback for a broken query.

```python
print(structquery.escape("What's the U.S. GDP (2020)?"))
print(structquery.bag_of_words("#combine(white house"))
show(f"#combine({structquery.escape('white-house economy?')})")
```

```text
Whats the US GDP 2020
#combine(white house)
d3(-3.815) d4(-3.831) d7(-3.839)
```

`escape` is lossy: it drops punctuation. It does follow Indri for the two common cases. When
Indri indexes "U.S." it stores the single term `us`, and it stores "don't" as `dont`; `escape`
produces `US` and `dont`, which match those terms; see
[apostrophes and dots](#apostrophes-and-dots-in-documents). Never call `escape` on a whole
Indri query, because it deletes the operators:

```python
print(structquery.escape("#1(white house)"))
```

```text
1 white house
```

## Not errors, but surprising

None of these raise an error. Each one returns fewer results, or different results, than
people expect.

### Unknown fields return nothing

A field that does not exist in the index gives an empty result list. It does not raise an
error. Check `idx.fields`.

```python
show("#combine(retrieval.nosuchfield)")
show("#combine[nosuchfield](retrieval)")
show("#combine(retrieval.Title)")     # field names are case-sensitive in queries
```

```text
(no results)
(no results)
(no results)
```

### Terms that are not in the index

A term that is not in the index matches nothing. The other terms still count.

```python
show("#combine(zebra)")
show("#combine(zebra cat)")
```

```text
(no results)
d8(-4.674)
```

### Case-insensitive terms

Query terms are case-insensitive, but operator names and field names are not.

```python
show("#combine(WHITE HOUSE)")
show("#combine(gdp)")
```

```text
d3(-3.631) d4(-3.641)
d7(-4.855)
```

### Stemming

Indri stems query terms the same way the index was stemmed. The default is Krovetz.
Krovetz maps "houses" to `house`, but it keeps "housing" as `housing`. `idx.stem(word)` shows
the stem.

```python
print(idx.stem("houses"), idx.stem("housing"), idx.stem("retrieved"))
show("#combine(houses)")
show("#combine(housing)")
```

```text
house housing retrieve
d3(-3.491) d4(-3.493)
d4(-4.160)
```

### No stopwords by default

structquery ships no stopword list, so "the", "is" and "of" are indexed and searched. A
natural-language question matches almost every document through those words:

```python
show("What is the capital of France")
```

```text
d2(-4.600) d1(-4.600) d6(-4.602) d7(-4.603) d3(-4.603) d8(-4.604) d4(-4.605)
```

To drop them, pass `stopwords=[...]` to `IndexBuilder`. The same words are then also dropped
from queries. See [indexing.md](indexing.md#stopwords).

### Hyphens mean a phrase

A hyphenated query word such as `e-mail` is read as the exact phrase `#1(e mail)`. In
documents, Indri splits "e-mail" into the two terms `e` and `mail`. A hyphen with a space
before it, as in `cat -dog`, is a syntax error.

```python
show("#combine(e-mail)")
show("#1(e mail)")
show("#combine(email)")
show("#combine(state-of-the-art models)")
```

```text
d7(-4.855)
d7(-4.855)
(no results)
d7(-4.181) d6(-4.198) d5(-4.203)
```

### Apostrophes and dots in documents

This needs a second tiny index to show. Indri removes apostrophes and dots *inside* a word
when it indexes: "what's" becomes `whats`, "don't" becomes `dont`, and "U.S." becomes `us`.
A query must use the same form, which is what `escape` produces. A spaced version (`what s`, `u s`) does not match.

```python
with structquery.IndexBuilder("tok_index", overwrite=True, stemmer=None) as b:
    b.add("t1", "What's new? We don't know. The U.S. economy grew.")
tok = structquery.Index("tok_index")
for q in ["#combine(whats)", "#combine(what s)", "#combine(dont)", "#combine(don t)",
          "#combine(us)", "#1(u s)", "#combine(U.S)"]:
    print(q, [h.docid for h in tok.search(q)])
tok.close()
```

```text
#combine(whats) ['t1']
#combine(what s) []
#combine(dont) ['t1']
#combine(don t) []
#combine(us) ['t1']
#1(u s) []
#combine(U.S) []
```

The last query, `U.S` with no final dot, is valid syntax. It reads as the term `u` restricted
to a field named `s`, so it silently matches nothing.

With the default Krovetz stemmer, `whats` is stemmed to `what`. A query for `what` then
matches documents that contain "what's".

### Numbers with punctuation

"3.5" and "1,000" are split at the punctuation when they are indexed, giving `3` `5` and `1`
`000`. In a query, `3.5` parses, but it matches nothing. `1,000` is a syntax error. Use
`#1(3 5)` and `#1(1 000)`.

```python
with structquery.IndexBuilder("num_index", overwrite=True) as b:
    b.add("n1", "It cost 3.5 dollars or 1,000 yen.")
num = structquery.Index("num_index")
for q in ["#combine(3.5)", "#1(3 5)", "#1(1 000)"]:
    print(q, [h.docid for h in num.search(q)])
num.close()
```

```text
#combine(3.5) []
#1(3 5) ['n1']
#1(1 000) ['n1']
```

### Other scoring rules change the sign of the score

Scores are negative only under the language-model rules: `dirichlet` (the default), `jm` and
`twostage`. With `okapi` or `tfidf` they are positive. Indri does not report an error for a
rule string it does not understand. It uses the default rule.

```python
for rule in ["method:jm,lambda:0.4", "method:okapi,k1:1.2,b:0.75,k3:7", "method:bogus"]:
    with structquery.Index("ql_index", rule=rule) as other:
        print(rule, [(h.docid, round(h.score, 3)) for h in other.search("#combine(white house)")])
```

```text
method:jm,lambda:0.4 [('d3', -2.403), ('d4', -2.897)]
method:okapi,k1:1.2,b:0.75,k3:7 [('d3', 1.354), ('d4', 1.086)]
method:bogus [('d3', -3.631), ('d4', -3.641)]
```

## Prompt for an LLM

The block below teaches a model to write Indri queries for structquery. It mentions only the
operators shown on this page. Replace `{fields}` with `", ".join(idx.fields)`, or delete that
line if the index has no fields. This check runs every query that appears in the prompt:

```python
PROMPT_QUERIES = [
    "#combine(white house economy)", "#combine(#1(white house) economy)",
    "#weight(2.0 #1(white house) 1.0 economy)", "#combine(#uw8(house white) press)",
    "#combine(#syn(cat dog) chase)", "#band(white economy)",
    "#filrej(economy #combine(white house))", "#filreq(#1(white house) #combine(economy))",
    "#combine(economy.title)", "#combine[title](economy)", "#combine(us economy)",
    "#combine(e-mail)", "#max(#1(white house) #1(lemur project))", "#od5(white house)",
]
for q in PROMPT_QUERIES:
    assert idx.search(q), q
print("all prompt queries return results")
```

```text
all prompt queries return results
```

```text
You write search queries in the Indri query language. Put your final query between
<query> and </query>. Only the last <query> block in your answer is used.

Syntax rules (a query that breaks them is rejected):
- Operators are lowercase and start with #. Every "(" must be closed by ")".
- Terms are plain words made of letters and digits, separated by spaces.
- Do not use: commas, apostrophes, quotes, ? ! : ; / + & @ [ ], or a leading "-".
- Write abbreviations and contractions without punctuation: U.S. -> us, don't -> dont,
  what's -> whats, 3.5 -> #1(3 5).
- A hyphenated word such as e-mail is allowed and means the exact phrase "e mail".

Operators you may use:
- #combine(a b c)          rank by all terms together, equal weight. Plain words = #combine.
- #weight(2.0 a 1.0 b)     like #combine with weights; every item needs a number before it.
- #1(a b)                  exact phrase.             Example: #1(white house)
- #odN(a b)                in order, at most N-1 words apart.  Example: #od5(white house)
- #uwN(a b)                any order, within a window of N words. Example: #uw8(house white)
- #syn(a b)                treat the terms as synonyms (counts are added).
- #band(a b)               only documents that contain every term.
- #max(q1 q2)              score by the best-matching item.
- #filreq(f q)             only documents matching f, ranked by q.
- #filrej(f q)             only documents NOT matching f, ranked by q. Use this to exclude.
- term.field               the term only inside a field.  Example: economy.title
- #combine[field](a b)     score each field on its own.   Example: #combine[title](economy)
Phrase and window operators (#1, #odN, #uwN, #syn) may contain only terms or other
#1/#odN/#uwN/#syn, never #combine or #weight.
There is no #and (use #band) and no #not for exclusion (use #filrej).
Searchable fields in this index: {fields}

Examples:
<query>#combine(#1(white house) economy)</query>
<query>#weight(2.0 #1(white house) 1.0 economy)</query>
<query>#filrej(economy #combine(white house))</query>

If your query is rejected you will be shown the parser error. Fix the query and answer
again with a new <query> block.
```

To use it, find the query with `structquery.extract_query`, check it with `structquery.validate`, and
send any `QuerySyntaxError` message back to the model. A complete runnable loop is in
[`examples/llm_query_loop.py`](../examples/llm_query_loop.py).

```python
idx.close()
```
