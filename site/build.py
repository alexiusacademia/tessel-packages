"""Builds the index's website (https://tessel-packages.syncster.dev) from
the entries in ../packages: a home page listing every library, with a
search box, and a page for each with its versions, the libraries it uses
and its README (fetched from its repository at the latest version's tag).

Netlify runs it on every push to main (see netlify.toml), so a merged
version shows up by itself. Run it locally with:

    pip install -r requirements.txt
    python3 build.py            # writes dist/

Author: Alexius Academia
Date: 2026-10-25
"""

import html
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

from markdown_it import MarkdownIt

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.normpath(os.path.join(HERE, "..", "packages"))
OUT = os.path.join(HERE, "dist")
SITE = "https://tessel-packages.syncster.dev"
INDEX_REPO = "https://github.com/alexiusacademia/tessel-packages"
GUIDE = "https://tessel-lang.syncster.dev/guides/libraries/"


def esc(s):
    return html.escape(str(s), quote=True)


# --- Reading the entries -------------------------------------------------

def parse_entry(text):
    """An entry file: `key = "value"` lines and a [dependencies] table.
    (The format is small and fixed, so no TOML library is needed.)"""
    entry = {"dependencies": {}}
    table = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.fullmatch(r"\[([A-Za-z_]+)\]", line)
        if m:
            table = m.group(1)
            continue
        m = re.fullmatch(r'([A-Za-z0-9_]+)\s*=\s*"((?:[^"\\]|\\.)*)"', line)
        if not m:
            continue
        key, value = m.group(1), json.loads('"' + m.group(2) + '"')
        if table == "dependencies":
            entry["dependencies"][key] = value
        elif table is None:
            entry[key] = value
    return entry


def version_key(v):
    """1.10.0 after 1.9.0; a pre-release before its release."""
    main, _, pre = v.partition("-")
    parts = [int(p) if p.isdigit() else 0 for p in main.split(".")]
    return (parts, 0 if pre else 1, pre)


def published_date(path):
    """When the entry was merged, from git (empty if git can't say)."""
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%cI", "--", path], cwd=HERE,
                             capture_output=True, text=True, timeout=30).stdout.strip()
        return out[:10]
    except Exception:
        return ""


def read_index():
    libs = {}
    for name in sorted(os.listdir(INDEX)):
        folder = os.path.join(INDEX, name)
        if not os.path.isdir(folder):
            continue
        versions = []
        for f in os.listdir(folder):
            if f.endswith(".toml"):
                path = os.path.join(folder, f)
                with open(path, encoding="utf-8") as fh:
                    e = parse_entry(fh.read())
                e["date"] = published_date(path)
                versions.append(e)
        if versions:
            versions.sort(key=lambda e: version_key(e.get("version", "0")), reverse=True)
            libs[name] = versions
    return libs


# --- What each library's repository says ---------------------------------

def fetch(url, accept=None):
    req = urllib.request.Request(url, headers={"User-Agent": "tessel-packages-site"})
    if accept:
        req.add_header("Accept", accept)
    token = os.environ.get("GITHUB_TOKEN")
    if token and "api.github.com" in url:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def github_path(repository):
    m = re.match(r"https://github\.com/([^/]+)/([^/#?]+?)(?:\.git)?/?$", repository or "")
    return (m.group(1), m.group(2)) if m else None


def readme_of(entry):
    gh = github_path(entry.get("repository", ""))
    if not gh:
        return None
    for name in ("README.md", "readme.md", "Readme.md"):
        try:
            return fetch(f"https://raw.githubusercontent.com/{gh[0]}/{gh[1]}/{entry['tag']}/{name}")
        except urllib.error.HTTPError:
            continue
        except Exception as e:
            print(f"  can't fetch the README of {entry['name']}: {e}", file=sys.stderr)
            return None
    return None


def homepage_of(entry):
    """The repository's website, if it says one (GitHub's API allows few
    requests without a token, so this may come back empty)."""
    gh = github_path(entry.get("repository", ""))
    if not gh:
        return ""
    try:
        data = json.loads(fetch(f"https://api.github.com/repos/{gh[0]}/{gh[1]}", "application/vnd.github+json"))
        page = data.get("homepage") or ""
        return page if page.startswith("https://") or page.startswith("http://") else ""
    except Exception as e:
        print(f"  can't ask GitHub about {entry['name']}: {e}", file=sys.stderr)
        return ""


# --- READMEs as HTML -----------------------------------------------------

# Raw HTML in a README is shown as text, never run: these READMEs come from
# anyone who publishes a library.
md = MarkdownIt("commonmark", {"html": False, "linkify": False, "typographer": False}).enable("table").enable("strikethrough")


def slug(text):
    s = re.sub(r"<[^>]+>", "", text).lower()
    s = re.sub(r"[^\w\- ]", "", s).strip().replace(" ", "-")
    return s or "section"


def readme_html(text, entry):
    """The README as HTML, with links and pictures that point into the
    repository at the version's tag, and anchors on the headings."""
    gh = github_path(entry["repository"])
    tag = entry["tag"]
    body = md.render(text)

    def fix(attr, url, raw):
        if re.match(r"^[a-z][a-z0-9+.-]*:", url, re.I) or url.startswith("#") or url.startswith("//"):
            return f'{attr}="{url}"'
        clean = url.lstrip("./")
        if raw:
            return f'{attr}="https://raw.githubusercontent.com/{gh[0]}/{gh[1]}/{tag}/{clean}"'
        return f'{attr}="https://github.com/{gh[0]}/{gh[1]}/blob/{tag}/{clean}"'

    body = re.sub(r'src="([^"]*)"', lambda m: fix("src", m.group(1), True), body)
    body = re.sub(r'href="([^"]*)"', lambda m: fix("href", m.group(1), False), body)
    # The README's own title repeats the page's.
    body = re.sub(r"^\s*<h1>[^<]*</h1>\n?", "", body, count=1)
    seen = {}

    def anchor(m):
        level, inner = m.group(1), m.group(2)
        s = slug(inner)
        seen[s] = seen.get(s, 0) + 1
        if seen[s] > 1:
            s = f"{s}-{seen[s] - 1}"
        return f'<h{level} id="{s}">{inner}</h{level}>'

    body = re.sub(r"<h([2-4])>(.*?)</h\1>", anchor, body)
    # Tables scroll on their own on a phone.
    body = body.replace("<table>", '<div class="table"><table>').replace("</table>", "</table></div>")
    return body


# --- Pages ---------------------------------------------------------------

ICON_GITHUB = '<svg viewBox="0 0 16 16" aria-hidden="true"><path fill="currentColor" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/></svg>'


def page(title, description, body, path, depth):
    up = "../" * depth
    canonical = SITE + "/" + path
    return f"""<!doctype html>
<!--
  The Tessel library index's website, made by site/build.py from the
  entries in packages/ of {INDEX_REPO}.
  Author: Alexius Academia
-->
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="author" content="Alexius Academia">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)}</title>
  <meta name="description" content="{esc(description)}">
  <meta name="theme-color" content="#0063d1">
  <link rel="canonical" href="{esc(canonical)}">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="Tessel libraries">
  <meta property="og:title" content="{esc(title)}">
  <meta property="og:description" content="{esc(description)}">
  <meta property="og:url" content="{esc(canonical)}">
  <meta property="og:image" content="{SITE}/share.png">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta name="twitter:card" content="summary_large_image">
  <link rel="icon" href="{up}favicon.svg" type="image/svg+xml">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400;12..96,600;12..96,700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="{up}styles.css">
</head>
<body>
<header class="top">
  <div class="wrap">
    <a class="brand" href="{up}"><img src="{up}favicon.svg" alt="" width="28" height="28"> Tessel libraries</a>
    <nav>
      <a href="{up}#publish" class="optional">Publish one</a>
      <a href="https://tessel-lang.syncster.dev">Tessel</a>
      <a href="{INDEX_REPO}">GitHub</a>
    </nav>
  </div>
</header>
<main>
{body}
</main>
<footer>
  <div class="wrap">
    <span>The Tessel library index · © 2026 <a href="https://syncster.dev" rel="author">Alexius Academia</a> · <a href="mailto:admin@syncster.dev">admin@syncster.dev</a> · <a href="https://syncster.dev">syncster.dev</a></span>
    <nav>
      <a href="{INDEX_REPO}">The index on GitHub</a>
      <a href="{GUIDE}">Libraries guide</a>
      <a href="https://tessel-lang.syncster.dev">Tessel</a>
    </nav>
  </div>
</footer>
<script src="{up}site.js"></script>
</body>
</html>
"""


def install_box(name):
    cmd = f"tessel add {name}"
    return (f'<div class="install"><code>{esc(cmd)}</code>'
            f'<button class="copy" type="button" data-copy="{esc(cmd)}">Copy</button></div>')


def home(libs, info, built):
    cards = []
    order = sorted(libs, key=lambda n: n)
    for name in order:
        latest = libs[name][0]
        deps = latest.get("dependencies") or {}
        uses = ""
        if deps:
            uses = '<span class="uses">uses ' + ", ".join(
                f'<a href="{esc(d)}/">{esc(d)}</a>' for d in sorted(deps)) + "</span>"
        site = info[name]["homepage"]
        links = f'<a href="{esc(name)}/">Details</a>'
        if site:
            links += f'<a href="{esc(site)}">Website</a>'
        links += f'<a href="{esc(latest.get("repository", ""))}">Code</a>'
        search = " ".join([name, latest.get("description", ""), " ".join(deps)]).lower()
        cards.append(f"""      <article class="lib" data-search="{esc(search)}">
        <div class="lib-head">
          <h3><a href="{esc(name)}/">{esc(name)}</a></h3>
          <span class="version">{esc(latest.get("version", ""))}</span>
        </div>
        <p>{esc(latest.get("description", ""))}</p>
        <div class="lib-meta">
          <code class="add" data-copy="tessel add {esc(name)}" title="Copy">tessel add {esc(name)}</code>
          <span>{esc(latest.get("license", ""))}</span>
          {f'<span>{esc(latest["date"])}</span>' if latest.get("date") else ""}
          {uses}
        </div>
        <div class="lib-links">{links}</div>
      </article>""")
    versions = sum(len(v) for v in libs.values())
    body = f"""<div class="hero">
  <div class="wrap">
    <p class="eyebrow">The Tessel library index</p>
    <h1>Libraries for Tessel programs.</h1>
    <p class="lede">Everything published with <code>tessel publish</code>: {len(libs)} libraries, {versions} versions. Add one to a project with <code>tessel add</code>, then <code>import</code> it.</p>
    <div class="search">
      <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7" fill="none" stroke="currentColor" stroke-width="2"/><path d="M20 20l-4-4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
      <input id="q" type="search" placeholder="Search {len(libs)} libraries" autocomplete="off" aria-label="Search libraries">
    </div>
  </div>
</div>
<section class="list">
  <div class="wrap">
    <div class="libs" id="libs">
{chr(10).join(cards)}
    </div>
    <p class="none" id="none" hidden>No library matches that. <a href="#publish">Publish one?</a></p>
  </div>
</section>
<section id="publish">
  <div class="wrap">
    <h2>Publish a library</h2>
    <p class="intro">A library is a Tessel module in a git repository, with a <code>[library]</code> table in its <code>tessel.toml</code>. Publishing tags a version and proposes its entry here as a pull request, which is checked automatically: the tag, the checksum, and that the code compiles.</p>
    <div class="steps">
<pre>tessel new textkit --template library   # start one
cd textkit
# write it, push it to GitHub, then:
tessel publish                           # tag it and propose it here</pre>
    </div>
    <p class="intro">Once the pull request is merged, the library is on this page within a minute or two, and <code>tessel add</code> finds it. See the <a href="{GUIDE}">Libraries guide</a> for the details.</p>
  </div>
</section>
<p class="built wrap">Made from the index on {esc(built)}.</p>
"""
    return page("Tessel libraries", f"The libraries published for Tessel programs: {len(libs)} libraries, from charts and CSV files to regular expressions and property panels.",
                body, "", 0)


def detail(name, versions, info):
    latest = versions[0]
    deps = latest.get("dependencies") or {}
    site = info["homepage"]
    links = ""
    if site:
        links += f'<a class="button primary" href="{esc(site)}">Website</a>'
    links += f'<a class="button" href="{esc(latest.get("repository", ""))}">{ICON_GITHUB} Code</a>'
    rows = []
    gh = github_path(latest.get("repository", ""))
    for e in versions:
        tag_link = esc(e.get("tag", ""))
        if gh:
            tag_link = f'<a href="https://github.com/{gh[0]}/{gh[1]}/tree/{esc(e["tag"])}">{esc(e["tag"])}</a>'
        edeps = ", ".join(f"{esc(k)} {esc(v)}" for k, v in sorted((e.get("dependencies") or {}).items())) or "–"
        rows.append(f'<tr><td><b>{esc(e.get("version", ""))}</b></td><td>{tag_link}</td>'
                    f'<td><code>{esc(e.get("commit", "")[:10])}</code></td><td>{esc(e.get("date", ""))}</td><td>{edeps}</td></tr>')
    uses = ""
    if deps:
        uses = "<p class=\"intro\">Uses " + ", ".join(
            f'<a href="../{esc(d)}/">{esc(d)}</a> {esc(v)}' for d, v in sorted(deps.items())) + ".</p>"
    if info["readme"]:
        readme = f'<article class="readme">{info["readme"]}</article>'
    else:
        readme = f'<p class="intro">Its README couldn\'t be read. See <a href="{esc(latest.get("repository", ""))}">its repository</a>.</p>'
    body = f"""<div class="hero detail">
  <div class="wrap">
    <p class="eyebrow"><a href="../">Tessel libraries</a> / {esc(name)}</p>
    <h1>{esc(name)} <span class="version">{esc(latest.get("version", ""))}</span></h1>
    <p class="lede">{esc(latest.get("description", ""))}</p>
    {install_box(name)}
    <div class="buttons">{links}</div>
    <p class="meta">{esc(latest.get("license", ""))} licence · {len(versions)} version{"s" if len(versions) != 1 else ""}{(" · published " + esc(latest["date"])) if latest.get("date") else ""}</p>
  </div>
</div>
<section class="readme-section">
  <div class="wrap">
    {readme}
  </div>
</section>
<section>
  <div class="wrap">
    <h2>Versions</h2>
    {uses}
    <div class="table"><table>
      <tr><th>Version</th><th>Tag</th><th>Commit</th><th>Published</th><th>Uses</th></tr>
      {"".join(rows)}
    </table></div>
    <p class="intro" style="margin-top:14px">Each version's entry in the index records its commit and the checksum of its code, and <code>tessel add</code> checks the download against them.</p>
  </div>
</section>
"""
    return page(f"{name} · Tessel libraries", latest.get("description", "") or f"The {name} library for Tessel.",
                body, f"{name}/", 1)


def main():
    libs = read_index()
    if not libs:
        sys.exit("no entries in " + INDEX)
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    for f in os.listdir(os.path.join(HERE, "static")):
        shutil.copy(os.path.join(HERE, "static", f), os.path.join(OUT, f))
    info = {}
    for name, versions in libs.items():
        print(f"{name} {versions[0]['version']}")
        text = readme_of(versions[0])
        info[name] = {
            "readme": readme_html(text, versions[0]) if text else "",
            "homepage": homepage_of(versions[0]),
        }
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as f:
        f.write(home(libs, info, built))
    for name, versions in libs.items():
        os.makedirs(os.path.join(OUT, name), exist_ok=True)
        with open(os.path.join(OUT, name, "index.html"), "w", encoding="utf-8") as f:
            f.write(detail(name, versions, info[name]))
    urls = [SITE + "/"] + [f"{SITE}/{n}/" for n in libs]
    with open(os.path.join(OUT, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
        f.write("".join(f"  <url><loc>{esc(u)}</loc></url>\n" for u in urls))
        f.write("</urlset>\n")
    with open(os.path.join(OUT, "libraries.json"), "w", encoding="utf-8") as f:
        json.dump({n: [{k: v for k, v in e.items()} for e in vs] for n, vs in libs.items()}, f, indent=1)
    missing = [n for n in libs if not info[n]["readme"]]
    print(f"{len(libs)} libraries -> {OUT}" + (f" (no README: {', '.join(missing)})" if missing else ""))


main()
