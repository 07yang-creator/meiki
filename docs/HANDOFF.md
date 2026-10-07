# Spell `Meiki` — the hand-off for a session on the owner's Mac (rewritten 2026-10-07, after the first Mac session)

The owner types **`Meiki`** in a new session. That session has a browser signed in to Vercel, Supabase and GitHub, the
Vercel CLI, the Supabase CLI, and an open network. Do the open items below **in order**, under the rules at the end.
Report **once at the end**, in plain language for a business manager: what is live, what you changed, what still needs
him — plus one line whenever you need a click or an e-mail from him.

## 0. Cold start (3 min)

- The checkout is `~/Documents/GitHub/meiki` (`git pull`; if it is missing: `cd ~/Documents/GitHub && git clone
  https://github.com/07yang-creator/meiki.git`). Its local git identity is `Yano <07.yang@gmail.com>` — keep it (see §1).
- Read `CLAUDE.md`, `README.md` (the go-live runbook), this file. The spec is in the Rakusalab repo:
  `docs/MEI_TREE_GALLERY_PLAN.md` (rulings 1–17, §16 status); branch `claude/dazzling-galileo-tzxevs` carries the mei
  schema migration and the plan until it is merged.
- State when this was written: production = the latest `main` (繁體 everywhere · TC typefaces · 審 desk v0 · 入 intake ·
  the gallery reads published trees from the database ahead of the samples · sample photos replaceable via `/?edit=1`).
  Checks: `pytest -q` → 45 pass · `for f in assets/*.js; do node --check "$f"; done`.
- Done: the `mei` schema migration (SQL editor, ledger row, Exposed schemas) · the GitHub → Vercel link works again ·
  `SUPABASE_URL` / `SUPABASE_ANON_KEY` / `SUPABASE_SERVICE_ROLE_KEY` are on the Vercel project for Production and Preview.
  **Not done:** the supplier's login · the `mei.members` rows (§3).

## 1. Vercel — healed; the one rule

The link was never broken. Vercel creates a deployment for every push to `main` and then **cancels it with no build when
the commit's author *name* is `07yang-creator`** (the global git identity on the Mac and the cloud's override). Commits
authored `Yano <07.yang@gmail.com>` or `claude` build in about 10 seconds — the same pattern on Rakusalab. The checkout
sets `user.name Yano` locally; a session anywhere else must do the same before pushing. The Deploy Hook (Settings → Git →
Deploy Hooks, `main`) is still there if a redeploy without a commit is ever needed.

Verify after any push: `curl -s https://meiki.rakusalab.com/ | grep -c 關東名園出品` → at least 1, and the deployment list
(`vercel ls meiki`) shows **Ready**, not Canceled.

## 2. Vercel — the three keys (done; how, for next time)

Production and Preview have them. The Rakusalab project's values are marked *Sensitive* on Vercel, so `vercel env pull`
returns them empty; the working source is the Supabase CLI: `supabase projects api-keys --project-ref iagbrhyqatsccwdlxoww -o json`
(`anon` → `SUPABASE_ANON_KEY`, `service_role` → `SUPABASE_SERVICE_ROLE_KEY`; the URL is `https://iagbrhyqatsccwdlxoww.supabase.co`).
Pipe each value into `vercel env add <NAME> production` (stdin, never pasted into chat); the CLI refuses stdin for Preview
without a prompt, so widen the variable's targets instead: `PATCH /v9/projects/<id>/env/<envId>` with
`{"target":["production","preview"]}` — no value handling at all. Run the Supabase CLI from a scratch folder: inside the
repo it drops `supabase/.temp/` (gitignored now). Health: `curl -s 'https://meiki.rakusalab.com/api/mei?action=health'` → `"db": true`.

## 3. People

1. Ask the owner for the supplier's e-mail (and a staff e-mail if he wants one). His own login is his Rakusalab account —
   same Supabase project, nothing to create.
2. Supplier login: Supabase → Authentication → Users → Add user → Create new user → e-mail + password, **Auto Confirm**
   ticked. (A dashboard click: he does it, or you with his dashboard open.)
3. Seat the rows: `scripts/seat_members.sql` with the e-mails filled in → SQL Editor, or after
   `supabase link --project-ref iagbrhyqatsccwdlxoww` (do that in a scratch folder, never inside the Rakusalab checkout):
   `supabase db query --linked -f scripts/seat_members.sql`.
4. Verify with him in the browser: `/login/` → admin lands on `/desk/`, supplier on `/in/`; `/?edit=1` shows 「替換照片」.

## 4. Optional housekeeping

- The species `zh_hant` seed (`supabase/migrations/20261007120000_mei_species_hant.sql`) is **not** on the Rakusalab
  branch `claude/dazzling-galileo-tzxevs` — only `20261003120000_mei_schema.sql` is. Either the cloud session still holds
  it unpushed, or write it from `data/species.json` (`zh` per Latin binomial) and apply it through the SQL editor plus the
  ledger row `insert into supabase_migrations.schema_migrations (version, name) values ('20261007120000', 'mei_species_hant');`.
- Merge Rakusalab branch `claude/dazzling-galileo-tzxevs` into `main` (docs + migrations only; a Rakusalab `main` push
  deploys rakusalab.com, so its suite must be green first even though nothing in the branch touches its code).
- Before any China-facing launch: self-host the font subsets and drop the Google Fonts `<link>` (plan §8).

## 5. Pending owner decisions — do not act without his word

- **Sample photos.** Staff replace them one by one via `/?edit=1` (temporary feature; the samples retire later).
- (Decided 2026-10-07, 消除字體不一致: Chinese titles are LXGW WenKai TC, the serif Noto Serif TC; the brush keeps only the
  名木 wordmark and the season kanji. Veto handle: switching the wordmark to the same 楷 is one CSS line, `--f-brush`.)

## Rules

- Pushing `main` deploys production. Work on a branch, verify, then merge. Vercel preview URLs sit behind Vercel
  Authentication, so a non-signed-in browser cannot open them: verify on a local static server
  (`python3 -m http.server 4174 --directory ~/Documents/GitHub/meiki`; `/t/?slug=<id>` stands in for `/t/<id>`).
- Secrets never in chat, files or commits. Pull `.env*` only into a temp dir outside the repo; `.env*` is gitignored here anyway.
- Destructive or irreversible actions (deleting deployments, projects, users, tables; rotating keys) → ask first.
  Everything else: do it, report after with a veto handle.
- Every code fix ships with a test; `pytest -q` and `node --check` green before any push.
