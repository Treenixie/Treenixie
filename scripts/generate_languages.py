#!/usr/bin/env python3
"""Render a public, aggregated language chart using source-file sizes.

Only GitHub repository metadata and file trees are read. No code bodies, secrets,
private repository names, or per-repository measurements are published.
A repository token must already have read access to the desired repositories.
"""
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path
from xml.sax.saxutils import escape

API = "https://api.github.com"
ALLOWED_OWNERS = {"treenixie", "ritegear", "avelea-app"}
EXCLUDE_NAMES = {".github", "treenixie"}
SKIP_DIRS = {
    ".git", ".github", ".dart_tool", ".idea", ".vscode", "node_modules",
    "build", "dist", "vendor", "coverage", "generated",
    "android", "ios", "macos", "windows", "linux", ".next",
    "__pycache__", "assets", "branding", "docs", "public"
}
EXTENSIONS = {
    ".ts": "TypeScript", ".tsx": "TypeScript",
    ".dart": "Dart", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".js": "JavaScript", ".jsx": "JavaScript",
    ".py": "Python", ".tf": "HCL", ".tfvars": "HCL",
    ".css": "CSS", ".scss": "SCSS", ".html": "HTML",
    ".sql": "SQL", ".sh": "Shell", ".ps1": "PowerShell",
    ".lua": "Lua", ".cpp": "C++", ".cc": "C++", ".c": "C",
    ".cs": "C#", ".go": "Go", ".rs": "Rust", ".kt": "Kotlin",
    ".swift": "Swift", ".java": "Java", ".rb": "Ruby",
    ".php": "PHP", ".ex": "Elixir", ".exs": "Elixir",
}
COLORS = {
    "TypeScript": "#5B92EA", "Dart": "#5FD3DB", "JavaScript": "#E8C35F",
    "Python": "#8FC678", "HCL": "#B597F5", "CSS": "#EFA1C0",
    "SCSS": "#DF8BAA", "HTML": "#F29365", "SQL": "#7DC1D3",
    "C++": "#C4A0EE", "Shell": "#8DAD86", "PowerShell": "#73B6E9",
    "Lua": "#8B8DF7", "C": "#ABB8C9", "Go": "#4FC3C0",
    "Other": "#607084"
}
FALLBACK_COLORS = ["#F3A37E", "#A6C0E6", "#C3CE88", "#A397D9"]

def api_get(endpoint, token):
    request = urllib.request.Request(
        API + endpoint,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + token,
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Treenixie-profile-language-chart",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError("GitHub API returned HTTP " + str(exc.code)) from None

def all_repos(token):
    repos = []
    for page in range(1, 11):
        path = "/user/repos?visibility=all&affiliation=owner,organization_member&per_page=100&page=" + str(page)
        batch = api_get(path, token)
        if not isinstance(batch, list):
            raise RuntimeError("Unexpected repository list response")
        repos.extend(batch)
        if len(batch) < 100:
            break
    selected = []
    for item in repos:
        owner = (item.get("owner") or {}).get("login", "").lower()
        name = item.get("name", "").lower()
        if owner not in ALLOWED_OWNERS or name in EXCLUDE_NAMES:
            continue
        if item.get("archived") or item.get("fork") or item.get("disabled"):
            continue
        selected.append(item)
    return selected

def scan(token):
    totals = defaultdict(int)
    count = 0
    skipped = 0
    for repo in all_repos(token):
        slug = repo["full_name"]
        ref = urllib.parse.quote(repo["default_branch"], safe="")
        try:
            tree = api_get("/repos/" + slug + "/git/trees/" + ref + "?recursive=1", token)
            if tree.get("truncated"):
                skipped += 1
                continue
        except RuntimeError:
            skipped += 1
            continue
        saw_source = False
        for entry in tree.get("tree", []):
            if entry.get("type") != "blob":
                continue
            path = entry.get("path", "")
            components = path.lower().split("/")
            if any(component in SKIP_DIRS for component in components[:-1]):
                continue
            if ".min." in path.lower() or path.endswith(".g.dart"):
                continue
            filename = components[-1]
            suffix = "." + filename.rsplit(".", 1)[-1] if "." in filename else ""
            language = EXTENSIONS.get(suffix)
            if language:
                totals[language] += int(entry.get("size") or 0)
                saw_source = True
        if saw_source:
            count += 1
    if not count or not sum(totals.values()):
        raise RuntimeError("No accessible source repositories were found; keeping prior chart.")
    return totals, count, skipped

def svg_chart(totals, count, skipped):
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    grand_total = sum(totals.values())
    ordered = sorted(totals.items(), key=lambda entry: (-entry[1], entry[0]))
    top = ordered[:7]
    remainder = sum(value for _, value in ordered[7:])
    if remainder:
        top.append(("Other", remainder))
    w, h = 1000, 242
    s = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="242" viewBox="0 0 1000 242" role="img">',
        '<title>Live language footprint by source-file size</title>',
        '<desc>Aggregated source file sizes across accessible active repositories.</desc>',
        '<rect width="1000" height="242" rx="15" fill="#111923"/>',
        '<rect x="1" y="1" width="998" height="240" rx="14" fill="none" stroke="#354456"/>',
        '<text x="36" y="40" font-family="Arial,Helvetica,sans-serif" font-size="25" fill="#F2F6FA" font-weight="800">LANGUAGE FOOTPRINT</text>',
        '<text x="36" y="61" font-family="Consolas,monospace" font-size="12" fill="#9FB3C5">SOURCE FILE BYTES</text>',
        '<rect x="846" y="25" width="119" height="24" rx="6" fill="#1B2939"/>',
        '<text x="905" y="42" text-anchor="middle" font-family="Consolas,monospace" font-size="12" fill="#77DDD4">' + str(count) + ' CODEBASES</text>',
    ]
    # Same compact cells and spacing as the animated Tetris calendar.
    cells = 53 * 3
    cumulative = []
    running = 0
    for i, (name, amount) in enumerate(top):
        running += amount
        cumulative.append((running / grand_total, name, COLORS.get(name, FALLBACK_COLORS[i % len(FALLBACK_COLORS)])))
    for index in range(cells):
        col = index % 53
        row = index // 53
        x = 36 + col * 17.5
        y = 81 + row * 10
        t = (index + 0.5) / cells
        color = "#202A37"
        for threshold, name, item_color in cumulative:
            if t <= threshold:
                color = item_color
                break
        s.append('<rect x="{:.1f}" y="{}" width="12" height="6" rx="1" fill="{}"/>'.format(x, y, color))
    for i, (name, amount) in enumerate(top):
        col, row = i % 4, i // 4
        x, y = 36 + col * 238, 155 + row * 40
        color = COLORS.get(name, FALLBACK_COLORS[i % len(FALLBACK_COLORS)])
        s.extend([
            '<rect x="{}" y="{}" width="12" height="12" rx="2" fill="{}"/>'.format(x, y - 11, color),
            '<text x="{}" y="{}" font-family="Consolas,monospace" font-size="15" font-weight="600" fill="#E4EDF5">{}</text>'.format(x + 23, y, escape(name)),
            '<text x="{}" y="{}" text-anchor="end" font-family="Consolas,monospace" font-size="15" fill="#E4EDF5">{:.1f}%</text>'.format(x + 213, y, 100 * amount / grand_total),
        ])
    if skipped:
        s.append('<text x="36" y="227" font-family="Consolas,monospace" font-size="11" fill="#AEBCCB">Partial: ' + str(skipped) + ' repositories not accessible</text>')
    s.append('</svg>')
    return "\n".join(s) + "\n"

def main():
    token = os.environ.get("PROFILE_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("No existing GitHub API token available")
    totals, count, skipped = scan(token)
    destination = Path("generated-languages")
    destination.mkdir(exist_ok=True)
    destination.joinpath("languages.svg").write_text(svg_chart(totals, count, skipped), encoding="utf-8")
    print("Rendered language chart from " + str(count) + " accessible codebases.")
    if skipped:
        print(str(skipped) + " repositories inaccessible, partial coverage noted in chart.")

if __name__ == "__main__":
    main()
