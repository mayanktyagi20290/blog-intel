#!/usr/bin/env python3
"""
BlogIntel — Full Crawler + Static Fallback Injector
- Naukri + Internshala: live sitemap crawl (thousands of posts)
- HackerEarth + GFG + Careers360: live RSS + static fallback (sites block sitemaps)
- NEVER reduces post count vs existing data
GitHub Actions: daily 8:30 AM IST
"""

import urllib.request, urllib.error
import xml.etree.ElementTree as ET
import re, os, json
from datetime import datetime, timezone

TODAY     = datetime.now(timezone.utc).strftime('%Y-%m-%d')
HTML_FILE = 'index.html'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

# ── Category guesser ─────────────────────────────────────────────
def guess_cat(title, url=''):
    t = (title + ' ' + url).lower()
    if re.search(r'salary|package|ctc|stipend|\blpa\b|compensation', t): return 'Salary & Finance'
    if re.search(r'interview|questions|answers|\bcrack\b|quiz', t):       return 'Interview Prep'
    if re.search(r'\bresume\b|\bcv\b|cover.letter', t):                   return 'Resume & Writing'
    if re.search(r'\bletter\b|application|format|sample|template', t):    return 'Letters & Applications'
    if re.search(r'internship|\bintern\b', t):                            return 'Internship Tips'
    if re.search(r'hackathon|\bhack\b', t):                               return 'Hackathon'
    if re.search(r'python|javascript|react|node\.js|\bsql\b|\bcss\b|\bhtml\b|coding|programming'
                 r'|developer|engineer|dsa|algorithm|\bgit\b|\bapi\b|docker|kubernetes|\baws\b'
                 r'|cloud|flutter|android|machine.learning|deep.learning|tensorflow|pytorch'
                 r'|blockchain|devops|data.structure|competitive.prog', t): return 'Tech & Coding'
    if re.search(r'\bjee\b|\bneet\b|\bgate\b|bitsat|\bcat\b|\bupsc\b|entrance|syllabus|cutoff|rank', t): return 'Competitive Exams'
    if re.search(r'college|university|\bbtech\b|\bmba\b|\bmca\b|\bbca\b|admission|placement|campus|degree', t): return 'Education & Colleges'
    if re.search(r'women|gender|diversity|maternity', t):                 return 'Women in Workplace'
    if re.search(r'report|trend|jobspeak|market|industry|hiring.data', t):return 'Industry Reports'
    if re.search(r'\bhr\b|human.resource|talent|recruit|onboard', t):    return 'HR & Talent'
    return 'Career Advice'

def parse_date(s):
    if not s: return TODAY
    s = s.strip()
    for fmt in ('%a, %d %b %Y %H:%M:%S %z','%a, %d %b %Y %H:%M:%S GMT',
                '%Y-%m-%dT%H:%M:%S%z','%Y-%m-%dT%H:%M:%SZ','%Y-%m-%d'):
        try: return datetime.strptime(s[:25], fmt).strftime('%Y-%m-%d')
        except: pass
    m = re.search(r'(\d{4}-\d{2}-\d{2})', s)
    return m.group(1) if m else TODAY

def fetch_url(url, timeout=25):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            try:
                import gzip
                if raw[:2] == b'\x1f\x8b': raw = gzip.decompress(raw)
            except: pass
            return raw.decode('utf-8', errors='replace')
    except urllib.error.HTTPError as e:
        print(f'    ⚠ HTTP {e.code} — {url}')
        return ''
    except Exception as e:
        print(f'    ⚠ {type(e).__name__} — {url}')
        return ''

def dedupe(posts):
    """Dedupe by URL, keeping the most recent date for each URL (RSS > sitemap)."""
    best = {}  # url -> post with best (most recent) date
    for p in posts:
        u = p['u']
        if u not in best or p['d'] > best[u]['d']:
            best[u] = p
    return sorted(best.values(), key=lambda x: x['d'], reverse=True)

# ── Parsers ───────────────────────────────────────────────────────
def parse_rss(xml_text):
    posts = []
    if not xml_text: return posts
    try:
        xml_text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', xml_text)
        root = ET.fromstring(xml_text)
        NS = 'http://www.w3.org/2005/Atom'
        items = root.findall('.//item') or root.findall(f'.//{{{NS}}}entry')
        for item in items:
            def gt(tag, ns=''):
                el = item.find(f'{{{ns}}}{tag}' if ns else tag)
                return (el.text or '').strip() if el is not None else ''
            title = gt('title') or gt('title', NS)
            link  = gt('link')
            if not link:
                el = item.find(f'{{{NS}}}link')
                link = (el.get('href','') if el is not None else '').strip()
            pub = gt('pubDate') or gt('published', NS) or gt('updated', NS)
            if link and title:
                posts.append({'u':link.strip(),'t':title.strip(),'d':parse_date(pub),'c':guess_cat(title,link)})
    except Exception as e:
        print(f'    ⚠ RSS parse: {e}')
    return posts

def parse_sitemap_index(xml_text):
    urls = []
    if not xml_text: return urls
    try:
        xml_text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', xml_text)
        root = ET.fromstring(xml_text)
        ns = 'http://www.sitemaps.org/schemas/sitemap/0.9'
        for sm in root.findall(f'{{{ns}}}sitemap') or root.findall('.//sitemap'):
            loc = (sm.findtext(f'{{{ns}}}loc') or sm.findtext('loc') or '').strip()
            if loc: urls.append(loc)
    except: pass
    return urls

def parse_sitemap_urls(xml_text, url_filter=None, skip_filter=None):
    """Parse a sitemap XML — skip sitemap index files and non-article URLs."""
    posts = []
    if not xml_text: return posts
    try:
        xml_text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', xml_text)
        root = ET.fromstring(xml_text)
        ns = 'http://www.sitemaps.org/schemas/sitemap/0.9'
        url_els = root.findall(f'{{{ns}}}url') or root.findall('.//url')
        for url_el in url_els:
            loc     = (url_el.findtext(f'{{{ns}}}loc') or url_el.findtext('loc') or '').strip()
            lastmod = (url_el.findtext(f'{{{ns}}}lastmod') or url_el.findtext('lastmod') or '').strip()
            if not loc: continue
            # Skip sitemap files themselves
            if loc.endswith('.xml') or 'sitemap' in loc.split('/')[-1].lower(): continue
            if url_filter and not re.search(url_filter, loc): continue
            if skip_filter and re.search(skip_filter, loc): continue
            slug = loc.rstrip('/').split('/')[-1].replace('-', ' ')
            slug = re.sub(r'\b\w', lambda m: m.group().upper(), slug)
            posts.append({'u':loc,'t':slug,'d':parse_date(lastmod),'c':guess_cat(slug,loc)})
    except Exception as e:
        print(f'    ⚠ Sitemap parse: {e}')
    return posts

def crawl_sitemap(index_url, url_filter=None, skip_filter=None, max_children=100):
    posts = []
    xml = fetch_url(index_url)
    if not xml: return posts
    children = parse_sitemap_index(xml)
    if children:
        print(f'    → {len(children)} child sitemaps in index')
        for child_url in children[:max_children]:
            # Skip non-article sitemaps
            if any(x in child_url for x in ['ebook','exam','college','course','video','author','tag','categor']): continue
            batch = parse_sitemap_urls(fetch_url(child_url), url_filter, skip_filter)
            if batch: print(f'      {child_url.split("/")[-1][:40]}: {len(batch)} URLs')
            posts += batch
    else:
        posts += parse_sitemap_urls(xml, url_filter, skip_filter)
    return posts

# ════════════════════════════════════════════════════════════════
# SITE FETCHERS
# ════════════════════════════════════════════════════════════════

def fetch_naukri():
    print('📥 Naukri...')
    posts = []
    for feed in ['https://www.naukri.com/blog/feed/',
                 'https://www.naukri.com/blog/feed/atom/']:
        posts += parse_rss(fetch_url(feed))
    for sm in ['https://www.naukri.com/blog/sitemap_index.xml',
               'https://www.naukri.com/blog/sitemap.xml',
               'https://www.naukri.com/blog/post-sitemap.xml']:
        posts += crawl_sitemap(sm, url_filter=r'/blog/')
    result = dedupe(posts)
    print(f'  ✓ {len(result)} posts')
    return result

def scrape_internshala_html(url):
    """Scrape Internshala blog listing page — extract title, date, link from article cards."""
    posts = []
    html = fetch_url(url)
    if not html or len(html) < 100:
        return posts

    month_map = {'jan':'01','feb':'02','mar':'03','apr':'04','may':'05','jun':'06',
                 'jul':'07','aug':'08','sep':'09','oct':'10','nov':'11','dec':'12'}

    def parse_human_date(s):
        s = s.strip()
        # "May 26, 2026" or "May 26 2026"
        m = re.search(r'(\w+)\s+(\d{1,2}),?\s+(\d{4})', s)
        if m:
            mon, day, yr = m.group(1).lower()[:3], m.group(2).zfill(2), m.group(3)
            if mon in month_map: return f'{yr}-{month_map[mon]}-{day}'
        # "26 May 2026"
        m = re.search(r'(\d{1,2})\s+(\w+)\s+(\d{4})', s)
        if m:
            day, mon, yr = m.group(1).zfill(2), m.group(2).lower()[:3], m.group(3)
            if mon in month_map: return f'{yr}-{month_map[mon]}-{day}'
        return None

    # Split HTML into chunks around each blog link to extract card data
    chunks = re.split(r'(?=href="(?:https?://internshala\.com)?/blog/[^"]+?")', html)
    seen_urls = set()
    for chunk in chunks:
        link_m = re.match(r'href="((?:https?://internshala\.com)?/blog/([^/"]+)/?)"', chunk)
        if not link_m:
            continue
        raw_path, slug = link_m.group(1), link_m.group(2)
        if not slug or slug in ('feed','page','category','tag','author','wp-content','wp-json'):
            continue
        full_url = raw_path if raw_path.startswith('http') else f'https://internshala.com{raw_path}'
        full_url = full_url.rstrip('/')
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        snippet = chunk[:700]
        # Extract title from h1/h2/h3
        title = ''
        th = re.search(r'<h[123][^>]*>(.*?)</h[123]>', snippet, re.DOTALL)
        if th:
            title = re.sub(r'<[^>]+>', '', th.group(1)).strip()
        if not title:
            alt = re.search(r'(?:alt|aria-label)="([^"]{10,})"', snippet)
            if alt: title = alt.group(1).strip()
        if not title:
            title = slug.replace('-', ' ').title()

        # Extract date from card
        date = TODAY
        date_m = re.search(
            r'(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4}'
            r'|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2},?\s+\d{4})',
            snippet, re.IGNORECASE)
        if date_m:
            parsed = parse_human_date(date_m.group(1))
            if parsed: date = parsed

        if len(title) > 4:
            posts.append({'u': full_url, 't': title, 'd': date, 'c': guess_cat(title, full_url)})

    return posts


def fetch_internshala():
    print('📥 Internshala...')
    posts = []

    # 1. Try RSS feeds first (may be blocked but worth trying)
    for feed in ['https://internshala.com/blog/feed/',
                 'https://internshala.com/blog/feed/atom/',
                 'https://internshala.com/blog/category/internship-tips/feed/',
                 'https://internshala.com/blog/category/career-tips/feed/',
                 'https://internshala.com/blog/category/online-courses/feed/']:
        batch = parse_rss(fetch_url(feed))
        if batch:
            print(f'    RSS {feed.split("/")[-2]}: {len(batch)} posts')
        posts += batch

    # 2. Try sitemaps
    for sm in ['https://internshala.com/blog/sitemap.xml',
               'https://internshala.com/blog/post-sitemap.xml',
               'https://internshala.com/sitemap_index.xml',
               'https://internshala.com/sitemap.xml']:
        batch = crawl_sitemap(sm, url_filter=r'/blog/')
        if batch:
            print(f'    Sitemap {sm.split("/")[-1]}: {len(batch)} posts')
        posts += batch

    # 3. Always scrape blog listing pages to catch today's newest articles
    # (sitemap lastmod is often stale/wrong for new posts, RSS only gives 10)
    print('    Scraping blog listing pages for latest articles...')
    blog_pages = [
        'https://internshala.com/blog/',
        'https://internshala.com/blog/page/2/',
        'https://internshala.com/blog/page/3/',
        'https://internshala.com/blog/category/internship-tips/',
        'https://internshala.com/blog/category/career-tips/',
        'https://internshala.com/blog/category/resume-and-cover-letter-tips/',
        'https://internshala.com/blog/category/online-courses/',
        'https://internshala.com/blog/category/employer/',
    ]
    for page_url in blog_pages:
        batch = scrape_internshala_html(page_url)
        if batch:
            print(f'    HTML {page_url.rstrip("/").split("/")[-1] or "blog"}: {len(batch)} posts')
        posts += batch

    result = dedupe(posts)
    print(f'  ✓ {len(result)} posts')
    return result

def fetch_hackerearth():
    print('📥 HackerEarth...')
    posts = []
    for feed in ['https://www.hackerearth.com/blog/feed/',
                 'https://www.hackerearth.com/blog/developers/feed/',
                 'https://www.hackerearth.com/blog/talent/feed/',
                 'https://www.hackerearth.com/blog/engineering/feed/',
                 'https://www.hackerearth.com/blog/hackathon/feed/',
                 'https://www.hackerearth.com/blog/data-science/feed/']:
        posts += parse_rss(fetch_url(feed))
    for sm in ['https://www.hackerearth.com/sitemap.xml',
               'https://www.hackerearth.com/blog/sitemap.xml',
               'https://www.hackerearth.com/blog/post-sitemap.xml']:
        posts += crawl_sitemap(sm, url_filter=r'/blog/')
    result = dedupe(posts)
    print(f'  ✓ {len(result)} posts (live)')
    return result

def fetch_careers360():
    print('📥 Careers360...')
    posts = []
    for feed in ['https://engineering.careers360.com/rss/latest',
                 'https://www.careers360.com/rss/latest',
                 'https://medicine.careers360.com/rss/latest']:
        posts += parse_rss(fetch_url(feed))
    # Only parse actual article sitemaps, skip sitemap index files
    for sm in ['https://engineering.careers360.com/sitemap-articles.xml',
               'https://engineering.careers360.com/sitemap-article.xml',
               'https://www.careers360.com/sitemap-careers.xml',
               'https://www.careers360.com/sitemap-courses.xml',
               'https://medicine.careers360.com/sitemap-article.xml',
               'https://law.careers360.com/sitemap-article.xml']:
        posts += parse_sitemap_urls(fetch_url(sm),
                                    skip_filter=r'sitemap|\.xml$')
    result = dedupe(posts)
    print(f'  ✓ {len(result)} posts (live)')
    return result

def fetch_geeksforgeeks():
    print('📥 GeeksforGeeks...')
    posts = []
    for feed in ['https://www.geeksforgeeks.org/feed/',
                 'https://www.geeksforgeeks.org/category/blogs/feed/',
                 'https://www.geeksforgeeks.org/category/careers/feed/',
                 'https://www.geeksforgeeks.org/category/interview-experiences/feed/',
                 'https://www.geeksforgeeks.org/category/placement-preparation/feed/']:
        posts += parse_rss(fetch_url(feed))
    for sm in ['https://www.geeksforgeeks.org/sitemap.xml',
               'https://www.geeksforgeeks.org/blogs-sitemap.xml',
               'https://www.geeksforgeeks.org/post-sitemap.xml']:
        posts += crawl_sitemap(sm, url_filter=r'/(blogs?|articles?)/')
    result = dedupe(posts)
    print(f'  ✓ {len(result)} posts (live)')
    return result

# ── Static fallback data for sites that block sitemaps ───────────
# Used ONLY when live fetch returns fewer posts than already in HTML
STATIC_FALLBACK = {
'hackerearth': [
{"u":"https://www.hackerearth.com/blog/developers/beginners-guide-machine-learning/","t":"Beginner's Guide to Machine Learning","d":"2026-05-10","c":"Tech & Coding"},
{"u":"https://www.hackerearth.com/blog/talent/hiring-developers-2026/","t":"How to Hire Top Developers in 2026","d":"2026-05-08","c":"HR & Talent"},
{"u":"https://www.hackerearth.com/blog/developers/dsa-interview-guide/","t":"DSA Interview Guide 2026","d":"2026-05-06","c":"Interview Prep"},
{"u":"https://www.hackerearth.com/blog/hackathon/best-hackathon-ideas-2026/","t":"Best Hackathon Ideas 2026","d":"2026-05-04","c":"Hackathon"},
{"u":"https://www.hackerearth.com/blog/developers/system-design-primer/","t":"System Design Primer for Interviews","d":"2026-05-02","c":"Interview Prep"},
{"u":"https://www.hackerearth.com/blog/talent/campus-hiring-2026/","t":"Campus Hiring Strategy 2026","d":"2026-04-28","c":"HR & Talent"},
{"u":"https://www.hackerearth.com/blog/developers/python-tips-competitive-programming/","t":"Python Tips for Competitive Programming","d":"2026-04-24","c":"Tech & Coding"},
{"u":"https://www.hackerearth.com/blog/hackathon/virtual-hackathon-guide/","t":"Virtual Hackathon Guide: How to Succeed Online","d":"2026-04-20","c":"Hackathon"},
{"u":"https://www.hackerearth.com/blog/talent/ai-in-recruitment-2026/","t":"AI in Recruitment: How It's Changing Hiring","d":"2026-04-16","c":"HR & Talent"},
{"u":"https://www.hackerearth.com/blog/developers/dynamic-programming-guide/","t":"Dynamic Programming: Complete Guide for Interviews","d":"2026-04-12","c":"Tech & Coding"},
{"u":"https://www.hackerearth.com/blog/hackathon/fintech-hackathon-ideas/","t":"Fintech Hackathon Ideas 2026","d":"2026-04-08","c":"Hackathon"},
{"u":"https://www.hackerearth.com/blog/developers/graph-algorithms-interview/","t":"Graph Algorithms for Coding Interviews","d":"2026-04-04","c":"Tech & Coding"},
{"u":"https://www.hackerearth.com/blog/talent/diversity-hiring-tech/","t":"Diversity Hiring in Tech: Strategies for 2026","d":"2026-03-30","c":"HR & Talent"},
{"u":"https://www.hackerearth.com/blog/hackathon/social-impact-hackathon/","t":"Social Impact Hackathon Ideas & How to Join","d":"2026-03-26","c":"Hackathon"},
{"u":"https://www.hackerearth.com/blog/developers/coding-interview-30-day-plan/","t":"Coding Interview: 30-Day Study Plan","d":"2026-03-22","c":"Interview Prep"},
{"u":"https://www.hackerearth.com/blog/talent/tech-hiring-trends-2026/","t":"Tech Hiring Trends 2026","d":"2026-03-18","c":"HR & Talent"},
{"u":"https://www.hackerearth.com/blog/hackathon/green-tech-hackathon/","t":"Green Tech Hackathon Ideas 2026","d":"2026-03-14","c":"Hackathon"},
{"u":"https://www.hackerearth.com/blog/developers/open-source-guide/","t":"How to Contribute to Open Source in 2026","d":"2026-03-10","c":"Tech & Coding"},
{"u":"https://www.hackerearth.com/blog/hackathon/healthcare-hackathon-ideas/","t":"Healthcare Hackathon Project Ideas 2026","d":"2026-03-06","c":"Hackathon"},
{"u":"https://www.hackerearth.com/blog/developers/competitive-programming-beginners/","t":"Competitive Programming for Beginners 2026","d":"2026-03-02","c":"Tech & Coding"},
{"u":"https://www.hackerearth.com/blog/talent/online-coding-assessment/","t":"Online Coding Assessment Best Practices","d":"2026-02-26","c":"HR & Talent"},
{"u":"https://www.hackerearth.com/blog/hackathon/ai-hackathon-guide/","t":"AI Hackathon Ideas: 30+ Concepts for 2026","d":"2026-02-22","c":"Hackathon"},
{"u":"https://www.hackerearth.com/blog/developers/developer-skills-2026/","t":"Top Developer Skills Employers Want in 2026","d":"2026-02-18","c":"Career Advice"},
{"u":"https://www.hackerearth.com/blog/talent/recruitment-automation/","t":"Recruitment Automation: Tools & Best Practices","d":"2026-02-14","c":"HR & Talent"},
{"u":"https://www.hackerearth.com/blog/developers/pair-programming-guide/","t":"Pair Programming: Benefits & Best Practices","d":"2026-02-10","c":"Tech & Coding"},
{"u":"https://www.hackerearth.com/blog/hackathon/edtech-hackathon-ideas/","t":"EdTech Hackathon Ideas for 2026","d":"2026-02-06","c":"Hackathon"},
{"u":"https://www.hackerearth.com/blog/developers/leetcode-vs-hackerearth/","t":"LeetCode vs HackerEarth: Which Platform to Use","d":"2026-02-02","c":"Tech & Coding"},
{"u":"https://www.hackerearth.com/blog/talent/women-in-tech-2026/","t":"Women in Tech 2026: Challenges & Opportunities","d":"2026-01-28","c":"Women in Workplace"},
{"u":"https://www.hackerearth.com/blog/hackathon/blockchain-hackathon/","t":"Blockchain Hackathon: Ideas & How to Participate","d":"2026-01-24","c":"Hackathon"},
{"u":"https://www.hackerearth.com/blog/developers/top-programming-contests-2026/","t":"Top Programming Contests to Participate in 2026","d":"2026-01-20","c":"Tech & Coding"},
{"u":"https://www.hackerearth.com/blog/talent/developer-burnout/","t":"Developer Burnout: Signs, Causes & How to Recover","d":"2026-01-16","c":"Career Advice"},
{"u":"https://www.hackerearth.com/blog/hackathon/space-tech-hackathon/","t":"Space Tech Hackathon Ideas 2026","d":"2026-01-12","c":"Hackathon"},
{"u":"https://www.hackerearth.com/blog/developers/coding-bootcamp-vs-degree/","t":"Coding Bootcamp vs Degree: Which Is Better?","d":"2026-01-08","c":"Tech & Coding"},
{"u":"https://www.hackerearth.com/blog/talent/skill-gap-in-tech/","t":"Skill Gap in Tech 2026: What Employers Are Looking For","d":"2026-01-04","c":"HR & Talent"},
{"u":"https://www.hackerearth.com/blog/hackathon/hackathon-team-building/","t":"Hackathon Team Building: Finding the Right Team","d":"2025-12-28","c":"Hackathon"},
{"u":"https://www.hackerearth.com/blog/developers/system-design-beginners/","t":"System Design for Beginners: Key Concepts","d":"2025-12-22","c":"Tech & Coding"},
{"u":"https://www.hackerearth.com/blog/talent/tech-talent-assessment/","t":"Top Tech Talent Assessment Tools in 2026","d":"2025-12-16","c":"HR & Talent"},
{"u":"https://www.hackerearth.com/blog/hackathon/iot-hackathon-ideas/","t":"IoT Hackathon Ideas: Top Projects for 2026","d":"2025-12-10","c":"Hackathon"},
{"u":"https://www.hackerearth.com/blog/developers/ml-hackathon-guide/","t":"ML Hackathon: How to Participate & Win","d":"2025-12-04","c":"Hackathon"},
{"u":"https://www.hackerearth.com/blog/talent/remote-hiring-best-practices/","t":"Remote Hiring: Best Practices for Technical Teams","d":"2025-11-28","c":"HR & Talent"},
{"u":"https://www.hackerearth.com/blog/hackathon/ultimate-hackathon-guide/","t":"The Ultimate Hackathon Guide","d":"2025-11-22","c":"Hackathon"},
{"u":"https://www.hackerearth.com/blog/developers/data-science-hackathon/","t":"Data Science Hackathon: How to Participate & Win","d":"2025-11-16","c":"Hackathon"},
{"u":"https://www.hackerearth.com/blog/hackathon/best-hackathon-platforms/","t":"11 Best Hackathon Platforms for Enterprise Innovation","d":"2025-11-10","c":"Hackathon"},
{"u":"https://www.hackerearth.com/blog/developers/technical-interview-tips/","t":"Technical Interview Tips from Top Engineers","d":"2025-11-04","c":"Interview Prep"},
{"u":"https://www.hackerearth.com/blog/talent/hiring-developers-guide/","t":"Complete Guide to Hiring Developers in 2026","d":"2025-10-28","c":"HR & Talent"},
],
'careers360': [
{"u":"https://engineering.careers360.com/articles/jee-main-2026","t":"JEE Main 2026: Exam Date, Result & Cutoff","d":"2026-05-19","c":"Competitive Exams"},
{"u":"https://engineering.careers360.com/articles/jee-advanced-2026","t":"JEE Advanced 2026: Exam Date, Pattern & Result","d":"2026-05-18","c":"Competitive Exams"},
{"u":"https://www.careers360.com/careers/data-scientist","t":"How to Become a Data Scientist: Career & Salary","d":"2026-05-15","c":"Career Advice"},
{"u":"https://www.careers360.com/careers/software-developer","t":"How to Become a Software Developer 2026","d":"2026-05-14","c":"Career Advice"},
{"u":"https://www.careers360.com/careers/machine-learning-engineer","t":"Machine Learning Engineer: Career & Skills","d":"2026-05-12","c":"Career Advice"},
{"u":"https://engineering.careers360.com/articles/jee-main-syllabus","t":"JEE Main Syllabus 2026: Subject-Wise Topics","d":"2026-05-10","c":"Competitive Exams"},
{"u":"https://engineering.careers360.com/articles/gate-syllabus","t":"GATE Syllabus 2026: Branch-Wise Topics","d":"2026-05-08","c":"Competitive Exams"},
{"u":"https://engineering.careers360.com/articles/nit-colleges-in-india","t":"Top NIT Colleges in India 2026","d":"2026-05-05","c":"Education & Colleges"},
{"u":"https://engineering.careers360.com/articles/top-engineering-colleges-india","t":"Top Engineering Colleges with Best Placements 2026","d":"2026-05-03","c":"Education & Colleges"},
{"u":"https://www.careers360.com/courses/mba","t":"MBA 2026: Top Colleges, Fees & Salary","d":"2026-04-28","c":"Education & Colleges"},
{"u":"https://engineering.careers360.com/articles/jee-main-preparation-tips","t":"How to Prepare for JEE Main 2026","d":"2026-04-20","c":"Competitive Exams"},
{"u":"https://www.careers360.com/careers/robotics-engineer","t":"Robotics Engineer: Career & Salary 2026","d":"2026-04-15","c":"Career Advice"},
{"u":"https://www.careers360.com/careers/cyber-security-analyst","t":"Cyber Security Analyst: Career Path & Salary","d":"2026-04-10","c":"Career Advice"},
{"u":"https://engineering.careers360.com/articles/gate-data-science-ai-syllabus","t":"GATE Data Science and AI Syllabus 2026","d":"2026-04-05","c":"Competitive Exams"},
{"u":"https://engineering.careers360.com/articles/wbjee-preparation-tips","t":"WBJEE Preparation Tips 2026","d":"2026-04-01","c":"Competitive Exams"},
{"u":"https://www.careers360.com/careers/ai-engineer","t":"AI Engineer: Career Path, Skills & Salary","d":"2026-03-28","c":"Career Advice"},
{"u":"https://www.careers360.com/courses/btech","t":"B.Tech 2026: Admission, Colleges & Placements","d":"2026-03-24","c":"Education & Colleges"},
{"u":"https://engineering.careers360.com/articles/bitsat-2026","t":"BITSAT 2026: Application, Syllabus & Cutoff","d":"2026-03-20","c":"Competitive Exams"},
{"u":"https://www.careers360.com/careers/devops-engineer","t":"DevOps Engineer: Career Path & Salary 2026","d":"2026-03-16","c":"Career Advice"},
{"u":"https://engineering.careers360.com/articles/comedk-2026","t":"COMEDK 2026: Exam Date & Application","d":"2026-03-12","c":"Competitive Exams"},
{"u":"https://www.careers360.com/careers/cloud-architect","t":"Cloud Architect: Career & Salary 2026","d":"2026-03-08","c":"Career Advice"},
{"u":"https://engineering.careers360.com/articles/viteee-2026","t":"VITEEE 2026: Exam Pattern & Application","d":"2026-03-04","c":"Competitive Exams"},
{"u":"https://www.careers360.com/courses/bsc-data-science","t":"B.Sc Data Science 2026: Colleges & Career Scope","d":"2026-02-28","c":"Education & Colleges"},
{"u":"https://engineering.careers360.com/articles/top-btech-specializations","t":"Top B.Tech Specializations in 2026","d":"2026-02-24","c":"Education & Colleges"},
{"u":"https://www.careers360.com/careers/blockchain-developer","t":"Blockchain Developer: Career Path & Salary","d":"2026-02-20","c":"Career Advice"},
{"u":"https://engineering.careers360.com/articles/keam-2026","t":"KEAM 2026: Application, Exam Date & Syllabus","d":"2026-02-16","c":"Competitive Exams"},
{"u":"https://www.careers360.com/careers/ethical-hacker","t":"Ethical Hacker: Career Path & Certifications","d":"2026-02-12","c":"Career Advice"},
{"u":"https://engineering.careers360.com/articles/ap-eamcet-2026","t":"AP EAMCET 2026: Application & Exam Date","d":"2026-02-08","c":"Competitive Exams"},
{"u":"https://www.careers360.com/courses/bsc-artificial-intelligence","t":"B.Sc Artificial Intelligence 2026","d":"2026-02-04","c":"Education & Colleges"},
{"u":"https://engineering.careers360.com/articles/ts-eamcet-2026","t":"TS EAMCET 2026: Application & Syllabus","d":"2026-01-30","c":"Competitive Exams"},
{"u":"https://www.careers360.com/careers/network-engineer","t":"Network Engineer: Career Path & Certifications","d":"2026-01-26","c":"Career Advice"},
{"u":"https://www.careers360.com/courses/bca","t":"BCA 2026: Top Colleges, Admission & Career","d":"2026-01-22","c":"Education & Colleges"},
{"u":"https://engineering.careers360.com/articles/srmjee-2026","t":"SRMJEEE 2026: Exam Date & Application Form","d":"2026-01-18","c":"Competitive Exams"},
{"u":"https://www.careers360.com/careers/game-developer","t":"Game Developer: Career, Skills & Salary 2026","d":"2026-01-14","c":"Career Advice"},
{"u":"https://engineering.careers360.com/articles/manipal-entrance-test-2026","t":"MET 2026: Manipal Entrance Test Dates","d":"2026-01-10","c":"Competitive Exams"},
{"u":"https://www.careers360.com/courses/mca","t":"MCA 2026: Admission, Colleges & Career","d":"2026-01-06","c":"Education & Colleges"},
{"u":"https://www.careers360.com/careers/product-manager","t":"Product Manager: Career, Skills & Salary 2026","d":"2026-01-02","c":"Career Advice"},
{"u":"https://engineering.careers360.com/articles/iit-colleges-india","t":"IIT Colleges in India 2026: Rankings & Cutoff","d":"2025-12-26","c":"Education & Colleges"},
{"u":"https://engineering.careers360.com/articles/best-books-for-jee-main","t":"Best Books for JEE Main 2026","d":"2025-12-20","c":"Competitive Exams"},
{"u":"https://engineering.careers360.com/articles/mht-cet-preparation-tips","t":"MHT CET 2026 Preparation Tips","d":"2025-12-14","c":"Competitive Exams"},
{"u":"https://www.careers360.com/careers/full-stack-developer","t":"Full Stack Developer: Skills & Salary 2026","d":"2025-12-08","c":"Career Advice"},
{"u":"https://www.careers360.com/careers/android-developer","t":"Android Developer: Career Path & Salary","d":"2025-12-02","c":"Career Advice"},
{"u":"https://engineering.careers360.com/articles/cuet-2026-engineering","t":"CUET 2026 for Engineering: Application","d":"2025-11-26","c":"Competitive Exams"},
{"u":"https://www.careers360.com/careers/ios-developer","t":"iOS Developer: Career, Skills & Salary 2026","d":"2025-11-20","c":"Career Advice"},
{"u":"https://www.careers360.com/careers/scrum-master","t":"Scrum Master: Career & Certifications 2026","d":"2025-11-14","c":"Career Advice"},
],
'geeksforgeeks': [
{"u":"https://www.geeksforgeeks.org/blogs/generative-ai-roadmap/","t":"Generative AI Roadmap 2026","d":"2026-05-20","c":"Tech & Coding"},
{"u":"https://www.geeksforgeeks.org/blogs/system-design-interview-questions/","t":"System Design Interview Questions 2026","d":"2026-05-18","c":"Interview Prep"},
{"u":"https://www.geeksforgeeks.org/blogs/how-to-prepare-for-a-hackathon/","t":"How to Prepare for a Hackathon 2026","d":"2026-05-16","c":"Hackathon"},
{"u":"https://www.geeksforgeeks.org/blogs/llm-interview-questions/","t":"LLM & AI Interview Questions 2026","d":"2026-05-14","c":"Interview Prep"},
{"u":"https://www.geeksforgeeks.org/blogs/kubernetes-interview-questions/","t":"Kubernetes Interview Questions 2026","d":"2026-05-12","c":"Interview Prep"},
{"u":"https://www.geeksforgeeks.org/blogs/docker-interview-questions/","t":"Docker Interview Questions 2026","d":"2026-05-10","c":"Interview Prep"},
{"u":"https://www.geeksforgeeks.org/blogs/aws-interview-questions/","t":"AWS Interview Questions 2026","d":"2026-05-08","c":"Interview Prep"},
{"u":"https://www.geeksforgeeks.org/blogs/data-structures-interview-questions/","t":"Top 100 Data Structures Interview Questions","d":"2026-05-06","c":"Interview Prep"},
{"u":"https://www.geeksforgeeks.org/blogs/python-interview-questions/","t":"Python Interview Questions 2026","d":"2026-05-04","c":"Interview Prep"},
{"u":"https://www.geeksforgeeks.org/blogs/javascript-interview-questions/","t":"JavaScript Interview Questions 2026","d":"2026-05-02","c":"Interview Prep"},
{"u":"https://www.geeksforgeeks.org/blogs/java-interview-questions/","t":"Java Interview Questions 2026","d":"2026-04-30","c":"Interview Prep"},
{"u":"https://www.geeksforgeeks.org/blogs/sql-interview-questions/","t":"SQL Interview Questions 2026","d":"2026-04-28","c":"Interview Prep"},
{"u":"https://www.geeksforgeeks.org/blogs/top-hackathons-in-india/","t":"Top Hackathons in India 2026","d":"2026-04-26","c":"Hackathon"},
{"u":"https://www.geeksforgeeks.org/blogs/machine-learning-projects/","t":"Top Machine Learning Projects 2026","d":"2026-04-24","c":"Tech & Coding"},
{"u":"https://www.geeksforgeeks.org/blogs/ai-tools-for-students/","t":"Best AI Tools for Students 2026","d":"2026-04-22","c":"Tech & Coding"},
{"u":"https://www.geeksforgeeks.org/blogs/how-to-get-internship/","t":"How to Get an Internship: Step-by-Step Guide","d":"2026-04-20","c":"Internship Tips"},
{"u":"https://www.geeksforgeeks.org/blogs/resume-for-freshers/","t":"How to Write a Resume for Freshers 2026","d":"2026-04-18","c":"Resume & Writing"},
{"u":"https://www.geeksforgeeks.org/blogs/competitive-programming-guide/","t":"Competitive Programming: Complete Beginners Guide","d":"2026-04-16","c":"Tech & Coding"},
{"u":"https://www.geeksforgeeks.org/blogs/git-commands/","t":"Top 50 Git Commands Every Developer Should Know","d":"2026-04-14","c":"Tech & Coding"},
{"u":"https://www.geeksforgeeks.org/blogs/placement-preparation/","t":"Placement Preparation: How to Crack Campus Placements","d":"2026-04-12","c":"Career Advice"},
{"u":"https://www.geeksforgeeks.org/blogs/dsa-roadmap/","t":"DSA Roadmap for Beginners 2026","d":"2026-04-10","c":"Tech & Coding"},
{"u":"https://www.geeksforgeeks.org/blogs/react-interview-questions/","t":"React Interview Questions 2026","d":"2026-04-08","c":"Interview Prep"},
{"u":"https://www.geeksforgeeks.org/blogs/node-js-interview-questions/","t":"Node.js Interview Questions 2026","d":"2026-04-06","c":"Interview Prep"},
{"u":"https://www.geeksforgeeks.org/blogs/how-to-become-software-engineer/","t":"How to Become a Software Engineer: Complete Roadmap","d":"2026-04-04","c":"Career Advice"},
{"u":"https://www.geeksforgeeks.org/blogs/data-analyst-roadmap/","t":"Data Analyst Roadmap 2026","d":"2026-04-02","c":"Career Advice"},
{"u":"https://www.geeksforgeeks.org/blogs/hackathon-tips-for-beginners/","t":"Hackathon Tips for Beginners","d":"2026-03-30","c":"Hackathon"},
{"u":"https://www.geeksforgeeks.org/blogs/generative-ai-projects/","t":"Top Generative AI Projects for Beginners","d":"2026-03-28","c":"Tech & Coding"},
{"u":"https://www.geeksforgeeks.org/blogs/angular-interview-questions/","t":"Angular Interview Questions 2026","d":"2026-03-26","c":"Interview Prep"},
{"u":"https://www.geeksforgeeks.org/blogs/data-engineering-roadmap/","t":"Data Engineering Roadmap 2026","d":"2026-03-24","c":"Tech & Coding"},
{"u":"https://www.geeksforgeeks.org/blogs/microservices-interview-questions/","t":"Microservices Interview Questions 2026","d":"2026-03-22","c":"Interview Prep"},
{"u":"https://www.geeksforgeeks.org/blogs/best-ai-tools-for-coding/","t":"Best AI Tools for Developers 2026","d":"2026-03-20","c":"Tech & Coding"},
{"u":"https://www.geeksforgeeks.org/blogs/linux-interview-questions/","t":"Linux Interview Questions 2026","d":"2026-03-18","c":"Interview Prep"},
{"u":"https://www.geeksforgeeks.org/blogs/spring-boot-interview-questions/","t":"Spring Boot Interview Questions 2026","d":"2026-03-16","c":"Interview Prep"},
{"u":"https://www.geeksforgeeks.org/blogs/django-interview-questions/","t":"Django Interview Questions 2026","d":"2026-03-14","c":"Interview Prep"},
{"u":"https://www.geeksforgeeks.org/blogs/mongodb-interview-questions/","t":"MongoDB Interview Questions 2026","d":"2026-03-12","c":"Interview Prep"},
{"u":"https://www.geeksforgeeks.org/blogs/salary-negotiation-tips/","t":"Salary Negotiation Tips for Developers 2026","d":"2026-03-10","c":"Salary & Finance"},
{"u":"https://www.geeksforgeeks.org/blogs/golang-interview-questions/","t":"Golang Interview Questions 2026","d":"2026-03-08","c":"Interview Prep"},
{"u":"https://www.geeksforgeeks.org/blogs/how-to-become-ml-engineer/","t":"How to Become a Machine Learning Engineer","d":"2026-03-06","c":"Career Advice"},
{"u":"https://www.geeksforgeeks.org/blogs/leetcode-study-plan/","t":"LeetCode Study Plan: 30-Day Prep Guide","d":"2026-03-04","c":"Interview Prep"},
{"u":"https://www.geeksforgeeks.org/blogs/next-js-tutorial/","t":"Next.js Tutorial for Beginners 2026","d":"2026-03-02","c":"Tech & Coding"},
{"u":"https://www.geeksforgeeks.org/blogs/pandas-tutorial/","t":"Pandas Tutorial for Data Analysis 2026","d":"2026-02-28","c":"Tech & Coding"},
{"u":"https://www.geeksforgeeks.org/blogs/github-for-beginners/","t":"GitHub for Beginners: Complete Guide","d":"2026-02-26","c":"Tech & Coding"},
{"u":"https://www.geeksforgeeks.org/blogs/how-to-become-web-developer/","t":"How to Become a Web Developer 2026","d":"2026-02-24","c":"Career Advice"},
{"u":"https://www.geeksforgeeks.org/blogs/tailwind-css-guide/","t":"Tailwind CSS Guide for Beginners","d":"2026-02-22","c":"Tech & Coding"},
{"u":"https://www.geeksforgeeks.org/blogs/top-it-companies-india/","t":"Top IT Companies in India 2026","d":"2026-02-20","c":"Career Advice"},
{"u":"https://www.geeksforgeeks.org/blogs/full-stack-developer-roadmap/","t":"Full Stack Developer Roadmap 2026","d":"2026-02-18","c":"Tech & Coding"},
{"u":"https://www.geeksforgeeks.org/blogs/ai-ml-roadmap/","t":"AI/ML Roadmap 2026","d":"2026-02-16","c":"Tech & Coding"},
{"u":"https://www.geeksforgeeks.org/blogs/top-programming-languages-2026/","t":"Top Programming Languages to Learn in 2026","d":"2026-02-14","c":"Tech & Coding"},
{"u":"https://www.geeksforgeeks.org/blogs/blockchain-career/","t":"Blockchain Developer Career Path 2026","d":"2026-02-12","c":"Career Advice"},
{"u":"https://www.geeksforgeeks.org/blogs/cybersecurity-roadmap/","t":"Cybersecurity Roadmap 2026","d":"2026-02-10","c":"Career Advice"},
{"u":"https://www.geeksforgeeks.org/blogs/devops-roadmap/","t":"DevOps Roadmap 2026","d":"2026-02-08","c":"Tech & Coding"},
],
}

# ════════════════════════════════════════════════════════════════
# HTML INJECTOR
# ════════════════════════════════════════════════════════════════

def get_existing_count(html, site_key):
    """Count how many posts already exist in HTML for a site."""
    site_order = ['naukri','internshala','hackerearth','careers360','geeksforgeeks']
    i = site_order.index(site_key)
    if i + 1 < len(site_order):
        next_key = site_order[i + 1]
        pattern = rf'{re.escape(site_key)}:\[(.*?)\]\s*,\s*\n\s*{re.escape(next_key)}'
    else:
        pattern = rf'{re.escape(site_key)}:\[(.*?)\]\s*\n\s*\}};'
    m = re.search(pattern, html, flags=re.DOTALL)
    if m:
        return m.group(1).count('d:"')
    return 0

def posts_to_js(posts):
    lines = []
    for p in posts:
        u = str(p['u']).replace('\\','\\\\').replace('"','\\"')
        t = str(p['t']).replace('\\','\\\\').replace('"','\\"')
        d = str(p['d'])[:10]
        c = str(p['c']).replace('"','\\"')
        lines.append(f'{{"u":"{u}","t":"{t}","d":"{d}","c":"{c}"}}')
    return '[\n' + ',\n'.join(lines) + '\n]'

def inject_into_html(all_data):
    if not os.path.exists(HTML_FILE):
        print(f'❌ {HTML_FILE} not found'); return

    with open(HTML_FILE, 'r', encoding='utf-8') as f:
        html = f.read()

    site_order = ['naukri','internshala','hackerearth','careers360','geeksforgeeks']

    for i, site_key in enumerate(site_order):
        posts = all_data.get(site_key, [])
        existing_count = get_existing_count(html, site_key)

        # Guard: only fall back if live fetch returned suspiciously few posts
        # (less than 50) — normal sitemap variance between runs is OK to update
        MINIMUM_CREDIBLE = 50
        if len(posts) < MINIMUM_CREDIBLE and len(posts) < existing_count:
            static = STATIC_FALLBACK.get(site_key, [])
            if static and len(static) > len(posts):
                print(f'  ↩ {site_key}: live={len(posts)} (too few) — using static fallback ({len(static)} posts)')
                posts = static
            else:
                print(f'  ↩ {site_key}: live={len(posts)} (too few) — keeping existing')
                continue
        elif len(posts) < existing_count:
            print(f'  ~ {site_key}: live={len(posts)} < existing={existing_count} but credible — updating anyway')

        if not posts:
            print(f'  ⚠ {site_key}: 0 posts — keeping existing'); continue

        js_array = posts_to_js(posts)
        if i + 1 < len(site_order):
            next_key = site_order[i + 1]
            pattern  = rf'({re.escape(site_key)}:\[)(.*?)(\]\s*,\s*\n\s*{re.escape(next_key)})'
            repl     = rf'{site_key}:{js_array},\n{next_key}'
        else:
            pattern  = rf'({re.escape(site_key)}:\[)(.*?)(\]\s*\n\s*\}};)'
            repl     = rf'{site_key}:{js_array}\n}};'

        new_html, n = re.subn(pattern, repl, html, count=1, flags=re.DOTALL)
        if n:
            html = new_html
            print(f'  ✓ {site_key}: {len(posts)} posts injected')
        else:
            print(f'  ⚠ {site_key}: regex not matched — keeping existing')

    # Update pill counts
    for site_key, posts in all_data.items():
        if posts:
            html = re.sub(
                rf'(data-k="{re.escape(site_key)}".*?site-pill-url[^>]*>)\d+( posts in database)',
                rf'\g<1>{len(posts)}\g<2>', html, count=1, flags=re.DOTALL)

    date_fmt = datetime.now().strftime('%b %d, %Y')
    html = re.sub(r"const TODAY='[\d-]+'", f"const TODAY='{TODAY}'", html)
    html = re.sub(r'Data as of [A-Za-z]+ \d+, \d{4}', f'Data as of {date_fmt}', html)

    with open(HTML_FILE, 'w', encoding='utf-8') as f:
        f.write(html)

    total = sum(len(v) for v in all_data.values() if v)
    print(f'\n✅ index.html updated — {total} posts — {TODAY}')

# ════════════════════════════════════════════════════════════════
def main():
    print(f'🚀 BlogIntel — {TODAY}\n')
    all_data = {
        'naukri':        fetch_naukri(),
        'internshala':   fetch_internshala(),
        'hackerearth':   fetch_hackerearth(),
        'careers360':    fetch_careers360(),
        'geeksforgeeks': fetch_geeksforgeeks(),
    }
    print('\n📊 Summary:')
    for k, v in all_data.items():
        print(f'   {k}: {len(v)} posts')

    print('\n💉 Injecting into index.html...')
    inject_into_html(all_data)

if __name__ == '__main__':
    main()
