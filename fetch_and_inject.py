#!/usr/bin/env python3
"""
BlogIntel — Auto Data Fetcher & Injector
Fetches RSS/sitemaps for all 5 competitors and injects into index.html
GitHub Actions: runs daily at 8:30 AM IST
Manual: python3 fetch_and_inject.py
"""

import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
import re
import os
from datetime import datetime, timezone

TODAY = datetime.now(timezone.utc).strftime('%Y-%m-%d')
HTML_FILE = 'index.html'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
    'Accept': 'application/rss+xml, application/xml, text/xml, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Cache-Control': 'no-cache',
}

# ── Category guesser ─────────────────────────────────────────────
def guess_cat(title, url=''):
    t = (title + ' ' + url).lower()
    if re.search(r'salary|package|ctc|stipend|\blpa\b', t):           return 'Salary & Finance'
    if re.search(r'interview|questions|answers|\bcrack\b', t):         return 'Interview Prep'
    if re.search(r'\bresume\b|\bcv\b|cover letter', t):                return 'Resume & Writing'
    if re.search(r'\bletter\b|application|format|sample|template', t): return 'Letters & Applications'
    if re.search(r'internship|\bintern\b', t):                         return 'Internship Tips'
    if re.search(r'hackathon|\bhack\b', t):                            return 'Hackathon'
    if re.search(r'python|javascript|react|node\.js|sql|\bcss\b|\bhtml\b|coding|programming|developer|dsa|algorithm|\bgit\b|\bapi\b|docker|kubernetes|\baws\b|cloud|flutter|android|machine.learning|deep.learning|tensorflow|pytorch', t): return 'Tech & Coding'
    if re.search(r'\bjee\b|\bneet\b|\bgate\b|bitsat|\bcat\b|\bupsc\b|entrance|syllabus|cutoff', t): return 'Competitive Exams'
    if re.search(r'college|university|\bbtech\b|\bmba\b|\bmca\b|\bbca\b|admission|placement|campus', t): return 'Education & Colleges'
    if re.search(r'women|gender|diversity', t):                        return 'Women in Workplace'
    if re.search(r'report|trend|hiring|jobspeak|market|industry', t):  return 'Industry Reports'
    if re.search(r'\bhr\b|human resource|talent|recruit', t):          return 'HR & Talent'
    return 'Career Advice'

def parse_date(s):
    if not s: return TODAY
    s = s.strip()
    for fmt in ('%a, %d %b %Y %H:%M:%S %z', '%a, %d %b %Y %H:%M:%S GMT',
                '%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%d'):
        try:
            return datetime.strptime(s[:25], fmt).strftime('%Y-%m-%d')
        except: pass
    m = re.search(r'(\d{4}-\d{2}-\d{2})', s)
    return m.group(1) if m else TODAY

def fetch_url(url, timeout=20):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode('utf-8', errors='replace')
    except urllib.error.HTTPError as e:
        print(f'  ⚠ HTTP {e.code} — {url}')
        return ''
    except Exception as e:
        print(f'  ⚠ {type(e).__name__} — {url}')
        return ''

def dedupe(posts):
    seen, out = set(), []
    for p in posts:
        if p['u'] not in seen:
            seen.add(p['u'])
            out.append(p)
    return sorted(out, key=lambda x: x['d'], reverse=True)

# ── RSS Parser ───────────────────────────────────────────────────
def parse_rss(xml_text):
    posts = []
    if not xml_text: return posts
    try:
        root = ET.fromstring(xml_text)
        items = root.findall('.//item') or root.findall('.//{http://www.w3.org/2005/Atom}entry')
        for item in items:
            def gt(tag, ns=''):
                ns_tag = f'{{{ns}}}{tag}' if ns else tag
                el = item.find(ns_tag)
                return (el.text or '').strip() if el is not None else ''
            title = gt('title') or gt('title', 'http://www.w3.org/2005/Atom')
            link  = gt('link')
            if not link:
                el = item.find('{http://www.w3.org/2005/Atom}link')
                link = (el.get('href','') if el is not None else '').strip()
            pub   = gt('pubDate') or gt('published','http://www.w3.org/2005/Atom') or gt('updated','http://www.w3.org/2005/Atom')
            if link and title:
                posts.append({'u':link.strip(),'t':title.strip(),'d':parse_date(pub),'c':guess_cat(title,link)})
    except Exception as e:
        print(f'  ⚠ RSS parse error: {e}')
    return posts

def parse_sitemap(xml_text, url_filter=None):
    posts = []
    if not xml_text: return posts
    try:
        root = ET.fromstring(xml_text)
        ns = 'http://www.sitemaps.org/schemas/sitemap/0.9'
        for url_el in root.findall(f'{{{ns}}}url'):
            loc     = (url_el.findtext(f'{{{ns}}}loc') or '').strip()
            lastmod = (url_el.findtext(f'{{{ns}}}lastmod') or '').strip()
            if not loc: continue
            if url_filter and not re.search(url_filter, loc): continue
            slug = loc.rstrip('/').split('/')[-1].replace('-',' ')
            slug = re.sub(r'\b\w', lambda m: m.group().upper(), slug)
            posts.append({'u':loc,'t':slug,'d':parse_date(lastmod),'c':guess_cat(slug,loc)})
    except Exception as e:
        print(f'  ⚠ Sitemap parse error: {e}')
    return posts

def sitemap_index_urls(xml_text):
    urls = []
    if not xml_text: return urls
    try:
        root = ET.fromstring(xml_text)
        ns = 'http://www.sitemaps.org/schemas/sitemap/0.9'
        for sm in root.findall(f'{{{ns}}}sitemap'):
            loc = sm.findtext(f'{{{ns}}}loc') or ''
            if loc: urls.append(loc.strip())
    except: pass
    return urls

# ════════════════════════════════════════════════════════════════
# SITE FETCHERS — multiple fallbacks per site
# ════════════════════════════════════════════════════════════════

def fetch_naukri():
    print('📥 Naukri...')
    posts = []
    for url in ['https://www.naukri.com/blog/feed/',
                'https://www.naukri.com/blog/feed/atom/']:
        posts += parse_rss(fetch_url(url))
    if len(posts) < 10:
        for sm in ['https://www.naukri.com/blog/sitemap_index.xml',
                   'https://www.naukri.com/blog/news-sitemap.xml']:
            xml = fetch_url(sm)
            for child_url in sitemap_index_urls(xml)[:4]:
                posts += parse_sitemap(fetch_url(child_url), r'/blog/')
            posts += parse_sitemap(xml, r'/blog/')
    result = dedupe(posts)
    print(f'  ✓ {len(result)} posts')
    return result

def fetch_internshala():
    print('📥 Internshala...')
    posts = []
    for url in ['https://internshala.com/blog/feed/',
                'https://internshala.com/blog/feed/atom/',
                'https://internshala.com/blog/category/internship-tips/feed/']:
        posts += parse_rss(fetch_url(url))
    if len(posts) < 10:
        xml = fetch_url('https://internshala.com/sitemap.xml')
        for child_url in sitemap_index_urls(xml):
            if 'blog' in child_url:
                posts += parse_sitemap(fetch_url(child_url))
    result = dedupe(posts)
    print(f'  ✓ {len(result)} posts')
    return result

def fetch_hackerearth():
    print('📥 HackerEarth...')
    posts = []
    for url in ['https://www.hackerearth.com/blog/feed/',
                'https://www.hackerearth.com/blog/developers/feed/',
                'https://www.hackerearth.com/blog/talent/feed/',
                'https://www.hackerearth.com/blog/engineering/feed/']:
        posts += parse_rss(fetch_url(url))
    if len(posts) < 10:
        xml = fetch_url('https://www.hackerearth.com/sitemap.xml')
        for child_url in sitemap_index_urls(xml)[:3]:
            if 'blog' in child_url:
                posts += parse_sitemap(fetch_url(child_url))
    result = dedupe(posts)
    print(f'  ✓ {len(result)} posts')
    return result

def fetch_careers360():
    print('📥 Careers360...')
    posts = []
    for url in ['https://engineering.careers360.com/sitemap-article.xml',
                'https://www.careers360.com/sitemap-careers.xml',
                'https://www.careers360.com/sitemap-courses.xml',
                'https://medicine.careers360.com/sitemap-article.xml']:
        posts += parse_sitemap(fetch_url(url))
    for url in ['https://engineering.careers360.com/rss/latest',
                'https://www.careers360.com/rss/latest']:
        posts += parse_rss(fetch_url(url))
    result = dedupe(posts)
    print(f'  ✓ {len(result)} posts')
    return result

def fetch_geeksforgeeks():
    print('📥 GeeksforGeeks...')
    posts = []
    for url in ['https://www.geeksforgeeks.org/feed/',
                'https://www.geeksforgeeks.org/category/blogathon/feed/',
                'https://www.geeksforgeeks.org/category/careers/feed/']:
        posts += parse_rss(fetch_url(url))
    for url in ['https://www.geeksforgeeks.org/blogs-sitemap.xml',
                'https://www.geeksforgeeks.org/sitemap.xml']:
        xml = fetch_url(url)
        for child_url in sitemap_index_urls(xml)[:3]:
            if 'blog' in child_url or 'article' in child_url:
                posts += parse_sitemap(fetch_url(child_url))
        posts += parse_sitemap(xml, r'/blogs/')
    result = dedupe(posts)
    print(f'  ✓ {len(result)} posts')
    return result

# ════════════════════════════════════════════════════════════════
# HTML INJECTOR
# ════════════════════════════════════════════════════════════════

def posts_to_js(posts):
    lines = []
    for p in posts:
        u = p['u'].replace('\\','\\\\').replace('"','\\"')
        t = p['t'].replace('\\','\\\\').replace('"','\\"')
        d = str(p['d'])[:10]
        c = p['c'].replace('"','\\"')
        lines.append(f'{{u:"{u}",t:"{t}",d:"{d}",c:"{c}"}}')
    return '[\n' + ',\n'.join(lines) + '\n]'

def inject_into_html(all_data):
    if not os.path.exists(HTML_FILE):
        print(f'❌ {HTML_FILE} not found')
        return False

    with open(HTML_FILE, 'r', encoding='utf-8') as f:
        html = f.read()

    # Sites in DB order — used for lookahead in regex
    site_order = ['naukri','internshala','hackerearth','careers360','geeksforgeeks']

    for i, site_key in enumerate(site_order):
        posts = all_data.get(site_key, [])
        if not posts:
            print(f'  ⚠ {site_key}: 0 posts fetched — keeping existing data')
            continue

        js_array = posts_to_js(posts)

        # Lookahead: next site key or end of DB object
        if i + 1 < len(site_order):
            lookahead = site_order[i + 1]
            pattern = rf'({re.escape(site_key)}:\[)(.*?)(\]\s*,\s*\n\s*{re.escape(lookahead)})'
            repl    = rf'{site_key}:{js_array},\n{lookahead}'
        else:
            # Last site — lookahead for closing };
            pattern = rf'({re.escape(site_key)}:\[)(.*?)(\]\s*\n\s*\}};)'
            repl    = rf'{site_key}:{js_array}\n}};'

        new_html, n = re.subn(pattern, repl, html, count=1, flags=re.DOTALL)
        if n:
            html = new_html
            print(f'  ✓ {site_key}: {len(posts)} posts injected')
        else:
            print(f'  ⚠ {site_key}: regex not matched — keeping existing')

    # Update pill counts in HTML
    for site_key, posts in all_data.items():
        if posts:
            html = re.sub(
                rf'(data-k="{re.escape(site_key)}".*?site-pill-url[^>]*>)\d+( posts in database)',
                rf'\g<1>{len(posts)}\g<2>', html, count=1, flags=re.DOTALL
            )

    # Update date references
    date_fmt = datetime.now().strftime('%b %d, %Y')
    html = re.sub(r"const TODAY='[\d-]+'", f"const TODAY='{TODAY}'", html)
    html = re.sub(r'Data as of [A-Za-z]+ \d+, \d{4}', f'Data as of {date_fmt}', html)

    with open(HTML_FILE, 'w', encoding='utf-8') as f:
        f.write(html)

    total = sum(len(v) for v in all_data.values() if v)
    print(f'\n✅ index.html updated — {total} new posts — {TODAY}')
    return True

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

    fetched_any = any(len(v) > 0 for v in all_data.values())
    if not fetched_any:
        print('\n⚠ No data fetched (likely IP restrictions in this environment).')
        print('  GitHub Actions will work fine — sites allow GitHub IPs.')
        print('  Skipping injection to preserve existing data.')
        return

    print('\n💉 Injecting into index.html...')
    inject_into_html(all_data)

if __name__ == '__main__':
    main()
