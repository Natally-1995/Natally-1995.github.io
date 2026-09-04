#!/usr/bin/env python3
"""
Fetches recent public commits and merged PRs for the repos listed in repos.json
and writes them to data/activity.json for the site to render.

Runs inside GitHub Actions using the workflow-provided GITHUB_TOKEN — this
token never leaves the Actions runner and is never embedded in the site.
The output is plain, static JSON with no credentials in it.

Fails gracefully: if the API is unreachable or a repo has no recent activity,
writes an empty (but valid) list rather than crashing the build.
"""
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

API = "https://api.github.com"
TOKEN = os.environ.get("GITHUB_TOKEN", "")

# The portfolio repo is never eligible for the feed, no matter what's in
# repos.json. Its commits are about building this site, not engineering
# work — mixing the two defeats the point of the feed. Enforced here rather
# than by convention, so a future edit to repos.json can't reintroduce it.
EXCLUDED_REPOS = {"natally-1995/natally-1995.github.io"}


def gh(path):
    req = urllib.request.Request(API + path)
    req.add_header("Accept", "application/vnd.github+json")
    if TOKEN:
        req.add_header("Authorization", "Bearer " + TOKEN)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.load(r)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        print(f"  warn: {path} failed ({e})", file=sys.stderr)
        return None


def relative_when(iso_ts):
    try:
        dt = datetime.strptime(iso_ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return ""
    days = (datetime.now(timezone.utc) - dt).days
    if days <= 0:
        return "today"
    if days == 1:
        return "1 day ago"
    if days < 30:
        return f"{days} days ago"
    months = days // 30
    return f"{months} mo ago"


def fetch_repo_activity(repo, limit):
    # The portfolio repo itself never qualifies as "recent work" — its commits
    # are about building this site, not engineering work worth showing a
    # recruiter. This guard applies even if it's ever added to repos.json.
    EXCLUDED = {"natally-1995/natally-1995.github.io"}
    if repo.lower() in EXCLUDED:
        print(f"  skipping {repo}: portfolio repo is permanently excluded from the feed", file=sys.stderr)
        return []

    items = []

    commits = gh(f"/repos/{repo}/commits?per_page={limit}") or []
    for c in commits:
        msg = (c.get("commit", {}) or {}).get("message", "").split("\n")[0]
        date = (c.get("commit", {}) or {}).get("author", {}).get("date", "")
        if not msg:
            continue
        items.append({
            "kind": "commit",
            "desc": msg[:90],
            "repo": repo.split("/")[-1],
            "url": c.get("html_url", f"https://github.com/{repo}"),
            "ts": date,
            "when": relative_when(date),
        })

    prs = gh(f"/repos/{repo}/pulls?state=closed&per_page={limit}") or []
    for p in prs:
        if not p.get("merged_at"):
            continue
        title = p.get("title", "")
        date = p.get("merged_at", "")
        if not title:
            continue
        items.append({
            "kind": "pr",
            "desc": title[:90],
            "repo": repo.split("/")[-1],
            "url": p.get("html_url", f"https://github.com/{repo}"),
            "ts": date,
            "when": relative_when(date),
        })

    return items


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "repos.json")) as f:
        cfg = json.load(f)

    repos = cfg.get("repos", [])
    max_items = cfg.get("max_items", 8)

    all_items = []
    for repo in repos:
        if repo.strip().lower() in EXCLUDED_REPOS:
            print(f"skipping {repo} — portfolio repo is permanently excluded from the feed")
            continue
        print(f"fetching {repo}...")
        all_items.extend(fetch_repo_activity(repo, max_items))

    # newest first, real timestamps only
    all_items = [i for i in all_items if i.get("ts")]
    all_items.sort(key=lambda i: i["ts"], reverse=True)
    all_items = all_items[:max_items]

    for i in all_items:
        i.pop("ts", None)  # not needed client-side, keeps the payload small

    out_dir = os.path.join(here, "data")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "activity.json")
    with open(out_path, "w") as f:
        json.dump(all_items, f, indent=2)

    print(f"wrote {len(all_items)} item(s) to {out_path}")


if __name__ == "__main__":
    main()
