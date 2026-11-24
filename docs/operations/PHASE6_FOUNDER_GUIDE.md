# Phase 6 — The Founder's Step-by-Step Guide

This guide is for **you, the founder**. It lists the jobs only you can do, such as creating
accounts, paying for plans, clicking buttons in provider dashboards and typing secrets onto the
server. It explains every step as simply as possible.

Claude does the code, the configuration files and the checks. You do the things that need your
accounts, your money or your secrets.

> **The big picture.** Right now ZUVOORA Engage only runs on your laptop. In Phase 6 we put it on
> your Contabo server so clinics can use it on the internet, safely. We build a **practice copy**
> first ("staging"), test it, and only then build the **real copy** ("production") for the three
> pilot clinics.

---

## Part 0 — Golden rules (read these first)

1. **Never paste a secret into the chat with Claude.** Not in ChatGPT, not in an email, not in a
   screenshot. A secret is any password, API key, private key or the contents of a `.env` file.
   Claude will never ask you for one.
2. **Keep every secret in a password manager.** Part 1 shows you how.
3. **Turn on two-factor login (2FA) everywhere.** That means a code from an app on your phone as
   well as your password.
4. **Never delete or stop anything on the server that you did not create**, especially the main
   ZUVOORA application.
5. **"STOP" means stop.** When you see 🛑, do not go further until Claude has checked your results
   and you have both agreed.
6. If something looks scary or different from this guide, **stop and ask**. Asking is free;
   fixing a broken server is not.

**How to "redact" (hide) private details before sharing output with Claude:** open the text in
Notepad. Wherever you see your server's IP address (four numbers with dots, like
`123.45.67.89`), replace it with `[REDACTED]`. Do the same for any password or key. Usually there
are none, because the commands in this guide never print them.

---

## Part 1 — Get ready (about 30 minutes) — do now

### Step 1.1 — Install a password manager
1. Go to **bitwarden.com** and create a free account. Choose a long master password you can
   remember, and write it on paper kept somewhere safe at home.
2. Install the Bitwarden app on your phone and the browser extension on your laptop.
3. Create a folder called **ZUVOORA Engage**. Every secret from now on goes in that folder.

✅ **Done when:** you can open Bitwarden and see the "ZUVOORA Engage" folder.

### Step 1.2 — Turn on 2FA on every account
Install an authenticator app on your phone, such as Google Authenticator, Microsoft
Authenticator or 2FAS. Then turn on two-factor login in:

- [ ] GitHub (Settings → Password and authentication)
- [ ] Cloudflare (My Profile → Authentication)
- [ ] Contabo (Customer Control Panel → Account → Security / 2FA)
- [ ] Supabase (Account → Security)
- [ ] OpenRouter, Resend, Cal.com and Calendly, when you open them later

Save each account's **recovery codes** in Bitwarden.

✅ **Done when:** every box above is ticked.

---

## Part 2 — Look at your server, without changing anything (about 20 minutes) — do now

### Step 2.1 — Find your server's details in Contabo
1. Log in at **my.contabo.com**.
2. Click **Your services** and find the Cloud VPS.
3. Write down, in Bitwarden as a note (not in the chat):
   - the **IP address**;
   - the **login username**, often `root`;
   - the **region or location**, for example "European Union (Germany)".
4. Write down for Claude (these are safe to share): the **plan name**, **CPU cores**, **RAM**,
   **disk size**, **region**, and whether you see a **Snapshots** option.

✅ **Already done (2026-11-24):** Cloud VPS 6, 6 cores, 12 GB RAM, 200 GB disk, EU region, user
`root`, VNC console enabled, and a Snapshots tab is present. Keep the IP address in Bitwarden.
Avoid posting screenshots of the Contabo page in public places, because they show the IP and the
VNC address.

### Step 2.2 — Connect to the server
1. On your laptop press the **Windows key**, type **PowerShell** and open it.
2. Type the following, replacing the two words in CAPITALS, then press Enter:
   ```powershell
   ssh YOUR_USERNAME@YOUR_VPS_IP
   ```
3. The first time, it asks *"Are you sure you want to continue connecting?"* Type `yes` and press
   Enter.
4. Enter the **server** password (see "Which password?" below). Copy it from Bitwarden, then
   **right-click once** in the PowerShell window to paste it. In Windows Terminal, **Ctrl+V** also
   works. **Nothing appears**: no dots, no stars, and the cursor does not move. That is normal.
   Press **Enter** once.
5. You are in when the line ends with something like `root@vmi12345:~#`.

#### Which password? (the most common confusion)
There are **three different passwords**, and PowerShell only accepts one of them:

| Password | Used for | Works in PowerShell? |
|---|---|---|
| Contabo **account** password | Logging in to the my.contabo.com website | ❌ No |
| **Server (root)** password | Logging in to the server itself with `ssh root@...` | ✅ **Yes, this one** |
| **VNC** password | The emergency console on the Contabo website | ❌ No |

**Where to find the server password:**
- **You chose it when you ordered the VPS.** During checkout Contabo asks for a password for the
  server (the "root password" or "Login data"). Look in Bitwarden or your notes.
- **Check your email.** Contabo sends a message such as "Your login data" with the IP address and
  the user name (`root`).

**If you cannot find it, set a new one:**
1. Log in at **my.contabo.com** → **VPS** → click your server.
2. Click the **three dots (⋮)** at the top right of the server box, next to the power and refresh
   icons.
3. Choose **Reset credentials**. A panel opens with two tabs, **Password** and **SSH-Key**. Stay
   on **Password**.
4. Click the box **"Select or create new password"** → choose **Create new password**
   (Contabo calls it a "secret"):
   - **Name:** for example `engage-vps-root`
   - **Password:** let Bitwarden generate one, about 20 characters, letters and numbers. If
     Contabo insists on a symbol, add only `!` or `@` or `#`. Avoid `" ' \ $ % ^`, which can paste
     wrongly in PowerShell.
   - **Save it in Bitwarden first**, then save it in Contabo.
5. Make sure the new password is selected in the box, then click **Reset credentials**.
6. Wait a few minutes before logging in again. Contabo may restart the server to
   apply it. If another application (for example the main ZUVOORA app) already runs on this
   server, tell Claude **before** resetting, because a restart briefly interrupts it.

#### If the password still fails: log in with an SSH key instead (recommended anyway)
An SSH key replaces the server password. Stage 6B switches to keys in any case.
1. **On your laptop**, in PowerShell, check whether you already have a key:
   `Test-Path $HOME\.ssh\id_ed25519.pub`. If it says `False`, create one:
   ```powershell
   ssh-keygen -t ed25519 -C "engage-admin-laptop"
   ```
   - Press **Enter** to accept the default location.
   - Type a **passphrase** twice (save it in Bitwarden first). It is not shown while you type.
2. Show the **public** key and copy the whole line, which starts with `ssh-ed25519`:
   ```powershell
   Get-Content $HOME\.ssh\id_ed25519.pub
   ```
   Only the `.pub` file is safe to share. Never copy or upload `id_ed25519` (without `.pub`).
3. In Contabo: VPS → ⋮ → **Reset credentials** → **SSH-Key** tab → **create a new SSH key**.
   - Name: `engage-laptop`
   - Key: paste the `ssh-ed25519 ...` line
   - Select it, then click **Reset credentials**.
4. Wait about 5 minutes. Check that the 🔔 notification in the Contabo panel says the task has
   finished.
5. Run `ssh root@` followed by the IP address. This time it asks
   `Enter passphrase for key '...id_ed25519':`. That is **your key's passphrase**, not a server
   password.

#### "Permission denied"? Check these
- **Wrong password type:** the Contabo website password or the VNC password will not work (see
  the table above).
- **Pasted twice:** if you are unsure whether it pasted, press Enter anyway. If it says
  "Permission denied, please try again", paste **once** more and press Enter.
- **An extra space or line break:** this can come along when you copy from an email or Notepad.
  Copy with Bitwarden's copy button instead.
- **Wrong command:** it must be exactly `ssh root@` followed by the IP address, with no `< >`
  brackets and no spaces around the `@`.
- **Still denied after a password reset:** wait 5 minutes and try again. If it still fails, send
  Claude the exact message on the screen; it contains no secrets.

### Step 2.3 — Run the inspection
1. Open [CONTABO_VPS_SETUP.md](CONTABO_VPS_SETUP.md), section 1.
2. Copy the **big block** that starts with `{` and ends with `Saved to ~/engage-inspection.txt"`.
3. Paste it into the server window. In PowerShell, right-click pastes. Press Enter.
4. Wait until you see **Saved to ~/engage-inspection.txt**.
5. Type `exit` and press Enter to leave the server.

This block **only reads** information. It does not change, stop or delete anything.

### Step 2.4 — Bring the results to your laptop
In PowerShell on your laptop, not on the server:
```powershell
scp YOUR_USERNAME@YOUR_VPS_IP:~/engage-inspection.txt $HOME\Desktop\engage-inspection.txt
```
Type the password again. A file called **engage-inspection.txt** appears on your Desktop.

### Step 2.5 — Hide private details and share
1. Open the file in Notepad.
2. Replace every IP address with `[REDACTED]`.
3. Paste the whole text into the chat with Claude, together with the plan details from step 2.1.

✅ **Done when:** Claude has the redacted inspection output.

---

## Part 2b — How to log in to your server (every time, with your SSH key)

Since 2026-11-25 you log in with your **SSH key**, not a password. The key lives on your laptop
in `C:\Users\User\.ssh\`:

| File | What it is | Share it? |
|---|---|---|
| `id_ed25519` | **Private** key: your real "door key" | **Never.** Back it up only to a USB stick and Bitwarden. |
| `id_ed25519.pub` | **Public** key: the "lock" placed on the server | Safe |

### The normal way
1. Open **PowerShell**.
2. Type the following and press Enter:
   ```powershell
   ssh root@YOUR_VPS_IP
   ```
   After stage 6B, use `ssh engageadmin@YOUR_VPS_IP`. Root login is then switched off.
3. It asks `Enter passphrase for key 'C:\Users\User/.ssh/id_ed25519':`. Paste your key's
   **passphrase** from Bitwarden (right-click; nothing appears) and press Enter.
4. You are in when you see `root@vmi3748133:~#`, or `engageadmin@vmi3748133:~$` after 6B.
5. To leave, type `exit` and press Enter.

### Shortcut: type `ssh engage-vps` instead of the IP (optional, do once)
This saves the server's details in a small settings file on your laptop.
1. In PowerShell, check whether the file already exists:
   ```powershell
   Test-Path $HOME\.ssh\config
   ```
   If it says **True**, stop and ask Claude, so that nothing in it is overwritten.
2. If it says **False**, paste this, with your real IP in place of `YOUR_VPS_IP`, and press Enter:
   ```powershell
   @"
   Host engage-vps
       HostName YOUR_VPS_IP
       User root
       IdentityFile ~/.ssh/id_ed25519
       ServerAliveInterval 60
   "@ | Set-Content -Encoding ascii $HOME\.ssh\config
   ```
3. From now on, just type `ssh engage-vps`.
4. **After stage 6B**, change `User root` to `User engageadmin`. Run `notepad $HOME\.ssh\config`,
   edit that line, save and close.

### Type the passphrase less often (optional)
Windows can remember the unlocked key until you sign out of Windows. Open PowerShell **as
administrator** (right-click PowerShell → *Run as administrator*) and run:
```powershell
Get-Service ssh-agent | Set-Service -StartupType Automatic
Start-Service ssh-agent
```
Then, in a normal PowerShell window: `ssh-add $HOME\.ssh\id_ed25519`, and enter the passphrase
once. Only do this on your own laptop, protected with your Windows password.

### Copying a file from the server to your laptop
Run this in PowerShell on the **laptop**, not on the server:
```powershell
scp root@YOUR_VPS_IP:~/FILE_NAME $HOME\Desktop\FILE_NAME
```
With the shortcut: `scp engage-vps:~/FILE_NAME $HOME\Desktop\FILE_NAME`.

### Back up your key (do this today)
If your laptop is lost or broken, the key goes with it.
1. Copy `C:\Users\User\.ssh\id_ed25519` and `id_ed25519.pub` to a USB stick kept somewhere safe.
2. Also attach `id_ed25519` to a Bitwarden item called "Engage VPS SSH key", together with its
   passphrase.

### If you ever lose the key or cannot log in
- Make a new key (step 2.2, "log in with an SSH key instead") and add it in Contabo: **Reset
  credentials → SSH-Key**.
- Emergency door: Contabo panel → your VPS → **VNC** console.
- Do not reinstall the server. Ask Claude first.

---

## Part 3 — Look at your Cloudflare settings, without changing anything (about 10 minutes) — do now

1. Log in at **dash.cloudflare.com** and click **zuvoora.com**.
2. Click **DNS → Records**. Check whether any of these names already exist, and write down "exists"
   or "free" for each:
   - `engage`
   - `api-engage`
   - `staging-engage`
   - `staging-api-engage`
3. Still in **DNS → Records**, write down whether you see records named `send`, `resend`,
   `_dmarc`, or TXT records containing `spf`. These tell us whether email is already set up for
   zuvoora.com.
4. Click **SSL/TLS → Overview** and write down the mode: Off, Flexible, Full or Full (strict).
5. Tell Claude what you found. These are not secrets.

**Do not add, change or delete anything in Cloudflare yet.**

---

## Part 4 — Answer the founder questions — do now

Open [PHASE6_DEPLOYMENT_PLAN.md](PHASE6_DEPLOYMENT_PLAN.md) section 8 and answer the questions in
the chat. Short answers are fine, for example "Q2: same server is OK" or "Q3: yes, Pro". If you are
unsure, say "use your recommendation" and Claude will explain it first.

✅ **Answered on 2026-11-24** (recorded in the plan, §1a):
- staging on the same server;
- Supabase Free for now;
- emails sent from `engage.zuvoora.com`, with your mailbox receiving alerts and replies;
- AI on at launch;
- virus scanning added;
- no lawyer yet.

**Still to answer:** Q4, Q6, Q7, Q10, Q11 and Q13. "Use your recommendation" is fine for these.

> 🛑 **STOP HERE.** Claude now prepares the code and configuration (stage 6A) and shows you the
> results. Do **not** start Part 5 until Claude says "6A is done" and you have approved 6B.

---

## Part 5 — Make your server safer (stage 6B) — after approval

Claude gives you **exact commands tailored to your server** after reading your inspection results.
These steps prepare you for that.

### Step 5.1 — Take a snapshot (a "save point")
1. In Contabo, open your VPS → **Snapshots** → **Create snapshot**. Name it
   `before-engage-hardening`.
2. Wait until it says it is finished.
3. If Contabo asks you to pay for snapshots, stop and tell Claude. We will decide together. Your
   panel shows "Auto Backup: Add-On required", which means automatic server backups are **not**
   switched on.

This is the "undo button" for the whole server.

### Step 5.2 — Make your own SSH key (on your laptop only)
An SSH key is like a special door key. It is much safer than a password.
1. In PowerShell on your **laptop**:
   ```powershell
   ssh-keygen -t ed25519 -C "engage-admin-laptop"
   ```
2. When asked where to save, press **Enter** to accept the default.
3. When asked for a passphrase, type a strong one (twice) and save it in Bitwarden.
4. This creates two files in `C:\Users\<you>\.ssh\`:
   - `id_ed25519`, the **private** key. **Never share this file. Never copy it anywhere except a
     backup USB stick.**
   - `id_ed25519.pub`, the **public** key. This one is safe to put on the server.
5. To see the public key: `Get-Content $HOME\.ssh\id_ed25519.pub`

### Step 5.3 — Find the "emergency door"
In Contabo, open your VPS and find **VNC** or **Console** access. Write down how to open it. If a
mistake ever blocks normal login, this console still works.

### Step 5.4 — Run Claude's hardening commands
- Keep **two PowerShell windows** connected to the server.
- Run one command group at a time, and paste the result (redacted) to Claude after each.
- Test a new login in a second window **before** closing the first.
- After each step, open the main ZUVOORA website to check it still works.

✅ **Done when:** Claude confirms the 6B checks passed and ZUVOORA still works.

---

## Part 6 — Create the accounts and keys (stage 6C) — after approval

You can do 6.1 to 6.7 in any order. **Every secret goes straight into Bitwarden.** Never into
the chat.

### Step 6.1 — Create the production database (Supabase)
1. Log in at **supabase.com/dashboard**.
   - **First, count your projects.** The free plan allows only **two active free projects**. If
     you already have two (for example the Engage staging project plus a project for the main
     ZUVOORA app), stop and tell Claude before creating anything.
2. Click **New project**, inside the same organisation as the existing Engage project.
   - Name: `zuvoora-engage-production`
   - Database password: click **Generate a password**, then **copy it into Bitwarden right
     away**, named "Supabase production DB password".
   - Region: **the same region as your existing Engage project**, unless Claude advises otherwise
     after seeing the server region.
3. Stay on the **Free** plan for now (your decision). That means Supabase keeps **no backups** for
   you. Our own nightly backup (6.4 and 6.5) is the only safety copy, so those two steps are a
   must. Upgrade to Pro when paying clinics arrive.
4. Tell Claude: "production project created", plus the **project reference**. That is the short
   code in the project's web address (`supabase.com/dashboard/project/<this part>`). It is not a
   secret.

Claude then guides you through the Auth settings: turning sign-ups off, the website address, the
email sender and two-factor login.

### Step 6.2 — Set up email sending (Resend)
1. Log in at **resend.com** (create an account if needed).
2. **Domains → Add domain.** Type `engage.zuvoora.com`.
   - Why not your Gmail? Email services can only send *from* a domain you own. Gmail belongs to
     Google, so emails "from" a Gmail address sent by Resend would be blocked or marked as spam.
   - Emails will come from `ZUVOORA Engage <no-reply@engage.zuvoora.com>`. Your Gmail receives
     the alerts and replies. You type it into the server settings yourself (Part 7); it is never
     written into the code.
   - A clinic's emails to patients show **the clinic's name**, and when a patient presses
     "Reply", the answer goes **to the clinic**, not to you.
3. Resend shows some DNS records. Choose **"Sign in to Cloudflare"** (automatic setup) if offered;
   otherwise Claude helps you add them by hand.
4. Wait until the domain shows **Verified**.
5. **API Keys → Create API key**, three times:
   - `engage-staging`: permission **Sending access**, domain = your sending domain
   - `engage-production`: same settings
   - `engage-supabase-smtp`: same settings. Supabase uses this to send login and invitation emails.
6. Each key is shown **only once**. Copy each into Bitwarden immediately.
7. The free Resend plan allows **100 emails a day**, shared by staging, production and login
   emails. That is enough to start, and Claude sets up an alert before the limit is reached.

### Step 6.2b — Official addresses that forward to your Gmail (free, optional)
This lets you show `support@engage.zuvoora.com` or `admin@engage.zuvoora.com` today, with the
emails arriving in your Gmail.
1. In Cloudflare open **zuvoora.com** → **Email** → **Email Routing**.
2. Follow the screens to enable it, and add your Gmail as the **destination address**. Google
   sends you a confirmation email; click the link in it.
3. Create the addresses, for example `support@engage.zuvoora.com` → your Gmail.

Claude checks the records with you before you click "Add records", so that nothing used by the
main ZUVOORA email is changed.

### Step 6.3 — AI keys with a spending limit (OpenRouter)
1. Log in at **openrouter.ai** → **Settings → API Keys → Create key**.
2. Create two keys, and give each a **credit limit**:
   - `engage-staging`, limit **$1**
   - `engage-production`, limit **$5** to start. AI is switched on at launch, as you chose; raise
     the limit later when you see real usage.
3. Copy each key into Bitwarden.

The limit is a hard ceiling. Even if something went wrong, it cannot spend more than that.

### Step 6.4 — Backup storage (Backblaze B2, recommended)
B2 is recommended because it can give the server a key that can **add** backups but cannot
**read or delete** them.
1. Create an account at **backblaze.com** (B2 Cloud Storage).
2. **Buckets → Create a bucket:**
   - Name: `zuvoora-engage-backups-<random word>`
   - Files: **Private**
   - **Object Lock: Enable.** This stops anyone deleting backups early. It can only be turned on
     now, at creation.
3. **Application Keys → Add a new application key:**
   - Name: `engage-server-backup`
   - Bucket: only the new bucket
   - Type of access: **Write Only**
4. Copy the **keyID** and **applicationKey** into Bitwarden. They are shown once.

### Step 6.5 — Backup encryption key (on your laptop)
This key lets **only you** open the backups.
1. In PowerShell on your laptop: `winget install FiloSottile.age`, then close and reopen
   PowerShell.
2. Create the key:
   ```powershell
   age-keygen -o $HOME\Documents\engage-backup-key.txt
   ```
3. It prints a line starting with `Public key: age1...`. **The public key is safe to share.**
   Give it to Claude; it goes on the server.
4. The file `engage-backup-key.txt` is the **private** key:
   - Copy it to **two USB sticks** kept in different safe places, **and** into Bitwarden (as an
     attachment or secure note).
   - Then delete it from Documents.
   - If you lose it, nobody can ever open the backups, including you.

### Step 6.6 — Uptime alerts (UptimeRobot or Better Stack)
1. Create a free account at **uptimerobot.com** (or **betterstack.com**).
2. Add your email and phone as alert contacts.
3. Do not add monitors yet. Claude tells you the exact addresses after deployment.

### Step 6.7 — Test booking accounts (Cal.com and Calendly)
1. Create free accounts at **cal.com** and **calendly.com** with a test email address, not a
   clinic's.
2. In each, create one event type called "Eye test (TEST)".
3. Claude guides the connection when staging is live.

> 🛑 **STOP.** Tell Claude which of 6.1–6.7 are done. Claude applies the database setup to the
> production project and checks everything.

---

## Part 7 — Putting secrets on the server (whenever Claude asks)

This is how secrets travel from Bitwarden to the server **without** passing through the chat.

1. Connect to the server, as in Part 2.2, but with your new admin user.
2. Claude gives you a command like:
   ```bash
   sudo nano /opt/zuvoora-engage/staging/.env
   ```
   This opens a simple text editor on the server.
3. Claude gives you a **template** with names and empty values, for example `RESEND_API_KEY=`.
   For each line, copy the value from Bitwarden and paste it after the `=`. In nano, right-click
   pastes.
4. Save: press **Ctrl+O**, then **Enter**. Exit: press **Ctrl+X**.
5. Protect the file:
   ```bash
   sudo chmod 600 /opt/zuvoora-engage/staging/.env
   ```
6. Run the check Claude gives you (`preflight.sh`). It says **OK** or names what is missing,
   **without** showing any values.

Some secrets (`WIDGET_TOKEN_SECRET`, `INTEGRATIONS_ENCRYPTION_KEY`) are **generated on the server**
with a command Claude gives you. Copy them into Bitwarden too. **Staging and production must
never share a secret.**

---

## Part 8 — Web addresses and the padlock (stage 6D) — after approval

Claude gives you the exact Cloudflare clicks. In short, you will:
1. Add the four web addresses (DNS records) pointing to your server, with the **orange cloud**
   (proxied) on.
2. Create a **Cloudflare Origin Certificate** (SSL/TLS → Origin Server). Its private key goes onto
   the server with the Part 7 method, never into the chat.
3. Set **SSL/TLS mode to Full (strict)** **only after** Claude confirms that the main ZUVOORA site
   works with it. This setting affects the whole domain.
4. Turn on **Authenticated Origin Pulls**.
5. Put the staging dashboard behind **Cloudflare Zero Trust → Access**, so only your email can open
   it.

✅ **Done when:** all four addresses show a padlock 🔒 in the browser.

---

## Part 9 — Practice copy, testing, then the real thing (6E–6I)

Claude does most of this. Your jobs:
- [ ] Approve each step when Claude asks.
- [ ] Walk through the [Demo guide](DEMO_GUIDE.md) on the **staging** web address (Acts 1–6),
  using made-up data only.
- [ ] Check that the test emails arrive in your test inbox.
- [ ] Make a real test booking in your Cal.com and Calendly test accounts.
- [ ] Add the uptime monitors with the addresses Claude gives you, then confirm that you received
  a test alert.
- [ ] Be present for the **restore drill**. Claude needs your backup private key from the USB
  stick, used on your laptop only.
- [ ] Read and sign the [Production security checklist](../security/PRODUCTION_SECURITY_CHECKLIST.md).
- [ ] Give the written go-ahead for production: "I approve production release vX.Y.Z".
- [ ] After production is live, create your platform admin account and set up two-factor login
  (Claude guides you; see [PRODUCTION_DEPLOYMENT.md](PRODUCTION_DEPLOYMENT.md) §3).

---

## Part 10 — Legal papers (start now, it takes time)

Real patient conversations must not go through the system until these are ready. Ask a
**qualified lawyer** who knows the Nigeria Data Protection Act 2023, and the laws of any other
country where your clinics are, to prepare or review:

- [ ] **Privacy notice**: what the chat collects, why, how long it is kept and who the
  subprocessors are (Supabase, Contabo, Cloudflare, OpenRouter, Resend, Cal.com, Calendly).
- [ ] **Terms of service** for clinics.
- [ ] **Data processing agreement (DPA)**, to be signed with each clinic.
- [ ] **Retention schedule**: how long conversations, call-backs and records are kept.
- [ ] **Incident (data breach) plan**: who to call and what deadlines apply.

Give Claude the final texts. They are added to the website footer and the demo form.

**You don't have a lawyer yet, and that's fine for now.** Everything technical can continue,
including putting the system online with **made-up test data**. Only real patient conversations
must wait. If you want, Claude can write **first drafts** of these documents, clearly marked
"DRAFT — not legal advice". A lawyer then only needs to check and correct them, which is usually
quicker and cheaper than writing from nothing.

---

## Part 11 — Getting the three pilot clinics ready

For each clinic, collect:
- [ ] The signed agreement and DPA (Part 10).
- [ ] The clinic's legal name, and the owner's name and work email.
- [ ] The clinic website address, and who can add a DNS record for it (needed to prove the
  website belongs to them).
- [ ] Their booking system (Cal.com, Calendly or none) and who can connect it.
- [ ] Their opening hours, services, prices and FAQs (they can also type these in themselves).

Clinics are switched on **one at a time**, with a check-in call after the first week.

---

## Quick reference — what is safe to share with Claude

| Safe to share | **Never** share |
|---|---|
| Plan name, CPU, RAM, disk, region | Server password, SSH **private** key (`id_ed25519` without `.pub`) |
| Redacted inspection output | Any API key (Supabase secret, OpenRouter, Resend, Backblaze) |
| Supabase **project reference** | Supabase database password |
| The backup **public** key (`age1...`) | The backup **private** key file |
| Which DNS names exist; the SSL/TLS mode | Cloudflare Origin Certificate **private key** |
| "Done", "error message (with secrets removed)" | Contents of any `.env` file |
