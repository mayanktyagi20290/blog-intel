"""
inject_data.py
JSON data ko index.html mein inject karta hai.
GitHub Actions mein fetch_data.py ke baad chalta hai.
"""

import json
import re
import os
from datetime import datetime

def load_json(path):
    if not os.path.exists(path):
        print(f"  ✗ {path} not found — skipping")
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def posts_to_js(posts):
    """Posts list ko JS array string mein convert karo"""
    lines = []
    for p in posts:
        u = p.get('u','').replace('"','\\"').replace('\\','\\\\')
        t = p.get('t','').replace('"','\\"').replace('\\','\\\\')
        d = p.get('d','')
        c = p.get('c','').replace('"','\\"')
        lines.append(f'{{u:"{u}",t:"{t}",d:"{d}",c:"{c}"}}')
    return '[\n' + ',\n'.join(lines) + '\n]'

def main():
    print("\n📝 Injecting data into index.html...")

    naukri_data    = load_json('data/naukri.json')
    internshala_data = load_json('data/internshala.json')

    if not naukri_data and not internshala_data:
        print("  ✗ No data files found — aborting")
        return

    with open('index.html', 'r', encoding='utf-8') as f:
        html = f.read()

    today = datetime.now().strftime('%Y-%m-%d')

    # ── Replace naukri data ──────────────────────────────────────
    if naukri_data:
        posts = naukri_data['posts']
        js_array = posts_to_js(posts)
        # Match the naukri: [...] block inside const DB = { naukri:[...], internshala:[...] }
        pattern = r'(naukri:\s*\[)(.*?)(\](?=\s*,?\s*internshala))'
        replacement = f'naukri:{js_array}'
        new_html = re.sub(pattern, replacement, html, flags=re.DOTALL)
        if new_html != html:
            html = new_html
            print(f"  ✓ Naukri: {len(posts)} posts injected")
        else:
            print("  ✗ Naukri: pattern not matched — check DB format in index.html")

    # ── Replace internshala data ─────────────────────────────────
    if internshala_data:
        posts = internshala_data['posts']
        js_array = posts_to_js(posts)
        pattern = r'(internshala:\s*\[)(.*?)(\]\s*\};\s*//\s*CATEGORY)'
        replacement = f'internshala:{js_array}\n}}; // CATEGORY'
        new_html = re.sub(pattern, replacement, html, flags=re.DOTALL)
        if new_html != html:
            html = new_html
            print(f"  ✓ Internshala: {len(posts)} posts injected")
        else:
            print("  ✗ Internshala: pattern not matched — check DB format in index.html")

    # ── Update "Data as of" date ─────────────────────────────────
    html = re.sub(
        r'Data as of [A-Za-z]+ \d+, \d{4}',
        f'Data as of {datetime.now().strftime("%b %d, %Y")}',
        html
    )
    # Update TODAY variable
    html = re.sub(
        r"const TODAY='[\d-]+'",
        f"const TODAY='{today}'",
        html
    )
    # Update topbar date
    html = re.sub(
        r'<span class="topbar-date">[^<]+</span>',
        f'<span class="topbar-date">{datetime.now().strftime("%b %d, %Y")}</span>',
        html
    )
    # Update masthead post counts
    if naukri_data:
        html = re.sub(
            r'(\d+) posts in database(?=.*?Naukri)',
            f"{naukri_data['total']} posts in database",
            html, count=1
        )
    if internshala_data:
        html = re.sub(
            r'(\d+) posts in database(?=.*?Internshala)',
            f"{internshala_data['total']} posts in database",
            html, count=1
        )

    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"  ✓ index.html updated — {today}")
    print("✅ Done!\n")

if __name__ == '__main__':
    main()
