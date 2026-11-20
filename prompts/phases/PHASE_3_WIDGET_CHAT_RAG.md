# Phase 3 — Widget, conversations, AI gateway and RAG

Build isolated embeddable widget, active tenant/domain validation, rate-limited public sessions, conversation lifecycle, human handover, server-side OpenRouter gateway, tenant-scoped retrieval over approved knowledge, usage metering and AI evaluations.

AI is administrative only. Unknown facts are not invented. User and retrieved text are untrusted. No system prompt/secret/other-tenant disclosure. No arbitrary SQL, shell or network tools.

Acceptance: widget works only on verified test domain; RAG isolation and prompt-injection tests pass; safe fallback and handover work; quality evaluation meets an agreed threshold.
