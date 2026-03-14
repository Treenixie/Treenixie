from pathlib import Path
import os
import calendar as cal
import datetime as dt
import hashlib
import json
import requests

GRAPHQL_URL = "https://api.github.com/graphql"

GRAPHQL_QUERY = """
query($from: DateTime!, $to: DateTime!) {
  viewer {
    login
    contributionsCollection(from: $from, to: $to) {
      hasAnyRestrictedContributions
      restrictedContributionsCount
      earliestRestrictedContributionDate
      contributionCalendar {
        totalContributions
        weeks {
          firstDay
          contributionDays {
            contributionCount
            contributionLevel
            date
            weekday
          }
        }
      }
    }
  }
}
"""

LEVEL_MAP = {
    "NONE": 0,
    "FIRST_QUARTILE": 1,
    "SECOND_QUARTILE": 2,
    "THIRD_QUARTILE": 3,
    "FOURTH_QUARTILE": 4,
}

THEMES = {
    "dark": {
        "bg": "#0d1117",
        "border": "#30363d",
        "divider": "#21262d",
        "text": "#c9d1d9",
        "muted": "#8b949e",
        "greens": ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"],
    },
    "light": {
        "bg": "#ffffff",
        "border": "#d0d7de",
        "divider": "#d8dee4",
        "text": "#24292f",
        "muted": "#57606a",
        "greens": ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"],
    },
}

CANVAS_W = 767
CANVAS_H = 220

CARD_X = 8
CARD_Y = 8
CARD_W = CANVAS_W - 16
CARD_H = CANVAS_H - 16
CARD_RIGHT = CARD_X + CARD_W
CARD_BOTTOM = CARD_Y + CARD_H

GRID_X = 60
GRID_Y = 72
CELL = 10
GAP = 3
STEP = CELL + GAP

COLS = 53
ROWS = 7

FONT_STACK = '-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif,"Apple Color Emoji","Segoe UI Emoji"'


def svg_rect(x, y, w, h, fill, rx=2, extra=""):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" ry="{rx}" fill="{fill}" {extra}/>'


def svg_text(
    x,
    y,
    text,
    fill,
    size=12,
    weight="400",
    anchor="start",
    baseline="alphabetic",
    family=FONT_STACK,
):
    safe = (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    return (
        f'<text x="{x}" y="{y}" fill="{fill}" '
        f'font-family="{family}" '
        f'font-size="{size}" font-weight="{weight}" '
        f'text-anchor="{anchor}" dominant-baseline="{baseline}">{safe}</text>'
    )


def cell_rect(col, row):
    x = GRID_X + col * STEP
    y = GRID_Y + row * STEP
    return x, y, CELL, CELL


def choose_token():
    token = os.getenv("PROFILE_TOKEN") or os.getenv("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("Не найден токен. Нужен PROFILE_TOKEN в secrets.")
    return token


def fetch_calendar(username, token):
    today = dt.datetime.utcnow().date()
    start = today - dt.timedelta(days=370)

    response = requests.post(
        GRAPHQL_URL,
        headers={
            "Authorization": f"bearer {token}",
            "Accept": "application/vnd.github+json",
        },
        json={
            "query": GRAPHQL_QUERY,
            "variables": {
                "from": f"{start.isoformat()}T00:00:00Z",
                "to": f"{today.isoformat()}T23:59:59Z",
            },
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()

    if "errors" in payload:
        raise RuntimeError(f"GitHub GraphQL error: {payload['errors']}")

    viewer = payload.get("data", {}).get("viewer")
    if not viewer:
        raise RuntimeError("GitHub не вернул viewer. Проверь PROFILE_TOKEN.")

    if viewer.get("login", "").lower() != username.lower():
        raise RuntimeError(
            f"PROFILE_TOKEN авторизован не как {username}, а как {viewer.get('login')}. "
            "Токен должен принадлежать аккаунту Treenixie."
        )

    collection = viewer["contributionsCollection"]
    calendar = collection["contributionCalendar"]

    diagnostics = {
        "viewer_login": viewer["login"],
        "has_any_restricted_contributions": collection.get("hasAnyRestrictedContributions"),
        "restricted_contributions_count": collection.get("restrictedContributionsCount"),
        "earliest_restricted_contribution_date": collection.get("earliestRestrictedContributionDate"),
    }

    return calendar, diagnostics


def pad_weeks(weeks):
    if len(weeks) >= COLS:
        return weeks[-COLS:]

    missing = COLS - len(weeks)
    first_day = dt.date.fromisoformat(weeks[0]["firstDay"])
    padding = []

    for i in range(missing, 0, -1):
        week_start = first_day - dt.timedelta(days=7 * i)
        contribution_days = []
        for j in range(7):
            day = week_start + dt.timedelta(days=j)
            contribution_days.append(
                {
                    "contributionCount": 0,
                    "contributionLevel": "NONE",
                    "date": day.isoformat(),
                    "weekday": j,
                }
            )
        padding.append(
            {
                "firstDay": week_start.isoformat(),
                "contributionDays": contribution_days,
            }
        )

    return padding + weeks


def normalize_calendar(calendar_data):
    weeks = pad_weeks(calendar_data["weeks"])

    board = [[0 for _ in range(COLS)] for _ in range(ROWS)]
    raw_days = []
    month_labels = []
    prev_month = None

    for col, week in enumerate(weeks):
        week_start = dt.date.fromisoformat(week["firstDay"])
        month_name = cal.month_abbr[week_start.month]
        if month_name != prev_month:
            month_labels.append((month_name, col))
            prev_month = month_name

        for day in week["contributionDays"]:
            day_date = dt.date.fromisoformat(day["date"])
            row = (day_date.weekday() + 1) % 7
            level = LEVEL_MAP.get(day["contributionLevel"], 0)
            count = int(day["contributionCount"])

            board[row][col] = level
            raw_days.append(
                {
                    "date": day["date"],
                    "col": col,
                    "row": row,
                    "level": level,
                    "count": count,
                }
            )

    total = int(calendar_data["totalContributions"])
    active_cells = sum(1 for item in raw_days if item["level"] > 0)

    hash_source = {
        "total": total,
        "days": [
            [item["date"], item["col"], item["row"], item["level"], item["count"]]
            for item in raw_days
        ],
    }

    calendar_hash = hashlib.sha256(
        json.dumps(hash_source, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()

    return board, month_labels, total, active_cells, calendar_hash


def render_svg(theme_name, board, month_labels, total, active_cells, username):
    theme = THEMES[theme_name]
    parts = []

    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS_W}" height="{CANVAS_H}" '
        f'viewBox="0 0 {CANVAS_W} {CANVAS_H}" shape-rendering="geometricPrecision" text-rendering="geometricPrecision">'
    )
    parts.append(svg_rect(0, 0, CANVAS_W, CANVAS_H, theme["bg"], rx=0))
parts.append(
    svg_rect(
        CARD_X,
        CARD_Y,
        CARD_W,
        CARD_H,
        theme["bg"],
        rx=6,
        extra=f'stroke="{theme["border"]}" stroke-width="1"',
    )
)

# Верхняя строка
parts.append(
    svg_text(
        16,
        31,
        f"{total} contributions in the last year",
        theme["text"],
        size=14,
        weight="600",
        anchor="start",
        baseline="alphabetic",
    )
)

parts.append(
    svg_text(
        CARD_RIGHT - 16,
        31,
        "Contribution settings ▾",
        theme["muted"],
        size=11,
        weight="400",
        anchor="end",
        baseline="alphabetic",
    )
)

parts.append(
    f'<line x1="{CARD_X + 1}" y1="40" x2="{CARD_RIGHT - 1}" y2="40" stroke="{theme["divider"]}" stroke-width="1"/>'
)

# Месяцы
for month_name, col in month_labels:
    x = GRID_X + col * STEP
    parts.append(
        svg_text(
            x,
            62,
            month_name,
            theme["text"],
            size=12,
            weight="400",
            anchor="start",
            baseline="alphabetic",
        )
    )

# Подписи дней
for label, row in (("Mon", 1), ("Wed", 3), ("Fri", 5)):
    y = GRID_Y + row * STEP + CELL / 2
    parts.append(
        svg_text(
            GRID_X - 18,
            y,
            label,
            theme["text"],
            size=12,
            weight="400",
            anchor="end",
            baseline="middle",
        )
    )

# Сетка
for row in range(ROWS):
    for col in range(COLS):
        x, y, w, h = cell_rect(col, row)
        parts.append(svg_rect(x, y, w, h, theme["greens"][board[row][col]], rx=2))

# Нижняя подпись
parts.append(
    svg_text(
        66,
        197,
        "Learn how we count contributions",
        theme["muted"],
        size=11,
        weight="400",
        anchor="start",
        baseline="alphabetic",
    )
)

# Less / More
legend_blocks_x = CARD_RIGHT - 88
legend_y = 188

parts.append(
    svg_text(
        legend_blocks_x - 10,
        197,
        "Less",
        theme["text"],
        size=11,
        weight="400",
        anchor="end",
        baseline="alphabetic",
    )
)

for i, color in enumerate(theme["greens"]):
    parts.append(svg_rect(legend_blocks_x + i * 13, legend_y, 10, 10, color, rx=2))

parts.append(
    svg_text(
        legend_blocks_x + 5 * 13 + 4,
        197,
        "More",
        theme["text"],
        size=11,
        weight="400",
        anchor="start",
        baseline="alphabetic",
    )
)
    parts.append(f'<metadata>{{"username":"{username}","active_cells":{active_cells}}}</metadata>')
    parts.append("</svg>")
    return "\n".join(parts)


def main():
    username = os.getenv("GITHUB_USERNAME")
    if not username:
        raise RuntimeError("Нет GITHUB_USERNAME в окружении.")

    token = choose_token()
    outdir = Path("generated")
    outdir.mkdir(parents=True, exist_ok=True)

    calendar_data, diagnostics = fetch_calendar(username, token)
    board, month_labels, total, active_cells, calendar_hash = normalize_calendar(calendar_data)

    light_svg = render_svg("light", board, month_labels, total, active_cells, username)
    dark_svg = render_svg("dark", board, month_labels, total, active_cells, username)

    (outdir / "github-tetris-light.svg").write_text(light_svg, encoding="utf-8")
    (outdir / "github-tetris-dark.svg").write_text(dark_svg, encoding="utf-8")

    meta = {
        "username": username,
        "total_contributions": total,
        "active_cells": active_cells,
        "calendar_hash": calendar_hash,
        "diagnostics": diagnostics,
    }
    (outdir / "meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("Generated live calendar SVGs.")
    print(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
