# 名木 Mei — prestige Japanese garden trees · exhibition & inquiry

`mei.rakusalab.com` · the isolated sibling of Rakusalab (same paid resources, no shared code).
Spec: `docs/MEI_TREE_GALLERY_PLAN.md` in the Rakusalab repo (v1.2) and `MEI_SPECIES_SEED.md`; a copy lands in `docs/` here with the next slice.

> Repository `07yang-creator/meiki` (moved here from the Rakusalab working tree on 2026-10-03 with its
> history). The Vercel project `mei` git-links to this repo; the schema migrations for the shared Supabase
> project stay in the Rakusalab repo under `supabase/migrations/*_mei_*` (plan D2).

## What is here (slice P1 + the public gallery)

- `index.html` — the four-season home: the current season first, then calendar order; within a season
  signature trees one per viewport, then the collection grid ordered by species preference rank.
- `t/index.html` — the tree page (`/t/<slug>` via the rewrite): 見頃 hero with the 節気 date, plaque,
  export plaque, 四季 strip, gallery, 树种小识, logistics line, disclaimer line, one 询价 button.
- `journey/` — 木の旅: the seven gates, the dormant-window rule, contingencies, cost items.
- `legal/` — the disclaimer draft (JA 正本, pre-lawyer).
- `assets/mei.css` — design system v2 (paper · ink · four seasons · gold · red seal · curves).
- `assets/mei.js` — the runtime: season order, 二十四節気, ordering, placeholders, renderers.
- `data/species.json` — the registry seed (32 species, Latin key, ZH/JA/EN, 見頃, rank, CN trade
  status, knowledge for the first eight). `data/trees.json` — **sample** trees for the preview.
- `api/mei.py` — public reads over the seed; Supabase next.
- `scripts/fetch_samples.py` — pulls public-domain sample photos from Wikimedia Commons on a machine
  that can reach it (this session could not).

## Run

Nothing to build. Serve the repo root statically (`python3 -m http.server 8080`) and open
`http://localhost:8080/`. Tests: `pytest -q` (data + page locks) and `node --check assets/mei.js`.

## Deploy (owner, one time)

1. Vercel → New Project → import `meiki` → project name `mei` → framework **Other**, root `.`, region Seoul (icn1). The
   `vercel.json` here carries the rewrites and the Python function.
2. Cloudflare DNS → CNAME `mei` → the project's `*.vercel-dns-*.com` target, DNS only (the `mt.` recipe).
3. Environment variables (when the API moves to Supabase): `SUPABASE_URL`, `SUPABASE_ANON_KEY`,
   `SUPABASE_SERVICE_ROLE_KEY`, later `MEI_GEMINI_API_KEY`, `RESEND_API_KEY`.
4. Fonts: before any China-facing launch, replace the Google Fonts `<link>` (marked DEV ONLY) with
   self-hosted subsets (plan §8).

## Rules that bite

- Species names are per-language columns joined by the Latin binomial; never map kanji to Chinese.
- The paper is always paper; season colours in five places; gold = signature; red = the seal.
- The plaque is the only square thing. 「推定」 sits next to every age.
- Every export plaque ends with the fixed sentence. Pines are prohibited into mainland China.
- Nothing Google-hosted on a public page (fonts excepted during development).
