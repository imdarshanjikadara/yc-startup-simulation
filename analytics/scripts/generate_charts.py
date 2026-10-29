"""Run the queries in answer.sql against shiptivity.db and render the charts in charts/.

Usage: python scripts/generate_charts.py
"""
import re
import sqlite3
from collections import Counter
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "shiptivity.db"
SQL_PATH = ROOT / "answer.sql"
OUT_DIR = ROOT / "charts"
RELEASE = date(2018, 6, 2)

BLUE = "#2a78d6"
ORANGE = "#eb6834"
AQUA = "#1baf7a"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e4e3df"
SURFACE = "#fcfcfb"


def load_queries():
    """Split answer.sql into {name: sql} using the "-- @query: name" tags."""
    text = SQL_PATH.read_text(encoding="utf-8")
    parts = re.split(r"^-- @query: (\w+)\s*$", text, flags=re.M)
    return {name: body.strip() for name, body in zip(parts[1::2], parts[2::2])}


def style(ax, title, subtitle):
    ax.set_facecolor(SURFACE)
    ax.figure.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(INK_2)
    ax.tick_params(colors=INK_2, labelsize=9, length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_title(title, loc="left", fontsize=13, fontweight="bold", color=INK, pad=24)
    ax.text(0, 1.02, subtitle, transform=ax.transAxes, fontsize=9.5, color=INK_2)


def dau_chart(db, queries):
    rows = db.execute(queries["daily_active_users"]).fetchall()
    days = [date.fromisoformat(r[0]) for r in rows]
    dau = [r[1] for r in rows]
    averages = dict((r[0], r[2]) for r in db.execute(queries["avg_dau_before_after"]))

    # 7-day trailing average to make the trend readable over the daily noise
    rolling = [sum(dau[max(0, i - 6):i + 1]) / len(dau[max(0, i - 6):i + 1]) for i in range(len(dau))]

    fig, ax = plt.subplots(figsize=(12, 5.5))
    style(ax, "Daily active users, before vs. after the Kanban board release",
          f"Average DAU: {averages['before']} before → {averages['after']} after "
          f"({averages['after'] / averages['before']:.1f}x). Release on {RELEASE:%Y-%m-%d}.")

    before = [d < RELEASE for d in days]
    for is_before, color, label in ((True, BLUE, "Before release"), (False, ORANGE, "After release")):
        xs = [d for d, b in zip(days, before) if b == is_before]
        ax.bar(xs, [v for v, b in zip(dau, before) if b == is_before], width=0.8,
               color=color, alpha=0.28, label=f"{label} (daily)")
        ax.plot(xs, [v for v, b in zip(rolling, before) if b == is_before], color=color,
                linewidth=2, label=f"{label} (7-day avg)")

    for key, color, (start, end) in (("before", BLUE, (days[0], RELEASE)),
                                     ("after", ORANGE, (RELEASE, days[-1]))):
        ax.hlines(averages[key], start, end, colors=color, linestyles="--", linewidth=1.5)
        ax.annotate(f"avg {averages[key]}", (end, averages[key]), xytext=(-4, 5),
                    textcoords="offset points", ha="right", fontsize=9, color=INK)

    ax.axvline(RELEASE, color=INK_2, linewidth=1)
    ax.annotate("Kanban board released", (RELEASE, ax.get_ylim()[1]), xytext=(6, -14),
                textcoords="offset points", fontsize=9, color=INK)
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    ax.set_ylabel("Unique users logged in", color=INK_2, fontsize=9)
    ax.legend(frameon=False, fontsize=8.5, ncol=4, loc="upper left", bbox_to_anchor=(0, -0.08))
    fig.tight_layout()
    fig.savefig(OUT_DIR / "daily_active_users.png", dpi=150)
    plt.close(fig)


def status_changes_by_card_chart(db, queries):
    rows = db.execute(queries["status_changes_by_card"]).fetchall()
    counts = Counter(r[3] for r in rows)
    xs = list(range(0, max(counts) + 1))
    ys = [counts.get(x, 0) for x in xs]

    fig, ax = plt.subplots(figsize=(8, 5))
    style(ax, "Status changes per card",
          f"{len(rows)} cards · {sum(r[3] for r in rows)} status changes · "
          f"{counts[0]} cards have never moved")
    bars = ax.bar(xs, ys, width=0.7, color=BLUE)
    ax.bar_label(bars, padding=3, fontsize=9, color=INK)
    ax.set_xticks(xs)
    ax.set_xlabel("Number of status changes on the card", color=INK_2, fontsize=9)
    ax.set_ylabel("Number of cards", color=INK_2, fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "status_changes_by_card.png", dpi=150)
    plt.close(fig)


def status_changes_daily_chart(db, queries):
    rows = db.execute(queries["status_changes_daily"]).fetchall()
    days = [date.fromisoformat(r[0]) for r in rows]
    series = (("Backlog → In progress", 2, BLUE),
              ("In progress → Complete", 3, AQUA),
              ("Moved backwards", 4, ORANGE))

    fig, ax = plt.subplots(figsize=(12, 5))
    style(ax, "Card status changes per day",
          f"{sum(r[1] for r in rows)} status changes since the release · "
          "board usage accelerates sharply from Nov 2018")
    bottom = [0] * len(rows)
    for label, col, color in series:
        values = [r[col] for r in rows]
        ax.bar(days, values, bottom=bottom, width=0.8, color=color, label=label,
               edgecolor=SURFACE, linewidth=0.5)
        bottom = [b + v for b, v in zip(bottom, values)]
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    ax.set_ylabel("Status changes", color=INK_2, fontsize=9)
    ax.legend(frameon=False, fontsize=9, loc="upper left")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "status_changes_daily.png", dpi=150)
    plt.close(fig)


def main():
    OUT_DIR.mkdir(exist_ok=True)
    queries = load_queries()
    with sqlite3.connect(DB_PATH) as db:
        dau_chart(db, queries)
        status_changes_by_card_chart(db, queries)
        status_changes_daily_chart(db, queries)
        for name in ("avg_dau_before_after", "avg_dau_30d_window"):
            print(name, db.execute(queries[name]).fetchall())
    print(f"Charts written to {OUT_DIR}")


if __name__ == "__main__":
    main()
