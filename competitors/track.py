#!/usr/bin/env python3
"""Competitor blog tracker: weekly new-post counts per competitor/category.
Reads competitors.csv (Category, Competitor, Blog URL, Sitemap override), discovers sitemaps
(robots.txt, common paths, www/non-www, RSS via <link rel=alternate>), buckets posts by
lastmod/pubDate into Monday-based weeks. If a sitemap has no dates, uses first-seen tracking
(seen.json). History merges into history.json; dashboard reads data.json."""
import csv, gzip, json, os, re, urllib.request, urllib.error
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

HERE = os.path.dirname(os.path.abspath(__file__))
WEEKS = 12
MAX_SITEMAPS = 30
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/124.0.0.0 Safari/537.36')
HDR = {'User-Agent': UA, 'Accept': 'application/xml,text/xml,text/html,*/*;q=0.8',
       'Accept-Language': 'en-US,en;q=0.9'}
COMMON = ['/sitemap_index.xml', '/sitemap-index.xml', '/sitemap.xml', '/wp-sitemap.xml',
          '/post-sitemap.xml', '/blog-sitemap.xml', '/sitemap-posts.xml', '/sitemap-0.xml',
          '/blog/sitemap.xml', '/blog/sitemap_index.xml', '/blog/post-sitemap.xml',
          '/blog/sitemap-index.xml', '/sitemap.xml.gz']


def get(url, codes=None, timeout=20):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=HDR), timeout=timeout) as r:
            raw = r.read()
        if raw[:2] == b'\x1f\x8b':
            raw = gzip.decompress(raw)
        return raw.decode('utf-8', errors='replace')
    except urllib.error.HTTPError as e:
        if codes is not None:
            codes.append(e.code)
    except Exception:
        if codes is not None:
            codes.append('net')
    return None


def parse_dt(s):
    if not s:
        return None
    s = s.strip()
    try:
        d = datetime.fromisoformat(s.replace('Z', '+00:00'))
    except ValueError:
        try:
            d = parsedate_to_datetime(s)
        except Exception:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def tag(block, t):
    m = re.search(r'<%s>\s*(?:<!\[CDATA\[)?([^<\]]+)' % t, block)
    return m.group(1).strip() if m else ''


def week_starts():
    today = datetime.now(timezone.utc).date()
    monday = today - timedelta(days=today.weekday())
    return [monday - timedelta(weeks=i) for i in range(WEEKS - 1, -1, -1)]


def bare(u):
    return re.sub(r'^https?://(www\.)?', '', u)


def hosts(origin):
    """origin plus its www/non-www twin."""
    h = re.sub(r'^https?://', '', origin)
    alt = h[4:] if h.startswith('www.') else 'www.' + h
    return [origin, 'https://' + alt]


def crawl(roots, origin, prefix, cutoff, codes):
    queue, seen_s, seen_u, out = list(roots), set(), set(), []
    base = bare(origin) + prefix
    while queue and len(seen_s) < MAX_SITEMAPS:
        s = queue.pop(0)
        if s in seen_s:
            continue
        seen_s.add(s)
        xml = get(s, codes)
        if not xml:
            continue
        for b in re.findall(r'<sitemap>[\s\S]*?</sitemap>', xml):
            loc, lm = tag(b, 'loc'), parse_dt(tag(b, 'lastmod'))
            if lm and lm < cutoff:
                continue
            if re.search(r'blog|post|article|news|resource|insight', loc, re.I):
                queue.insert(0, loc)
            else:
                queue.append(loc)
        for b in re.findall(r'<url>[\s\S]*?</url>', xml):
            loc = tag(b, 'loc')
            norm = loc.rstrip('/')
            if bare(loc).startswith(base + '/') and bare(norm) != base and norm not in seen_u:
                seen_u.add(norm)
                out.append((norm, parse_dt(tag(b, 'lastmod'))))
    return out


def collect_sitemap(blog, override, cutoff, codes):
    m = re.match(r'https?://[^/]+', blog)
    origin, prefix = m.group(0), blog[m.end():].rstrip('/')
    if override:
        return crawl([x for x in re.split(r'[\s,]+', override) if x], origin, prefix, cutoff, codes)
    roots = []
    for h in hosts(origin):
        roots += re.findall(r'(?im)^sitemap:\s*(\S+)', get(h + '/robots.txt', codes) or '')
    out = crawl(roots, origin, prefix, cutoff, codes) if roots else []
    if not out:  # probe common locations
        cands = []
        for h in hosts(origin):
            cands += [h + p for p in COMMON]
            if prefix:
                cands += [h + prefix + p for p in ('/sitemap.xml', '/sitemap_index.xml', '/post-sitemap.xml')]
        out = crawl(list(dict.fromkeys(cands)), origin, prefix, cutoff, codes)
    return out


def collect_rss(blog, codes):
    m = re.match(r'https?://[^/]+', blog)
    origin, base = m.group(0), blog.rstrip('/')
    feeds = []
    page = get(base, codes) or ''
    for h in re.findall(r'<link[^>]+type="application/(?:rss|atom)\+xml"[^>]*>', page):
        href = re.search(r'href="([^"]+)"', h)
        if href:
            u = href.group(1)
            feeds.append(u if u.startswith('http') else origin + (u if u.startswith('/') else '/' + u))
    feeds += [base + '/feed', base + '/feed/', base + '/rss.xml', base + '/feed.xml', base + '/rss',
              origin + '/feed', origin + '/rss.xml', origin + '/blog/feed', origin + '/blog/rss.xml']
    out = {}
    for f in dict.fromkeys(feeds):
        xml = get(f, codes)
        if not xml or ('<item' not in xml and '<entry' not in xml):
            continue
        for b in re.findall(r'<item[ >][\s\S]*?</item>|<entry[ >][\s\S]*?</entry>', xml):
            link = tag(b, 'link') or (re.search(r'<link[^>]+href="([^"]+)"', b) or [None, ''])[1]
            dt = parse_dt(tag(b, 'pubDate') or tag(b, 'published') or tag(b, 'updated') or tag(b, 'dc:date'))
            if link and dt:
                out[link.rstrip('/')] = dt
        if out:
            break
    return list(out.items())


def process(row, weeks, seen):
    cat, name, blog, override = (row + ['', '', '', ''])[:4]
    counts, latest, status, codes = [0] * len(weeks), None, 'OK', []
    first = datetime.combine(weeks[0], datetime.min.time(), tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    try:
        urls = collect_sitemap(blog, override.strip(), first, codes)
        dated = [(u, d) for u, d in urls if d]
        if not dated:
            rss = collect_rss(blog, codes)
            if rss:
                dated, status = rss, 'RSS only (latest posts, partial)'
            elif urls:  # sitemap without lastmod -> first-seen tracking
                s = seen.get(name)
                if s is None:
                    seen[name] = {u: 'base' for u, _ in urls}
                    status = 'First-seen tracking started (counts from next run)'
                else:
                    for u, _ in urls:
                        if u not in s:
                            s[u] = now.date().isoformat()
                    dated = [(u, parse_dt(d)) for u, d in s.items() if d != 'base']
                    status = 'First-seen tracking (no lastmod in sitemap)'
            else:
                top = Counter(codes).most_common(1)
                why = {403: 'blocked 403', 404: 'not at common paths', 'net': 'network/timeout'}.get(top[0][0] if top else None, '')
                status = 'No sitemap/RSS found' + (' (%s)' % why if why else '') + ' - add override'
        for _, d in dated:
            if d:
                if latest is None or d > latest:
                    latest = d
                idx = (d.date() - weeks[0]).days // 7
                if 0 <= idx < len(weeks):
                    counts[idx] += 1
    except Exception as e:
        status = 'Error: %s' % str(e)[:60]
    return {'category': cat, 'name': name, 'blog': blog, 'counts': counts,
            'latest': latest.date().isoformat() if latest else '', 'status': status}


def load(p, default):
    return json.load(open(p)) if os.path.exists(p) else default


def main():
    weeks = week_starts()
    with open(os.path.join(HERE, 'competitors.csv'), newline='', encoding='utf-8') as f:
        rows = [r for r in list(csv.reader(f))[1:] if len(r) > 2 and r[1].strip() and r[2].strip()]
    sp = os.path.join(HERE, 'seen.json')
    seen = load(sp, {})
    with ThreadPoolExecutor(6) as ex:
        results = list(ex.map(lambda r: process(r, weeks, seen), rows))
    json.dump(seen, open(sp, 'w'))

    hp = os.path.join(HERE, 'history.json')
    hist = load(hp, {})
    for r in results:
        h = hist.setdefault(r['name'], {'category': r['category'], 'blog': r['blog'], 'weeks': {}})
        h['category'], h['blog'] = r['category'], r['blog']
        if r['status'] == 'OK' or r['status'].startswith(('RSS', 'First-seen')):
            for w, c in zip(weeks, r['counts']):
                k = w.isoformat()
                h['weeks'][k] = max(h['weeks'].get(k, 0), c)
    json.dump(hist, open(hp, 'w'), indent=1)

    out_rows = []
    for r in results:
        hw = hist[r['name']]['weeks']
        counts = [hw.get(w.isoformat(), 0) for w in weeks]
        out_rows.append({**r, 'counts': counts, 'total': sum(counts)})
    json.dump({'generated': datetime.now(timezone.utc).isoformat(timespec='minutes'),
               'weeks': [w.isoformat() for w in weeks], 'rows': out_rows},
              open(os.path.join(HERE, 'data.json'), 'w'), indent=1)
    bad = [r for r in results if r['status'] != 'OK']
    print('Done: %d competitors, %d OK, %d need attention' % (len(results), len(results) - len(bad), len(bad)))
    for r in bad:
        print('  -', r['name'], '|', r['status'])


if __name__ == '__main__':
    main()
