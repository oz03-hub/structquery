"""Extract -> validate -> search -> feedback loop for LLM-written Indri queries.

No network and no LLM needed: `call_llm` below returns canned responses. To use a real model,
replace only `call_llm(prompt) -> str`.

    python examples/llm_query_loop.py                               # two built-in samples
    python examples/llm_query_loop.py --llm-output 'x <query>#1(white house)</query>'
"""
import argparse
import os
import tempfile

import structquery

DOCS = {
    "d1": {"title": "White House press briefing", "body": "The press secretary spoke at the White House about the economy."},
    "d2": {"title": "Housing market", "body": "House prices rose. The white paint on the old house was new."},
    "d3": {"title": "U.S. economy in 2020", "body": "The U.S. GDP fell in 2020 and recovered in 2021."},
    "d4": {"title": "Cats and dogs", "body": "Dogs chase cats. A cat sleeps while the dog runs."},
}

SAMPLE_GOOD = """The user wants briefings at the White House about the economy.
<query>#combine(#1(white house) economy press)</query>"""

SAMPLE_BROKEN = """Let me search for the U.S. economy.
<query>#combine(U.S. economy, what's new?)</query>"""

PROMPT = """Write an Indri query for the request below. Put it inside <query></query>.
Use lowercase operators (#combine, #weight, #1, #uwN, #syn, #band, #filreq, #filrej),
plain words with no punctuation, and term.field for fields ({fields}).
Request: {request}"""


def call_llm(prompt: str, canned: list) -> str:
    """Swap this for a real model call. Here it returns canned replies in order."""
    return canned.pop(0) if canned else "<query>#combine(economy)</query>"


def feedback(query, error) -> str:
    """The message sent back to the model when its query is unusable."""
    if query is None:
        return "No <query>...</query> block found. Answer with exactly one <query> block."
    return (f"Your query was rejected by the Indri parser.\nQuery: {query}\nError: {error}\n"
            "Remove punctuation inside words (U.S. -> us, what's -> whats), drop commas and "
            "question marks, and balance parentheses. Answer with a new <query> block.")


def run_loop(idx, request, canned, max_turns=3, k=5):
    prompt = PROMPT.format(fields=", ".join(idx.fields) or "none", request=request)
    for turn in range(1, max_turns + 1):
        reply = call_llm(prompt, canned)
        query = structquery.extract_query(reply)
        error = None
        if query is not None:
            try:
                structquery.validate(query)
            except structquery.QuerySyntaxError as e:
                error = str(e)
        if query is None or error:
            msg = feedback(query, error)
            print(f"turn {turn}: rejected {query!r}\n  feedback -> {msg.splitlines()[0]} {error or ''}")
            prompt += "\n\n" + msg
            continue
        hits = idx.search(query, k=k)
        print(f"turn {turn}: ran {query!r}")
        for h in hits:
            print(f"  {h.rank} {h.docid} {h.score:.3f}")
        return query, hits
    fallback = structquery.bag_of_words(request)
    print(f"giving up after {max_turns} turns; bag-of-words fallback {fallback!r}")
    return fallback, idx.search(fallback, k=k)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--llm-output", action="append",
                    help="a model reply to process (repeatable; default: two built-in samples)")
    ap.add_argument("--request", default="White House briefings about the economy")
    ap.add_argument("--index", help="index directory to create (default: a new temp directory)")
    a = ap.parse_args()
    path = a.index or os.path.join(tempfile.mkdtemp(prefix="structquery_llm_"), "index")
    with structquery.IndexBuilder(path, fields=["title", "body"]) as b:
        for docid, doc in DOCS.items():
            b.add(docid, doc)

    with structquery.Index(path) as idx:
        if a.llm_output:
            run_loop(idx, a.request, list(a.llm_output))
        else:
            print("== sample 1: valid query")
            run_loop(idx, a.request, [SAMPLE_GOOD])
            print("== sample 2: broken query, then the model's corrected reply")
            run_loop(idx, a.request, [SAMPLE_BROKEN, "<query>#combine(us economy whats new)</query>"])


if __name__ == "__main__":
    main()
