#!/usr/bin/env python3
"""Render a public, aggregated language chart using source-file sizes.

Only GitHub repository metadata and file trees are read. No code bodies, secrets,
private repository names, or per-repository measurements are published.
A repository token must already have read access to the desired repositories.
"""
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
ALLOWED_OWNERS = {"treenixie", "ritegear"}
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
    grand_total = sum(totals.values())
    if grand_total <= 0:
        raise RuntimeError("No source-file bytes found; keeping prior chart.")

    ordered = sorted(totals.items(), key=lambda entry: (-entry[1], entry[0]))
    # Test the 1% threshold against ALL measured languages before normalizing.
    visible = [(name, amount) for name, amount in ordered
               if amount > 0 and amount * 100 >= grand_total]
    if not visible:
        raise RuntimeError("No languages reached the display threshold; keeping prior chart.")

    # Bound the legend to two rows. Group only languages already >=1% if
    # more than eight qualify, so the bar and legend still cover the same data.
    top = visible if len(visible) <= 8 else [
        *visible[:7], ("Other", sum(amount for _, amount in visible[7:]))
    ]
    visible_total = sum(amount for _, amount in top)

    # Allocate one-decimal percentage units with the largest-remainder method.
    # The printed values sum to exactly 100.0%, even after rounding.
    percentage_units = []
    remainders = []
    for _, amount in top:
        whole, remainder = divmod(amount * 1000, visible_total)
        percentage_units.append(whole)
        remainders.append(remainder)
    extra_units = 1000 - sum(percentage_units)
    ranked = sorted(range(len(top)), key=lambda i: (-remainders[i], i))
    for i in ranked[:extra_units]:
        percentage_units[i] += 1

    s = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="104" viewBox="0 0 1000 104" role="img">',
        '<title>Language footprint</title>',
        '<desc>Languages with at least 1% of source-file bytes; percentages normalized to the displayed languages.</desc>',
        '<style>@media (prefers-color-scheme: light) { text { fill: #24292f; } }</style>',
    ]

    cumulative = []
    running = 0
    for i, (name, amount) in enumerate(top):
        running += amount
        cumulative.append((running / visible_total,
                           COLORS.get(name, FALLBACK_COLORS[i % len(FALLBACK_COLORS)])))

    # Same Tetris tile geometry as before, scaled from 660 to 1000 units.
    # Use the COLUMN coordinate for every row. This gives a proportional
    # left-to-right strip rather than misleading row-major color segments.
    strip_columns = 53
    strip_rows = 1
    tetris_scale = 1000 / 660
    strip_cell_width = 10 * tetris_scale
    strip_cell_height = 5 * tetris_scale
    strip_cell_radius = 1 * tetris_scale
    strip_step_x = 12.5 * tetris_scale
    strip_step_y = 7.5 * tetris_scale
    for row in range(strip_rows):
        for col in range(strip_columns):
            point = (col + .5) / strip_columns
            color = next((c for threshold, c in cumulative if point <= threshold),
                         cumulative[-1][1])
            s.append(
                '<rect x="{:.2f}" y="{:.2f}" width="{:.2f}" height="{:.2f}" rx="{:.2f}" fill="{}"/>'.format(
                    col * strip_step_x, row * strip_step_y,
                    strip_cell_width, strip_cell_height, strip_cell_radius, color
                )
            )

    legend_left = 0
    legend_right = 1000
    legend_columns = 4
    legend_gap = 20
    legend_width = (legend_right - legend_left - (legend_columns - 1) * legend_gap) // legend_columns
    legend_step = legend_width + legend_gap
    legend_marker_size = 10
    legend_marker_radius = 2
    legend_label_offset = 18
    legend_marker_y_offset = 10.5

    for i, (name, _) in enumerate(top):
        col, row = i % legend_columns, i // legend_columns
        x, y = legend_left + col * legend_step, 47 + row * 38
        percent_x = x + legend_width
        color = COLORS.get(name, FALLBACK_COLORS[i % len(FALLBACK_COLORS)])
        percent_label = "{:.1f}%".format(percentage_units[i] / 10)
        s.extend([
            '<rect x="{}" y="{}" width="{}" height="{}" rx="{}" fill="{}"/>'.format(
                x, y - legend_marker_y_offset, legend_marker_size, legend_marker_size, legend_marker_radius, color
            ),
            '<text x="{}" y="{}" font-family="-apple-system, BlinkMacSystemFont, &apos;Segoe UI&apos;, &apos;Noto Sans&apos;, Helvetica, Arial, sans-serif" font-size="15" font-weight="500" fill="#E4EDF5">{}</text>'.format(x + legend_label_offset, y, escape(name)),
            '<text x="{}" y="{}" text-anchor="end" font-family="ui-monospace,SFMono-Regular,&apos;SF Mono&apos;,Menlo,Consolas,&apos;Liberation Mono&apos;,monospace" font-size="15" fill="#E4EDF5">{}</text>'.format(percent_x, y, percent_label),
        ])

    if skipped:
        s.append('<text x="0" y="101" font-family="ui-monospace,SFMono-Regular,&apos;SF Mono&apos;,Menlo,Consolas,&apos;Liberation Mono&apos;,monospace" font-size="11" fill="#9BAFC2">PARTIAL DATA</text>')
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
