# Deploying the Auriga Opportunity Discovery Engine to GitHub Pages

This repository ships a fully automated workflow that rebuilds the public
**Opportunity Discovery Engine** website and publishes it to **GitHub Pages** —
free, with no server and no manual steps.

> **Why this exists.** Auriga's thesis is the *awareness gap*: most students
> aren't choosing the wrong career — they're choosing from an *incomplete list of
> possibilities* (IIT, NEET, government jobs). This site is the public face of the
> Opportunity Discovery Engine: an always-fresh, verified feed of the wider world
> students rarely see — scholarships, research, olympiads, summer schools, global
> programs. Automating its deployment means that feed updates itself.

The workflow lives at `.github/workflows/deploy.yml`. On every push to `main`
(or a manual run) it: installs Python → installs dependencies → runs
`python main.py --preview` (generates cards/captions, no Meta credentials needed)
→ runs `python main.py --export-site` → publishes the `site/` folder to Pages.

---

## 1. Create the GitHub repository

1. Sign in to GitHub → **New repository**.
2. Name it (e.g. `auriga`) and make it **Public** (required for free Pages on
   personal accounts).
3. Do **not** add a README/`.gitignore` (you already have the project).
4. Push this project to it:

```bash
cd auriga-opportunities          # the project root (contains main.py + .github/)
git init
git add .
git commit -m "Auriga Opportunity Discovery Engine"
git branch -M main
git remote add origin https://github.com/<username>/<repository>.git
git push -u origin main
```

> Push the **whole project** (so the workflow and `main.py` are in the repo) — not
> just the `site/` folder. GitHub Pages will still only serve `site/`.

---

## 2. Enable GitHub Actions

1. Repo → **Settings** → **Actions** → **General**.
2. Under *Actions permissions*, select **Allow all actions and reusable workflows**.
3. Under *Workflow permissions*, select **Read and write permissions** → **Save**.

(New repos usually have Actions enabled by default; this just guarantees it.)

---

## 3. Enable GitHub Pages (source = GitHub Actions)

1. Repo → **Settings** → **Pages**.
2. Under **Build and deployment → Source**, choose **GitHub Actions**
   (⚠️ *not* "Deploy from a branch" — this project deploys via the workflow).
3. That's it. There is nothing else to configure here.

> This **supersedes** the older `site/README_DEPLOY.md` branch method. Use *GitHub
> Actions* as the source; the branch method is only for a manual one-off deploy.

---

## 4. Run it

- **Automatic:** push any commit to `main`. The **Actions** tab shows the
  *"Deploy Auriga site to GitHub Pages"* run (build → deploy).
- **Manual:** Actions tab → select the workflow → **Run workflow**
  (this is the `workflow_dispatch` trigger).

When the run finishes, your site is live at:

```
https://<username>.github.io/<repository>/
```

The deploy job prints the exact URL in its summary. Because the workflow runs on
**every** push with a single-deployment concurrency lock, Pages always ends up
serving the **most recently exported** website.

---

## 5. Connect a custom domain later (optional)

1. Buy a domain (any registrar).
2. Repo → **Settings → Pages → Custom domain** → enter e.g. `opportunities.auriga.org`
   → **Save**. GitHub stores the domain and issues free HTTPS.
3. At your DNS provider, point the domain at GitHub Pages:
   - **Subdomain** (e.g. `opportunities.`): add a **CNAME** record →
     `<username>.github.io`.
   - **Apex/root** (e.g. `auriga.org`): add **A** records to
     `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153`
     (and AAAA records if you want IPv6).
4. Wait for DNS to propagate (minutes to a few hours), then tick
   **Enforce HTTPS** in Settings → Pages.

> **Custom domain + Actions deploys:** GitHub re-applies the custom domain on each
> deploy. If it ever resets, add a one-line file `site/CNAME` containing just your
> domain (e.g. `opportunities.auriga.org`) before pushing, so the domain ships
> inside the published artifact. (You can create it manually — no pipeline change
> needed.)

---

## 6. Troubleshooting failed deployments

| Symptom | Fix |
|---|---|
| Workflow didn't run | Actions disabled → **Settings → Actions → General → Allow all**. Confirm the file is at `.github/workflows/deploy.yml` on `main`. |
| `404` at the Pages URL | **Settings → Pages → Source** must be **GitHub Actions** (not a branch). Re-run the workflow after switching. |
| `Error: Pages site not found` / permission denied | Ensure the workflow `permissions:` block has `pages: write` and `id-token: write` (it does). Re-run. |
| `pip install` fails | Confirm `requirements.txt` is in the repo root (it lists `Pillow`). |
| Site loads but **no images / blank cards** | The build must run `--preview` *before* `--export-site` so the card PNGs exist. The provided workflow already does this in order. |
| Stats/opportunities don't load locally (`file://`) | Pages serves over HTTPS so `fetch()` works there. For **local** preview run `cd site && python -m http.server 8000`. |
| Old content still showing | Hard-refresh (Ctrl/Cmd+Shift+R); Pages/CDN cache can lag a minute. Check the latest **Actions** run actually succeeded. |
| Custom domain shows "improperly configured" | DNS not propagated yet, or wrong record type. Re-check CNAME/A records from step 5; wait and retry. |

---

## 7. Cost

**₹0 / $0.** Public repositories get unlimited GitHub Pages hosting and generous
free Actions minutes — more than enough for this build. No backend, no database
server, no hosting bill.

---

## 8. Keeping the catalog fresh (optional next step)

This workflow rebuilds the site from the data committed to the repo. To make the
catalog *self-update* (the "engine that learns"), add a scheduled job that runs
`python main.py --refill` and commits the updated `sources/opportunities.json`
before export. Ask and this can be added as a second, additive workflow — the
deploy workflow here stays unchanged.
