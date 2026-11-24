"""Check that structquery returns exactly what stock Indri returns.

Builds one small TREC-text corpus from a JSONL file, indexes it twice (stock IndriBuildIndex and
structquery), runs the same queries through stock IndriRunQuery and through structquery, and compares
rankings and scores. Needs the reference tools from scripts/build_indri_ref.sbatch.

    python scripts/parity_check.py --jsonl CORPUS.jsonl --ref-bin scratchspace/indripy/indri-ref/bin \
        --work scratchspace/indripy/parity
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

import structquery

QUERIES = {
    "1": "#combine(university student)",
    "2": "#1(new york)",
    "3": "#weight(0.7 #combine(music album) 0.3 #uw8(released album))",
    "4": "#combine(#syn(film movie) director running)",
    "5": "#band(history war)",
    "6": "#combine(#od3(united states) president studies)",
    "7": "#filreq(#1(new york) #combine(city population))",
    "8": "international development houses",
}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--jsonl", required=True)
    ap.add_argument("--ref-bin", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--docs", type=int, default=300)
    ap.add_argument("--skip", type=int, default=0, help="skip this many leading lines of the JSONL")
    ap.add_argument("--k", type=int, default=50)
    ap.add_argument("--timeout", type=int, default=120)
    a = ap.parse_args()

    work = os.path.abspath(a.work)
    if os.path.isdir(work):
        shutil.rmtree(work)
    os.makedirs(work)
    corpus = os.path.join(work, "corpus.trectext")
    n = 0
    with open(a.jsonl, encoding="utf-8") as fh, open(corpus, "w", encoding="utf-8") as out:
        for i, line in enumerate(fh):
            if i < a.skip:
                continue
            if n >= a.docs:
                break
            o = json.loads(line)
            text = re.sub(r"[<>&]", " ", o["text"])[:20000]
            out.write(f"<DOC>\n<DOCNO>{o['docid']}</DOCNO>\n<TEXT>\n{text}\n</TEXT>\n</DOC>\n")
            n += 1

    ref_index = os.path.join(work, "ref_index")
    with open(os.path.join(work, "build.xml"), "w") as f:
        f.write(f"<parameters><index>{ref_index}</index><memory>512M</memory><corpus><path>{corpus}</path>"
                "<class>trectext</class></corpus><stemmer><name>krovetz</name></stemmer></parameters>\n")
    r = subprocess.run([os.path.join(a.ref_bin, "IndriBuildIndex"), os.path.join(work, "build.xml")],
                       capture_output=True, text=True, timeout=a.timeout)
    if r.returncode != 0:
        sys.exit(f"stock IndriBuildIndex failed (exit {r.returncode}); is it built with the patches?\n{r.stdout[-500:]}")
    with open(os.path.join(work, "q.xml"), "w") as f:
        f.write(f"<parameters><index>{ref_index}</index><count>{a.k}</count><trecFormat>true</trecFormat>\n")
        for qid, q in QUERIES.items():
            f.write(f"<query><number>{qid}</number><text>{q}</text></query>\n")
        f.write("</parameters>\n")
    r = subprocess.run([os.path.join(a.ref_bin, "IndriRunQuery"), os.path.join(work, "q.xml")],
                       capture_output=True, text=True, timeout=a.timeout)
    if r.returncode != 0:
        sys.exit(f"stock IndriRunQuery failed (exit {r.returncode}): {r.stderr[-500:]}")
    ref = {}
    for line in r.stdout.splitlines():
        p = line.split()
        if len(p) == 6:
            ref.setdefault(p[0], []).append((p[2], float(p[4])))

    py_index = os.path.join(work, "py_index")
    with structquery.IndexBuilder(py_index, stemmer="krovetz", memory="512M") as b:
        b.add_files(corpus, "trectext")

    ok = True
    for label, path in (("structquery index + structquery search", py_index),
                        ("stock index   + structquery search", ref_index)):
        with structquery.Index(path) as idx:
            total = same = 0
            maxdiff = 0.0
            for qid, q in QUERIES.items():
                got = [(h.docid, h.score) for h in idx.search(q, k=a.k)]
                exp = ref.get(qid, [])
                total += max(len(got), len(exp))
                same += sum(1 for g, e in zip(got, exp) if g[0] == e[0])
                maxdiff = max([maxdiff] + [abs(g[1] - e[1]) for g, e in zip(got, exp)])
            good = same == total and maxdiff < 1e-4 and total > 0
            ok &= good
            print(f"{'PASS' if good else 'FAIL'}  {label}: {same}/{total} rank positions identical, "
                  f"max |score diff| = {maxdiff:.2e}  ({len(idx)} docs)")
    print(f"reference hits per query: { {q: len(v) for q, v in ref.items()} }")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
