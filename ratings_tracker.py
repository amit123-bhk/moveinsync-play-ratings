#!/usr/bin/env python3
"""
MoveInSync Play Store ratings tracker.

Answers "How are our Play Store ratings?" on demand, and keeps history so the
answer is a trend, not a single number.

    pip install google-play-scraper pandas
    python ratings_tracker.py snapshot      # today's rating + star histogram -> data/history.csv
    python ratings_tracker.py reviews -n 3000   # newest reviews -> data/reviews.csv (deduped)
    python ratings_tracker.py report        # themes, by-version, week-over-week -> report.md

    # offline (no network): analyse any CSV with columns
    # reviewId, score, content, appVersion, at
    python ratings_tracker.py report --reviews data/reviews.csv

Run weekly (cron / GitHub Actions) and post report.md to the product channel.
"""
import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

APP_ID = "com.moveinsync.ets"
DATA = Path("data")
HISTORY = DATA / "history.csv"
REVIEWS = DATA / "reviews.csv"

# Theme rules. Order does not matter; a review can hit several themes.
# Includes common Hinglish spellings because many reviews are written that way.
THEMES = {
    "Login / OTP": r"\botp\b|log ?in|sign ?in|can'?t (log|sign)|unable to (log|sign)|verification code|not receiv",
    "Crash / won't open": r"crash|force close|not open|won'?t open|keeps? closing|stuck on (splash|loading)|white screen|black screen|hang|freez",
    "Booking / trip not showing": r"book(ing)?\b.*(fail|not|error|cancel)|trip.*(not|missing|disappear|cancel)|roster|schedule.*(not|fail)|no (cab|trip|booking)|not (booked|showing)",
    "Notifications": r"notification|notif|alert|reminder",
    "Live tracking / ETA": r"track|gps|location|eta\b|live map|map|late|delay|wrong route|not moving",
    "Safety checks (OTP / seat belt / SOS)": r"seat ?belt|sos|panic|safety|unsafe|driver verif|face|selfie|boarding",
    "Ads / clutter": r"\bads?\b|advert|promo|clutter|useless feature|too many",
    "Slow / performance": r"slow|lag|loading|takes? (long|time)|battery|storage|heavy",
    "Permissions / privacy": r"permission|microphone|mic\b|camera|privacy|always asking",
    "Support / no response": r"support|customer care|no response|nobody|complaint|helpdesk|not resolved|ignored",
}
COMPILED = {k: re.compile(v, re.I) for k, v in THEMES.items()}


def tag(text: str) -> list[str]:
    text = text or ""
    hits = [k for k, rx in COMPILED.items() if rx.search(text)]
    return hits or ["Other / unclear"]


def snapshot() -> None:
    from google_play_scraper import app

    a = app(APP_ID, lang="en", country="in")
    h = a["histogram"]  # [1*, 2*, 3*, 4*, 5*]
    row = {
        "date": datetime.now(timezone.utc).date().isoformat(),
        "score": round(a["score"], 3),
        "ratings": a["ratings"],
        "reviews": a["reviews"],
        "installs": a["installs"],
        "version": a["version"],
        "updated": datetime.fromtimestamp(a["updated"], timezone.utc).date().isoformat() if a.get("updated") else "",
        **{f"star{i + 1}": h[i] for i in range(5)},
    }
    row["one_star_share"] = round(h[0] / sum(h), 4)
    DATA.mkdir(exist_ok=True)
    df = pd.DataFrame([row])
    if HISTORY.exists():
        old = pd.read_csv(HISTORY)
        df = pd.concat([old[old["date"] != row["date"]], df])
    df.to_csv(HISTORY, index=False)
    print(df.tail(1).to_string(index=False))


def reviews(n: int) -> None:
    from google_play_scraper import Sort, reviews as fetch

    out, token = [], None
    while len(out) < n:
        batch, token = fetch(
            APP_ID, lang="en", country="in", sort=Sort.NEWEST,
            count=min(200, n - len(out)), continuation_token=token,
        )
        out += batch
        if not token or not batch:
            break
    new = pd.DataFrame(out)[["reviewId", "score", "content", "appVersion", "at", "thumbsUpCount", "replyContent"]]
    DATA.mkdir(exist_ok=True)
    if REVIEWS.exists():
        new = pd.concat([pd.read_csv(REVIEWS), new]).drop_duplicates("reviewId")
    new.to_csv(REVIEWS, index=False)
    print(f"{len(new)} reviews stored in {REVIEWS}")


def report(path: Path, days: int = 28) -> str:
    df = pd.read_csv(path, parse_dates=["at"])
    df["themes"] = df["content"].fillna("").map(tag)
    df["week"] = df["at"].dt.to_period("W").dt.start_time
    lines = [f"# MoveInSync Play Store report ({len(df)} reviews, {df['at'].min():%d %b} to {df['at'].max():%d %b %Y})\n"]

    lines.append(f"Average of sampled reviews: **{df['score'].mean():.2f}**  |  1-star share: **{(df['score'] == 1).mean():.1%}**\n")

    # Themes among 1-2 star reviews: this is what to fix first.
    low = df[df["score"] <= 2].explode("themes")
    t = (low.groupby("themes").size().sort_values(ascending=False).rename("low_star_reviews").to_frame())
    t["share_of_low_star"] = (t["low_star_reviews"] / (df["score"] <= 2).sum()).map("{:.0%}".format)
    lines.append("## What 1-2 star reviewers complain about (a review can hit several themes)\n")
    lines.append(t.to_markdown() + "\n")

    # Version health.
    v = df.groupby("appVersion").agg(reviews=("score", "size"), avg=("score", "mean"), one_star=("score", lambda s: (s == 1).mean()))
    v = v[v["reviews"] >= 20].sort_values("reviews", ascending=False).head(8).round(2)
    lines.append("## By app version (min 20 reviews)\n")
    lines.append(v.to_markdown() + "\n")

    # Week over week.
    w = df.groupby("week").agg(reviews=("score", "size"), avg=("score", "mean"), one_star=("score", lambda s: (s == 1).mean())).tail(6).round(2)
    lines.append("## Last weeks\n")
    lines.append(w.to_markdown() + "\n")

    # Reply coverage on low-star reviews.
    if "replyContent" in df:
        cov = df[df["score"] <= 2]["replyContent"].notna().mean()
        lines.append(f"Developer reply rate on 1-2 star reviews: **{cov:.0%}**\n")
    return "\n".join(lines)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["snapshot", "reviews", "report"])
    p.add_argument("-n", type=int, default=2000)
    p.add_argument("--reviews", type=Path, default=REVIEWS)
    a = p.parse_args()
    if a.cmd == "snapshot":
        snapshot()
    elif a.cmd == "reviews":
        reviews(a.n)
    else:
        md = report(a.reviews)
        Path("report.md").write_text(md)
        print(md)
