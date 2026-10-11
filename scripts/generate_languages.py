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
    s = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="350" viewBox="0 0 1000 350" role="img">',
        '<title>Programming language footprint by source file size</title>',
        '<desc>Aggregate source file sizes across accessible active repositories, updated automatically.</desc>',
        '<rect width="1000" height="350" rx="15" fill="#111923"/>',
        '<rect x="1" y="1" width="998" height="348" rx="15" fill="none" stroke="#364457"/>',
        '<text x="35" y="46" fill="#F2F6FA" font-family="Arial,sans-serif" font-size="25" font-weight="800">LANGUAGE FOOTPRINT</text>',
        '<text x="35" y="73" fill="#95ADBD" font-family="Consolas,monospace" font-size="13">SOURCE FILE BYTES / ACTIVE REPOSITORIES</text>',
        '<text x="964" y="46" text-anchor="end" fill="#79DCCB" font-family="Consolas,monospace" font-size="13">' + str(count) + ' CODEBASES</text>',
        '<text x="964" y="72" text-anchor="end" fill="#A8B8C9" font-family="Consolas,monospace" font-size="12">UPDATED ' + now + '</text>',
        '<rect x="35" y="100" width="930" height="34" rx="6" fill="#263240"/>'
    ]
    cursor = 35.0
    for i, (name, amount) in enumerate(top):
        width = 930.0 * amount / grand_total
        color = COLORS.get(name, FALLBACK_COLORS[i % len(FALLBACK_COLORS)])
        s.append('<rect x="{:.2f}" y="100" width="{:.2f}" height="34" fill="{}"/>'.format(cursor, width, color))
        cursor += width
    for i, (name, amount) in enumerate(top):
        col = i % 2
        row = i // 2
        x = 37 + col * 486
        y = 183 + row * 36
        color = COLORS.get(name, FALLBACK_COLORS[i % len(FALLBACK_COLORS)])
        label = escape(name)
        percent = 100 * amount / grand_total
        s += [
            '<rect x="{}" y="{}" width="12" height="12" rx="2" fill="{}"/>'.format(x, y-11, color),
            '<text x="{}" y="{}" font-family="Consolas,monospace" font-weight="600" font-size="17" fill="#DBE5EC">{}</text>'.format(x+23, y, label),
            '<text x="{}" y="{}" font-family="Consolas,monospace" text-anchor="end" font-size="16" fill="#D8E0EC">{:.1f}%</text>'.format(x+440, y, percent),
        ]
    s.append('<path d="M35 316 H965" stroke="#354456"/>')
    footnote = "Based on tracked source-file extensions, not GitHub Linguist or commit counts"
    if skipped:
        footnote += " · " + str(skipped) + " repositories inaccessible"
    s.append('<text x="35" y="337" font-family="Consolas,monospace" fill="#92A8B9" font-size="12">' + escape(footnote) + '</text>')
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
