# Architecture Decision Log

| ID | Decision | Status |
|---|---|---|
| ADR-001 | Engage separate repository from existing ZUVOORA | Accepted |
| ADR-002 | Dedicated Supabase project initially | Proposed; approve after setup/RLS review |
| ADR-003 | Widget isolation: prototype iframe first | Proposed |
| ADR-004 | Persistent worker/queue | Required; choose in Phase 4 |
| ADR-005 | Common scheduling interface for Cal.com and Calendly | Accepted; sequence after provider validation |
| ADR-006 | Resend initial email adapter; keep Brevo option | Accepted |
| ADR-007 | OpenRouter server-side model gateway | Accepted; model must pass evaluation |
| ADR-008 | Three commercial layers | Accepted |
| ADR-009 | Reusable modules first; custom enterprise separately priced | Accepted |
| ADR-010 | Docker Compose before Kubernetes | Proposed; reassess on evidence |
| ADR-011 | Web dashboard on Next.js 16 (was 15) | Accepted (Phase 0, 2026-11-20) |
| ADR-012 | Keep `apps/api` (backend) + `apps/web` (frontend) monorepo layout | Accepted (Phase 0, 2026-11-20) |
| ADR-013 | Python 3.12 for API (local venv, Docker, CI) | Accepted (Phase 0, 2026-11-20) |
| ADR-014 | Web container receives only browser-safe config, never the shared `.env` | Accepted (Phase 0, 2026-11-20) |
| ADR-015 | Node.js 24 LTS for web, widget, CI and Docker (was 22) | Accepted (Phase 0, 2026-11-20) |

### ADR-011 — Next.js 16
- **Context:** `eslint.config.mjs` used the Next 16 flat-config entry points, so lint failed on Next 15; Next 15 also pulled a high-severity `postcss` advisory (npm's only fix was Next 16.4.6); the webpack build failed on the exFAT SSD (`EISDIR readlink`).
- **Alternatives:** stay on 15 with FlatCompat + `postcss` override + webpack `symlinks: false` workaround.
- **Decision:** upgrade to `next@^16.4.6`, `eslint-config-next@^16.4.6`, React 19.2+, while the dashboard is still a shell.
- **Consequences:** lint/typecheck/build pass; audit clean; Turbopack is the default builder. Next added `.next/dev/types` to `tsconfig.json` and set `jsx: react-jsx` automatically.

### ADR-012 — Repository layout
- **Context:** founder asked whether to use `backend/` and `frontend/` folders.
- **Decision:** keep `apps/api` (backend), `apps/web` (frontend), `apps/widget`, `apps/worker` — already a backend/frontend split, matching the blueprint docs, CI and prompts.

### ADR-013 — Python 3.12
- **Context:** founder initially preferred 3.11; tests pass on 3.11 but `pyproject.toml`, Dockerfile and CI target 3.12.
- **Decision:** use 3.12 everywhere so local, CI and production match.

### ADR-014 — No shared secrets in the web container
- **Context:** Compose loaded the full `.env` (service-role, OpenRouter, Resend, OAuth secrets) into the web service.
- **Decision:** web gets only explicit `NEXT_PUBLIC_*` build args and non-secret runtime values; the API alone loads `.env`.

### ADR-015 — Node.js 24 LTS
- **Context:** starter targeted Node 22 (older LTS); founder's machine runs Node 24.18.0. Node 24 is a supported LTS line with a longer support window than 22.
- **Decision:** standardise on Node 24. Root `.nvmrc` is the single source for local version managers and CI (`node-version-file`); Docker uses `node:24-alpine`; `engines.node` is `>=24 <25`.
- **Consequences:** local, CI and container runtimes match. Revisit when the next LTS line is adopted; bump `.nvmrc`, Dockerfile tag and `engines` together.

Record context, alternatives, decision and consequences for every major architecture change.
