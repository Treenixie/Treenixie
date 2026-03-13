from pathlib import Path
import os

CANVAS_W = 767
CANVAS_H = 220

GRID_X = 60
GRID_Y = 72
CELL = 10
GAP = 3
STEP = CELL + GAP

COLS = 53
ROWS = 7

THEMES = {
    "dark": {
        "bg": "#0d1117",
        "border": "#30363d",
        "divider": "#21262d",
        "text": "#c9d1d9",
        "muted": "#8b949e",
        "empty": "#161b22",
        "greens": ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"],
        "piece_colors": ["#58a6ff", "#d2a8ff", "#ffa657", "#f85149", "#79c0ff", "#ff7b72"],
    },
    "light": {
        "bg": "#ffffff",
        "border": "#d0d7de",
        "divider": "#d8dee4",
        "text": "#24292f",
        "muted": "#57606a",
        "empty": "#ebedf0",
        "greens": ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"],
        "piece_colors": ["#0969da", "#8250df", "#bc4c00", "#cf222e", "#218bff", "#bf3989"],
    },
}


def cell_rect(col: int, row: int):
    x = GRID_X + col * STEP
    y = GRID_Y + row * STEP
    return x, y, CELL, CELL


def svg_rect(x, y, w, h, fill, rx=2, extra=""):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" ry="{rx}" fill="{fill}" {extra}/>'


def svg_text(x, y, text, fill, size=12, weight="400"):
    safe = (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    return (
        f'<text x="{x}" y="{y}" fill="{fill}" font-family="system-ui, -apple-system, Segoe UI, Arial, sans-serif" '
        f'font-size="{size}" font-weight="{weight}">{safe}</text>'
    )


def make_base(theme_name: str):
    theme = THEMES[theme_name]
    parts = []

    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS_W}" height="{CANVAS_H}" viewBox="0 0 {CANVAS_W} {CANVAS_H}">'
    )
    parts.append(svg_rect(0, 0, CANVAS_W, CANVAS_H, theme["bg"], rx=0))
    parts.append(svg_rect(8, 8, CANVAS_W - 16, CANVAS_H - 16, theme["bg"], rx=6, extra=f'stroke="{theme["border"]}" stroke-width="1"'))

    parts.append(svg_text(16, 30, "GitHub Tetris bootstrap mode", theme["text"], size=15, weight="700"))
    parts.append(svg_text(CANVAS_W - 150, 30, "Contribution settings ▾", theme["muted"], size=11))
    parts.append(f'<line x1="9" y1="40" x2="{CANVAS_W - 9}" y2="40" stroke="{theme["divider"]}" stroke-width="1"/>')

    months = ["Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar"]
    month_cols = [0, 4, 8, 12, 16, 21, 25, 30, 34, 39, 44, 47, 51]
    for label, col in zip(months, month_cols):
        x = GRID_X + col * STEP
        parts.append(svg_text(x, 62, label, theme["text"], size=12))

    day_rows = [("Mon", 1), ("Wed", 3), ("Fri", 5)]
    for label, row in day_rows:
        y = GRID_Y + row * STEP + 9
        parts.append(svg_text(18, y, label, theme["text"], size=12))

    parts.append(svg_text(66, 197, "Pipeline test: next step is real contribution data", theme["muted"], size=11))

    parts.append(svg_text(CANVAS_W - 120, 197, "Less", theme["text"], size=11))
    legend_x = CANVAS_W - 90
    for i, color in enumerate(theme["greens"]):
        parts.append(svg_rect(legend_x + i * 13, 188, 10, 10, color, rx=2))
    parts.append(svg_text(CANVAS_W - 22, 197, "More", theme["text"], size=11))

    return parts


def draw_empty_board(parts, theme_name: str):
    theme = THEMES[theme_name]
    for row in range(ROWS):
        for col in range(COLS):
            x, y, w, h = cell_rect(col, row)
            parts.append(svg_rect(x, y, w, h, theme["empty"], rx=2))


def make_test_shapes(parts, theme_name: str):
    theme = THEMES[theme_name]
    colors = theme["piece_colors"]

    shapes = [
        [(44, 0), (45, 0), (46, 0), (45, 1)],  # T
        [(48, 2), (48, 3), (49, 3), (50, 3)],  # J
        [(51, 1), (51, 2), (51, 3), (52, 3)],  # L
        [(40, 5)],                              # DOT
    ]

    for idx, shape in enumerate(shapes):
        color = colors[idx % len(colors)]
        for col, row in shape:
            x, y, w, h = cell_rect(col, row)
            parts.append(svg_rect(x, y, w, h, color, rx=2))

    parts.append(svg_text(60, 178, "If you can see this block, visual branch works.", theme["muted"], size=11))


def write_svg(theme_name: str, output_path: Path):
    parts = make_base(theme_name)
    draw_empty_board(parts, theme_name)
    make_test_shapes(parts, theme_name)
    parts.append("</svg>")
    output_path.write_text("\n".join(parts), encoding="utf-8")


def main():
    username = os.getenv("GITHUB_USERNAME", "unknown-user")

    outdir = Path("generated")
    outdir.mkdir(parents=True, exist_ok=True)

    write_svg("light", outdir / "github-tetris-light.svg")
    write_svg("dark", outdir / "github-tetris-dark.svg")

    meta = outdir / "meta.txt"
    meta.write_text(f"Generated for {username}\n", encoding="utf-8")

    print("Generated:")
    print(outdir / "github-tetris-light.svg")
    print(outdir / "github-tetris-dark.svg")


if __name__ == "__main__":
    main()
