"""
inject_data.py — Blog Intel Data Injector v2
=============================================
JSON files se data padhta hai aur index.html mein inject karta hai.
Nayi sites bhi automatically add karta hai agar DB mein nahi hain.

Run: python inject_data.py
"""

import json, re, os
from datetime import datetime

DATA_DIR  = "data"
HTML_FILE = "index.html"
TODAY     = datetime.now().strftime("%Y-%m-%d")
TODAY_LONG= datetime.now().strftime("%b %d, %Y")

SITES = {
    "naukri":        {"name":"Naukri.com",       "color":"#f97316","light":"#fff7ed"},
    "internshala":   {"name":"Internshala.com",   "color":"#2563eb","light":"#eff6ff"},
    "hackerearth":   {"name":"HackerEarth",       "color":"#00d084","light":"#ecfdf5"},
    "careers360":    {"name":"Careers360",         "color":"#e91e63","light":"#fdf2f8"},
    "geeksforgeeks": {"name":"GeeksforGeeks",      "color":"#2f8d46","light":"#f0fdf4"},
}

def load_json(site):
    path = os.path.join(DATA_DIR, f"{site}.json")
    if not os.path.exists(path):
        print(f"  ⚠  {path} not found — skipping")
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def posts_to_js(posts):
    lines = []
    for p in posts:
        u = str(p.get("u","")).replace("\\","\\\\").replace('"','\\"')
        t = str(p.get("t","")).replace("\\","\\\\").replace('"','\\"').replace("'","")
        d = str(p.get("d",""))[:10]
        c = str(p.get("c","")).replace('"','\\"')
        lines.append(f'{{u:"{u}",t:"{t}",d:"{d}",c:"{c}"}}')
    return "[\n" + ",\n".join(lines) + "\n]"

def build_site_pill(key, cfg, count):
    return f'''
            <div class="site-pill" data-k="{key}" onclick="pickSite(this)">
              <span class="site-pill-dot" style="background:{cfg["color"]}"></span>
              <div class="site-pill-info">
                <div class="site-pill-name">{cfg["name"]}</div>
                <div class="site-pill-url">{count:,} posts in database</div>
              </div>
            </div>'''

def build_nav_item(key, cfg):
    return f'''
  <div class="nav-item" id="nav-{key}" onclick="quickSite('{key}')">
    <span style="width:8px;height:8px;border-radius:50%;background:{cfg["color"]};display:inline-block;flex-shrink:0"></span> {cfg["name"]}
  </div>'''

def main():
    print(f"\n{'='*50}")
    print(f"  BLOG INTEL — inject_data.py v2")
    print(f"  {TODAY}")
    print(f"{'='*50}\n")

    if not os.path.exists(HTML_FILE):
        print(f"❌ {HTML_FILE} not found!"); return

    with open(HTML_FILE, "r", encoding="utf-8") as f:
        html = f.read()

    print(f"📄 Loaded {HTML_FILE} ({len(html):,} bytes)\n")

    # ── Load all available JSON data ──
    site_data = {}
    for key in SITES:
        data = load_json(key)
        if data:
            site_data[key] = data.get("posts", [])
            print(f"  ✅ {key}: {len(site_data[key]):,} posts loaded")

    if not site_data:
        print("❌ No JSON data found in data/ folder!"); return

    print()

    # ── Step 1: Rebuild entire DB object ──
    print("📝 Rebuilding DB object...")
    db_parts = []
    for key, posts in site_data.items():
        js = posts_to_js(posts)
        db_parts.append(f"{key}:{js}")

    new_db = "const DB={\n" + ",\n".join(db_parts) + "\n};"

    # Replace existing DB
    pattern = r'const DB=\{.*?\};'
    new_html, n = re.subn(pattern, new_db, html, count=1, flags=re.DOTALL)
    if n:
        html = new_html
        print(f"  ✅ DB rebuilt with {len(site_data)} sites\n")
    else:
        print(f"  ⚠  DB pattern not found — appending before </script>")
        html = html.replace("// CATEGORY STYLES", new_db + "\n\n// CATEGORY STYLES", 1)

    # ── Step 2: Rebuild site pills ──
    print("🎨 Rebuilding site pills...")
    pills_html = ""
    for key, cfg in SITES.items():
        if key in site_data:
            pills_html += build_site_pill(key, cfg, len(site_data[key]))

    # Replace entire site-pills div content
    pattern = r'(<div class="site-pills">)(.*?)(</div>(?=\s*</div>))'
    new_html, n = re.subn(pattern, r'\1' + pills_html + r'\3', html, count=1, flags=re.DOTALL)
    if n:
        html = new_html
        print(f"  ✅ {len(site_data)} site pills built\n")
    else:
        print(f"  ⚠  site-pills pattern not found\n")

    # ── Step 3: Rebuild nav items for sites ──
    print("🗂 Rebuilding nav items...")
    nav_html = ""
    for key, cfg in SITES.items():
        if key in site_data:
            nav_html += build_nav_item(key, cfg)

    # Replace between SITES section labels
    pattern = r'(<div class="nav-section-label">Sites</div>)(.*?)(<div class="nav-section-label">Quick Ranges</div>)'
    new_html, n = re.subn(
        pattern,
        r'\1' + nav_html + r'\n  \3',
        html, count=1, flags=re.DOTALL
    )
    if n:
        html = new_html
        print(f"  ✅ Nav items rebuilt\n")
    else:
        print(f"  ⚠  Nav section pattern not found\n")

    # ── Step 4: Update masthead ──
    print("📊 Updating masthead counts...")
    meta_items = ""
    for key, posts in site_data.items():
        name = SITES[key]["name"].replace(".com","").replace("GeeksforGeeks","GFG")
        meta_items += f'\n      <div class="mmeta-item">{name}: <b>{len(posts):,}</b></div>'

    pattern = r'(<div class="topbar-logo">.*?</div>\s*)((?:<div class="mmeta-item">.*?</div>\s*)+)'
    new_html, n = re.subn(pattern, r'\1' + meta_items, html, count=1, flags=re.DOTALL)
    if n:
        html = new_html
        print(f"  ✅ Masthead updated\n")

    # ── Step 5: Update site config in renderAll ──
    print("⚙️  Updating site config map...")
    site_map_entries = []
    for key, cfg in SITES.items():
        if key in site_data:
            site_map_entries.append(
                f"    {key}:{{name:'{cfg['name']}',color:'{cfg['color']}',colorLight:'{cfg['light']}'}}"
            )
    new_site_map = "const siteMap={\n" + ",\n".join(site_map_entries) + "\n  };\n  const site=siteMap[CUR]||Object.values(siteMap)[0];"

    pattern = r'const siteMap=\{.*?\};\s*const site=siteMap\[CUR\][^;]*;'
    new_html, n = re.subn(pattern, new_site_map, html, count=1, flags=re.DOTALL)
    if n:
        html = new_html
        print(f"  ✅ Site config updated\n")

    # ── Step 6: Update updateNavHighlight ──
    print("🎨 Updating nav highlight function...")
    nav_map_entries = []
    for key, cfg in SITES.items():
        if key in site_data:
            # compute darker text color
            nav_map_entries.append(
                f"    {key}:{{id:'nav-{key}',color:'{cfg['color']}',bg:'rgba(0,0,0,.06)',text:'#fff'}}"
            )
    new_nav_fn = """function updateNavHighlight(){
  const navMap={
""" + ",\n".join(nav_map_entries) + """
  };
  Object.entries(navMap).forEach(([k,v])=>{
    const el=document.getElementById(v.id);
    if(el) el.style.cssText=CUR===k?'border-left:3px solid '+v.color+';background:'+v.bg+';color:'+v.text:'';
  });
}"""

    pattern = r'function updateNavHighlight\(\)\{.*?\}'
    new_html, n = re.subn(pattern, new_nav_fn, html, count=1, flags=re.DOTALL)
    if n:
        html = new_html
        print(f"  ✅ Nav highlight updated\n")

    # ── Step 7: Update date strings ──
    html = re.sub(r'Data as of [A-Za-z]+ \d{1,2}, \d{4}', f'Data as of {TODAY_LONG}', html)
    html = re.sub(r"const TODAY='[\d-]+'", f"const TODAY='{TODAY}'", html)
    html = re.sub(r'<span class="topbar-date">[^<]+</span>', f'<span class="topbar-date">{TODAY_LONG}</span>', html)

    # ── Save ──
    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    total = sum(len(p) for p in site_data.values())
    print(f"{'='*50}")
    print(f"✅ {HTML_FILE} updated — {TODAY_LONG}")
    print(f"📊 Total posts: {total:,} across {len(site_data)} sites")
    print(f"{'='*50}\n")

if __name__ == "__main__":
    main()
