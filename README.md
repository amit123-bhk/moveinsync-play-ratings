# MoveInSync Play Store ratings tracker

A small Python script that answers "How are our Play Store ratings?" on demand, and keeps history so the answer is a trend instead of a single number.

Built for the MoveInSync FDE case study. The full recommendation is linked in my submission.

## What it does

- `snapshot` records today's rating, rating count, star split and app version for `com.moveinsync.ets` into `data/history.csv`.
- `reviews` pulls the newest Play Store reviews into `data/reviews.csv`, with duplicates removed.
- `report` tags each review by theme (login/OTP, crashes, booking, notifications, tracking, safety checks, ads, performance, permissions, support) and writes `report.md`: complaint themes among 1 and 2 star reviews, health by app version, and week-over-week movement.

## Run it

```
pip install google-play-scraper pandas tabulate
python ratings_tracker.py snapshot
python ratings_tracker.py reviews -n 3000
python ratings_tracker.py report
```

To analyse an existing CSV instead of scraping, use columns `reviewId, score, content, appVersion, at`:

```
python ratings_tracker.py report --reviews path/to/reviews.csv
```

## Notes

- Theme tagging is keyword based, so expect to tune the lists in `THEMES` after reading real reviews.
- Run it weekly (cron or GitHub Actions) and post `report.md` to the product channel.
- `tests/fixture.csv` is a tiny made-up sample for checking the logic offline. It is not real data.
