# Phase 0 — Environment and repository validation

1. Confirm repository root and folder spelling.
2. Inspect Git status; initialise Git only if not already initialised and founder approves.
3. Confirm remote points to the new private Engage repository; never overwrite an existing remote.
4. Verify Python 3.12, Node 24 LTS/npm, Git, Docker Desktop and Claude Code.
5. Inspect `.gitignore`; confirm `.env`, `.venv`, `node_modules`, `.next`, uploads and logs are ignored.
6. Check for tracked secrets/patient data; report filenames only, never secret values.
7. Install API dependencies, run pytest and Ruff.
8. Install web dependencies, run lint, typecheck and build.
9. Validate `docker compose config`; do not start or deploy without approval.
10. Update `docs/operations/IMPLEMENTATION.md` only with verified results.

Acceptance: root path and Git remote confirmed; no secrets/patient data tracked; API tests and web checks pass; Compose parses; results recorded. No live provider accounts or real clinic data in Phase 0.
