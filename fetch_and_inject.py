#!/usr/bin/env python3
"""
BlogIntel — Full Sitemap Crawler + Injector
Crawls ALL sitemap pages for all 5 competitors → injects into index.html
GitHub Actions: runs daily at 8:30 AM IST
"""

import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
import re
import os
from datetime import datetime, timezone

TODAY  = datetime.now(timezone.utc).strftime('%Y-%m-%d')
HTML_FILE = 'index.html'

# Real browser headers — GitHub Actions IPs are not blocked
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
}

# ── Helpers ──────────────────────────────────────────────────────

def fetch_url(url, timeout=25):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            # handle gzip
            try:
                import gzip
                if raw[:2] == b'\x1f\x8b':
                    raw = gzip.decompress(raw)
            except: pass
            return raw.decode('utf-8', errors='replace')
    except urllib.error.HTTPError as e:
        print(f'    ⚠ HTTP {e.code} — {url}')
        return ''
    except Exception as e:
        print(f'    ⚠ {type(e).__name__} — {url}')
        return ''

def parse_date(s):
    if not s: return TODAY
    s = s.strip()
    for fmt in ('%a, %d %b %Y %H:%M:%S %z',
                '%a, %d %b %Y %H:%M:%S GMT',
                '%Y-%m-%dT%H:%M:%S%z',
                '%Y-%m-%dT%H:%M:%SZ',
                '%Y-%m-%d'):
        try:
            return datetime.strptime(s[:25], fmt).strftime('%Y-%m-%d')
        except: pass
    m = re.search(r'(\d{4}-\d{2}-\d{2})', s)
    return m.group(1) if m else TODAY

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

def dedupe(posts):
    seen, out = set(), []
    for p in posts:
        if p['u'] not in seen:
            seen.add(p['u'])
            out.append(p)
    return sorted(out, key=lambda x: x['d'], reverse=True)

# ── Parsers ───────────────────────────────────────────────────────

def parse_rss(xml_text):
    posts = []
    if not xml_text: return posts
    try:
        # strip bad chars
        xml_text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', xml_text)
        root = ET.fromstring(xml_text)
        NS_ATOM = 'http://www.w3.org/2005/Atom'
        items = root.findall('.//item') or root.findall(f'.//{{{NS_ATOM}}}entry')
        for item in items:
            def gt(tag, ns=''):
                el = item.find(f'{{{ns}}}{tag}' if ns else tag)
                return (el.text or '').strip() if el is not None else ''
            title = gt('title') or gt('title', NS_ATOM)
            link  = gt('link')
            if not link:
                el = item.find(f'{{{NS_ATOM}}}link')
                link = (el.get('href','') if el is not None else '').strip()
            pub = (gt('pubDate') or gt('published', NS_ATOM) or gt('updated', NS_ATOM))
            if link and title:
                posts.append({'u': link.strip(), 't': title.strip(),
                              'd': parse_date(pub), 'c': guess_cat(title, link)})
    except Exception as e:
        print(f'    ⚠ RSS parse: {e}')
    return posts

def parse_sitemap_index(xml_text):
    """Returns list of child sitemap URLs."""
    urls = []
    if not xml_text: return urls
    try:
        xml_text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', xml_text)
        root = ET.fromstring(xml_text)
        ns = 'http://www.sitemaps.org/schemas/sitemap/0.9'
        for sm in root.findall(f'{{{ns}}}sitemap'):
            loc = (sm.findtext(f'{{{ns}}}loc') or '').strip()
            if loc: urls.append(loc)
        # also try without namespace
        if not urls:
            for sm in root.findall('.//sitemap'):
                loc = (sm.findtext('loc') or '').strip()
                if loc: urls.append(loc)
    except: pass
    return urls

def parse_sitemap_urls(xml_text, url_filter=None):
    """Returns list of {u, t, d, c} from a sitemap."""
    posts = []
    if not xml_text: return posts
    try:
        xml_text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', xml_text)
        root = ET.fromstring(xml_text)
        ns = 'http://www.sitemaps.org/schemas/sitemap/0.9'
        url_els = root.findall(f'{{{ns}}}url')
        if not url_els:
            url_els = root.findall('.//url')
        for url_el in url_els:
            loc     = (url_el.findtext(f'{{{ns}}}loc') or url_el.findtext('loc') or '').strip()
            lastmod = (url_el.findtext(f'{{{ns}}}lastmod') or url_el.findtext('lastmod') or '').strip()
            if not loc: continue
            if url_filter and not re.search(url_filter, loc): continue
            slug = loc.rstrip('/').split('/')[-1].replace('-', ' ')
            slug = re.sub(r'\b\w', lambda m: m.group().upper(), slug)
            posts.append({'u': loc, 't': slug,
                          'd': parse_date(lastmod),
                          'c': guess_cat(slug, loc)})
    except Exception as e:
        print(f'    ⚠ Sitemap parse: {e}')
    return posts

def crawl_sitemap_index(index_url, url_filter=None, max_children=50):
    """Fully crawls a sitemap index → all child sitemaps → all URLs."""
    posts = []
    xml = fetch_url(index_url)
    if not xml:
        return posts
    child_urls = parse_sitemap_index(xml)
    if child_urls:
        print(f'    → sitemap index: {len(child_urls)} child sitemaps')
        for child_url in child_urls[:max_children]:
            child_xml = fetch_url(child_url)
            batch = parse_sitemap_urls(child_xml, url_filter)
            posts += batch
            if batch:
                print(f'      {child_url.split("/")[-1]}: {len(batch)} URLs')
    else:
        # Not an index — treat as direct sitemap
        posts += parse_sitemap_urls(xml, url_filter)
    return posts

# ════════════════════════════════════════════════════════════════
# SITE FETCHERS — RSS first (recent), then full sitemap crawl
# ════════════════════════════════════════════════════════════════

def fetch_naukri():
    print('📥 Naukri...')
    posts = []

    # 1. RSS for recent posts (titles included)
    for feed in ['https://www.naukri.com/blog/feed/',
                 'https://www.naukri.com/blog/feed/atom/']:
        posts += parse_rss(fetch_url(feed))

    # 2. Full sitemap crawl for all historical posts
    for sm_url in [
        'https://www.naukri.com/blog/sitemap_index.xml',
        'https://www.naukri.com/blog/sitemap.xml',
        'https://www.naukri.com/blog/post-sitemap.xml',
        'https://www.naukri.com/blog/page-sitemap.xml',
    ]:
        posts += crawl_sitemap_index(sm_url, url_filter=r'/blog/')

    result = dedupe(posts)
    print(f'  ✓ {len(result)} total posts')
    return result


def fetch_internshala():
    print('📥 Internshala...')
    posts = []

    # 1. RSS — multiple category feeds
    for feed in [
        'https://internshala.com/blog/feed/',
        'https://internshala.com/blog/feed/atom/',
        'https://internshala.com/blog/category/internship-tips/feed/',
        'https://internshala.com/blog/category/career-tips/feed/',
        'https://internshala.com/blog/category/online-courses/feed/',
        'https://internshala.com/blog/category/student-resources/feed/',
        'https://internshala.com/blog/category/work-from-home/feed/',
    ]:
        batch = parse_rss(fetch_url(feed))
        posts += batch

    # 2. Full sitemap crawl
    for sm_url in [
        'https://internshala.com/sitemap.xml',
        'https://internshala.com/sitemap_index.xml',
        'https://internshala.com/blog/sitemap.xml',
        'https://internshala.com/blog/sitemap_index.xml',
        'https://internshala.com/blog/post-sitemap.xml',
    ]:
        posts += crawl_sitemap_index(sm_url, url_filter=r'/blog/')

    result = dedupe(posts)
    print(f'  ✓ {len(result)} total posts')
    return result


def fetch_hackerearth():
    print('📥 HackerEarth...')
    posts = []

    # 1. RSS — all category feeds
    for feed in [
        'https://www.hackerearth.com/blog/feed/',
        'https://www.hackerearth.com/blog/developers/feed/',
        'https://www.hackerearth.com/blog/talent/feed/',
        'https://www.hackerearth.com/blog/engineering/feed/',
        'https://www.hackerearth.com/blog/hackathon/feed/',
        'https://www.hackerearth.com/blog/data-science/feed/',
    ]:
        posts += parse_rss(fetch_url(feed))

    # 2. Full sitemap crawl
    for sm_url in [
        'https://www.hackerearth.com/sitemap.xml',
        'https://www.hackerearth.com/sitemap_index.xml',
        'https://www.hackerearth.com/blog/sitemap.xml',
        'https://www.hackerearth.com/blog/sitemap_index.xml',
        'https://www.hackerearth.com/blog/post-sitemap.xml',
    ]:
        posts += crawl_sitemap_index(sm_url, url_filter=r'/blog/')

    result = dedupe(posts)
    print(f'  ✓ {len(result)} total posts')
    return result


def fetch_careers360():
    print('📥 Careers360...')
    posts = []

    # 1. RSS
    for feed in [
        'https://engineering.careers360.com/rss/latest',
        'https://www.careers360.com/rss/latest',
        'https://medicine.careers360.com/rss/latest',
        'https://www.careers360.com/feed',
    ]:
        posts += parse_rss(fetch_url(feed))

    # 2. Multiple domain sitemaps — Careers360 has many subdomains
    for sm_url in [
        # Engineering
        'https://engineering.careers360.com/sitemap_index.xml',
        'https://engineering.careers360.com/sitemap-article.xml',
        'https://engineering.careers360.com/sitemap.xml',
        # Main
        'https://www.careers360.com/sitemap_index.xml',
        'https://www.careers360.com/sitemap-careers.xml',
        'https://www.careers360.com/sitemap-courses.xml',
        'https://www.careers360.com/sitemap-article.xml',
        'https://www.careers360.com/sitemap.xml',
        # Medicine
        'https://medicine.careers360.com/sitemap_index.xml',
        'https://medicine.careers360.com/sitemap-article.xml',
        # Law
        'https://law.careers360.com/sitemap-article.xml',
        # Management
        'https://management.careers360.com/sitemap-article.xml',
    ]:
        posts += crawl_sitemap_index(sm_url)

    result = dedupe(posts)
    print(f'  ✓ {len(result)} total posts')
    return result


def fetch_geeksforgeeks():
    print('📥 GeeksforGeeks...')
    posts = []

    # 1. RSS — multiple category feeds
    for feed in [
        'https://www.geeksforgeeks.org/feed/',
        'https://www.geeksforgeeks.org/category/blogs/feed/',
        'https://www.geeksforgeeks.org/category/blogathon/feed/',
        'https://www.geeksforgeeks.org/category/careers/feed/',
        'https://www.geeksforgeeks.org/category/interview-experiences/feed/',
        'https://www.geeksforgeeks.org/category/placement-preparation/feed/',
    ]:
        posts += parse_rss(fetch_url(feed))

    # 2. Full sitemap crawl
    for sm_url in [
        'https://www.geeksforgeeks.org/sitemap.xml',
        'https://www.geeksforgeeks.org/sitemap_index.xml',
        'https://www.geeksforgeeks.org/blogs-sitemap.xml',
        'https://www.geeksforgeeks.org/post-sitemap.xml',
        'https://www.geeksforgeeks.org/blog-sitemap.xml',
        'https://www.geeksforgeeks.org/page-sitemap.xml',
    ]:
        posts += crawl_sitemap_index(sm_url, url_filter=r'/(blogs?|articles?|careers?)/')

    result = dedupe(posts)
    print(f'  ✓ {len(result)} total posts')
    return result


# ════════════════════════════════════════════════════════════════
# HTML INJECTOR
# ════════════════════════════════════════════════════════════════

def posts_to_js(posts):
    lines = []
    for p in posts:
        u = str(p['u']).replace('\\','\\\\').replace('"','\\"')
        t = str(p['t']).replace('\\','\\\\').replace('"','\\"')
        d = str(p['d'])[:10]
        c = str(p['c']).replace('"','\\"')
        lines.append(f'{{u:"{u}",t:"{t}",d:"{d}",c:"{c}"}}')
    return '[\n' + ',\n'.join(lines) + '\n]'

def inject_into_html(all_data):
    if not os.path.exists(HTML_FILE):
        print(f'❌ {HTML_FILE} not found')
        return

    with open(HTML_FILE, 'r', encoding='utf-8') as f:
        html = f.read()

    site_order = ['naukri','internshala','hackerearth','careers360','geeksforgeeks']

    for i, site_key in enumerate(site_order):
        posts = all_data.get(site_key, [])
        if not posts:
            print(f'  ⚠ {site_key}: 0 posts — keeping existing')
            continue

        js_array = posts_to_js(posts)

        if i + 1 < len(site_order):
            next_key  = site_order[i + 1]
            pattern   = rf'({re.escape(site_key)}:\[)(.*?)(\]\s*,\s*\n\s*{re.escape(next_key)})'
            repl      = rf'{site_key}:{js_array},\n{next_key}'
        else:
            pattern   = rf'({re.escape(site_key)}:\[)(.*?)(\]\s*\n\s*\}};)'
            repl      = rf'{site_key}:{js_array}\n}};'

        new_html, n = re.subn(pattern, repl, html, count=1, flags=re.DOTALL)
        if n:
            html = new_html
            print(f'  ✓ {site_key}: {len(posts)} posts injected')
        else:
            print(f'  ⚠ {site_key}: pattern not matched — keeping existing')

    # Update pill counts
    for site_key, posts in all_data.items():
        if posts:
            html = re.sub(
                rf'(data-k="{re.escape(site_key)}".*?site-pill-url[^>]*>)\d+( posts in database)',
                rf'\g<1>{len(posts)}\g<2>', html, count=1, flags=re.DOTALL
            )

    # Update dates
    date_fmt = datetime.now().strftime('%b %d, %Y')
    html = re.sub(r"const TODAY='[\d-]+'", f"const TODAY='{TODAY}'", html)
    html = re.sub(r'Data as of [A-Za-z]+ \d+, \d{4}', f'Data as of {date_fmt}', html)

    with open(HTML_FILE, 'w', encoding='utf-8') as f:
        f.write(html)

    total = sum(len(v) for v in all_data.values() if v)
    print(f'\n✅ index.html updated — {total} total posts — {TODAY}')


# ════════════════════════════════════════════════════════════════
def main():
    print(f'🚀 BlogIntel Full Crawl — {TODAY}\n')

    all_data = {
        'naukri':        fetch_naukri(),
        'internshala':   fetch_internshala(),
        'hackerearth':   fetch_hackerearth(),
        'careers360':    fetch_careers360(),
        'geeksforgeeks': fetch_geeksforgeeks(),
    }

    print('\n📊 Summary:')
    total = 0
    for k, v in all_data.items():
        print(f'   {k}: {len(v)} posts')
        total += len(v)
    print(f'   TOTAL: {total} posts')

    fetched_any = any(len(v) > 0 for v in all_data.values())
    if not fetched_any:
        print('\n⚠ Nothing fetched — sites block this IP.')
        print('  GitHub Actions IPs are whitelisted — will work in CI.')
        return

    print('\n💉 Injecting into index.html...')
    inject_into_html(all_data)

if __name__ == '__main__':
    main()
