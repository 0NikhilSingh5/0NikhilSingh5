#!/usr/bin/env python3
"""Render assets/streak.svg from the GitHub contribution calendar.

The card is ours, so there is no third-party cache between a commit and the profile
picture: the workflow commits the SVG, and the README points at the raw file.
"""

import hashlib
import json
import os
import re
import urllib.request
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
LOGIN = os.environ.get("GH_USER", "0NikhilSingh5")
TZ = ZoneInfo(os.environ.get("STREAK_TZ", "Asia/Kolkata"))
OUT = os.path.join(os.path.dirname(__file__), "..", "assets", "streak.svg")

QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays { date contributionCount }
        }
      }
    }
  }
}
"""


def fetch_calendar() -> tuple[int, dict[str, int], date]:
    if not TOKEN:
        raise SystemExit("GH_TOKEN or GITHUB_TOKEN is required")
    today = datetime.now(TZ).date()
    try:
        start = today.replace(year=today.year - 1)
    except ValueError:  # 29 February
        start = today.replace(year=today.year - 1, day=28)
    variables = {
        "login": LOGIN,
        "from": datetime.combine(start, time.min, TZ).isoformat(),
        "to": datetime.combine(today, time.max, TZ).isoformat(),
    }
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": variables}).encode(),
        headers={
            "Authorization": f"bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "streak-card",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if "errors" in payload:
        raise SystemExit(payload["errors"])
    calendar = payload["data"]["user"]["contributionsCollection"][
        "contributionCalendar"
    ]
    days = {
        day["date"]: day["contributionCount"]
        for week in calendar["weeks"]
        for day in week["contributionDays"]
    }
    return calendar["totalContributions"], days, today


def streaks(
    days: dict[str, int], today: date
) -> tuple[tuple[str, str] | None, int, tuple[str, str] | None]:
    # A day still in progress should not break the current streak: fall back to yesterday.
    end = today
    if days.get(end.isoformat(), 0) == 0:
        end = date.fromordinal(end.toordinal() - 1)
    current = None
    start = end
    while days.get(start.isoformat(), 0) > 0:
        start = date.fromordinal(start.toordinal() - 1)
    first = date.fromordinal(start.toordinal() + 1)
    if first <= end:
        current = ((first.isoformat(), end.isoformat()), (end - first).days + 1)

    longest = (None, 0)
    run_start = None
    for iso in sorted(days):
        if days[iso] > 0:
            if run_start is None:
                run_start = iso
            length = (date.fromisoformat(iso) - date.fromisoformat(run_start)).days + 1
            if length > longest[1]:
                longest = ((run_start, iso), length)
        else:
            run_start = None
    return (current[0] if current else None, longest[0], longest[1])


def pretty_range(bounds: tuple[str, str] | None) -> str:
    if not bounds:
        return "No active streak"
    start, end = (datetime.strptime(value, "%Y-%m-%d").date() for value in bounds)
    if start.year == end.year:
        return f"{start:%b} {start.day} - {end:%b} {end.day}"
    return f"{start:%b} {start.day}, {start.year} - {end:%b} {end.day}, {end.year}"


def render(total: int, days: dict[str, int], today: date) -> str:
    current_range, longest_range, longest_length = streaks(days, today)
    current_length = 0
    if current_range:
        current_length = (
            date.fromisoformat(current_range[1]) - date.fromisoformat(current_range[0])
        ).days + 1
    first, last = sorted(days)[0], sorted(days)[-1]
    total_range = pretty_range((first, last))

    columns = [
        (str(total), "Total Contributions", total_range, "#c9d1d9", "#8b949e"),
        (
            str(current_length),
            "Current Streak",
            pretty_range(current_range),
            "#dc4405",
            "#dc4405",
        ),
        (
            str(longest_length),
            "Longest Streak",
            pretty_range(longest_range),
            "#c9d1d9",
            "#8b949e",
        ),
    ]
    width, height = 495, 195
    centers = (82.5, 247.5, 412.5)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title">',
        f'<title id="title">{LOGIN} contribution streak</title>',
        f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="4.5" fill="#0d1117" stroke="#21262d"/>',
        '<line x1="165" y1="28" x2="165" y2="170" stroke="#21262d"/>',
        '<line x1="330" y1="28" x2="330" y2="170" stroke="#21262d"/>',
    ]
    font = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"
    for x, (number, label, dates, number_color, label_color) in zip(centers, columns):
        parts.extend(
            [
                f'<text x="{x}" y="84" text-anchor="middle" font-family="{font}" font-size="30" '
                f'font-weight="700" fill="{number_color}">{number}</text>',
                f'<text x="{x}" y="112" text-anchor="middle" font-family="{font}" font-size="11" '
                f'font-weight="600" letter-spacing="0.8" fill="{label_color}">{label.upper()}</text>',
                f'<text x="{x}" y="136" text-anchor="middle" font-family="{font}" font-size="10" '
                f'fill="#8b949e">{dates}</text>',
            ]
        )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def main() -> None:
    total, days, today = fetch_calendar()
    svg = render(total, days, today)
    path = os.path.abspath(OUT)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(svg)
    # GitHub proxies README images through camo, which keys on the URL. Bump the query
    # whenever the drawing changes so the profile cannot keep serving the old card.
    version = hashlib.sha1(svg.encode()).hexdigest()[:8]
    readme = os.path.join(os.path.dirname(__file__), "..", "README.md")
    with open(readme, encoding="utf-8") as handle:
        text = handle.read()
    text, count = re.subn(r"assets/streak\.svg(?:\?v=[0-9a-f]+)?", f"assets/streak.svg?v={version}", text)
    if count:
        with open(readme, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"wrote {path} ({total} contributions, {version})")


if __name__ == "__main__":
    main()
