#!/usr/bin/env python3
"""Ask the bot the cases in ops/eval-cases.txt several times each and check every answer.

Uses ops/test.sh, so it tests the local data/ in a throwaway container on the server (only the NEAR AI
key, never a bot token). Answers vary between runs, so each case is asked --runs times and a
regression case passes only if every run passes. deploy.sh runs the regression cases before deploying.

  ops/eval.py                                    all cases, 3 runs each
  ops/eval.py --only regression                  what deploy.sh runs
  ops/eval.py --model Qwen/Qwen3.6-35B-A3B-FP8   the same cases on another NEAR AI model

A case with a date is asked as if it were then (ops/test.sh's FAKE_DATE), in a test.sh run of its own.

Exits 1 if a regression case failed. Every answer is saved to a file to read, not just counted.
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

OPS = Path(__file__).resolve().parent
EXCERPT = 160


def load_cases(path):
    """[{"kind", "q", "must": [regex], "not": [regex], "max": int|None, "date": str|None}] from the cases file."""
    cases, kind, case = [], None, None
    for line in path.read_text().splitlines() + [""]:
        if line.startswith("## "):
            kind = line[3:].strip()
        elif line.startswith("Q: "):
            case = {"kind": kind, "q": line[3:].strip(), "must": [], "not": [], "max": None, "date": None}
            cases.append(case)
        elif case and line.startswith(("must: ", "not: ", "max: ", "date: ")):
            key, value = line.split(": ", 1)
            if key == "max":
                case["max"] = int(value)
            elif key == "date":
                case["date"] = value.strip()
            else:
                case[key].append(re.compile(value.strip(), re.I | re.M))
        elif not line.strip():
            case = None
    return cases


def problems(case, answer):
    found = [f"missing /{p.pattern}/" for p in case["must"] if not p.search(answer)]
    found += [f"has /{p.pattern}/: {m.group(0)!r}" for p in case["not"] if (m := p.search(answer))]
    if case["max"] and len(answer) > case["max"]:
        found.append(f"{len(answer)} chars > {case['max']}")
    return found


def when(case):
    return f"[on {case['date']}] " if case["date"] else ""


def ask(questions, model, date=None):
    """Answers in order, via ops/test.sh. Each question is one line, so test.sh's echo of it is exact."""
    env = dict(os.environ, MODEL=model or "", FAKE_DATE=date or "")
    run = subprocess.run([str(OPS / "test.sh"), *questions], env=env, capture_output=True, text=True)
    blocks = re.split(r"^=== .*$", run.stdout, flags=re.M)[1:]
    if len(blocks) != len(questions):
        sys.exit(f"expected {len(questions)} answers, got {len(blocks)}; ops/test.sh exited {run.returncode}, "
                 f"its output ends:\n{run.stdout[-2000:]}\n{run.stderr[-2000:]}")
    return ["\n".join(l for l in b.splitlines() if l.strip()) for b in blocks]


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--only", choices=["regression", "capability"])
    parser.add_argument("--model", help="a NEAR AI model id; default: model.default in data/config.yaml")
    parser.add_argument("--cases", type=Path, default=OPS / "eval-cases.txt")
    args = parser.parse_args()

    cases = [c for c in load_cases(args.cases) if not args.only or c["kind"] == args.only]
    asked = [c for _ in range(args.runs) for c in cases]
    start = time.time()
    answers = [None] * len(asked)
    for date in dict.fromkeys(c["date"] for c in asked):  # one test.sh run per date
        idx = [i for i, c in enumerate(asked) if c["date"] == date]
        for i, a in zip(idx, ask([asked[i]["q"] for i in idx], args.model, date)):
            answers[i] = a
    elapsed = time.time() - start

    label = args.model or "data/config.yaml model"
    saved = Path(tempfile.gettempdir()) / f"hack-bot-eval-{re.sub(r'[^A-Za-z0-9.-]+', '_', label)}.txt"
    failed_regression = 0
    with saved.open("w") as out:
        for kind in dict.fromkeys(c["kind"] for c in cases):
            group = [c for c in cases if c["kind"] == kind]
            print(f"\n{kind}: {len(group)} cases x {args.runs} runs")
            passed = 0
            for case in group:
                runs = [(a, problems(case, a)) for c, a in zip(asked, answers) if c is case]
                for i, (a, p) in enumerate(runs, 1):
                    out.write(f"=== [{kind}] run {i} {'PASS' if not p else 'FAIL: ' + '; '.join(p)}\n{when(case)}{case['q']}\n---\n{a}\n\n")
                ok = sum(not p for _, p in runs)
                passed += ok == len(runs)
                if ok < len(runs):
                    print(f"  {ok}/{len(runs)}  {when(case)}{case['q'][:70]}")
                    for a, p in runs:
                        if p:
                            print(f"        {'; '.join(p)}\n        > {a[:EXCERPT].replace(chr(10), ' ')}")
            print(f"  {passed}/{len(group)} cases passed every run")
            if kind == "regression":
                failed_regression = len(group) - passed

    lengths = [len(a) for a in answers]
    print(f"\n{label}: {len(answers)} answers, {sum(lengths) // len(lengths)} chars on average, "
          f"{elapsed / len(answers):.1f}s per answer (including container startup)")
    print(f"every answer: {saved}")
    sys.exit(1 if failed_regression else 0)


if __name__ == "__main__":
    main()
