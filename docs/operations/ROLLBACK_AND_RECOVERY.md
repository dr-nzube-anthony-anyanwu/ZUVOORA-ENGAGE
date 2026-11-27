# Rollback, Backups and Recovery

Part of [PHASE6_DEPLOYMENT_PLAN.md](PHASE6_DEPLOYMENT_PLAN.md) (stages 6G and 6I).

**Status: rollback scripts built in 6A (2026-11-25; `deploy.sh` also rolls back automatically when a health check fails); backups are built in 6G.** No
backup or restore drill has been carried out yet. Do not rely on this document until the drill in
§4 has been run and recorded in `IMPLEMENTATION.md`.

## 1. Targets for the pilot (to be confirmed by the founder)

| Measure | Target | How |
|---|---|---|
| RPO (data that may be lost) | ≤ 24 hours; minutes if point-in-time recovery is bought | Supabase daily backups plus our nightly encrypted dump |
| RTO (time to be working again) | ≤ 4 hours | Scripted redeploy and a practised restore |
| Code rollback | ≤ 10 minutes | Previous image digests kept on the server |

## 2. Rolling back a release

### Code only (no database change, or a backward-compatible one)

```bash
cd /opt/zuvoora-engage/app
sudo deploy/scripts/rollback.sh production      # swaps release.env with release.env.previous
```

Then run the smoke tests, note the event in `releases.log`, and tell the founder.

### A migration caused the problem

Migrations are written to be backward compatible (see `PRODUCTION_DEPLOYMENT.md` §1), so in most
cases rolling back the **code** is enough while a fix is prepared.

**Never** edit or delete an applied migration. Fix forward with a new migration, tested on staging
first.

Restoring the database to an earlier time is the last resort, because it loses everything written
since that time. Only the founder decides it (§3).

### A bad configuration value

Fix `/opt/zuvoora-engage/<env>/.env` and run `sudo deploy/scripts/deploy.sh <env> --current`. To switch AI off
quickly, set `AI_ENABLED=false` and `AI_VISION_ENABLED=false` and redeploy. Answers fall back to
the facts-first responder.

### The proxy or DNS is broken

- Validate before reloading: `caddy validate`, or `nginx -t`.
- Restore the previous proxy config file (kept as `*.bak-<date>`) and reload.
- At Cloudflare, revert the record. Changes take effect within minutes.

## 3. Backups

| What | How | Where | Kept |
|---|---|---|---|
| Production database | Supabase daily backup. **Not available on the Free plan the founder chose for now (D2).** Our own copy below is the only backup until the upgrade. | Supabase | 7 days (Pro only) |
| Production database (independent copy) | Nightly `backup.sh`: `pg_dump` custom format, then `age` encryption with the **public** backup key | Off-site bucket (B2 or R2), write-only key, versioning or object lock | 30 days |
| Stored documents (Storage bucket) | Nightly copy with the same encryption | Same bucket | 30 days |
| Encryption keys and secrets | Password manager, plus an offline copy of the **backup private key** and `INTEGRATIONS_ENCRYPTION_KEY` | Founder | Always |
| Server configuration | Git (`deploy/`); env files only in the password manager | — | — |

Backups are encrypted to the public key(s) in `deploy/backup/age-recipients.txt` (created
2026-11-27). The private key never touches the server or the repository.

### Rules

- The server can **write** backups but cannot **read or delete** them. Only the founder's offline
  private key can decrypt a backup.
- A backup that has never been restored is not trusted. Run the restore check monthly, and after
  every major migration.
- Staging is not backed up; it holds synthetic data only.
- An alert fires when a nightly backup is missing or smaller than 50% of the previous one.

## 4. Restore drill (stage 6G, then monthly)

Use a **scratch** target only, never production: a temporary Supabase project or the local stack.

1. Download the latest backup to the laptop.
2. Decrypt it: `age -d -i <private key file> backup.dump.age > backup.dump`.
3. Restore it into the scratch database with `pg_restore --no-owner`, following the restore
   script's notes for Supabase-managed schemas.
4. Run `npx supabase test db` against the scratch database, plus the API smoke tests.
5. Spot-check:
   - the clinic count matches;
   - the latest audit event time is close to the backup time;
   - a stored document opens.
6. Record the start and end times, the size and any problems in `IMPLEMENTATION.md`.
7. Delete the scratch project and the decrypted file.

## 5. Disaster scenarios

| Scenario | First steps |
|---|---|
| **VPS lost or unbootable** | Order or restore a VPS (snapshot if available). Run [CONTABO_VPS_SETUP.md](CONTABO_VPS_SETUP.md) §3, recreate the env files from the password manager, run `deploy.sh` with the last release, and point DNS to the new IP. The data is safe in Supabase. |
| **Supabase outage** | The API reports `/health/ready` 503 and the widget shows "chat not available". Wait, and follow Supabase status. Do not fail over to another database without the founder. |
| **Data corrupted by a bug** | Stop writes: put the affected clinic on hold (suspend), or stop the `api` and `worker` containers. Assess with the founder. Restore the affected rows from a backup into a scratch database and copy them back with a reviewed script; otherwise do a point-in-time restore. |
| **Leaked secret** | Rotate it immediately (`PRODUCTION_DEPLOYMENT.md` §5) and check provider logs for misuse. If patient data may be affected, start the incident procedure (§6). |
| **AI cost spike** | The budgets stop calls automatically. Also set `AI_ENABLED=false` and check the OpenRouter activity page. The key's own credit limit is the hard stop. |
| **Disk full** | Run `sudo docker system df`, prune old Engage images (`PRODUCTION_DEPLOYMENT.md` §4) and check the log caps. Never delete ZUVOORA's data. |

## 6. Suspected data breach — first hour

1. **Contain.** Revoke the exposed keys, suspend affected accounts or clinics, and block the
   source at Cloudflare.
2. **Preserve evidence.** Keep the logs (`docker compose logs > file`), the audit events and the
   provider logs. Do not wipe anything.
3. **Assess.** Which clinics and which data were involved, and when.
4. **Inform the founder and the legal or privacy lead.** Follow the notification duties in the
   reviewed incident runbook (Nigeria Data Protection Act 2023 and the NDPC rules, and the
   clinics' DPAs).
5. Fix, independently retest, and write a post-incident report.
