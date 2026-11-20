# Phase 2 — Clinic onboarding and knowledge administration

Build tenant onboarding/invitations; clinic profile, branches, timezone, contacts, opening hours, services and FAQs; domain registration/verification; knowledge upload quarantine, parsing, approval, publication and versioning.

Every query must be tenant-scoped and role-authorised. Public content is unavailable until approved/published. Validate uploads by content, type and size; do not trust filename or MIME alone. Prevent HTML/script execution. Use structured facts for opening hours/services where possible.

Acceptance: a synthetic demo clinic can configure and publish content; another tenant cannot view or edit it.
