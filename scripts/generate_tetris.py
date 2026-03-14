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
        "piece_colors": ["#58a6ff", "#d2a8ff", "#ffa657", "#f85149", "#79c0ff", "#ff7b72", "#e3b341", "#8ddb8c"],
    },
    "light": {
        "bg": "#ffffff",
        "border": "#d0d7de",
        "divider": "#d8dee4",
        "text": "#24292f",
        "muted": "#57606a",
        "greens": ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"],
        "piece_colors": ["#0969da", "#8250df", "#bc4c00", "#cf222e", "#218bff", "#bf3989", "#9a6700", "#1a7f37"],
    },
}

# Размер блока
CANVAS_W = 767
CANVAS_H = 196

CARD_X = 8
CARD_Y = 8
CARD_W = CANVAS_W - 16
CARD_H = CANVAS_H - 16
CARD_RIGHT = CARD_X + CARD_W

# Позиции сетки
GRID_X = 69
GRID_Y = 66
CELL = 10
GAP = 3
STEP = CELL + GAP

COLS = 53
ROWS = 7

FONT_STACK = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif,'Apple Color Emoji','Segoe UI Emoji'"

BASE_SHAPES = {
    "I": [(0, 0), (1, 0), (2, 0), (3, 0)],
    "O": [(0, 0), (1, 0), (0, 1), (1, 1)],
    "T": [(0, 0), (1, 0), (2, 0), (1, 1)],
    "S": [(1, 0), (2, 0), (0, 1), (1, 1)],
    "Z": [(0, 0), (1, 0), (1, 1), (2, 1)],
    "J": [(0, 0), (0, 1), (1, 1), (2, 1)],
    "L": [(2, 0), (0, 1), (1, 1), (2, 1)],
    "DOT": [(0, 0)],
}

PIECE_ORDER = ["T", "L", "J", "S", "Z", "O", "I", "DOT"]


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

    if not weeks:
        raise RuntimeError("GitHub вернул пустой список weeks.")

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
    weeks = pad_weeks(calendar_data["weeks"][-COLS:])

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
            row = (day_date.weekday() + 1) % 7  # Sunday first
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


def normalize_shape(shape):
    min_x = min(x for x, _ in shape)
    min_y = min(y for _, y in shape)
    return tuple(sorted((x - min_x, y - min_y) for x, y in shape))


def rotate_shape(shape):
    return [(-y, x) for x, y in shape]


def get_rotations(shape):
    result = []
    current = list(shape)
    for _ in range(4):
        norm = normalize_shape(current)
        if norm not in result:
            result.append(norm)
        current = rotate_shape(current)
    return result


ROTATIONS = {name: get_rotations(coords) for name, coords in BASE_SHAPES.items()}


def shape_width(shape):
    return max(x for x, _ in shape) + 1


def shape_height(shape):
    return max(y for _, y in shape) + 1


def neighbor_score(cells, active):
    score = 0
    cells = set(cells)
    for col, row in cells:
        for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            neighbor = (col + dc, row + dr)
            if neighbor in active and neighbor not in cells:
                score += 1
    return score


def best_piece_for_anchor(anchor, active):
    candidates = []

    for piece_name in PIECE_ORDER:
        for rotation in ROTATIONS[piece_name]:
            for pivot_x, pivot_y in rotation:
                origin_x = anchor[0] - pivot_x
                origin_y = anchor[1] - pivot_y
                absolute_cells = {(origin_x + x, origin_y + y) for x, y in rotation}

                if not absolute_cells.issubset(active):
                    continue

                score = len(absolute_cells) * 100 + neighbor_score(absolute_cells, active)
                candidates.append(
                    {
                        "name": piece_name,
                        "shape": rotation,
                        "origin_x": origin_x,
                        "origin_y": origin_y,
                        "cells": sorted(absolute_cells),
                        "score": score,
                        "priority": len(PIECE_ORDER) - PIECE_ORDER.index(piece_name),
                    }
                )

    if not candidates:
        return {
            "name": "DOT",
            "shape": ((0, 0),),
            "origin_x": anchor[0],
            "origin_y": anchor[1],
            "cells": [anchor],
            "score": 1,
            "priority": 0,
        }

    candidates.sort(
        key=lambda item: (
            item["score"],
            item["priority"],
            -shape_width(item["shape"]),
            -shape_height(item["shape"]),
        ),
        reverse=True,
    )
    return candidates[0]


def partition_into_pieces(board):
    active = {
        (col, row)
        for row in range(ROWS)
        for col in range(COLS)
        if board[row][col] > 0
    }

    pieces = []
    while active:
        anchor = min(active, key=lambda item: (item[0], item[1]))
        piece = best_piece_for_anchor(anchor, active)
        for cell in piece["cells"]:
            active.discard(cell)
        pieces.append(piece)

    pieces.sort(key=lambda p: (max(r for _, r in p["cells"]), min(c for c, _ in p["cells"])))
    return pieces


def render_piece_overlay(parts, theme_name, pieces):
    palette = THEMES[theme_name]["piece_colors"]

    for index, piece in enumerate(pieces):
        color = palette[index % len(palette)]
        stroke_width = 1.4 if piece["name"] != "DOT" else 1.8
        opacity = 0.95 if piece["name"] != "DOT" else 1.0

        for col, row in piece["cells"]:
            x, y, w, h = cell_rect(col, row)
            parts.append(
                svg_rect(
                    x + 0.6,
                    y + 0.6,
                    w - 1.2,
                    h - 1.2,
                    "none",
                    rx=2,
                    extra=f'stroke="{color}" stroke-width="{stroke_width}" opacity="{opacity}"',
                )
            )


def render_svg(theme_name, board, month_labels, total, active_cells, username, pieces=None):
    theme = THEMES[theme_name]
    parts = []

    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS_W}" height="{CANVAS_H}" '
        f'viewBox="0 0 {CANVAS_W} {CANVAS_H}">'
    )

    # Фон и карточка
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
                56,
                month_name,
                theme["text"],
                size=11,
                weight="400",
            )
        )

    # Подписи дней
    for label, row in (("Mon", 1), ("Wed", 3), ("Fri", 5)):
        y = GRID_Y + row * STEP + 6
        parts.append(
            svg_text(
                GRID_X - 18,
                y,
                label,
                theme["text"],
                size=11,
                weight="400",
                anchor="end",
            )
        )

    # Сетка
    for row in range(ROWS):
        for col in range(COLS):
            x, y, w, h = cell_rect(col, row)
            parts.append(svg_rect(x, y, w, h, theme["greens"][board[row][col]], rx=2))

    # Overlay preview
    if pieces is not None:
        render_piece_overlay(parts, theme_name, pieces)

    # Нижняя подпись
    parts.append(
        svg_text(
            66,
            176,
            "Learn how we count contributions",
            theme["muted"],
            size=11,
            weight="400",
        )
    )

    # Легенда
    legend_y = 166
    legend_blocks_x = CARD_RIGHT - 118

    parts.append(
        svg_text(
            legend_blocks_x - 8,
            176,
            "Less",
            theme["text"],
            size=11,
            weight="400",
            anchor="end",
        )
    )

    for i, color in enumerate(theme["greens"]):
        parts.append(svg_rect(legend_blocks_x + i * 13, legend_y, 10, 10, color, rx=2))

    parts.append(
        svg_text(
            legend_blocks_x + 5 * 13 + 4,
            176,
            "More",
            theme["text"],
            size=11,
            weight="400",
            anchor="start",
        )
    )

    # Metadata
    meta_payload = {
        "username": username,
        "active_cells": active_cells,
        "pieces_overlay": pieces is not None,
    }
    parts.append(f"<metadata>{json.dumps(meta_payload, ensure_ascii=False)}</metadata>")
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
    pieces = partition_into_pieces(board)

    # Обычные live SVG
    light_svg = render_svg("light", board, month_labels, total, active_cells, username, pieces=None)
    dark_svg = render_svg("dark", board, month_labels, total, active_cells, username, pieces=None)

    (outdir / "github-tetris-light.svg").write_text(light_svg, encoding="utf-8")
    (outdir / "github-tetris-dark.svg").write_text(dark_svg, encoding="utf-8")

    # Preview разбиения на фигуры
    light_partition_svg = render_svg("light", board, month_labels, total, active_cells, username, pieces=pieces)
    dark_partition_svg = render_svg("dark", board, month_labels, total, active_cells, username, pieces=pieces)

    (outdir / "github-tetris-light-partition.svg").write_text(light_partition_svg, encoding="utf-8")
    (outdir / "github-tetris-dark-partition.svg").write_text(dark_partition_svg, encoding="utf-8")

    piece_counts = {}
    for piece in pieces:
        piece_counts[piece["name"]] = piece_counts.get(piece["name"], 0) + 1

    meta = {
        "username": username,
        "total_contributions": total,
        "active_cells": active_cells,
        "calendar_hash": calendar_hash,
        "pieces_count": len(pieces),
        "dot_count": piece_counts.get("DOT", 0),
        "piece_breakdown": piece_counts,
        "diagnostics": diagnostics,
    }

    (outdir / "meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("Generated live calendar SVGs + partition previews.")
    print(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
