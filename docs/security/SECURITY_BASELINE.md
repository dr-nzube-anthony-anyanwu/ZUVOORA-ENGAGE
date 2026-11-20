# Security Baseline

Security is a release requirement, not a final polish task. This is a practical baseline, not a certification or guarantee.

## Controls
1. Separate repository and dedicated Engage Supabase project.
2. Server-side authorisation and least privilege.
3. RLS on every tenant-owned table.
4. Automated cross-tenant negative tests.
5. Secrets in environment/secret manager only.
6. MFA for platform administrators.
7. Domain validation and rate limiting for widget endpoints.
8. Strict schemas, safe rendering and upload quarantine.
9. AI prompt-injection and tool-abuse controls.
10. Persistent idempotent jobs and verified webhooks.
11. Audit events for privileged actions.
12. Backups, restore drills, monitoring and incident response.

## Tenant isolation tests
- Anonymous user cannot query private tables.
- Tenant A cannot access Tenant B records by changing tenant ID or guessing UUID.
- Tenant A RAG cannot retrieve Tenant B chunks.
- Tenant A cannot access Tenant B storage files or conversations.
- Worker rejects mismatched tenant/appointment jobs.
- Revoked membership and suspended tenant lose access.

## AI safety
Administrative assistant only. No diagnosis, prescription, treatment plan or false reassurance. Unknown clinic facts are not invented. Retrieved documents and user messages are untrusted. No arbitrary SQL, shell, unrestricted URL or database tools.

## CI security gates
Ruff, pytest, ESLint, type checks, Gitleaks, Semgrep, dependency audit, Trivy, RLS negative tests, OWASP ZAP on staging and AI adversarial evaluation.

## Privacy and incidents
Map controller/processor roles, subprocessors, retention, data requests and cross-border processing. Review Nigeria Data Protection Act 2023 and NDPC guidance with qualified counsel; assess destination-market laws before expansion. For suspected exposure, contain, preserve evidence, assess affected data, engage privacy/legal lead, follow applicable notification obligations and independently retest.
