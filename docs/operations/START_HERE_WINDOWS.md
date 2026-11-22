# Start Here — Windows 10 + Transcend SSD + VS Code + Claude Code

> **Already set up? To run the system day to day** (database, API, website/dashboard, worker —
> start and stop), follow **[Local Development → Quick start](LOCAL_DEVELOPMENT.md#quick-start--every-day-after-the-first-time-setup-below)**.
> This page records the original Phase 0 machine and repository setup.

## 1. Extract and move
Your intended structure is:

```text
D:\
  Technologies\
    ZUVOORA\
    ZUVOORA-ENGAGE\
```

The drive letter may change when the SSD is reconnected. Confirm it in File Explorer. Extract the ZIP, move the `ZUVOORA-ENGAGE` folder into `Technologies`, and leave the existing `ZUVOORA` folder untouched. Rename the old empty Engage folder to `ZUVOORA-ENGAGE-old` temporarily; do not delete until the new folder is verified and backed up.

Open the new folder in VS Code using File → Open Folder.

## 2. Check tools
In PowerShell:

```powershell
python --version
py -0p
node --version
npm --version
git --version
docker --version
claude --version
```

Use Python 3.12.x and Node 24.x LTS (pinned in `.nvmrc`). Docker Desktop compatibility depends on Windows edition/build and WSL 2; check current vendor requirements before installing.

## 3. Verify root and Git
```powershell
Get-Location
Get-ChildItem
git status
```
If Git reports "dubious ownership", the SSD is exFAT (which does not record file owners). Trust only this folder:

```powershell
git config --global --add safe.directory D:/technologies/ZUVOORA-ENGAGE
```

If this is not already a repository, confirm the current directory is the new Engage folder before running `git init`. Create a new private GitHub repository; do not reuse the existing ZUVOORA remote.

```powershell
git init
git branch -M main
git remote add origin YOUR_PRIVATE_REPOSITORY_URL
git remote -v
```
Only run the remote commands after replacing the placeholder with the exact URL from GitHub and confirming the repository is correct.

## 4. API setup
Before the API can work it needs the local database and its settings file — from the repository
root run `npm ci`, `npm run db:start` and `npm run env:local` (see `LOCAL_DEVELOPMENT.md`).
```powershell
cd apps\api
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
pytest
ruff check .
uvicorn app.main:app --reload --host 127.0.0.1 --port 8073
```
If activation is blocked, for this terminal only:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```
Health endpoint: `http://127.0.0.1:8073/health/live` (expected `{"status":"ok"}`). Stop with Ctrl+C.

## 5. Web setup
In another terminal:
```powershell
cd apps\web
npm install
npm run lint
npm run typecheck
npm run build
npm run dev
```
Open `http://localhost:3073`.

## 6. Accounts — create only when phase is ready
- GitHub: private repository and Actions (Phase 0).
- Supabase: a **new dedicated Engage project**, not the existing ZUVOORA project (Phase 1).
- OpenRouter: server-side API key, spend limit/alerts and model evaluation (Phase 3).
- Resend: sending-domain verification, SPF/DKIM/DMARC and transactional key (Phase 4).
- Cal.com and Calendly: test accounts; verify current APIs, webhooks, OAuth scopes, rate limits and plan requirements before promises (Phase 4).
- Domain/DNS and monitoring: when staging/production deployment is planned.

Vendor features and pricing change; verify current provider docs at implementation time.

## 7. Secrets
Copy `.env.example` to `.env` only when needed:
```powershell
Copy-Item .env.example .env
```
Never paste real keys into chat, prompts, source files or Git. Never expose service-role keys in browser code.

Check ignores:
```powershell
git check-ignore .env
git check-ignore apps\api\.venv
git check-ignore apps\web\node_modules
```

## 8. First commit
```powershell
git status --short
git add .
git status --short
git commit -m "chore: establish ZUVOORA Engage starter workspace"
git push -u origin main
```
Only push after verifying the remote is the new private Engage repository and no secrets/patient data are staged.

## 9. Claude Code
From the repository root:
```powershell
claude
```
Ask Claude to read `CLAUDE.md`, `prompts/MASTER_BUILDER_PROMPT.md` and `prompts/phases/PHASE_0_ENVIRONMENT.md`, inspect only, and report findings. Do not approve broad edits before review.

## 10. SSD backup
Keep the SSD connected during development. Consider assigning a stable drive letter. Never unplug during Docker/database writes. Keep an encrypted backup elsewhere; the SSD and GitHub alone are not a complete backup of all local work.
