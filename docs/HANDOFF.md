# Spell `Meiki` — the hand-off for a session on the owner's Mac (written 2026-10-07)

The owner types **`Meiki`** in a new session. That session has what the cloud session lacked: a browser signed in to
Vercel, Supabase and GitHub, the Vercel CLI, the Supabase CLI, and an open network. Do the open items below **in
order**, under the rules at the end. Report **once at the end**, in plain language for a business manager: what is
live, what you changed, what still needs him — plus one line whenever you need a click or an e-mail from him.

## 0. Cold start (5 min)

- No checkout yet → `cd ~/Documents/GitHub && git clone https://github.com/07yang-creator/meiki.git && cd meiki`; with one → `git pull`.
- Read `CLAUDE.md`, `README.md` (the go-live runbook), this file. The spec is in the Rakusalab repo:
  `docs/MEI_TREE_GALLERY_PLAN.md` (rulings 1–17, §16 status). Clone it only if you need it
  (`git clone https://github.com/07yang-creator/Rakusalab.git`; branch `claude/dazzling-galileo-tzxevs` carries the mei
  migrations and the plan until it is merged).
- State when this was written: `main` = `4d54d78` (繁體 everywhere · 審 desk v0 · 入 intake · the gallery reads
  published trees from the database ahead of the samples · sample photos replaceable via `/?edit=1`).
  Checks: `pytest -q` → 43 pass · `for f in assets/*.js; do node --check "$f"; done`.
- Done by the owner: the `mei` schema migration applied through the SQL editor, its ledger row inserted, `mei` added to
  Exposed schemas. **Not done:** the three Supabase keys on the Vercel project · the supplier's login · the `mei.members` rows.

## 1. Vercel — auto-deploy stopped (the blocker)

Production is still `dfd641a` (Oct 3). The later `main` commits `6e1d0cc`, `21d7488`, `4d54d78` produced **no deployment
at all**, while GitHub's own CI ran on each — so the GitHub → Vercel link broke, not the code.

1. `vercel login` (browser) → in the repo `vercel link` → pick the account/team that owns project **`mei`**.
2. `vercel git connect` — expect "already connected" to `07yang-creator/meiki`, or let it reconnect. In the dashboard,
   Settings → Git must show that repo, Production Branch `main`, and no warning banner. If Vercel's GitHub App lacks the
   repo: github.com → Settings → Applications → Vercel → Configure → add `meiki`.
3. Put the latest `main` live now: on a clean `main`, `vercel --prod` (never from a dirty tree) — or the Deploy Hook the
   owner created (Settings → Git → Deploy Hooks, `main`); a plain GET on its URL triggers a build.
4. Verify: `curl -s https://meiki.rakusalab.com/ | grep -c 關東名園出品` → at least 1 (the old page says 关东名园出品).
5. Confirm the link is healed by the next real push (never an empty commit); the owner's next change is the test.

## 2. Vercel — the three keys

1. `vercel env ls` on `mei` → expect none of `SUPABASE_URL` · `SUPABASE_ANON_KEY` · `SUPABASE_SERVICE_ROLE_KEY`.
2. Source: the Rakusalab project **`monopages`** in the same account. In a temp dir **outside any repo**:
   `vercel link --project monopages` then `vercel env pull .env.monopages --environment production`; read the three
   values; delete the file afterwards.
3. `vercel env add <NAME> production` and `… preview` for each of the three (paste the value when prompted).
4. Redeploy (`vercel --prod` or the hook). Verify: `curl -s 'https://meiki.rakusalab.com/api/mei?action=health'` → `"db": true`.

## 3. People

1. Ask the owner for the supplier's e-mail (and a staff e-mail if he wants one). His own login is his Rakusalab account —
   same Supabase project, nothing to create.
2. Supplier login: Supabase → Authentication → Users → Add user → Create new user → e-mail + password, **Auto Confirm**
   ticked. (A dashboard click: he does it, or you with his dashboard open.)
3. Seat the rows: `scripts/seat_members.sql` with the e-mails filled in → SQL Editor, or after
   `supabase link --project-ref <ref>` (the ref is the subdomain of `SUPABASE_URL`):
   `supabase db query --linked -f scripts/seat_members.sql`.
4. Verify with him in the browser: `/login/` → admin lands on `/desk/`, supplier on `/in/`; `/?edit=1` shows 「替換照片」.

## 4. Optional housekeeping

- `supabase/migrations/20261007120000_mei_species_hant.sql` (Rakusalab repo) sets `zh_hant` for the 32 seeded species:
  SQL Editor + `insert into supabase_migrations.schema_migrations (version, name) values ('20261007120000', 'mei_species_hant');`
  or `supabase db push --linked` from a Rakusalab checkout on that branch.
- Merge Rakusalab branch `claude/dazzling-galileo-tzxevs` into `main` (docs + migrations only; a Rakusalab `main` push
  deploys rakusalab.com, so its suite must be green first even though nothing in the branch touches its code).

## 5. Pending owner decisions — do not act without his word

- **Chinese title font.** The brush face (Ma Shan Zheng) has no glyphs for most Traditional-only characters, so titles
  render mixed brush/serif. Full-coverage candidates, verified against their glyph tables: LXGW WenKai TC · Iansui ·
  Noto Serif TC. Ruling so far: "字體保持不變" (keep the fonts).
- **Sample photos.** Staff replace them one by one via `/?edit=1` (temporary feature; the samples retire later).

## Rules

- Pushing `main` deploys production. Work on a branch, `vercel` for a preview, verify, then merge.
- Secrets never in chat, files or commits. Pull `.env*` only into a temp dir outside the repo; `.env*` is gitignored here anyway.
- Destructive or irreversible actions (deleting deployments, projects, users, tables; rotating keys) → ask first.
  Everything else: do it, report after with a veto handle.
- Every code fix ships with a test; `pytest -q` and `node --check` green before any push.
