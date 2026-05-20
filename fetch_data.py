"""
fetch_data.py
Naukri aur Internshala ka latest blog data fetch karta hai.
GitHub Actions mein automatically roz chalta hai.
"""

import requests
import json
import os
import xml.etree.ElementTree as ET
from datetime import datetime

# ─── HEADERS ───────────────────────────────────────────────────────
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-IN,en;q=0.9',
}

# ─── CATEGORY DETECTION ────────────────────────────────────────────
def categorize(url, title=''):
    s = (url + ' ' + title).lower()
    if any(x in s for x in ['interview','tell-me-about','strengths','weakness','motivate','stress','employment-gap','why-should-i-hire','behavioral','walk-in','promotion-interview','interview-tips','interview-mistakes']):
        return 'Interview Prep'
    if any(x in s for x in ['leave-application','casual-leave','sick-leave','maternity','one-day-leave','letter','resignation','apology','formal-letter','job-application']):
        return 'Letters & Applications'
    if any(x in s for x in ['resume','career-objective','email-writing','introduction','how-to-apply']):
        return 'Resume & Writing'
    if any(x in s for x in ['salary','negotiate','high-paying','mis-report','finance']):
        return 'Salary & Finance'
    if any(x in s for x in ['women','international-womens','empowerment']):
        return 'Women in Workplace'
    if any(x in s for x in ['jobspeak','hiring-trends','white-collar','resdex','premiumx','ai-rex','recruiting']):
        return 'Industry Reports'
    if any(x in s for x in ['data-scientist','data-analyst','software-engineer','electrical','mechanical','ui-ux','project-manager','product-manager','artificial-intelligence','machine-learning','technology','upskilling','data-science']):
        return 'Tech & Career Paths'
    if any(x in s for x in ['appointment-letter','hr-resources','employer','hiring','telecaller','job-description']):
        return 'HR Resources'
    if any(x in s for x in ['internship','intern']):
        return 'Internship Tips'
    if any(x in s for x in ['resume-writing','resume-for','resume-template']):
        return 'Resume Writing'
    return 'Career Advice'

def slug_to_title(slug):
    """URL slug se readable title banao"""
    slug = slug.strip('/').split('/')[-1]
    slug = slug.replace('-2', '').replace('-covid-article3', '')
    words = slug.replace('-', ' ').split()
    return ' '.join(w.capitalize() for w in words)[:100]

# ─── FETCH SITEMAP ─────────────────────────────────────────────────
def fetch_sitemap(url, visited=None, depth=0):
    if visited is None:
        visited = set()
    if url in visited or depth > 3:
        return []
    visited.add(url)

    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"  ✗ Cannot fetch {url}: {e}")
        return []

    try:
        root = ET.fromstring(r.content)
    except ET.ParseError as e:
        print(f"  ✗ XML parse error {url}: {e}")
        return []

    ns = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
    
    # Sitemap index — recursively fetch child sitemaps
    child_sitemaps = root.findall('.//sm:sitemap/sm:loc', ns)
    if child_sitemaps:
        all_urls = []
        for sm in child_sitemaps:
            child_url = sm.text.strip()
            print(f"  → Fetching child: {child_url}")
            all_urls.extend(fetch_sitemap(child_url, visited, depth+1))
        return all_urls

    # URL set — extract posts
    posts = []
    for url_el in root.findall('.//sm:url', ns):
        loc = url_el.find('sm:loc', ns)
        lastmod = url_el.find('sm:lastmod', ns)
        if loc is None:
            continue
        loc_text = loc.text.strip()
        date_text = lastmod.text.strip()[:10] if lastmod is not None else ''
        posts.append({
            'u': loc_text,
            't': slug_to_title(loc_text),
            'd': date_text,
            'c': categorize(loc_text)
        })

    return posts

# ─── FETCH BLOG PAGES (Internshala) ───────────────────────────────
def fetch_blog_pages(base_url, max_pages=50):
    """WordPress blog pages scrape karo"""
    from html.parser import HTMLParser

    class BlogParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.posts = []
            self.seen = set()
            self._in_article = False
            self._current_url = None
            self._current_title = None
            self._current_date = None

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == 'article':
                self._in_article = True
                self._current_url = None
                self._current_title = None
                self._current_date = None
            if self._in_article:
                if tag == 'a' and 'href' in attrs:
                    href = attrs['href']
                    if '/blog/' in href and href not in self.seen and len(href.split('/')) > 5:
                        self._current_url = href
                if tag == 'time' and 'datetime' in attrs:
                    self._current_date = attrs['datetime'][:10]

        def handle_endtag(self, tag):
            if tag == 'article' and self._current_url:
                self.seen.add(self._current_url)
                self.posts.append({
                    'u': self._current_url,
                    't': slug_to_title(self._current_url),
                    'd': self._current_date or '',
                    'c': categorize(self._current_url)
                })
                self._in_article = False

    all_posts = []
    seen_urls = set()

    for page in range(1, max_pages + 1):
        url = base_url if page == 1 else f"{base_url}page/{page}/"
        print(f"  → Scraping page {page}: {url}")
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code == 404:
                print(f"  ✓ Reached end at page {page}")
                break
            r.raise_for_status()
        except Exception as e:
            print(f"  ✗ Error page {page}: {e}")
            break

        parser = BlogParser()
        parser.feed(r.text)

        new_posts = [p for p in parser.posts if p['u'] not in seen_urls]
        if not new_posts:
            print(f"  ✓ No new posts at page {page}, stopping")
            break

        for p in new_posts:
            seen_urls.add(p['u'])
            all_posts.append(p)

        print(f"    Found {len(new_posts)} posts (total: {len(all_posts)})")

        import time
        time.sleep(0.5)  # Rate limiting — server pe zyada load mat dalo

    return all_posts

# ─── MAIN ─────────────────────────────────────────────────────────
def main():
    os.makedirs('data', exist_ok=True)
    today = datetime.now().strftime('%Y-%m-%d')
    print(f"\n{'='*50}")
    print(f"Blog Intel Data Fetch — {today}")
    print(f"{'='*50}\n")

    # ── NAUKRI ──
    print("📰 Fetching Naukri blog sitemap...")
    naukri_posts = fetch_sitemap('https://www.naukri.com/blog/sitemap-posts.xml')
    print(f"  ✓ Total: {len(naukri_posts)} posts\n")

    # ── INTERNSHALA ──
    print("📰 Fetching Internshala blog...")
    internshala_posts = fetch_blog_pages('https://internshala.com/blog/latest-posts/')
    print(f"  ✓ Total: {len(internshala_posts)} posts\n")

    # ── SAVE JSON ──
    naukri_data = {
        'site': 'naukri',
        'fetched': today,
        'total': len(naukri_posts),
        'posts': sorted(naukri_posts, key=lambda x: x['d'], reverse=True)
    }
    internshala_data = {
        'site': 'internshala',
        'fetched': today,
        'total': len(internshala_posts),
        'posts': sorted(internshala_posts, key=lambda x: x['d'], reverse=True)
    }

    with open('data/naukri.json', 'w', encoding='utf-8') as f:
        json.dump(naukri_data, f, ensure_ascii=False, indent=2)
    with open('data/internshala.json', 'w', encoding='utf-8') as f:
        json.dump(internshala_data, f, ensure_ascii=False, indent=2)

    print(f"✅ Data saved:")
    print(f"   data/naukri.json        — {len(naukri_posts)} posts")
    print(f"   data/internshala.json   — {len(internshala_posts)} posts")
    print(f"\n{'='*50}\n")

if __name__ == '__main__':
    main()
