# Blog Intel — Competitor Content Tracker

Naukri.com aur Internshala.com ke blog posts track karo date range ke saath.

## Features
- Date range filter (7d, 30d, 90d, 6mo, 1yr, All)
- Publishing timeline chart
- Category breakdown
- Content cluster detection
- Search + filter + CSV export

## Auto-update
GitHub Actions roz raat ko automatically:
1. Naukri sitemap fetch karta hai
2. Internshala blog scrape karta hai  
3. index.html update karta hai
4. Changes commit karta hai

## Manual trigger
GitHub → Actions → "Update Blog Data Daily" → "Run workflow"

## Live site
https://mayanktyagi20290.github.io/blog-intel/

---

## Competitor Weekly Tracker (`/competitors`)
~90 B2B competitors by category (assessment, ATS, AI hiring, campus, hackathons…) — kaun kitne naye blogs weekly add kar raha hai.

- List: `competitors/competitors.csv` (Category, Competitor, Blog URL, Sitemap override). Naya competitor = nayi row.
- Crawler: `competitors/track.py` (sitemap lastmod, RSS fallback). History `competitors/history.json` mein jama hoti hai.
- Auto-run: GitHub Actions "Competitor Blog Tracker" — har Monday 9:00 IST, ya Actions → Run workflow.
- Dashboard: `/competitors/` (https://mayanktyagi20290.github.io/blog-intel/competitors/) — category-wise aur competitor-wise weekly heatmap + CSV export.
- Jis row ka Status "No sitemap/RSS found" ho, uska sitemap URL CSV ke 4th column mein daalo.
