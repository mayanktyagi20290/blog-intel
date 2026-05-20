"""
fetch_data.py — Blog Intel Data Fetcher
=========================================
Yeh script in 5 sites ka blog data fetch karta hai:
1. Naukri.com        → sitemap se
2. Internshala.com   → blog pages scrape
3. HackerEarth       → blog pages scrape
4. Careers360        → sitemap + articles scrape
5. GeeksforGeeks     → blogs sitemap se

Run karo:
    pip install requests
    python fetch_data.py

Output:
    data/naukri.json
    data/internshala.json
    data/hackerearth.json
    data/careers360.json
    data/geeksforgeeks.json
"""

import requests
import json
import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
OUTPUT_DIR = "data"
TODAY = datetime.now().strftime("%Y-%m-%d")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}

# ─────────────────────────────────────────────
# CATEGORY DETECTION
# ─────────────────────────────────────────────
def categorize(url, title=""):
    s = (url + " " + title).lower()
    if any(x in s for x in ["hackathon","hack-a-thon","ideathon"]):
        return "Hackathon"
    if any(x in s for x in ["interview","tell-me-about","strengths","weakness","behavioral","walk-in","interview-tips","interview-mistakes","interview-questions"]):
        return "Interview Prep"
    if any(x in s for x in ["leave-application","casual-leave","sick-leave","maternity","one-day-leave","resignation","apology-letter","formal-letter","job-application","appointment-letter"]):
        return "Letters & Applications"
    if any(x in s for x in ["resume","cv-","career-objective","email-writing"]):
        return "Resume & Writing"
    if any(x in s for x in ["salary","negotiate","high-paying","stipend","ctc","package"]):
        return "Salary & Finance"
    if any(x in s for x in ["women","international-womens","empowerment"]):
        return "Women in Workplace"
    if any(x in s for x in ["jobspeak","hiring-trends","white-collar","resdex","premiumx","ai-rex","recruiting-trend","recruitment-trend"]):
        return "Industry Reports"
    if any(x in s for x in ["data-scientist","data-analyst","software-engineer","electrical","mechanical","ui-ux","project-manager","product-manager","artificial-intelligence","machine-learning","python","javascript","java-","cpp","data-science","system-design","git-","dsa","algorithm","data-structure"]):
        return "Tech & Coding"
    if any(x in s for x in ["employer-","hr-","hiring-","talent-","recruit","assessment","proctoring","campus-hiring"]):
        return "HR & Talent"
    if any(x in s for x in ["internship","intern-"]):
        return "Internship Tips"
    if any(x in s for x in ["jee","neet","gate","upsc","ssc","cat-exam","xat","gmat","gre","exam","result","admit-card","syllabus","cutoff","counselling"]):
        return "Competitive Exams"
    if any(x in s for x in ["college","university","admission","placement","campus"]):
        return "Education & Colleges"
    if any(x in s for x in ["career","job-","skills","leadership","entrepreneur","work-life","freelan"]):
        return "Career Advice"
    return "General"


def slug_to_title(url):
    path = urlparse(url).path
    slug = path.strip("/").split("/")[-1]
    slug = slug.replace("-", " ").replace("_", " ")
    return " ".join(w.capitalize() for w in slug.split())[:100]


# ─────────────────────────────────────────────
# FETCH HELPERS
# ─────────────────────────────────────────────
def safe_get(url, timeout=15, retries=2):
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
            if r.status_code == 200:
                return r
            elif r.status_code == 429:
                print(f"    ⏳ Rate limited, waiting 10s...")
                time.sleep(10)
            else:
                print(f"    ✗ HTTP {r.status_code}: {url}")
                return None
        except requests.exceptions.Timeout:
            print(f"    ⏳ Timeout (attempt {attempt+1}): {url}")
            time.sleep(3)
        except Exception as e:
            print(f"    ✗ Error: {e}")
            return None
    return None


def parse_sitemap_xml(xml_content, source_url):
    """Parse sitemap XML — handles both sitemap index and urlset"""
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as e:
        print(f"    ✗ XML parse error: {e}")
        return [], []

    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

    # Sitemap index
    child_sitemaps = root.findall(".//sm:sitemap/sm:loc", ns)
    if child_sitemaps:
        return [el.text.strip() for el in child_sitemaps], []

    # URL set
    posts = []
    for url_el in root.findall(".//sm:url", ns):
        loc = url_el.find("sm:loc", ns)
        lastmod = url_el.find("sm:lastmod", ns)
        if loc is None:
            continue
        u = loc.text.strip()
        d = (lastmod.text.strip()[:10] if lastmod is not None and lastmod.text else "")
        posts.append({
            "u": u,
            "t": slug_to_title(u),
            "d": d,
            "c": categorize(u),
        })
    return [], posts


def fetch_sitemap_recursive(start_url, visited=None, max_depth=4):
    """Recursively fetch all URLs from a sitemap index"""
    if visited is None:
        visited = set()
    if start_url in visited or len(visited) > 50:
        return []
    visited.add(start_url)

    print(f"  → Sitemap: {start_url}")
    r = safe_get(start_url)
    if not r:
        return []

    child_sitemaps, posts = parse_sitemap_xml(r.content, start_url)

    if child_sitemaps:
        print(f"    ↳ Index with {len(child_sitemaps)} child sitemaps")
        for child in child_sitemaps:
            if child not in visited:
                posts.extend(fetch_sitemap_recursive(child, visited, max_depth - 1))
                time.sleep(0.3)

    return posts


# ─────────────────────────────────────────────
# HTML BLOG PAGE SCRAPER
# ─────────────────────────────────────────────
class BlogListParser(HTMLParser):
    """Generic WordPress blog listing parser"""
    def __init__(self, base_domain):
        super().__init__()
        self.posts = []
        self.seen = set()
        self.base_domain = base_domain
        self._cur = {}
        self._in_article = False
        self._in_title = False
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("article", "div"):
            cls = attrs.get("class", "")
            if any(x in cls for x in ["post-item", "blog-post", "post ", "entry", "article-card", "blog-card"]):
                self._in_article = True
                self._cur = {}
        if tag == "article":
            self._in_article = True
            self._cur = {}

        if self._in_article:
            if tag == "a" and "href" in attrs:
                href = attrs["href"]
                # Only blog URLs, skip navigation/category links
                if (self.base_domain in href and
                    "/blog/" in href and
                    href not in self.seen and
                    len(href.split("/")) > 5 and
                    not any(x in href for x in ["#", "?cat=", "?tag=", "/page/", "/author/", "/category/"])):
                    if not self._cur.get("u"):
                        self._cur["u"] = href
            if tag in ("h1", "h2", "h3") and not self._cur.get("t"):
                self._in_title = True
            if tag == "time":
                dt = attrs.get("datetime", "")
                if dt and not self._cur.get("d"):
                    self._cur["d"] = dt[:10]

    def handle_data(self, data):
        if self._in_title and data.strip():
            self._cur["t"] = (self._cur.get("t", "") + data).strip()[:120]

    def handle_endtag(self, tag):
        if tag in ("h1", "h2", "h3"):
            self._in_title = False
        if tag in ("article", "div") and self._in_article and self._cur.get("u"):
            u = self._cur["u"]
            if u not in self.seen:
                self.seen.add(u)
                self.posts.append({
                    "u": u,
                    "t": self._cur.get("t") or slug_to_title(u),
                    "d": self._cur.get("d", ""),
                    "c": categorize(u, self._cur.get("t", "")),
                })
            self._in_article = False
            self._cur = {}


def scrape_blog_pages(base_url, domain, max_pages=100, delay=0.5):
    """Scrape WordPress blog listing pages"""
    all_posts = []
    seen_urls = set()

    for page in range(1, max_pages + 1):
        url = base_url if page == 1 else base_url.rstrip("/") + f"/page/{page}/"
        print(f"  → Page {page}: {url}")

        r = safe_get(url)
        if not r:
            print(f"  ✓ Stopped at page {page}")
            break

        # Check if it's a 404 page
        if "404" in r.url or r.status_code == 404:
            print(f"  ✓ Reached end at page {page}")
            break

        parser = BlogListParser(domain)
        try:
            parser.feed(r.text)
        except Exception as e:
            print(f"    ✗ Parse error: {e}")
            break

        new_posts = [p for p in parser.posts if p["u"] not in seen_urls]
        if not new_posts:
            print(f"  ✓ No new posts on page {page} — stopping")
            break

        for p in new_posts:
            seen_urls.add(p["u"])
            all_posts.append(p)

        print(f"    ✓ {len(new_posts)} new posts (total: {len(all_posts)})")
        time.sleep(delay)

    return all_posts


# ─────────────────────────────────────────────
# SITE-SPECIFIC FETCHERS
# ─────────────────────────────────────────────

def fetch_naukri():
    print("\n" + "="*50)
    print("📰 NAUKRI.COM — sitemap-posts.xml")
    print("="*50)
    posts = fetch_sitemap_recursive("https://www.naukri.com/blog/sitemap-posts.xml")
    print(f"  ✅ Total: {len(posts)} posts")
    return posts


def fetch_internshala():
    print("\n" + "="*50)
    print("📰 INTERNSHALA.COM — blog scrape")
    print("="*50)

    # Try sitemap first
    sitemap_posts = fetch_sitemap_recursive("https://internshala.com/blog/sitemap.xml")
    if sitemap_posts:
        print(f"  ✅ Sitemap: {len(sitemap_posts)} posts")
        return sitemap_posts

    # Fallback: scrape blog pages
    print("  Sitemap blocked — scraping blog pages...")
    posts = scrape_blog_pages(
        "https://internshala.com/blog/latest-posts/",
        "internshala.com",
        max_pages=250,
        delay=0.5
    )
    print(f"  ✅ Total: {len(posts)} posts")
    return posts


def fetch_hackerearth():
    print("\n" + "="*50)
    print("📰 HACKEREARTH — blog scrape")
    print("="*50)

    all_posts = []
    seen = set()

    # Try different blog URL patterns
    blog_urls = [
        "https://www.hackerearth.com/blog/",
        "https://www.hackerearth.com/blog/developers/",
        "https://www.hackerearth.com/blog/talent-assessment/",
        "https://www.hackerearth.com/blog/innovation-management/",
        "https://www.hackerearth.com/blog/recruit/",
    ]

    # First try sitemap
    sitemap_posts = fetch_sitemap_recursive("https://www.hackerearth.com/sitemap.xml")
    blog_posts = [p for p in sitemap_posts if "/blog/" in p["u"]]
    if blog_posts:
        print(f"  ✅ Sitemap: {len(blog_posts)} blog posts")
        return blog_posts

    # Scrape blog listing pages
    for base_url in blog_urls:
        print(f"\n  Section: {base_url}")
        posts = scrape_blog_pages(base_url, "hackerearth.com", max_pages=50, delay=0.6)
        for p in posts:
            if p["u"] not in seen:
                seen.add(p["u"])
                all_posts.append(p)

    # Also try paginated main blog
    posts = scrape_blog_pages("https://www.hackerearth.com/blog/", "hackerearth.com", max_pages=100, delay=0.5)
    for p in posts:
        if p["u"] not in seen:
            seen.add(p["u"])
            all_posts.append(p)

    print(f"\n  ✅ Total: {len(all_posts)} posts")
    return all_posts


def fetch_careers360():
    print("\n" + "="*50)
    print("📰 CAREERS360 — sitemap + articles")
    print("="*50)

    all_posts = []
    seen = set()

    # Try sitemaps for different subdomains
    sitemaps = [
        "https://www.careers360.com/sitemap.xml",
        "https://engineering.careers360.com/sitemap.xml",
        "https://medicine.careers360.com/sitemap.xml",
        "https://school.careers360.com/sitemap.xml",
        "https://studyabroad.careers360.com/sitemap.xml",
        "https://competition.careers360.com/sitemap.xml",
    ]

    for sm_url in sitemaps:
        print(f"\n  Trying: {sm_url}")
        posts = fetch_sitemap_recursive(sm_url)
        # Filter: only articles/blog posts
        filtered = [p for p in posts if "/articles/" in p["u"] or "/blogs/" in p["u"]]
        new = [p for p in filtered if p["u"] not in seen]
        for p in new:
            seen.add(p["u"])
            all_posts.append(p)
        print(f"  Found {len(new)} new article posts")
        time.sleep(0.5)

    # Also scrape articles listing
    if len(all_posts) < 100:
        print("\n  Scraping articles pages...")
        article_sections = [
            ("https://www.careers360.com/careers/articles", "careers360.com"),
            ("https://engineering.careers360.com/articles", "careers360.com"),
        ]
        for url, domain in article_sections:
            posts = scrape_blog_pages(url, domain, max_pages=50, delay=0.5)
            for p in posts:
                if p["u"] not in seen:
                    seen.add(p["u"])
                    all_posts.append(p)

    print(f"\n  ✅ Total: {len(all_posts)} posts")
    return all_posts


def fetch_geeksforgeeks():
    print("\n" + "="*50)
    print("📰 GEEKSFORGEEKS — blogs sitemap")
    print("="*50)

    all_posts = []
    seen = set()

    # GFG has a dedicated blogs section
    blog_sitemaps = [
        "https://www.geeksforgeeks.org/sitemap.xml",
        "https://www.geeksforgeeks.org/blogs-sitemap.xml",
        "https://www.geeksforgeeks.org/news-sitemap.xml",
    ]

    for sm_url in blog_sitemaps:
        print(f"\n  Trying: {sm_url}")
        posts = fetch_sitemap_recursive(sm_url)
        # Filter only blog posts
        filtered = [p for p in posts if "/blogs/" in p["u"] or "/blog/" in p["u"]]
        if not filtered:
            # If no blog filter, take all article-type URLs
            filtered = [p for p in posts if
                        any(x in p["u"] for x in ["/blogs/", "/blog/", "/techtips/", "/career/"]) and
                        "geeksforgeeks.org" in p["u"]]
        new = [p for p in filtered if p["u"] not in seen]
        for p in new:
            seen.add(p["u"])
            all_posts.append(p)
        print(f"  Found {len(new)} new posts")
        time.sleep(0.5)

    # Fallback: scrape GFG blogs page
    if len(all_posts) < 50:
        print("\n  Scraping GFG blogs pages...")
        posts = scrape_blog_pages(
            "https://www.geeksforgeeks.org/blogs/",
            "geeksforgeeks.org",
            max_pages=100,
            delay=0.5
        )
        for p in posts:
            if p["u"] not in seen:
                seen.add(p["u"])
                all_posts.append(p)

    print(f"\n  ✅ Total: {len(all_posts)} posts")
    return all_posts


# ─────────────────────────────────────────────
# SAVE
# ─────────────────────────────────────────────
def save_json(site_key, posts):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    # Sort by date desc
    posts.sort(key=lambda x: x.get("d", ""), reverse=True)
    # Deduplicate by URL
    seen = set()
    unique = []
    for p in posts:
        if p["u"] not in seen and p["u"]:
            seen.add(p["u"])
            unique.append(p)

    data = {
        "site": site_key,
        "fetched": TODAY,
        "total": len(unique),
        "posts": unique
    }
    path = os.path.join(OUTPUT_DIR, f"{site_key}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  💾 Saved: {path} ({len(unique)} posts)")
    return unique


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    print(f"\n{'='*50}")
    print(f"  BLOG INTEL — Data Fetcher")
    print(f"  {TODAY}")
    print(f"{'='*50}")

    sites = {
        "naukri":       fetch_naukri,
        "internshala":  fetch_internshala,
        "hackerearth":  fetch_hackerearth,
        "careers360":   fetch_careers360,
        "geeksforgeeks":fetch_geeksforgeeks,
    }

    results = {}
    for site_key, fetcher in sites.items():
        try:
            posts = fetcher()
            saved = save_json(site_key, posts)
            results[site_key] = len(saved)
        except Exception as e:
            print(f"\n  ❌ {site_key} failed: {e}")
            results[site_key] = 0

    print(f"\n{'='*50}")
    print("  SUMMARY")
    print(f"{'='*50}")
    total = 0
    for site, count in results.items():
        print(f"  {site:<20} {count:>6} posts")
        total += count
    print(f"  {'TOTAL':<20} {total:>6} posts")
    print(f"\n  Files saved in: ./{OUTPUT_DIR}/")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
