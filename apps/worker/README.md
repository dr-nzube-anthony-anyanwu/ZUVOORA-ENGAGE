# Background worker

Not implemented in Phase 0. Phase 4 adds a persistent queue consumer for verified webhooks,
booking notifications and reminders. Do not use in-memory timers or process-local task lists.
Jobs must be durable, idempotent, retryable, observable and re-check appointment status.
