# Cookbook

A small recipe website generated from markdown files. No framework, no server.

```
recipes/   one .md file per recipe
images/    optional cover photos
assets/    style.css and search.js (the look and the search)
build.py   turns recipes/ into site/
site/      the generated website (open index.html or upload the folder)
```

## Build

```
pip install pyyaml
python3 build.py                 # writes site/
python3 build.py --single-file   # also writes site/cookbook.html, the whole site in one file
python3 build.py --title "Our Kitchen"
```

## Add a recipe

Create `recipes/my-recipe.md`. Only the title and the two sections are needed.

```markdown
---
title: Avocado Toast
description: Fast and delicious toast for the whole family   # optional, shown under the title
servings: 2                                                   # optional, shown top right
time: 15 minutes                                              # optional, shown top right
tags: [breakfast, vegetarian]                                 # optional, used for filter chips and search
cover: ../images/avocado-toast.jpg                            # optional hero image
source: "@someone on Instagram"                               # optional credit, shown at the bottom
video: https://www.instagram.com/reel/XXXXXXXXXXX/            # optional link, shown top right as "Watch video"
---

## Ingredients

- 2 slices sourdough
- 1 ripe avocado

## Method

1. Toast the bread.
2. Mash the avocado and spread it on top.

## Notes

Optional section for tips.
```

- Without `cover:`, the build uses `images/<file-name>.jpg` (or .png, .webp) if it exists. With no image the recipe page simply has no hero.
- Ingredients can be grouped with `### Sauce`, `### To serve` and so on.
- `servings: 2` shows as "2 servings" and `time: 15` as "15 minutes". Any text works too, for example `time: 1 hr 30 min`.

## Search

The search box understands plain sentences. Filler words are ignored and the rest must all match the title, tags, ingredients or method:

- `I want to make a chicken recipe which has lemon` finds recipes with chicken and lemon
- `chicken without lemon` excludes lemon
- If nothing has every word, the closest matches are shown

Opening `index.html?q=chicken+lemon` starts with that search applied, which is useful for voice assistants or phone shortcuts later.

## Publish

Upload the `site/` folder to any static host (GitHub Pages, Netlify, Cloudflare Pages), or serve it from a Raspberry Pi with `python3 -m http.server -d site`.
