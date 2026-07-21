#!/usr/bin/env python3
"""Scrape the public GitHub contribution calendar and render it as an animated SVG.

No API token needed -- the calendar fragment at /users/<name>/contributions is
public HTML. Output is a self-contained SVG (no scripts, no external refs) so it
renders inside a GitHub README.
"""

import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

USERNAME = os.environ.get("GH_USERNAME", "hamsterowo")
OUT_PATH = Path(__file__).resolve().parent.parent / "assets" / "contrib-heatmap.svg"

# geometry
CELL = 11
GAP = 3
PITCH = CELL + GAP
PAD_X = 6
PAD_TOP = 40          # total line + month labels
LABEL_W = 30          # weekday label gutter
WEEKS = 53
LEGEND_H = 34

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def fetch_days(username):
    """Return [(date, level, count), ...] sorted by date."""
    url = f"https://github.com/users/{username}/contributions"
    resp = requests.get(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (contrib-heatmap generator)",
            "X-Requested-With": "XMLHttpRequest",
        },
        timeout=30,
    )
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # counts live in <tool-tip for="...">N contributions on ...</tool-tip>
    counts = {}
    for tip in soup.find_all("tool-tip"):
        target = tip.get("for")
        if not target:
            continue
        m = re.match(r"\s*(\d+)", tip.get_text())
        counts[target] = int(m.group(1)) if m else 0

    cells = soup.select("td.ContributionCalendar-day[data-date]")
    if not cells:  # older markup used <rect>
        cells = soup.select("rect.ContributionCalendar-day[data-date]")
    if not cells:
        raise RuntimeError("no contribution cells found -- GitHub markup changed?")

    days = []
    for cell in cells:
        d = datetime.strptime(cell["data-date"], "%Y-%m-%d").date()
        level = int(cell.get("data-level", 0))
        count = counts.get(cell.get("id"), 0)
        days.append((d, level, count))

    days.sort(key=lambda x: x[0])
    return days


def build_grid(days):
    """Map days onto (week, weekday) columns. GitHub weeks start on Sunday."""
    days = days[-WEEKS * 7:]
    start = days[0][0]
    start -= timedelta(days=(start.weekday() + 1) % 7)

    grid = {}
    for d, level, count in days:
        week = (d - start).days // 7
        weekday = (d.weekday() + 1) % 7  # Sun=0
        if 0 <= week < WEEKS:
            grid[(week, weekday)] = (d, level, count)
    return grid, start


def month_labels(start):
    """One label per month, positioned at the week its 1st falls in."""
    labels = []
    seen = set()
    for week in range(WEEKS):
        d = start + timedelta(days=week * 7)
        key = (d.year, d.month)
        if key in seen:
            continue
        # only label once the month is properly underway in this column
        if d.day <= 7 and week < WEEKS - 2:
            seen.add(key)
            labels.append((week, MONTHS[d.month - 1]))
    return labels


def render(grid, start, days):
    width = PAD_X * 2 + LABEL_W + WEEKS * PITCH
    grid_h = 7 * PITCH
    height = PAD_TOP + grid_h + LEGEND_H

    total = sum(c for _, _, c in days)
    today = date.today().isoformat()

    out = []
    add = out.append

    add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{total} GitHub contributions in the last year">')
    add("""  <style>
    svg {
      --text: #1f2328; --muted: #656d76; --accent: #1a7f37;
      --l0: #ebedf0; --l1: #9be9a8; --l2: #40c463; --l3: #30a14e; --l4: #216e39;
    }
    @media (prefers-color-scheme: dark) {
      svg {
        --text: #c9d1d9; --muted: #8b949e; --accent: #3fb950;
        --l0: #161b22; --l1: #0e4429; --l2: #006d32; --l3: #26a641; --l4: #39d353;
      }
    }
    text {
      font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace;
      font-size: 10px; fill: var(--muted);
    }
    .hd { font-size: 12px; fill: var(--text); }
    .ac { fill: var(--accent); font-weight: 600; }
    .l0 { fill: var(--l0); } .l1 { fill: var(--l1); } .l2 { fill: var(--l2); }
    .l3 { fill: var(--l3); } .l4 { fill: var(--l4); }
    .d {
      opacity: 0;
      transform-box: fill-box;
      transform-origin: center;
      animation: pop .45s cubic-bezier(.34,1.4,.64,1) forwards;
    }
    @keyframes pop {
      from { opacity: 0; transform: scale(.25); }
      to   { opacity: 1; transform: scale(1); }
    }
    .fade { opacity: 0; animation: fade .5s ease-out forwards; }
    @keyframes fade { to { opacity: 1; } }
    @media (prefers-reduced-motion: reduce) {
      .d, .fade { opacity: 1; animation: none; transform: none; }
    }
  </style>""")

    gx = PAD_X + LABEL_W  # grid origin x
    gy = PAD_TOP

    add(f'  <text class="hd fade" x="{gx}" y="14" style="animation-delay:.1s">'
        f'<tspan class="ac">{total}</tspan> contributions in the last year</text>')

    # month labels
    for week, name in month_labels(start):
        add(f'  <text class="fade" x="{gx + week * PITCH}" y="{gy - 6}" '
            f'style="animation-delay:{0.3 + week * 0.012:.2f}s">{name}</text>')

    # weekday labels (Mon / Wed / Fri, like GitHub)
    for row, name in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        add(f'  <text class="fade" x="{PAD_X}" y="{gy + row * PITCH + CELL - 2}" '
            f'style="animation-delay:{0.3 + row * 0.05:.2f}s">{name}</text>')

    # cells -- diagonal wave: delay grows with (week + weekday)
    for week in range(WEEKS):
        for day in range(7):
            entry = grid.get((week, day))
            if entry is None:
                continue
            d, level, count = entry
            x = gx + week * PITCH
            y = gy + day * PITCH
            delay = 0.35 + (week + day) * 0.016
            label = "No contributions" if count == 0 else f"{count} contribution{'s' if count != 1 else ''}"
            add(f'  <rect class="d l{level}" x="{x}" y="{y}" width="{CELL}" height="{CELL}" '
                f'rx="2" style="animation-delay:{delay:.2f}s">'
                f'<title>{label} on {d.isoformat()}</title></rect>')

    # legend
    ly = gy + grid_h + 14
    lx = width - PAD_X - (5 * PITCH) - 66
    add(f'  <text class="fade" x="{PAD_X}" y="{ly + CELL - 2}" '
        f'style="animation-delay:1.6s">updated {today}</text>')
    add(f'  <text class="fade" x="{lx}" y="{ly + CELL - 2}" style="animation-delay:1.6s">Less</text>')
    for i in range(5):
        add(f'  <rect class="d l{i}" x="{lx + 30 + i * PITCH}" y="{ly}" width="{CELL}" '
            f'height="{CELL}" rx="2" style="animation-delay:{1.65 + i * 0.06:.2f}s"/>')
    add(f'  <text class="fade" x="{lx + 30 + 5 * PITCH + 4}" y="{ly + CELL - 2}" '
        f'style="animation-delay:1.6s">More</text>')

    add("</svg>")
    return "\n".join(out) + "\n"


def main():
    days = fetch_days(USERNAME)
    grid, start = build_grid(days)
    svg = render(grid, start, days[-WEEKS * 7:])

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    old = OUT_PATH.read_text(encoding="utf-8") if OUT_PATH.exists() else None
    if old == svg:
        print(f"no change: {OUT_PATH}")
        return
    OUT_PATH.write_text(svg, encoding="utf-8")
    print(f"wrote {OUT_PATH} ({len(days)} days)")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - surface the reason in CI logs
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
