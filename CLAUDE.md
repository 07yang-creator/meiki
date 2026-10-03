# CLAUDE.md — 名木 Mei (meiki.rakusalab.com)

Three rules, inherited from Rakusalab: **the code wins** over this file; **this is an index**, the spec is
`docs/MEI_TREE_GALLERY_PLAN.md` in the Rakusalab repo (`07yang-creator/Rakusalab`; this repo is `07yang-creator/meiki`); **keep it alive** — change
the stack, routing, auth or data flow and update this file in the same change.

## Stack
Static HTML + vanilla JS + CSS, Python serverless (`api/mei.py`) on Vercel. **Not Next.js.** No build step.
Supabase (shared project, own schema `mei`; migrations live in the Rakusalab repo under `supabase/migrations/*_mei_*`).
Fonts: Google Fonts only during development (links marked DEV ONLY); production self-hosts subsets.
Nothing Google-hosted on a public page: the audience is in mainland China.

## Pages
`/` four-season home · `/t/<slug>` tree page (rewrite → `t/index.html?slug=`) · `/journey/` 木の旅 ·
`/legal/` · later `/find/` 寻木委托, `/in/` supplier (JA), `/desk/` staff (ZH), `/login/`.

## Data rules
- `data/species.json` is the registry seed: Latin binomial = the join key; ZH/JA/EN are separate human-typed
  columns; `best_season`, `rank`, `trade.CN.status`, `knowledge`. Never derive one language from another.
- `data/trees.json` is SAMPLE data for the preview. Real trees arrive through the intake app and Supabase.
- Public reads strip `garden_id`, `plot_ref`, `internal_*`, `supplier_notes_ja`, and the staff trade note.
- Provenance is the constant 关东名园出品 / 関東の名園出品 / From a distinguished Kantō garden.

## Auth (when writes arrive)
Every write re-validates a Supabase JWT against `/auth/v1/user` on the server; roles from `mei.members`;
client checks are cosmetic; RLS on; redirect happens in one place; gate in place for guests.

## Tests
`pytest -q` runs `tests/` (data locks: Latin unique, no Japanese glyphs in ZH names, pines prohibited, every
published tree has its 見頃 hero, no garden or price words in public texts, the API strips private fields;
page locks: language tags, no Google assets, the seal reads 名木). Every fix ships with a test.
