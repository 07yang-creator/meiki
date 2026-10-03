# 名木 Mei — prestige Japanese garden trees · exhibition & inquiry

`meiki.rakusalab.com` · the isolated sibling of Rakusalab (same paid resources, no shared code).
Spec: `docs/MEI_TREE_GALLERY_PLAN.md` in the Rakusalab repo (v1.2) and `MEI_SPECIES_SEED.md`; a copy lands in `docs/` here with the next slice.

> Repository `07yang-creator/meiki` (moved here from the Rakusalab working tree on 2026-10-03 with its
> history). The Vercel project `mei` git-links to this repo; the schema migrations for the shared Supabase
> project stay in the Rakusalab repo under `supabase/migrations/*_mei_*` (plan D2).

## What is here (P1 gallery + P2 intake)

- `index.html` — the four-season home: the current season first, then calendar order; within a season
  signature trees one per viewport, then the collection grid ordered by species preference rank.
- `t/index.html` — the tree page (`/t/<slug>` via the rewrite): 見頃 hero with the 節気 date, plaque,
  export plaque, 四季 strip, gallery, 树种小识, logistics line, disclaimer line, one 询价 button.
- `journey/` — 木の旅: the seven gates, the dormant-window rule, contingencies, cost items.
- `legal/` — the disclaimer draft (JA 正本, pre-lawyer).
- `assets/mei.css` — design system v2 (paper · ink · four seasons · gold · red seal · curves).
- `assets/mei.js` — the runtime: season order, 二十四節気, ordering, placeholders, renderers.
- `data/species.json` — the registry seed (32 species, Latin key, ZH/JA/EN, 見頃, rank, CN trade
  status, intro + knowledge + reading links for all 32). `data/trees.json` — **sample** trees for the preview.
- `in/` + `assets/intake.js` + `assets/auth.js` + `login/` — the supplier's 入 page (JA): gate in place, registry pick-list
  (「その他」 proposes a pending species), draft/submit, photos re-encoded to ≤2000 px in the browser (EXIF gone) and
  uploaded straight to Storage on a signed URL, HEVC refused, 10-shot grid, one video.
- `api/mei.py` — public reads over the seed + member actions over the `mei` schema (`api/_db.py`, service key); every
  member call re-validates the JWT (`api/_supabase_auth.py`).
- `scripts/fetch_samples.py` — pulls public-domain sample photos from Wikimedia Commons on a machine
  that can reach it (this session could not).

## Run

Nothing to build. Serve the repo root statically (`python3 -m http.server 8080`) and open
`http://localhost:8080/`. Tests: `pytest -q` (API on a fake Supabase, data + page locks) and `for f in assets/*.js; do node --check $f; done`.

## Go-live runbook (owner, one time, ~25 minutes)

Everything below is a one-time setting; nothing in the code changes. Until it is done the login page says
「データベースが未接続です」 and the gallery shows samples only.

**A · Database (Supabase, ~10 min)**

1. On the Mac, in the Rakusalab checkout (the folder with `supabase/config.toml`, already linked to the project):
   ```
   git fetch origin
   git checkout claude/dazzling-galileo-tzxevs     # the branch that carries the mei migration
   supabase db push --linked                       # lists 20261003120000_mei_schema.sql → answer Y
   git checkout main
   ```
   This creates the schema `mei` (tables, the two buckets `mei-vault` / `mei-public`, RLS on) and seeds the 樹形 list and the
   32 species. If the CLI says the project is not linked: `supabase link --project-ref <ref>` (the ref is the first part of the
   Supabase dashboard URL). *Fallback without a terminal:* Supabase → SQL Editor → New query → paste the whole migration file →
   Run — then say so, and the migration ledger gets repaired (`supabase migration repair --status applied 20261003120000`).
2. Supabase → **Project Settings → Data API** (older dashboards: Settings → API) → **Exposed schemas** → add `mei` → Save.
   Without this the API cannot read the schema (PostgREST refuses the profile header).

**B · Keys (Vercel, ~5 min)**

3. Vercel → project **`mei`** → Settings → Environment Variables → add, for Production *and* Preview:
   `SUPABASE_URL` · `SUPABASE_ANON_KEY` · `SUPABASE_SERVICE_ROLE_KEY`. The values are the same ones the Rakusalab project
   `monopages` already has (Vercel → monopages → Settings → Environment Variables → reveal and copy), or Supabase → Project
   Settings → API (Project URL · anon public · service_role secret).
4. Vercel → `mei` → Deployments → the latest → ⋯ → **Redeploy** (variables apply only to new deployments).

**C · People (~5 min)**

5. Supabase → Authentication → Users. The project is shared with Rakusalab, so an existing Rakusalab login works as is.
   For the supplier (and any staff): **Add user → Create new user** → e-mail + password → tick *Auto Confirm User*.
6. Supabase → SQL Editor → paste `scripts/seat_members.sql`, replace the three e-mails, Run. It creates the garden row and the
   `mei.members` rows (admin · supplier with the garden · staff). The last `select` shows the result.

**D · Check (~2 min)**

7. `https://meiki.rakusalab.com/api/mei?action=health` → `"db": true`.
8. `https://meiki.rakusalab.com/login/` → the admin lands on 审 (`/desk/`), the supplier on 入 (`/in/`).
9. `https://meiki.rakusalab.com/?edit=1` → log in as staff/admin → 「替换照片」 on every sample photo.

Later: `MEI_GEMINI_API_KEY`, `RESEND_API_KEY` (AI assists, mail). Before any China-facing launch, replace the Google Fonts
`<link>` (marked DEV ONLY) with self-hosted subsets (plan §8).

## Rules that bite

- Species names are per-language columns joined by the Latin binomial; never map kanji to Chinese.
- The paper is always paper; season colours in five places; gold = signature; red = the seal.
- The plaque is the only square thing. 「推定」 sits next to every age.
- Every export plaque ends with the fixed sentence. Pines are prohibited into mainland China.
- Nothing Google-hosted on a public page (fonts excepted during development).
