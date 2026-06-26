# Deploying the Auriga site to GitHub Pages

This `site/` folder is a fully static website (HTML5 + CSS3 + vanilla JS). No build
step, no server. It also hosts the Instagram card images.

## 1. Create a GitHub repository
Create a new repo, e.g. `auriga` (public).

## 2. Push the code
From the `site/` folder:
```bash
cd site
git init
git add .
git commit -m "Auriga static site"
git branch -M main
git remote add origin https://github.com/<username>/<repository>.git
git push -u origin main
```

## 3. Enable GitHub Pages
Repo → **Settings** → **Pages**.

## 4. Select the source
Under **Build and deployment**, set **Source = Deploy from a branch**, choose
**Branch: main**, folder **/(root)**, then **Save**.

## 5. Your site is live
After ~1 minute it is available at:
```
https://<username>.github.io/<repository>/
```

## Hooking up Instagram image hosting
Instagram needs a public image URL. Once deployed, set in your `.env`:
```
IG_IMAGE_BASE_URL=https://<username>.github.io/<repository>
```
The pipeline then builds image URLs as
`IG_IMAGE_BASE_URL/cards/<category>/<file>.png` — which this site serves.

## Local preview
The pages load data with `fetch()`, so open them through a tiny web server (not
file://):
```bash
cd site && python -m http.server 8000   # then visit http://localhost:8000
```

## Updating
Re-run `python main.py --export-site` to regenerate HTML, CSS, JS, JSON, cards and
QR images, then commit & push the `site/` folder again. (Cloudflare Pages works the
same way — point it at this folder.)
