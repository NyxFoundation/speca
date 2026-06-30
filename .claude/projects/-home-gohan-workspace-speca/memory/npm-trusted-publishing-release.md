---
name: npm-trusted-publishing-release
description: How speca-cli releases publish to npm (OIDC trusted publishing) and the gotchas that cause ENEEDAUTH/404
metadata:
  type: project
---

`speca-cli` (the `cli/` npm package) releases are tag-driven: pushing a `v*.*.*` tag runs `.github/workflows/release.yml`, which builds → tests → `npm publish` → creates a GitHub Release using `cli/RELEASE_NOTES_<tag>.md`.

As of v0.9.2 (2026-06-16) publishing uses **npm Trusted Publishing (OIDC), not NPM_TOKEN**. Hard-won requirements — all must hold or `npm publish` fails with a *misleading* `ENEEDAUTH`/`E404` (see npm/cli#9088):

- **npm CLI ≥ 11.5.1.** Node 22's bundled npm is 10.x and does NOT support OIDC. The workflow runs `npm install -g npm@latest` then `hash -r` before publishing.
- **No auth token / no `_authToken` in any `.npmrc`.** Do NOT set `registry-url` on `actions/setup-node` — it writes an `.npmrc` with `always-auth=true` + an empty `_authToken`, which makes npm auth with an empty token and skips OIDC. Default registry is npmjs.org anyway, so `npm ci` still works.
- **`permissions: id-token: write`** at workflow (or job) level.
- **The npmjs.com trusted-publisher config (package → Settings → access) must EXACTLY match** the workflow: org `NyxFoundation`, repo `speca`, workflow filename `release.yml` (filename only, with extension, case-sensitive), and **Environment left BLANK** (the `release` job sets no `environment:`). A stale Environment value was the actual blocker for v0.9.2 and surfaced only as `ENEEDAUTH`.

Package 2FA setting "Require 2FA and disallow tokens (recommended)" is compatible — trusted publishing is exempt from the token ban.

Branch protection on `main` requires a review; the maintainer authorized `gh pr merge --admin` to bypass during releases. Moving/re-pushing the release tag is safe as long as nothing is published yet (npm version absent + no GitHub Release).

Multi-runtime runners (codex/gemini/ollama/copilot) live in `scripts/orchestrator/` + `web/`, NOT this npm package — intentionally out of scope for CLI releases. See [[speca-cli-release-scope]].
