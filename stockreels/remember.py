"""Commit this run's state files without losing another run's update.

Two shows can finish within seconds of each other (on 2026-10-19 the hot stock and הידעת?
both edited episodes.json and the second push hit a rebase conflict, so its episode counter
was lost). Instead of rebasing, this takes main as it is now and merges our changes into it:
dict keys are combined (counters keep the higher number), list entries are appended if new.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = ["history.json", "episodes.json", "setups.json", "slots.json", "posted.json"]


def merge(theirs, ours):
    if isinstance(theirs, dict) and isinstance(ours, dict):
        out = dict(theirs)
        for k, v in ours.items():
            if isinstance(v, (int, float)) and isinstance(out.get(k), (int, float)):
                out[k] = max(out[k], v)
            else:
                out[k] = v
        return out
    if isinstance(theirs, list) and isinstance(ours, list):
        return theirs + [x for x in ours if x not in theirs]
    return ours


def git(*args, check=False):
    return subprocess.run(["git", *args], cwd=ROOT, check=check, capture_output=True, text=True)


def main(message):
    # only files this run changed: an untouched file here may be older than main's copy
    changed = set(git("diff", "--name-only", "HEAD").stdout.split()) | set(
        git("ls-files", "--others", "--exclude-standard").stdout.split())
    ours = {f: json.loads((ROOT / f).read_text()) for f in FILES if f in changed and (ROOT / f).exists()}
    if not ours:
        print("[remember] nothing changed")
        return
    for attempt in range(5):
        git("fetch", "-q", "origin", "main", check=True)
        git("reset", "-q", "--hard", "FETCH_HEAD", check=True)
        for f, data in ours.items():
            p = ROOT / f
            merged = merge(json.loads(p.read_text()), data) if p.exists() else data
            p.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n")
            git("add", f)
        if git("diff", "--cached", "--quiet").returncode == 0:
            print("[remember] nothing new to commit")
            return
        git("commit", "-q", "-m", message, check=True)
        if git("push", "-q", "origin", "HEAD:main").returncode == 0:
            print(f"[remember] pushed: {message}")
            return
        time.sleep(3 * (attempt + 1))
    sys.exit("[remember] could not push the state files")


if __name__ == "__main__":
    main(" ".join(sys.argv[1:]) or "state")
