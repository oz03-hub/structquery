#!/usr/bin/env python3
"""Run the examples in structquery's docs and check their output.

Usage (from the repo root, with the project venv active):

    PYTHONPATH=src python scripts/check_docs.py [files...]

Default files: README.md, docs/*.md, llms.txt, AGENTS.md. Stdlib only, no network.

Conventions in the docs:

- ```python blocks run in order, in one namespace per file, with a fresh temporary
  directory as the current directory. A block passes if it raises nothing and, when the
  next fenced block (with only blank lines in between) is ```text, prints exactly that text.
- ```console blocks hold `$ command` lines, each followed by its expected output (stdout
  and stderr merged). Commands run under bash in the same directory; `structquery` runs as
  `<this python> -m structquery`. In expected console output, `...` matches any text
  within one line.
- `<!-- file: NAME -->` before a fenced block writes that block to NAME before anything runs.
- A block with any flag after the language (```python no-run) is skipped, and so are
  other languages (bash, json, xml, and text that is neither a file nor an expected output).

Exit code 1 if any example failed. Temporary directories are removed; nothing is
written inside the repository.
"""
import argparse
import contextlib
import difflib
import gc
import io
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

sys.dont_write_bytecode = True  # importing structquery from src/ must not create __pycache__

REPO = Path(__file__).resolve().parent.parent
DEFAULT_FILES = ["README.md", "docs/*.md", "llms.txt", "AGENTS.md"]
FENCE = re.compile(r"^ {0,3}```")
FILE_MARK = re.compile(r"^<!--\s*file:\s*(\S+)\s*-->$")
TIMEOUT = 300  # seconds per console command


def parse(path):
    """Return ({filename: content}, [example], skipped_count) for one doc file.

    An example is a dict: kind ("python" or "console"), line, label, body, expected.
    """
    lines = path.read_text(encoding="utf-8").split("\n")
    files, examples, skipped = {}, [], 0
    file_name, prev = None, None  # pending file marker; last python example (for its output)
    i = 0
    while i < len(lines):
        line = lines[i]
        mark = FILE_MARK.match(line.strip())
        if mark or not FENCE.match(line):
            if mark:
                file_name = mark.group(1)
            elif line.strip():
                file_name, prev = None, None  # prose breaks "immediately following"
            i += 1
            continue
        info = line.strip()[3:].split()
        lang, flags = (info[0] if info else ""), info[1:]
        end = i + 1
        while end < len(lines) and not FENCE.match(lines[end]):
            end += 1
        body = lines[i + 1:end]
        text = "\n".join(body) + "\n" if body else ""
        new = None
        if file_name:
            files[file_name] = text
        elif lang == "text" and not flags and prev is not None and prev["expected"] is None:
            prev["expected"] = text
        elif flags or lang not in ("python", "console"):
            skipped += 1
        elif lang == "python":
            new = {"kind": "python", "line": i + 1, "label": body[0] if body else "",
                   "body": text, "expected": None}
            examples.append(new)
        else:
            examples.extend(parse_console(body, i + 2))
        file_name, prev = None, new
        i = end + 1
    return files, examples, skipped


def parse_console(body, first_line):
    """Split a console block into one example per `$ command`."""
    examples = []
    for n, line in enumerate(body):
        if line.startswith("$ "):
            examples.append({"kind": "console", "line": first_line + n, "label": line,
                             "body": line[2:], "expected": []})
        elif examples:
            examples[-1]["expected"].append(line)
    return examples


def wildcard_match(expected, actual):
    """True if one expected console line matches; `...` matches anything within the line."""
    pattern = ".*".join(re.escape(part) for part in expected.split("..."))
    return re.fullmatch(pattern, actual) is not None


def run_python(example, namespace, path):
    """Run one python block in the shared namespace; return (passed, diff)."""
    # Pad with newlines so traceback line numbers are line numbers in the doc file.
    code = compile("\n" * example["line"] + example["body"], str(path), "exec")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        try:
            exec(code, namespace)
            error = None
        except Exception as e:  # report the traceback from the doc's code down, not from here
            error = "".join(traceback.format_exception(type(e), e, e.__traceback__.tb_next))
    if error is not None:
        return False, out.getvalue() + error
    if example["expected"] is None or out.getvalue() == example["expected"]:
        return True, ""
    return False, "".join(difflib.unified_diff(
        example["expected"].splitlines(True), out.getvalue().splitlines(True),
        "expected", "actual"))


def run_console(example, work, env):
    """Run one `$ command` under bash; return (passed, diff)."""
    prelude = f'structquery() {{ {shlex.quote(sys.executable)} -m structquery "$@"; }}\n'
    try:
        proc = subprocess.run(["bash", "-c", prelude + example["body"]], cwd=work, env=env,
                              stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, timeout=TIMEOUT)
        output = proc.stdout.decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        output = f"TIMEOUT after {TIMEOUT} s\n"
    # Keep what a terminal shows: a progress line rewritten with "\r" shows its last version.
    actual = [line.rsplit("\r", 1)[-1] for line in output.split("\n")]
    if actual[-1] == "":
        actual.pop()
    expected = example["expected"]
    if len(actual) == len(expected) and all(map(wildcard_match, expected, actual)):
        return True, ""
    # Show wildcard-matched lines as the expected text so that the diff shows only real differences.
    shown, j = [], 0
    for a in actual:
        k = next((k for k in range(j, len(expected)) if wildcard_match(expected[k], a)), None)
        shown.append(a if k is None else expected[k])
        j = j if k is None else k + 1
    return False, "\n".join(difflib.unified_diff(expected, shown, "expected", "actual",
                                                 lineterm="")) + "\n"


def child_env():
    """Environment for console commands: absolute PYTHONPATH, unbuffered, no bytecode files."""
    env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONDONTWRITEBYTECODE="1", COLUMNS="80")
    paths = env.get("PYTHONPATH", "").split(os.pathsep)
    env["PYTHONPATH"] = os.pathsep.join(os.path.abspath(p) for p in paths if p)
    return env


def check_file(path, env):
    """Run every example in one doc; return (run, passed, skipped, failures)."""
    files, examples, skipped = parse(path)
    root = tempfile.mkdtemp(prefix="check_docs_")
    namespace = {"__name__": "__main__"}
    failures, passed, old_cwd = [], 0, os.getcwd()
    try:
        for name, text in files.items():
            Path(root, name).write_text(text, encoding="utf-8")
        os.chdir(root)
        for ex in examples:
            if ex["kind"] == "python":
                ok, diff = run_python(ex, namespace, path)
            else:
                ok, diff = run_console(ex, root, env)
            passed += ok
            if not ok:
                failures.append((ex, diff))
    finally:
        os.chdir(old_cwd)
        namespace.clear()  # drop open Index/IndexBuilder objects before deleting their files
        gc.collect()
        shutil.rmtree(root, ignore_errors=True)
    return len(examples), passed, skipped, failures


def display(path):
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the examples in the docs and compare outputs.")
    parser.add_argument("files", nargs="*", help="markdown files (default: README.md, "
                        "docs/*.md, llms.txt, AGENTS.md)")
    args = parser.parse_args(argv)
    if args.files:
        paths = [Path(f).resolve() for f in args.files]
    else:
        paths = [p for pat in DEFAULT_FILES for p in sorted(REPO.glob(pat))]
    missing = [str(p) for p in paths if not p.is_file()]
    if missing:
        parser.error("no such file: " + ", ".join(missing))
    sys.path[:] = [os.path.abspath(p) for p in sys.path if p]  # examples run in a temp dir
    env = child_env()

    totals, all_failures = [0, 0, 0], []
    for path in paths:
        run, passed, skipped, failures = check_file(path, env)
        print(f"{display(path)}: {run} run, {passed} passed, {len(failures)} failed, "
              f"{skipped} skipped", flush=True)
        totals = [totals[0] + run, totals[1] + passed, totals[2] + len(failures)]
        all_failures += [(path, ex, diff) for ex, diff in failures]

    for path, ex, diff in all_failures:
        print(f"\nFAIL {display(path)}:{ex['line']}: {ex['label']}")
        print(diff, end="" if diff.endswith("\n") else "\n")
    print(f"\ntotal: {totals[0]} run, {totals[1]} passed, {totals[2]} failed "
          f"({len(paths)} files)")
    return 1 if all_failures else 0


if __name__ == "__main__":
    sys.exit(main())
