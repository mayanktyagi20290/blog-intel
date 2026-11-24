#!/usr/bin/env python3
"""Competitor blog tracker: weekly new-post counts per competitor/category.
Reads competitors.csv (Category, Competitor, Blog URL, Sitemap override), crawls sitemaps
(fallback: RSS), buckets posts by lastmod/pubDate into Monday-based weeks, merges into
history.json (so history survives sitemap changes) and writes data.json for the dashboard."""
import csv, gzip, json, os, re, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

HERE = os.path.dirname(os.path.abspath(__file__))
WEEKS = 12
UA = 'Mozilla/5.0 (compatible; BlogIntelTracker/1.0)'
MAX_SITEMAPS = 25


def get(url, timeout=20):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': '*/*'})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
        if raw[:2] == b'\x1f\x8b':
            raw = gzip.decompress(raw)
        return raw.decode('utf-8', errors='replace')
    except Exception:
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


def sitemap_roots(origin, override):
    if override:
        return [x for x in re.split(r'[\s,]+', override) if x]
    roots = []
    txt = get(origin + '/robots.txt') or ''
    roots += re.findall(r'(?im)^sitemap:\s*(\S+)', txt)
    return roots or [origin + '/sitemap.xml']


def collect_sitemap(blog, override, cutoff):
    m = re.match(r'https?://[^/]+', blog)
    origin, prefix = m.group(0), blog[m.end():].rstrip('/')
    queue, seen_s, seen_u, out = sitemap_roots(origin, override), set(), set(), []
    while queue and len(seen_s) < MAX_SITEMAPS:
        s = queue.pop(0)
        if s in seen_s:
            continue
        seen_s.add(s)
        xml = get(s)
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
            if loc.startswith(origin + prefix + '/') and norm != origin + prefix and norm not in seen_u:
                seen_u.add(norm)
                out.append((norm, parse_dt(tag(b, 'lastmod'))))
    return out


def collect_rss(blog):
    m = re.match(r'https?://[^/]+', blog)
    origin, base = m.group(0), blog.rstrip('/')
    out = {}
    for f in (base + '/feed', base + '/feed/', base + '/rss.xml', base + '/feed.xml', origin + '/feed', origin + '/rss.xml'):
        xml = get(f)
        if not xml or '<item' not in xml and '<entry' not in xml:
            continue
        for b in re.findall(r'<item>[\s\S]*?</item>|<entry>[\s\S]*?</entry>', xml):
            link = tag(b, 'link') or (re.search(r'<link[^>]+href="([^"]+)"', b) or [None, ''])[1]
            dt = parse_dt(tag(b, 'pubDate') or tag(b, 'published') or tag(b, 'updated'))
            if link and dt:
                out[link.rstrip('/')] = dt
        if out:
            break
    return list(out.items())


def process(row, weeks):
    cat, name, blog, override = (row + ['', '', '', ''])[:4]
    counts, latest, status = [0] * len(weeks), None, 'OK'
    first = datetime.combine(weeks[0], datetime.min.time(), tzinfo=timezone.utc)
    try:
        urls = collect_sitemap(blog, override.strip(), first)
        dated = [(u, d) for u, d in urls if d]
        if not dated:
            rss = collect_rss(blog)
            if rss:
                dated, status = rss, 'RSS only (latest posts, partial)'
            elif urls:
                status = 'Sitemap has no lastmod'
            else:
                status = 'No sitemap/RSS found (add override)'
        for _, d in dated:
            if latest is None or d > latest:
                latest = d
            idx = (d.date() - weeks[0]).days // 7
            if 0 <= idx < len(weeks):
                counts[idx] += 1
    except Exception as e:
        status = 'Error: %s' % str(e)[:60]
    return {'category': cat, 'name': name, 'blog': blog, 'counts': counts,
            'latest': latest.date().isoformat() if latest else '', 'status': status}


def main():
    weeks = week_starts()
    with open(os.path.join(HERE, 'competitors.csv'), newline='', encoding='utf-8') as f:
        rows = [r for r in list(csv.reader(f))[1:] if len(r) > 2 and r[1].strip() and r[2].strip()]
    with ThreadPoolExecutor(6) as ex:
        results = list(ex.map(lambda r: process(r, weeks), rows))

    hp = os.path.join(HERE, 'history.json')
    hist = json.load(open(hp)) if os.path.exists(hp) else {}
    for r in results:
        h = hist.setdefault(r['name'], {'category': r['category'], 'blog': r['blog'], 'weeks': {}})
        h['category'], h['blog'] = r['category'], r['blog']
        if r['status'] in ('OK',) or r['status'].startswith('RSS'):
            for w, c in zip(weeks, r['counts']):
                k = w.isoformat()
                h['weeks'][k] = max(h['weeks'].get(k, 0), c)
    json.dump(hist, open(hp, 'w'), indent=1)

    out_rows = []
    for r in results:
        hw = hist[r['name']]['weeks']
        counts = [hw.get(w.isoformat(), 0) for w in weeks]
        out_rows.append({**r, 'counts': counts, 'total': sum(counts)})
    data = {'generated': datetime.now(timezone.utc).isoformat(timespec='minutes'),
            'weeks': [w.isoformat() for w in weeks], 'rows': out_rows}
    json.dump(data, open(os.path.join(HERE, 'data.json'), 'w'), indent=1)
    ok = sum(1 for r in results if r['status'] == 'OK')
    print('Done: %d competitors, %d OK, %d need attention' % (len(results), ok, len(results) - ok))
    for r in results:
        if r['status'] != 'OK':
            print('  -', r['name'], '|', r['status'])


if __name__ == '__main__':
    main()
