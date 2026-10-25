# The index's website

https://tessel-packages.syncster.dev: every library in `packages/`, with a
search box, and a page for each with its versions, the libraries it uses
and its README.

Author: Alexius Academia · Started 2026-10-25

Netlify (project `tessel-packages`, team syncster.dev) builds it from this
folder on every push to `main`, so a merged version is on the site a minute
or two later. Nothing here needs changing when a library is published.

```
build.py            # reads ../packages, fetches each latest version's README at its tag, writes dist/
requirements.txt    # markdown-it-py, for the READMEs (raw HTML in them is shown as text, never run)
netlify.toml        # the build, and "always build" (the entries are outside this folder)
static/             # styles.css, site.js (search, copy buttons, Tessel code colours), favicon, 404 page, share.png
```

A library's "Website" link is its GitHub repository's homepage, asked from
GitHub's API (left out if GitHub doesn't answer). Its dates come from when
its entry was merged (`git log`).

To build it locally:

```bash
cd site
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python build.py
python3 -m http.server 8080 -d dist    # http://localhost:8080/
```
