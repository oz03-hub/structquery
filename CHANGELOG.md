# Changelog

## 0.1.0 (2026-11-24)

First release.

- `IndexBuilder`: build Indri indexes from Python strings and dicts, JSON-lines files, and the
  formats Indri parses natively (TREC text/web, HTML, XML, WARC, ...). Tokenizing, stemming
  (Krovetz, Porter) and stopping are Indri's own.
- `Index`: search with the Indri query language; stored documents, query-biased snippets,
  collection and term statistics, selectable scoring rule.
- `validate`, `is_valid`, `escape`, `bag_of_words`, `extract_query` for queries written by
  language models.
- `batch_search`: multi-process batches with per-query error capture and TREC run output.
- `structquery` command-line tool: `index`, `search`, `validate`, `stats`, `doc`.
- Bundles Indri 5.21 with one patch (16-byte alignment in `RegionAllocator`; without it Indri
  crashes on the first indexed document when built with GCC 13).
- Verified: rankings and scores identical to stock `IndriRunQuery` (`scripts/parity_check.py`).

Known limits: Linux and macOS only (macOS untested); index paths longer than about 110
characters fail; numeric fields, priors and date operators are not exposed; an `Index` is not
thread-safe.
