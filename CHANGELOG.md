# Changelog

## 0.1.1 (2026-11-24)

- Fix the build with GCC 15 (Ubuntu 26.04): Indri's C sources are now compiled as gnu99;
  GCC 15 defaults to C23, which rejects them. Verified in an Ubuntu 26.04 container
  (GCC 15.2, CMake 4.2, Python 3.14): install, tests and docs examples all pass.
- macOS is no longer listed as supported: the build fails there.
- CI: test on Python versions available on current runners; docs help text for `--limit`.

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

Known limits: Linux only; index paths longer than about 110
characters fail; numeric fields, priors and date operators are not exposed; an `Index` is not
thread-safe.
