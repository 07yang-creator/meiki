# CLAUDE.md — 名木 Mei (meiki.rakusalab.com)

Three rules, inherited from Rakusalab: **the code wins** over this file; **this is an index**, the spec is
`docs/MEI_TREE_GALLERY_PLAN.md` in the Rakusalab repo (`07yang-creator/Rakusalab`; this repo is `07yang-creator/meiki`); **keep it alive** — change
the stack, routing, auth or data flow and update this file in the same change.

## Spell `Meiki`
The owner types **`Meiki`** in a new session (usually on his Mac: Vercel CLI, Supabase CLI, a signed-in browser). Read
`docs/HANDOFF.md` and run it top to bottom — it holds the state, the open items in order, and the rules. Report once at the end.

## Stack
Static HTML + vanilla JS + CSS, Python serverless (`api/mei.py`) on Vercel. **Not Next.js.** No build step.
Supabase (shared project, own schema `mei`; migrations live in the Rakusalab repo under `supabase/migrations/*_mei_*`).
Fonts: Google Fonts only during development (links marked DEV ONLY); production self-hosts subsets.
Nothing Google-hosted on a public page: the audience is in mainland China.

## Pages
`/` four-season home (`?species=` · `?sold=1` · `?edit=1` staff photo replace) · `/t/<slug>` tree page (rewrite →
`t/index.html?slug=`) · `/journey/` 木の旅 · `/legal/` · `/login/` (routes by role) · `/in/` supplier (JA) · `/desk/` staff
(ZH) · later `/find/` 尋木委託.

## Data rules
- `data/species.json` is the registry seed: Latin binomial = the join key; ZH/JA/EN are separate human-typed
  columns; `best_season`, `rank`, `trade.CN.status`, `knowledge`. Never derive one language from another.
- `data/trees.json` is SAMPLE data for the preview. Real trees arrive through the intake app and Supabase.
- Public reads strip `garden_id`, `plot_ref`, `internal_*`, `supplier_notes_ja`, and the staff trade note.
- Provenance is the constant 關東名園出品 / 関東の名園出品 / From a distinguished Kantō garden.
- **Chinese is Traditional (繁體) everywhere** (ruling 17, 2026-10-07; `lang="zh-Hant"`). Write new strings in 繁體;
  `scripts/to_hant.py` converts anything that arrives Simplified without touching Japanese. `species.zh` is 繁體,
  `species.zhs` keeps the Simplified name. Typefaces unchanged by the owner's call.

## Auth (when writes arrive)
Every write re-validates a Supabase JWT against `/auth/v1/user` on the server; roles from `mei.members`;
client checks are cosmetic; RLS on; redirect happens in one place; gate in place for guests.

## Tests
`pytest -q` runs `tests/` (43: the intake + desk API on `tests/fake_supabase.py`; data locks: Latin unique, no Japanese
glyphs and no Simplified characters in ZH names, pines prohibited, every published tree has its 見頃 hero, no named garden
or price words in public texts, the API strips private fields; page locks: `zh-Hant`, no Google assets, the seal reads
名木, the member entrance). Every fix ships with a test. `node --check` on every `assets/*.js`.
