from pathlib import Path
import os
import calendar as cal
import datetime as dt
import hashlib
import json
import random

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
        "empty": "#161b22",
        "greens": ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"],
        "blue_scale": ["#161b22", "#10253f", "#153b66", "#1b5aa0", "#1f6feb"],
        "piece_hues": [
            "#ff7b72",
            "#79c0ff",
            "#d2a8ff",
            "#ffa657",
            "#8ddb8c",
            "#e3b341",
            "#56d4dd",
            "#f2cc60",
        ],
    },
    "light": {
        "bg": "#ffffff",
        "border": "#d0d7de",
        "divider": "#d8dee4",
        "text": "#24292f",
        "muted": "#57606a",
        "empty": "#ebedf0",
        "greens": ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"],
        "blue_scale": ["#ebedf0", "#dbeafe", "#a8c7ff", "#5b95ff", "#1f6feb"],
        "piece_hues": [
            "#cf222e",
            "#0969da",
            "#8250df",
            "#bc4c00",
            "#1a7f37",
            "#9a6700",
            "#0a7ea4",
            "#b35900",
        ],
    },
}

CANVAS_W = 767
CANVAS_H = 196

CARD_X = 8
CARD_Y = 8
CARD_W = CANVAS_W - 16
CARD_H = CANVAS_H - 16
CARD_RIGHT = CARD_X + CARD_W
CARD_BOTTOM = CARD_Y + CARD_H
CARD_PAD = 10

CELL = 10
GAP = 3
STEP = CELL + GAP

COLS = 53
ROWS = 7
GRID_W = COLS * STEP - GAP
GRID_H = ROWS * STEP - GAP

GRID_X = CARD_RIGHT - CARD_PAD - GRID_W

DAY_LABEL_X = GRID_X - 9

CONTENT_LEFT = CARD_X + CARD_PAD
CONTENT_RIGHT = CARD_RIGHT - CARD_PAD
CONTENT_TOP = CARD_Y + CARD_PAD
CONTENT_BOTTOM = CARD_BOTTOM - CARD_PAD

HEADER_LEFT = CARD_X + CELL
HEADER_RIGHT = CARD_RIGHT - CELL

TITLE_Y = CARD_Y + CARD_PAD + 12
SETTINGS_X = HEADER_RIGHT
SETTINGS_Y = TITLE_Y

DIVIDER_Y = TITLE_Y + 14

GRID_X = HEADER_RIGHT - GRID_W

DAY_LABEL_X = GRID_X - 9

TITLE_X = GRID_X - 31

MONTH_Y = DIVIDER_Y + 18
GRID_Y = MONTH_Y + 11

FOOTER_Y = GRID_Y + GRID_H + 18
LEGEND_Y = FOOTER_Y - 10
LEGEND_BLOCKS_X = CARD_RIGHT - CARD_PAD - 122

FONT_STACK = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif,'Apple Color Emoji','Segoe UI Emoji'"

BASE_SHAPES = {
    "I": [(0, 0), (1, 0), (2, 0), (3, 0)],
    "O": [(0, 0), (1, 0), (0, 1), (1, 1)],
    "T": [(0, 0), (1, 0), (2, 0), (1, 1)],
    "S": [(1, 0), (2, 0), (0, 1), (1, 1)],
    "Z": [(0, 0), (1, 0), (1, 1), (2, 1)],
    "J": [(0, 0), (0, 1), (1, 1), (2, 1)],
    "L": [(2, 0), (0, 1), (1, 1), (2, 1)],
    "TRI_I": [(0, 0), (1, 0), (2, 0)],
    "TRI_L": [(0, 0), (0, 1), (1, 1)],
    "DOMINO": [(0, 0), (1, 0)],
    "DOT": [(0, 0)],
}

PIECE_ORDER = ["T", "L", "J", "S", "Z", "O", "I", "TRI_L", "TRI_I", "DOMINO", "DOT"]
EXACT_COMPONENT_LIMIT = 18

ANIM_STEP_DUR = 0.22
ANIM_PIECE_GAP = 0.08
ANIM_START_DELAY = 0.18


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


def add_grid_clip(parts, clip_id):
    parts.append("<defs>")
    parts.append(
        f'<clipPath id="{clip_id}">'
        f'<rect x="{GRID_X}" y="{GRID_Y}" width="{GRID_W}" height="{GRID_H}" rx="0" ry="0" />'
        f"</clipPath>"
    )
    parts.append("</defs>")


def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(
        max(0, min(255, int(round(rgb[0])))),
        max(0, min(255, int(round(rgb[1])))),
        max(0, min(255, int(round(rgb[2])))),
    )


def blend(c1, c2, t):
    r1, g1, b1 = hex_to_rgb(c1)
    r2, g2, b2 = hex_to_rgb(c2)
    return rgb_to_hex((
        r1 + (r2 - r1) * t,
        g1 + (g2 - g1) * t,
        b1 + (b2 - b1) * t,
    ))


def shade_from_level(base_color, level, theme_name):
    theme = THEMES[theme_name]
    if level <= 0:
        return theme["empty"]

    visibility = {
        1: 0.38,
        2: 0.56,
        3: 0.76,
        4: 0.98,
    }[level]

    return blend(theme["empty"], base_color, visibility)


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


def cell_degree(cell, component):
    col, row = cell
    degree = 0
    for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        if (col + dc, row + dr) in component:
            degree += 1
    return degree


def neighbor_score(cells, active):
    score = 0
    cells = set(cells)
    for col, row in cells:
        for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            neighbor = (col + dc, row + dr)
            if neighbor in active and neighbor not in cells:
                score += 1
    return score


def connected_components(active):
    remaining = set(active)
    components = []

    while remaining:
        start = remaining.pop()
        stack = [start]
        comp = {start}

        while stack:
            col, row = stack.pop()
            for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nb = (col + dc, row + dr)
                if nb in remaining:
                    remaining.remove(nb)
                    comp.add(nb)
                    stack.append(nb)

        components.append(comp)

    components.sort(key=lambda comp: min((c, r) for c, r in comp))
    return components


def piece_penalty(name):
    if name == "O":
        return 0
    if name in {"T", "L", "J"}:
        return 1
    if name in {"S", "Z"}:
        return 2
    if name == "I":
        return 3
    if name == "TRI_L":
        return 6
    if name == "TRI_I":
        return 8
    if name == "DOMINO":
        return 14
    if name == "DOT":
        return 1000
    return 0


def generate_piece_candidates(component, allow_connected_dots):
    component = set(component)
    placements = {}
    priorities = {name: len(PIECE_ORDER) - PIECE_ORDER.index(name) for name in PIECE_ORDER}

    for piece_name in PIECE_ORDER:
        if piece_name == "DOT":
            continue

        for rotation in ROTATIONS[piece_name]:
            for anchor_col, anchor_row in component:
                for pivot_x, pivot_y in rotation:
                    origin_x = anchor_col - pivot_x
                    origin_y = anchor_row - pivot_y

                    absolute_cells = tuple(
                        sorted((origin_x + x, origin_y + y) for x, y in rotation)
                    )

                    if not set(absolute_cells).issubset(component):
                        continue

                    key = absolute_cells
                    if key not in placements:
                        placements[key] = {
                            "name": piece_name,
                            "shape": rotation,
                            "origin_x": origin_x,
                            "origin_y": origin_y,
                            "cells": list(absolute_cells),
                            "priority": priorities[piece_name],
                        }

    for cell in sorted(component):
        deg = cell_degree(cell, component)
        if deg == 0 or allow_connected_dots:
            placements[(cell,)] = {
                "name": "DOT",
                "shape": ((0, 0),),
                "origin_x": cell[0],
                "origin_y": cell[1],
                "cells": [cell],
                "priority": priorities["DOT"],
            }

    return list(placements.values())


def solve_component_exact(component):
    component_cells = sorted(component)
    index_of = {cell: idx for idx, cell in enumerate(component_cells)}
    all_mask = (1 << len(component_cells)) - 1

    neighbor_masks = []
    original_degree = []
    for cell in component_cells:
        mask = 0
        for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nb = (cell[0] + dc, cell[1] + dr)
            if nb in index_of:
                mask |= 1 << index_of[nb]
        neighbor_masks.append(mask)
        original_degree.append(mask.bit_count())

    mask_penalty_cache = {}

    def mask_fragment_penalty(mask):
        if mask == 0:
            return 0
        if mask in mask_penalty_cache:
            return mask_penalty_cache[mask]

        remaining = mask
        component_sizes = []
        newly_isolated_connected = 0

        while remaining:
            lsb = remaining & -remaining
            idx = lsb.bit_length() - 1

            queue = [idx]
            comp_mask = 0
            remaining ^= 1 << idx

            while queue:
                cur = queue.pop()
                comp_mask |= 1 << cur
                nb_mask = neighbor_masks[cur] & remaining
                while nb_mask:
                    lsb2 = nb_mask & -nb_mask
                    j = lsb2.bit_length() - 1
                    remaining ^= 1 << j
                    queue.append(j)
                    nb_mask ^= lsb2

            size = comp_mask.bit_count()
            component_sizes.append(size)

        for i in range(len(component_cells)):
            if mask & (1 << i):
                deg_now = (neighbor_masks[i] & mask).bit_count()
                if deg_now == 0 and original_degree[i] > 0:
                    newly_isolated_connected += 1

        singletons = sum(1 for s in component_sizes if s == 1)
        pairs = sum(1 for s in component_sizes if s == 2)
        triples = sum(1 for s in component_sizes if s == 3)

        penalty = (
            singletons * 40
            + pairs * 8
            + triples * 2
            + len(component_sizes) * 3
            + newly_isolated_connected * 18
        )

        mask_penalty_cache[mask] = penalty
        return penalty

    def try_solve(allow_connected_dots):
        placements = generate_piece_candidates(component, allow_connected_dots=allow_connected_dots)
        placements_by_index = {i: [] for i in range(len(component_cells))}

        for placement in placements:
            mask = 0
            for cell in placement["cells"]:
                mask |= 1 << index_of[cell]

            item = {
                "mask": mask,
                "name": placement["name"],
                "shape": placement["shape"],
                "origin_x": placement["origin_x"],
                "origin_y": placement["origin_y"],
                "cells": placement["cells"],
                "priority": placement["priority"],
                "size": len(placement["cells"]),
            }

            for cell in placement["cells"]:
                placements_by_index[index_of[cell]].append(item)

        for idx in placements_by_index:
            placements_by_index[idx].sort(
                key=lambda p: (
                    piece_penalty(p["name"]),
                    -(p["size"]),
                    -p["priority"],
                )
            )

        memo = {}

        def solve(mask):
            if mask == 0:
                return (0, 0, 0, 0), []

            if mask in memo:
                return memo[mask]

            lsb = mask & -mask
            idx = lsb.bit_length() - 1

            best_score = None
            best_solution = None

            for placement in placements_by_index[idx]:
                if placement["mask"] & mask != placement["mask"]:
                    continue

                remaining_mask = mask ^ placement["mask"]
                tail_score, tail_solution = solve(remaining_mask)

                if tail_score is None:
                    continue

                name = placement["name"]
                score = (
                    tail_score[0] + (1 if name == "DOT" else 0),
                    tail_score[1] + piece_penalty(name) + mask_fragment_penalty(remaining_mask),
                    tail_score[2] + (0 if placement["size"] == 4 else 1),
                    tail_score[3] + 1,
                )

                if best_score is None or score < best_score:
                    best_score = score
                    best_solution = [placement] + tail_solution

            memo[mask] = (best_score, best_solution)
            return memo[mask]

        return solve(all_mask)

    score, solution = try_solve(allow_connected_dots=False)

    if solution is None:
        score, solution = try_solve(allow_connected_dots=True)

    if solution is None:
        solution = [
            {
                "name": "DOT",
                "shape": ((0, 0),),
                "origin_x": cell[0],
                "origin_y": cell[1],
                "cells": [cell],
            }
            for cell in component_cells
        ]

    return [
        {
            "name": p["name"],
            "shape": p["shape"],
            "origin_x": p["origin_x"],
            "origin_y": p["origin_y"],
            "cells": p["cells"],
        }
        for p in solution
    ]


def greedy_after_penalty(active, chosen_cells):
    remaining = set(active) - set(chosen_cells)
    penalty = 0
    for cell in remaining:
        old_deg = cell_degree(cell, active)
        new_deg = cell_degree(cell, remaining)
        if old_deg > 0 and new_deg == 0:
            penalty += 18
    return penalty


def best_piece_for_anchor_greedy(anchor, active):
    candidates = []

    for piece_name in PIECE_ORDER:
        if piece_name == "DOT" and cell_degree(anchor, active) > 0:
            continue

        for rotation in ROTATIONS[piece_name]:
            for pivot_x, pivot_y in rotation:
                origin_x = anchor[0] - pivot_x
                origin_y = anchor[1] - pivot_y
                absolute_cells = {(origin_x + x, origin_y + y) for x, y in rotation}

                if not absolute_cells.issubset(active):
                    continue

                score = (
                    len(absolute_cells) * 100
                    + neighbor_score(absolute_cells, active) * 10
                    - piece_penalty(piece_name) * 6
                    - greedy_after_penalty(active, absolute_cells)
                )

                candidates.append(
                    {
                        "name": piece_name,
                        "shape": rotation,
                        "origin_x": origin_x,
                        "origin_y": origin_y,
                        "cells": sorted(absolute_cells),
                        "score": score,
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
        }

    candidates.sort(
        key=lambda item: (
            item["score"],
            -shape_width(item["shape"]),
            -shape_height(item["shape"]),
        ),
        reverse=True,
    )
    return candidates[0]


def solve_component_greedy(component):
    active = set(component)
    pieces = []

    while active:
        anchor = min(
            active,
            key=lambda item: (
                cell_degree(item, active) == 0,
                item[0],
                item[1],
            ),
        )
        piece = best_piece_for_anchor_greedy(anchor, active)
        for cell in piece["cells"]:
            active.discard(cell)
        pieces.append(
            {
                "name": piece["name"],
                "shape": piece["shape"],
                "origin_x": piece["origin_x"],
                "origin_y": piece["origin_y"],
                "cells": piece["cells"],
            }
        )

    return pieces


def partition_into_pieces(board):
    active = {
        (col, row)
        for row in range(ROWS)
        for col in range(COLS)
        if board[row][col] > 0
    }

    components = connected_components(active)
    pieces = []

    for comp in components:
        if len(comp) <= EXACT_COMPONENT_LIMIT:
            pieces.extend(solve_component_exact(comp))
        else:
            pieces.extend(solve_component_greedy(comp))

    pieces.sort(
        key=lambda p: (
            max(r for _, r in p["cells"]),
            min(c for c, _ in p["cells"]),
            p["name"],
        )
    )
    return pieces


def pieces_touch_by_edge(piece_a, piece_b):
    a_cells = set(piece_a["cells"])
    b_cells = set(piece_b["cells"])

    for col, row in a_cells:
        for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            if (col + dc, row + dr) in b_cells:
                return True
    return False


def build_piece_color_indices(pieces, palette_size):
    adjacency = {i: set() for i in range(len(pieces))}

    for i in range(len(pieces)):
        for j in range(i + 1, len(pieces)):
            if pieces_touch_by_edge(pieces[i], pieces[j]):
                adjacency[i].add(j)
                adjacency[j].add(i)

    order = sorted(
        range(len(pieces)),
        key=lambda i: (-len(adjacency[i]), -len(pieces[i]["cells"]), i),
    )

    color_of = {}
    usage_count = {c: 0 for c in range(palette_size)}

    for idx in order:
        banned = {color_of[n] for n in adjacency[idx] if n in color_of}

        candidates = [c for c in range(palette_size) if c not in banned]
        if not candidates:
            candidates = list(range(palette_size))

        chosen = min(candidates, key=lambda c: (usage_count[c], c))
        color_of[idx] = chosen
        usage_count[chosen] += 1

    return [color_of[i] for i in range(len(pieces))]


def build_piece_styles(theme_name, pieces):
    hues = THEMES[theme_name]["piece_hues"]
    color_indices = build_piece_color_indices(pieces, len(hues))

    styles = []
    for index, piece in enumerate(pieces):
        base = hues[color_indices[index]]
        styles.append({"base": base, "name": piece["name"]})
    return styles


def build_animation_plan(pieces, calendar_hash):
    seed = int(calendar_hash[:8], 16)
    rng = random.Random(seed)

    plan = []
    current_t = ANIM_START_DELAY

    for piece in pieces:
        w = shape_width(piece["shape"])
        h = shape_height(piece["shape"])

        tx = piece["origin_x"]
        ty = piece["origin_y"]

        max_spawn_x = max(0, COLS - w)
        side_shift = rng.choice([-3, -2, 0, 0, 2, 3])
        spawn_x = max(0, min(max_spawn_x, tx + side_shift))
        spawn_y = -h - rng.randint(1, 2)

        mid_x = tx
        mid_y = min(-1, ty - 2)

        steps = max(abs(spawn_x - tx), abs(spawn_y - ty), 1)
        duration = max(0.38, steps * ANIM_STEP_DUR * 0.42)

        plan.append(
            {
                "start": current_t,
                "end": current_t + duration,
                "dur": duration,
                "spawn_x": spawn_x,
                "spawn_y": spawn_y,
                "mid_x": mid_x,
                "mid_y": mid_y,
                "target_x": tx,
                "target_y": ty,
            }
        )

        current_t += duration + ANIM_PIECE_GAP

    return plan


def render_piece_static_cells(parts, theme_name, board, pieces):
    styles = build_piece_styles(theme_name, pieces)

    for piece, style in zip(pieces, styles):
        for col, row in piece["cells"]:
            level = board[row][col]
            fill = shade_from_level(style["base"], level, theme_name)
            x, y, w, h = cell_rect(col, row)
            parts.append(svg_rect(x, y, w, h, fill, rx=2))


def render_piece_live_layers(parts, theme_name, board, pieces, calendar_hash):
    styles = build_piece_styles(theme_name, pieces)
    plan = build_animation_plan(pieces, calendar_hash)

    for piece, style, anim in zip(pieces, styles, plan):
        parts.append('<g opacity="0">')
        parts.append(
            f'<set attributeName="opacity" to="1" begin="{anim["end"]:.3f}s" fill="freeze" />'
        )
        for col, row in piece["cells"]:
            level = board[row][col]
            fill = shade_from_level(style["base"], level, theme_name)
            x, y, w, h = cell_rect(col, row)
            parts.append(svg_rect(x, y, w, h, fill, rx=2))
        parts.append("</g>")

        target_px_x = GRID_X + anim["target_x"] * STEP
        target_px_y = GRID_Y + anim["target_y"] * STEP
        spawn_dx = (anim["spawn_x"] - anim["target_x"]) * STEP
        spawn_dy = (anim["spawn_y"] - anim["target_y"]) * STEP
        mid_dx = (anim["mid_x"] - anim["target_x"]) * STEP
        mid_dy = (anim["mid_y"] - anim["target_y"]) * STEP

        parts.append(f'<g opacity="0" transform="translate({target_px_x} {target_px_y})">')
        parts.append(
            f'<set attributeName="opacity" to="1" begin="{anim["start"]:.3f}s" fill="freeze" />'
        )
        parts.append(
            f'<set attributeName="opacity" to="0" begin="{anim["end"]:.3f}s" fill="freeze" />'
        )
        parts.append(
            f'<animateTransform attributeName="transform" type="translate" additive="sum" '
            f'begin="{anim["start"]:.3f}s" dur="{anim["dur"]:.3f}s" fill="freeze" '
            f'values="{spawn_dx} {spawn_dy}; {mid_dx} {mid_dy}; 0 0" keyTimes="0;0.35;1" />'
        )

        for dx, dy in piece["shape"]:
            col = piece["origin_x"] + dx
            row = piece["origin_y"] + dy
            level = board[row][col]
            fill = shade_from_level(style["base"], level, theme_name)
            x = dx * STEP
            y = dy * STEP
            parts.append(svg_rect(x, y, CELL, CELL, fill, rx=2))

        parts.append("</g>")


def render_base(parts, theme_name, month_labels, total):
    theme = THEMES[theme_name]

    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS_W}" height="{CANVAS_H}" '
        f'viewBox="0 0 {CANVAS_W} {CANVAS_H}">'
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

    parts.append(
        svg_text(
            TITLE_X,
            TITLE_Y,
            f"{total} contributions in the last year",
            theme["text"],
            size=14,
            weight="600",
        )
    )

    parts.append(
        svg_text(
            SETTINGS_X,
            SETTINGS_Y,
            "Contribution settings ▾",
            theme["muted"],
            size=11,
            weight="400",
            anchor="end",
        )
    )

    parts.append(
        f'<line x1="{HEADER_LEFT}" y1="{DIVIDER_Y}" x2="{HEADER_RIGHT}" y2="{DIVIDER_Y}" stroke="{theme["divider"]}" stroke-width="1"/>'
    )

    for month_name, col in month_labels:
        x = GRID_X + col * STEP
        parts.append(svg_text(x, MONTH_Y, month_name, theme["text"], size=12, weight="400"))

    for label, row in (("Mon", 1), ("Wed", 3), ("Fri", 5)):
        y = GRID_Y + row * STEP + 6
        parts.append(
            svg_text(
                DAY_LABEL_X,
                y,
                label,
                theme["text"],
                size=12,
                weight="400",
                anchor="end",
            )
        )


def render_empty_grid(parts, theme_name):
    theme = THEMES[theme_name]
    for row in range(ROWS):
        for col in range(COLS):
            x, y, w, h = cell_rect(col, row)
            parts.append(svg_rect(x, y, w, h, theme["empty"], rx=2))


def render_blue_legend(parts, theme_name):
    theme = THEMES[theme_name]

    parts.append(
        svg_text(
            GRID_X,
            FOOTER_Y,
            "Learn how we count contributions",
            theme["muted"],
            size=11,
            weight="400",
        )
    )

    parts.append(
        svg_text(
            LEGEND_BLOCKS_X - 8,
            FOOTER_Y,
            "Less",
            theme["muted"],
            size=11,
            weight="400",
            anchor="end",
        )
    )

    for i, color in enumerate(theme["blue_scale"]):
        parts.append(svg_rect(LEGEND_BLOCKS_X + i * 13, LEGEND_Y, 10, 10, color, rx=2))

    parts.append(
        svg_text(
            LEGEND_BLOCKS_X + 5 * 13 + 4,
            FOOTER_Y,
            "More",
            theme["muted"],
            size=11,
            weight="400",
            anchor="start",
        )
    )


def render_live_svg(theme_name, board, month_labels, total, active_cells, username, pieces, calendar_hash):
    parts = []
    clip_id = f"grid-clip-live-{theme_name}"

    render_base(parts, theme_name, month_labels, total)
    add_grid_clip(parts, clip_id)
    render_empty_grid(parts, theme_name)

    parts.append(f'<g clip-path="url(#{clip_id})">')
    render_piece_live_layers(parts, theme_name, board, pieces, calendar_hash)
    parts.append("</g>")

    render_blue_legend(parts, theme_name)

    meta_payload = {
        "username": username,
        "active_cells": active_cells,
        "mode": "live-animation",
    }
    parts.append(f"<metadata>{json.dumps(meta_payload, ensure_ascii=False)}</metadata>")
    parts.append("</svg>")
    return "\n".join(parts)


def render_partition_svg(theme_name, board, month_labels, total, active_cells, username, pieces):
    parts = []
    clip_id = f"grid-clip-partition-{theme_name}"

    render_base(parts, theme_name, month_labels, total)
    add_grid_clip(parts, clip_id)
    render_empty_grid(parts, theme_name)

    parts.append(f'<g clip-path="url(#{clip_id})">')
    render_piece_static_cells(parts, theme_name, board, pieces)
    parts.append("</g>")

    render_blue_legend(parts, theme_name)

    meta_payload = {
        "username": username,
        "active_cells": active_cells,
        "mode": "partition-preview",
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

    light_live_svg = render_live_svg("light", board, month_labels, total, active_cells, username, pieces, calendar_hash)
    dark_live_svg = render_live_svg("dark", board, month_labels, total, active_cells, username, pieces, calendar_hash)

    (outdir / "github-tetris-light.svg").write_text(light_live_svg, encoding="utf-8")
    (outdir / "github-tetris-dark.svg").write_text(dark_live_svg, encoding="utf-8")

    light_partition_svg = render_partition_svg("light", board, month_labels, total, active_cells, username, pieces)
    dark_partition_svg = render_partition_svg("dark", board, month_labels, total, active_cells, username, pieces)

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

    print("Generated live animation SVGs + partition previews.")
    print(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
