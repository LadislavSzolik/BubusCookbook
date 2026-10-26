#!/usr/bin/env python3
"""Build the cookbook website from markdown recipes.

    pip install pyyaml
    python3 build.py                # recipes/ -> site/
    python3 build.py --out docs     # e.g. for GitHub Pages

Each recipe is one markdown file in recipes/ (see README.md for the format).
The output is plain HTML: open site/index.html in a browser or upload the
site/ folder to any static host.
"""
import argparse
import base64
import html
import json
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import yaml

ROOT = Path(__file__).resolve().parent
SITE_TITLE = "My Cookbook"

ING_NAMES = {"ingredients"}
STEP_NAMES = {"method", "directions", "instructions", "steps", "preparation"}
NOTE_NAMES = {"notes", "tips", "note"}
IMAGE_EXTS = ("jpg", "jpeg", "png", "webp")

FONTS = (
    "https://fonts.googleapis.com/css2?family=Crimson+Pro:ital,wght@0,400;0,500;0,600;1,400"
    "&family=Londrina+Solid&display=swap"
)

ICON_SERVINGS = (
    '<svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="1.8" '
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<path d="M7 4v7M10 4v7M13 4v7M7 11a3 3 0 0 0 6 0M10 14v14"/>'
    '<path d="M22 28V4M22 4c3 2 4 7 4 11h-4"/></svg>'
)
ICON_TIME = (
    '<svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="1.8" '
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<circle cx="16" cy="16" r="12"/><path d="M16 9v7l4 3"/></svg>'
)
ICON_LINK = (
    '<svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="1.8" '
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<circle cx="16" cy="16" r="12"/><path d="M12 20l8-8M13 12h7v7"/></svg>'
)
ICON_PLAY = (
    '<svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="1.8" '
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<circle cx="16" cy="16" r="12"/><path d="M13 10.5v11l9-5.5z"/></svg>'
)


# ---------- helpers ----------

def esc(s):
    return html.escape(str(s), quote=True)


def inline(s):
    """Escape text, then support **bold**, *italic* and [links](https://...)."""
    s = esc(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<em>\1</em>", s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', s)
    return s


def plain(s):
    s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", str(s))
    return re.sub(r"[*_`]", "", s).strip()


def fmt_servings(v):
    if isinstance(v, str) and v.strip().isdigit():
        v = int(v.strip())
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        n = int(v)
        return f"{n} serving{'s' if n != 1 else ''}"
    return str(v)


def fmt_time(v):
    if isinstance(v, str) and v.strip().isdigit():
        v = int(v.strip())
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return f"{int(v)} minutes"
    return str(v)


def clean_video_url(value, name):
    """Accept only full http(s) links. On Instagram, share parameters (?xtok=, ?igsh=, ?cplk=)
    are dropped, but ?img_index= is kept so a carousel post opens on the right slide."""
    url = str(value).strip()
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        print(f"  warning: {name}: 'video' must be a full link starting with https://, ignoring: {url}")
        return ""
    host = parts.netloc.lower()
    if host == "instagram.com" or host.endswith(".instagram.com"):
        keep = [(k, v) for k, v in parse_qsl(parts.query) if k == "img_index"]
        parts = parts._replace(query=urlencode(keep), fragment="")
    return urlunsplit(parts)


VIDEO_HOSTS = ("youtube.com", "youtu.be", "tiktok.com", "vimeo.com")


def video_link_info(url):
    """Label and icon for the link: reels and video sites say 'Watch video', other posts say 'View original post'."""
    parts = urlsplit(url)
    if "/reel/" in parts.path or "/tv/" in parts.path or parts.netloc.lower().endswith(VIDEO_HOSTS):
        return "Watch video", ICON_PLAY
    return "View original post", ICON_LINK


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "recipe"


# ---------- parsing ----------

def split_sections(body):
    """Return {section name: [lines]}. A line of '---' ends the current section."""
    sections, current = {}, None
    for line in body.splitlines():
        if re.match(r"^-{3,}\s*$", line):
            current = None
            continue
        if re.match(r"^#\s", line):
            current = None
            continue
        m = re.match(r"^##\s+(.*?)\s*$", line)
        if m:
            current = m.group(1).strip().lower()
            sections.setdefault(current, [])
            continue
        if current is not None:
            sections[current].append(line)
    return sections


def parse_ingredients(lines):
    groups, current = [], None
    for line in lines:
        s = line.strip()
        if not s:
            continue
        h = re.match(r"^###\s+(.*)$", s)
        if h:
            current = {"heading": h.group(1).strip(), "items": []}
            groups.append(current)
            continue
        item = re.match(r"^[-*+]\s+(.*)$", s)
        if item:
            if current is None:
                current = {"heading": None, "items": []}
                groups.append(current)
            current["items"].append(item.group(1).strip())
    return groups


def parse_steps(lines):
    steps = []
    for line in lines:
        if not line.strip():
            continue
        m = re.match(r"^\s*\d+[.)]\s+(.*)$", line)
        if m:
            steps.append(m.group(1).strip())
        elif line[:1] in (" ", "\t") and steps:
            steps[-1] += " " + line.strip()
        else:
            steps.append(re.sub(r"^[-*+]\s+", "", line.strip()))
    return steps


def parse_paragraphs(lines):
    paras, buf = [], []
    for line in lines + [""]:
        if line.strip():
            buf.append(line.strip())
        elif buf:
            paras.append(" ".join(buf))
            buf = []
    return paras


def load_recipe(path, images_dir):
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.S)
    meta, body = ({}, text)
    if m:
        meta = yaml.safe_load(m.group(1)) or {}
        body = m.group(2)

    slug = slugify(path.stem)
    sections = split_sections(body)

    def pick(names):
        for n in names:
            if n in sections:
                return sections[n]
        return []

    title = meta.get("title")
    if not title:
        h1 = re.search(r"^#\s+(.+)$", body, re.M)
        title = h1.group(1).strip() if h1 else path.stem.replace("-", " ").title()

    tags = meta.get("tags") or []
    if isinstance(tags, str):
        tags = [t for t in re.split(r"[,\s]+", tags) if t]
    tags = [str(t).strip().lower() for t in tags]

    cover_src = None
    if meta.get("cover"):
        p = (path.parent / str(meta["cover"])).resolve()
        if p.exists():
            cover_src = p
        else:
            print(f"  warning: {path.name}: cover image not found: {meta['cover']}")
    else:
        for ext in IMAGE_EXTS:
            p = images_dir / f"{slug}.{ext}"
            if p.exists():
                cover_src = p
                break

    ingredients = parse_ingredients(pick(ING_NAMES))
    steps = parse_steps(pick(STEP_NAMES))
    if not ingredients:
        print(f"  warning: {path.name}: no '## Ingredients' list found")
    if not steps:
        print(f"  warning: {path.name}: no '## Method' steps found")

    source = meta.get("source")
    return {
        "slug": slug,
        "title": str(title),
        "description": str(meta.get("description") or ""),
        "tags": tags,
        "servings": fmt_servings(meta.get("servings")),
        "time": fmt_time(meta.get("time")),
        "source": str(source) if source else "",
        "video": clean_video_url(meta["video"], path.name) if meta.get("video") else "",
        "cover_src": cover_src,
        "cover": f"images/{cover_src.name}" if cover_src else None,
        "ingredient_groups": ingredients,
        "steps": steps,
        "notes": parse_paragraphs(pick(NOTE_NAMES)),
    }


# ---------- HTML ----------

def page(title, description, css, body, js=""):
    desc = f'<meta name="description" content="{esc(description)}">\n' if description else ""
    script = f"<script>\n{js}\n</script>\n" if js else ""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
{desc}<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{FONTS}" rel="stylesheet">
<style>
{css}
</style>
</head>
<body>
{body}
{script}</body>
</html>
"""


def data_uri(path):
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
    ext = path.suffix.lower().lstrip(".")
    return f"data:{mime.get(ext, 'image/jpeg')};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def sheet_html(r, img_src, nav_html):
    """The recipe card: title, optional servings/time, optional hero, two columns."""
    meta_items = []
    if r["servings"]:
        meta_items.append(f"<li>{ICON_SERVINGS}<span>{esc(r['servings'])}</span></li>")
    if r["time"]:
        meta_items.append(f"<li>{ICON_TIME}<span>{esc(r['time'])}</span></li>")
    if r["video"]:
        link_label, link_icon = video_link_info(r["video"])
        meta_items.append(
            f'<li><a class="watch" href="{esc(r["video"])}" target="_blank" rel="noopener noreferrer">'
            f"{link_icon}<span>{esc(link_label)}</span></a></li>"
        )
    meta_html = f'<ul class="meta">{"".join(meta_items)}</ul>' if meta_items else ""
    sub_html = f'<p class="sub">{inline(r["description"])}</p>' if r["description"] else ""

    hero = ""
    if img_src:
        hero = f'<figure class="hero"><img src="{esc(img_src)}" alt="{esc(r["title"])}"></figure>'

    ing_html = ""
    for g in r["ingredient_groups"]:
        if g["heading"]:
            ing_html += f"<h3>{inline(g['heading'])}</h3>"
        ing_html += "<ul>" + "".join(f"<li>{inline(i)}</li>" for i in g["items"]) + "</ul>"

    steps_html = "".join(f"<li><span>{inline(s)}</span></li>" for s in r["steps"])

    notes = ""
    if r["notes"]:
        notes = (
            '<section class="notes"><h2>Notes</h2>'
            + "".join(f"<p>{inline(p)}</p>" for p in r["notes"])
            + "</section>"
        )

    credit = ""
    if r["source"]:
        credit = f'<p class="credit">Recipe credit: {inline(r["source"])}</p>'

    return f"""{nav_html}
<main class="sheet">
  <header class="sheet-head">
    <div>
      <h1>{esc(r["title"])}</h1>
      {sub_html}
    </div>
    {meta_html}
  </header>
  {hero}
  <div class="cols">
    <section class="ingredients">
      <h2>Ingredients</h2>
      {ing_html}
    </section>
    <section class="directions">
      <h2>Directions</h2>
      <ol>{steps_html}</ol>
    </section>
  </div>
  {notes}
  {credit}
</main>"""


def recipe_page(r, css):
    img = f"../{r['cover']}" if r["cover"] else None
    nav = '<nav class="topnav"><a href="../index.html">&larr; All recipes</a></nav>'
    return page(f"{r['title']} · {SITE_TITLE}", r["description"], css, sheet_html(r, img, nav))


def card_html(r, href=None, img_src=None, go=None):
    href = href or f"recipes/{r['slug']}.html"
    img_src = img_src if img_src is not None else r["cover"]
    go_attr = f' data-go="{esc(go)}"' if go is not None else ""
    if img_src:
        thumb = f'<img src="{esc(img_src)}" alt="" loading="lazy" decoding="async">'
    else:
        thumb = f'<span class="initial" aria-hidden="true">{esc(r["title"][:1].upper())}</span>'
    facts = [f"<span>{esc(x)}</span>" for x in (r["servings"], r["time"]) if x]
    facts_html = f'<div class="facts">{"".join(facts)}</div>' if facts else ""
    desc = f'<p class="desc">{esc(plain(r["description"]))}</p>' if r["description"] else ""
    chips = "".join(f"<span>{esc(t)}</span>" for t in r["tags"][:3])
    chips_html = f'<div class="chips">{chips}</div>' if chips else ""
    return (
        f'<article class="card" data-slug="{esc(r["slug"])}">'
        f'<a href="{esc(href)}"{go_attr}>'
        f'<div class="thumb">{thumb}</div>'
        f'<div class="body"><h2>{esc(r["title"])}</h2>{desc}{facts_html}{chips_html}</div>'
        f"</a></article>"
    )


SINGLE_FILE_JS = """
(function () {
  var list = document.getElementById("listview");
  var views = document.querySelectorAll("[data-view]");
  function show(slug) {
    for (var i = 0; i < views.length; i++) {
      views[i].hidden = views[i].getAttribute("data-view") !== slug;
    }
    list.hidden = !!slug;
    window.scrollTo(0, 0);
  }
  document.addEventListener("click", function (e) {
    var a = e.target.closest("a[data-go]");
    if (!a) return;
    e.preventDefault();
    show(a.getAttribute("data-go") || null);
  });
  show(null);
})();
"""


def index_page(recipes, css, js, single=False):
    recipes = sorted(recipes, key=lambda r: r["title"].lower())
    data = [
        {
            "slug": r["slug"],
            "title": r["title"],
            "description": plain(r["description"]),
            "tags": r["tags"],
            "ingredients": [plain(i) for g in r["ingredient_groups"] for i in g["items"]],
            "steps": [plain(s) for s in r["steps"]],
        }
        for r in recipes
    ]
    data_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")

    counts = {}
    for r in recipes:
        for t in r["tags"]:
            counts[t] = counts.get(t, 0) + 1
    tag_order = sorted(counts, key=lambda t: (-counts[t], t))
    tags_html = "".join(
        f'<button type="button" data-tag="{esc(t)}" aria-pressed="false">{esc(t)}</button>'
        for t in tag_order
    )

    n = len(recipes)
    count_text = f"{n} recipe{'s' if n != 1 else ''}"
    empty_text = (
        "No recipes yet. Add a markdown file to the recipes folder and run build.py."
        if n == 0
        else "No recipe matches that search. Try fewer words."
    )

    if single:
        cards = "".join(
            card_html(
                r,
                href="#" + r["slug"],
                img_src=data_uri(r["cover_src"]) if r["cover_src"] else "",
                go=r["slug"],
            )
            for r in recipes
        )
        back = '<nav class="topnav"><a href="#" data-go="">&larr; All recipes</a></nav>'
        views = "".join(
            f'<div data-view="{esc(r["slug"])}" hidden>'
            + sheet_html(r, data_uri(r["cover_src"]) if r["cover_src"] else None, back)
            + "</div>"
            for r in recipes
        )
    else:
        cards = "".join(card_html(r) for r in recipes)
        views = ""

    body = f"""<div class="wrap" id="listview">
  <header class="masthead">
    <h1>{esc(SITE_TITLE)}</h1>
    <p>{count_text}</p>
  </header>
  <div class="searchbar">
    <input id="q" type="search" placeholder="Search, e.g. chicken with lemon" aria-label="Search recipes" autocomplete="off" enterkeyhint="search">
  </div>
  <div id="tags" class="tags" aria-label="Filter by tag">{tags_html}</div>
  <p id="status" class="status" role="status" aria-live="polite"></p>
  <div id="grid" class="grid">
    {cards}
  </div>
  <p id="empty" class="empty" hidden>{esc(empty_text)}</p>
</div>
{views}
<script type="application/json" id="recipe-data">{data_json}</script>"""
    scripts = js + ("\n" + SINGLE_FILE_JS if single else "")
    return page(SITE_TITLE, "Our collection of recipes", css, body, scripts)


# ---------- main ----------

def main():
    global SITE_TITLE
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--recipes", default=str(ROOT / "recipes"), help="folder with .md recipes")
    ap.add_argument("--out", default=str(ROOT / "site"), help="output folder")
    ap.add_argument("--title", default=SITE_TITLE, help="site title")
    ap.add_argument("--single-file", action="store_true",
                    help="also write cookbook.html: the whole site in one self-contained file")
    args = ap.parse_args()
    SITE_TITLE = args.title

    recipes_dir = Path(args.recipes).resolve()
    out = Path(args.out).resolve()
    images_dir = recipes_dir.parent / "images"
    css = (ROOT / "assets" / "style.css").read_text(encoding="utf-8")
    js = (ROOT / "assets" / "search.js").read_text(encoding="utf-8")

    files = sorted(p for p in recipes_dir.glob("*.md") if p.name.lower() != "readme.md")
    recipes, seen = [], set()
    for p in files:
        r = load_recipe(p, images_dir)
        if r["slug"] in seen:
            sys.exit(f"Two recipes would use the page name '{r['slug']}'. Rename one file.")
        seen.add(r["slug"])
        recipes.append(r)

    for sub in ("recipes", "images"):
        shutil.rmtree(out / sub, ignore_errors=True)
    (out / "recipes").mkdir(parents=True, exist_ok=True)
    (out / "images").mkdir(parents=True, exist_ok=True)

    for r in recipes:
        (out / "recipes" / f"{r['slug']}.html").write_text(recipe_page(r, css), encoding="utf-8")
        if r["cover_src"]:
            shutil.copy2(r["cover_src"], out / "images" / r["cover_src"].name)
    (out / "index.html").write_text(index_page(recipes, css, js), encoding="utf-8")
    if args.single_file:
        (out / "cookbook.html").write_text(index_page(recipes, css, js, single=True), encoding="utf-8")

    print(f"Built {len(recipes)} recipe(s) into {out}")
    for r in recipes:
        print(f"  - {r['title']}" + ("" if r["cover"] else "  (no cover image)"))


if __name__ == "__main__":
    main()
