"""
inject_data.py — Blog Intel Data Injector
==========================================
JSON files se data padhta hai aur index.html mein inject karta hai.
GitHub Actions mein fetch_data.py ke baad automatically chalta hai.

Run karo:
    python inject_data.py
"""

import json
import re
import os
from datetime import datetime

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
DATA_DIR   = "data"
HTML_FILE  = "index.html"
TODAY      = datetime.now().strftime("%Y-%m-%d")
TODAY_LONG = datetime.now().strftime("%b %d, %Y")

SITES = [
    "naukri",
    "internshala",
    "hackerearth",
    "careers360",
    "geeksforgeeks",
]

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def load_json(site):
    path = os.path.join(DATA_DIR, f"{site}.json")
    if not os.path.exists(path):
        print(f"  ⚠  {path} not found — skipping")
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def posts_to_js(posts):
    """Posts list → JavaScript array string"""
    lines = []
    for p in posts:
        u = str(p.get("u", "")).replace("\\", "\\\\").replace('"', '\\"')
        t = str(p.get("t", "")).replace("\\", "\\\\").replace('"', '\\"').replace("'", "")
        d = str(p.get("d", ""))[:10]
        c = str(p.get("c", "")).replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'{{u:"{u}",t:"{t}",d:"{d}",c:"{c}"}}')
    return "[\n" + ",\n".join(lines) + "\n]"


def update_db(html, site, js_array):
    """Replace site's data array in const DB = {...}"""

    # Pattern: site_key:[ ... ] inside DB object
    # Uses non-greedy match between the site key and next site key or closing }
    pattern = rf'({re.escape(site)}:\[)(.*?)(\](?=\s*[,}}]))'

    def replacer(m):
        return site + ":" + js_array

    new_html, count = re.subn(pattern, replacer, html, count=1, flags=re.DOTALL)
    if count == 0:
        # Site not found in DB — append before closing };
        # Find DB end
        db_end = html.rfind("};")
        if db_end == -1:
            print(f"  ✗ Could not find DB end for {site}")
            return html
        insert = f",\n{site}:{js_array}"
        new_html = html[:db_end] + insert + "\n" + html[db_end:]
        print(f"  ➕ {site}: appended to DB")
    else:
        print(f"  ✅ {site}: data replaced")

    return new_html


def update_site_pill_count(html, site, count):
    """Update '107 posts in database' in site pill"""
    site_names = {
        "naukri":       "Naukri.com",
        "internshala":  "Internshala.com",
        "hackerearth":  "HackerEarth",
        "careers360":   "Careers360",
        "geeksforgeeks":"GeeksforGeeks",
    }
    name = site_names.get(site, site)

    # Match the pill for this site and update count
    pattern = rf'(data-k="{re.escape(site)}"[^>]*>.*?<div class="site-pill-url">)\d+ posts in database'
    replacement = rf'\g<1>{count} posts in database'
    new_html, n = re.subn(pattern, replacement, html, count=1, flags=re.DOTALL)
    if n:
        print(f"  ✅ {site}: pill count → {count}")
    return new_html


def update_masthead_count(html, site, count):
    """Update masthead meta counts"""
    labels = {
        "naukri":        "Naukri:",
        "internshala":   "Internshala:",
        "hackerearth":   "HackerEarth:",
        "careers360":    "Careers360:",
        "geeksforgeeks": "GFG:",
    }
    label = labels.get(site)
    if not label:
        return html

    pattern = rf'({re.escape(label)} <b>)\d+(</b>)'
    new_html, n = re.subn(pattern, rf'\g<1>{count}\2', html, count=1)
    if n:
        print(f"  ✅ {site}: masthead count → {count}")
    return new_html


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    print(f"\n{'='*50}")
    print(f"  BLOG INTEL — Data Injector")
    print(f"  {TODAY}")
    print(f"{'='*50}\n")

    # Load HTML
    if not os.path.exists(HTML_FILE):
        print(f"❌ {HTML_FILE} not found!")
        return

    with open(HTML_FILE, "r", encoding="utf-8") as f:
        html = f.read()

    print(f"📄 Loaded {HTML_FILE} ({len(html):,} bytes)\n")

    total_posts = 0

    for site in SITES:
        print(f"Processing: {site}")
        data = load_json(site)
        if not data:
            continue

        posts = data.get("posts", [])
        count = len(posts)
        total_posts += count

        # Build JS array
        js_array = posts_to_js(posts)

        # Update DB in HTML
        html = update_db(html, site, js_array)

        # Update pill count
        html = update_site_pill_count(html, site, count)

        # Update masthead count
        html = update_masthead_count(html, site, count)

        print()

    # Update date strings
    html = re.sub(
        r'Data as of [A-Za-z]+ \d{1,2}, \d{4}',
        f'Data as of {TODAY_LONG}',
        html
    )
    html = re.sub(
        r"const TODAY='[\d-]+'",
        f"const TODAY='{TODAY}'",
        html
    )
    html = re.sub(
        r'<span class="topbar-date">[^<]+</span>',
        f'<span class="topbar-date">{TODAY_LONG}</span>',
        html
    )

    # Save updated HTML
    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"{'='*50}")
    print(f"✅ index.html updated — {TODAY_LONG}")
    print(f"📊 Total posts injected: {total_posts:,}")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
