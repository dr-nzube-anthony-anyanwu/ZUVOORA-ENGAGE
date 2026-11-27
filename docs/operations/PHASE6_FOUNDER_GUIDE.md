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


## ⭐ Where you are now (updated 2026-11-26)

**Already done ✅**

| What | When |
|---|---|
| Server checked, then made safe: admin user `engageadmin`, SSH key login, firewall, fail2ban, updates, Docker, swap (Parts 2, 2b and 5) | 25 Nov |
| Contabo snapshot taken | 25 Nov |
| All founder questions answered (Part 4) | 24–25 Nov |
| **6.1** Production database created: `zuvoora-engage-production`, region `eu-west-1`, the same as staging. Claude checked it: healthy. | 26 Nov |
| **6.3** OpenRouter keys (staging and production) | 26 Nov |
| **6.4** Backblaze B2 backup bucket and key | 26 Nov |
| The email domain `engage.zuvoora.com` was verified in Resend back on 21 Nov, and the staging database already sends its emails through it | 21 Nov |
| Bitwarden account created | 26 Nov |
| SSH shortcut `ssh engage-vps` | 27 Nov |
| **6.2** Resend keys: `engage-staging-app`, `engage-production-app`, `engage-production-supabase-smtp` | 27 Nov |
| OpenRouter credit limits confirmed | 27 Nov |
| **6.8a** GitHub repository variables (4 public values) | 27 Nov |
| **6.7** Cal.com and Calendly test accounts | 27 Nov |
| **6.6** UptimeRobot account (monitoring `zuvoora.com` for now) | 27 Nov |
| **6.5** Backup padlock (public key) received and saved; the private key stays with you | 27 Nov |
| Quick checks: two-factor login on every account, SSH key backed up (USB stick and Bitwarden), B2 Object Lock on, B2 key write-only | 27 Nov |
| **6.1b** Production database finished (Jobs A–D). Claude then set the login rules: sign-ups **off** (they were open), passwords of at least 12 characters with mixed case and digits, the invitation email, the website addresses and a 10 MB upload limit. Checked: email sending through Resend works and two-factor login is on. | 27 Nov |
| **Part 3** Cloudflare looked at: the four Engage names are free; the Resend email records exist; SSL mode is "Full" (automatic) on the Free plan | 27 Nov |
| Production database linked (Job 0), and Claude copied in the full database structure: all 19 migrations, schema check clean | 26 Nov |

**Still to do, in this order 👇** (each one is explained step by step further down)

| # | Task | Time | Where in this guide |
|---|---|---|---|
| 1 | **Stage 6D: web addresses and the padlock.** Do steps 8.1–8.10 in order and tell Claude after each. | about 1 hour | [Part 8](#part-8--web-addresses-and-the-padlock-stage-6d) |

**Later (Claude will tell you when):** official email addresses (6.2b, optional), making the
GitHub images public (6.8b), putting secrets on the server (Part 7), web addresses and the
padlock (Part 8), testing staging (Part 9).
**Start soon, because it takes time:** find a lawyer (Part 10), and talk to the pilot clinics
(Part 11).

When you finish a task, tell Claude its number, for example "task 2 done". Never paste a key.

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

### Step 1.1 — Install a password manager ✅

> ✅ **Done (26 Nov).** Bitwarden account created. Step 1.2 (two-factor login everywhere) is
> checked in the quick checks of Part 6.
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

## Part 2 — Look at your server, without changing anything ✅ DONE
> ✅ **Done (25 Nov).** You found the server details, logged in, ran the read-only inspection and shared the results. The server is Ubuntu 24.04.5, 6 cores, 12 GB, empty. Kept below as reference.


### Step 2.1 — Find your server's details in Contabo ✅
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

### Step 2.2 — Connect to the server ✅
> ✅ **Done (25 Nov).** The password route failed, so you switched to an **SSH key** (the "log in with an SSH key instead" part). That key is how you log in now; see Part 2b. These steps are only needed again on a new laptop or after losing the key. Kept below as reference.

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

### Step 2.3 — Run the inspection ✅
1. Open [CONTABO_VPS_SETUP.md](CONTABO_VPS_SETUP.md), section 1.
2. Copy the **big block** that starts with `{` and ends with `Saved to ~/engage-inspection.txt"`.
3. Paste it into the server window. In PowerShell, right-click pastes. Press Enter.
4. Wait until you see **Saved to ~/engage-inspection.txt**.
5. Type `exit` and press Enter to leave the server.

This block **only reads** information. It does not change, stop or delete anything.

### Step 2.4 — Bring the results to your laptop ✅
In PowerShell on your laptop, not on the server:
```powershell
scp YOUR_USERNAME@YOUR_VPS_IP:~/engage-inspection.txt $HOME\Desktop\engage-inspection.txt
```
Type the password again. A file called **engage-inspection.txt** appears on your Desktop.

### Step 2.5 — Hide private details and share ✅
1. Open the file in Notepad.
2. Replace every IP address with `[REDACTED]`.
3. Paste the whole text into the chat with Claude, together with the plan details from step 2.1.

✅ **Done when:** Claude has the redacted inspection output.

---

## Part 2b — How to log in to your server (every time, with your SSH key) ✅ in use
> ✅ **Done (25 Nov).** You log in with `ssh engageadmin@...` and your key passphrase, and you use `sudo -v` and one-line pastes. Still open: the optional shortcut and passphrase memory, and **backing up the key** (in the quick checks, Part 6). Kept below as reference.


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

### Admin commands (`sudo`): unlock first, then paste
`sudo` runs a command with full admin rights and asks for the **engageadmin password**, not your
key passphrase. **Before pasting a block of several lines, run this on its own:**
```bash
sudo -v
```
Paste the password and press Enter. sudo then remembers it for 15 minutes.

If you skip this, the pasted lines pour into the password prompt. sudo counts each line as a
wrong password ("Sorry, try again", "3 incorrect password attempts"), and the block only half
runs.

### Paste one line at a time
On this laptop's terminal, a pasted block of several lines is unreliable. While the first command
runs, the remaining lines are swallowed and never run. This was seen on 2026-11-25 with `ufw` and
`apt install`. So:
1. Paste **one line**.
2. Press Enter.
3. Wait until the prompt (`engageadmin@vmi3748133:~$`) comes back.
4. Paste the next line.

Claude gives server commands as single lines, joined with `&&` where needed.

### Shortcut: type `ssh engage-vps` instead of the IP (optional, do once)
This saves the server's details in a small settings file on your laptop.
> ✅ **Done (27 Nov).** `ssh engage-vps` logs in as `engageadmin`. The entry was added at the end
> of the existing `config` file, which also holds another server's entry and VS Code's unused
> `Host alias` example; both were left unchanged. A safety copy is at `.ssh\config.backup`. Kept
> below as reference, for example for a new laptop.

1. Open **PowerShell** (Windows key → type `PowerShell` → Enter).
2. Make a safety copy of the file first:
   ```powershell
   Copy-Item $HOME\.ssh\config $HOME\.ssh\config.backup
   ```
3. Open the file in Notepad:
   ```powershell
   notepad $HOME\.ssh\config
   ```
4. In Notepad, click at the **very end** of the text, press **Enter twice** for an empty line,
   then type (or paste) these five lines. Put your server's real IP address (from Bitwarden) in
   place of `YOUR_VPS_IP`. The spaces at the start of lines 2–5 are fine as they are:
   ```text
   Host engage-vps
       HostName YOUR_VPS_IP
       User engageadmin
       IdentityFile ~/.ssh/id_ed25519
       ServerAliveInterval 60
   ```
5. Press **Ctrl+S** to save, then close Notepad.
6. Test it in PowerShell:
   ```powershell
   ssh engage-vps
   ```
   Type your key passphrase as usual. You should land at `engageadmin@vmi3748133:~$`. Type `exit`
   to leave.
7. If something goes wrong, put the old file back with
   `Copy-Item $HOME\.ssh\config.backup $HOME\.ssh\config -Force`.

### Type the passphrase less often (optional)
> **Status (27 Nov): not done.** It is optional. The Windows helper `ssh-agent` is currently
> switched off ("Disabled"). If you are happy typing the passphrase each time, skip this.

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
> ✅ **Done (27 Nov).** Key backed up to a USB stick and to Bitwarden (confirmed by you).

If your laptop is lost or broken, the key goes with it, and you would need the Contabo panel to
get back in.
1. Plug in a USB stick. Open **File Explorer** and note its drive letter, for example `E:`.
2. In PowerShell (put your drive letter in place of `E:`):
   ```powershell
   New-Item -ItemType Directory -Force E:\engage-ssh-key | Out-Null
   Copy-Item $HOME\.ssh\id_ed25519, $HOME\.ssh\id_ed25519.pub E:\engage-ssh-key\
   Get-ChildItem E:\engage-ssh-key
   ```
   You should see both files listed. Eject the USB stick safely and keep it somewhere safe at home.
3. In **Bitwarden**: **New** → **Login** (or **Secure note**) → name it **"Engage VPS SSH key"**.
   - Put the key's **passphrase** in the password or notes field.
   - Click **Attachments** → **Choose file** → pick `C:\Users\User\.ssh\id_ed25519` → **Save**.
     File attachments need Bitwarden Premium (about $10 a year). If you are on the free plan,
     open the file with `notepad $HOME\.ssh\id_ed25519`, copy **all** its text, from
     `-----BEGIN` to `-----END ... -----`, and paste it into the item's **Notes**. Close Notepad
     **without changing anything**.
4. The key is useless without its passphrase, and the passphrase is useless without the key.
   Keeping both in Bitwarden (protected by your master password and 2FA) plus the key on a USB
   stick is the safe combination.

### If you ever lose the key or cannot log in
- Make a new key (step 2.2, "log in with an SSH key instead") and add it in Contabo: **Reset
  credentials → SSH-Key**.
- Emergency door: Contabo panel → your VPS → **VNC** console.
- Do not reinstall the server. Ask Claude first.

---

## Part 3 — Look at your Cloudflare settings, without changing anything ✅ DONE

> ✅ **Done (27 Nov).** Results:
> - `engage`, `api-engage`, `staging-engage` and `staging-api-engage` do **not** exist yet, so
>   they are free to use.
> - The Resend email records under `engage` exist: `send.engage`, `resend._domainkey.engage`,
>   `rsend.engage` and `_dmarc.engage`. **Never change or delete them**, or Engage emails stop.
> - SSL/TLS mode for the whole `zuvoora.com` domain: **Full**, chosen by Cloudflare's automatic
>   mode. Plan: Free. The domain already receives some visits.
>
> Decision for Part 8: leave the domain-wide mode alone, so nothing else on `zuvoora.com` is
> affected. Add one Cloudflare **Configuration Rule** that sets **Full (strict)** for the four
> Engage addresses only.

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

## Part 4 — Answer the founder questions ✅ DONE
> ✅ **Done (24–25 Nov).** All questions are answered. The decisions D1–D12 are in the deployment plan, §1a and §8. Kept below as reference.


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

## Part 5 — Make your server safer (stage 6B) ✅ DONE
> ✅ **Done (25 Nov, accepted by you).** Snapshot taken; SSH key; admin user `engageadmin`; root and password login off; firewall on (22, 80, 443 only); fail2ban; automatic security updates; 2 GB swap; Docker; the `/opt/zuvoora-engage` folders. Claude checked from outside that only SSH answers. Kept below as reference.


Claude gives you **exact commands tailored to your server** after reading your inspection results.
These steps prepare you for that.

### Step 5.1 — Take a snapshot (a "save point") ✅
1. In Contabo, open your VPS → **Snapshots** → **Create snapshot**. Name it
   `before-engage-hardening`.
2. Wait until it says it is finished.
3. If Contabo asks you to pay for snapshots, stop and tell Claude. We will decide together. Your
   panel shows "Auto Backup: Add-On required", which means automatic server backups are **not**
   switched on.

This is the "undo button" for the whole server.

### Step 5.2 — Make your own SSH key (on your laptop only) ✅
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

### Step 5.3 — Find the "emergency door" ✅

> The Contabo panel shows **VNC: Enabled**, and that is your emergency door. Make sure you know
> how to open it: your VPS → **VNC** in the server box. It never needs the SSH key.
In Contabo, open your VPS and find **VNC** or **Console** access. Write down how to open it. If a
mistake ever blocks normal login, this console still works.

### Step 5.4 — Run Claude's hardening commands ✅
- Keep **two PowerShell windows** connected to the server.
- Run one command group at a time, and paste the result (redacted) to Claude after each.
- Test a new login in a second window **before** closing the first.
- After each step, open the main ZUVOORA website to check it still works.

✅ **Done when:** Claude confirms the 6B checks passed and ZUVOORA still works.

---

## Part 6 — Create the accounts and keys (stage 6C)

**Every key goes straight into Bitwarden. Never into the chat.** A "key" here is like a password
that lets a program use a service. Most services show a key **only once**, so copy it into
Bitwarden right away, before you close the window.

### Quick checks (5 minutes) ✅ all done 27 Nov
Tick each one. If one is not done, do it now; the "How" column explains.

| ✓ | Check | How |
|---|---|---|
| ✅ | Bitwarden has a folder **ZUVOORA Engage** holding every password and key from these steps | Step 1.1 |
| ✅ | Two-factor login (a code from your phone) is on for GitHub, Cloudflare, Contabo, Supabase, OpenRouter, Backblaze and Resend | Step 1.2. Look for "Two-factor", "2FA" or "Security" in each site's account settings. |
| ✅ | Your SSH key is backed up: `C:\Users\User\.ssh\id_ed25519` is on a USB stick **and** attached in Bitwarden with its passphrase | Part 2b, "Back up your key" |
| ✅ | **Backblaze:** the bucket shows **Object Lock: Enabled** | Backblaze → Buckets → your bucket. If it says disabled, tell Claude; the bucket must be recreated, because Object Lock can only be switched on at creation. |
| ✅ | **Backblaze:** the key `engage-server-backup` is **Write Only** and limited to that one bucket | Backblaze → Application Keys. If it says "Read and Write", delete it and make a new one (Step 6.4). |
| ✅ | **OpenRouter:** each key has a **credit limit** ($1 staging, $5 production). Confirmed 27 Nov. | openrouter.ai → Settings → API Keys → the pencil next to each key |

### Step 6.1 — Create the production database (Supabase) ✅ done 26 Nov
Project `zuvoora-engage-production` (reference `zitwanfosyhtjmfqjlsm`), region `eu-west-1`, Free
plan. Its database password must be in Bitwarden as "Supabase production DB password".
Because you are on the Free plan, Supabase keeps **no backups** for you. That is why steps 6.4
and 6.5 matter so much.

### Step 6.1b — Finish the production database ✅ done 27 Nov
**Job 0 (first, once): let Claude's database tool into the production database** ✅ done 26 Nov
Claude's tool needs the production **database password** once. Only you have it, and it must not
go through the chat.
1. Open **PowerShell** on your laptop. Type these two lines, pressing Enter after each:
   ```powershell
   cd D:\technologies\ZUVOORA-ENGAGE
   npx supabase --workdir D:\technologies\engage-prod-ops link --project-ref zitwanfosyhtjmfqjlsm
   ```
   ⚠️ Since 26 Nov Claude runs this **from inside** `D:\technologies\engage-prod-ops`. The
   project folder's own `.env` file holds the **staging** password, and the tool would
   wrongly use it.
2. It asks `Enter your database password`. In Bitwarden, copy **"Supabase production DB
   password"**, **right-click once** in PowerShell to paste it (nothing appears; that's normal),
   then press **Enter**.
3. You should see `Finished supabase link`. The tool remembers the password safely on your laptop.
   The folder `engage-prod-ops` is kept separate on purpose, so normal work can never touch
   production by accident.
4. Tell Claude **"production linked"**.

If it says "password authentication failed", the password does not match. Reset it in Supabase:
**Project Settings → Database → Reset database password**, save the new one in Bitwarden, and try
step 1 again.

✅ **The production database is ready** (26 Nov: 19 migrations applied, schema check clean).
Now do these four small jobs on
**supabase.com/dashboard → project `zuvoora-engage-production`**. Check the project name at the
top of the page every time, so you do not change the staging project by mistake.

**Job A — Give the app its own database password**
1. In Bitwarden, generate a new password: **letters and numbers only**, 32 characters. Save it as
   "Supabase production engage_api password".
2. In Supabase, click **SQL Editor** in the left menu, then **New query**.
3. Type this, putting your new password between the quote marks:
   ```sql
   alter role engage_api with password 'PASTE_THE_NEW_PASSWORD_HERE';
   ```
4. Click **Run**. You should see "Success. No rows returned".
5. Close the query **without saving it**: click the "⋯" next to it, then Delete, so the password
   is not stored there.

**Job B — Copy the two project keys into Bitwarden**
1. Click **Project Settings** (the cog at the bottom left) → **API Keys**.
2. **Publishable key** (starts `sb_publishable_`): copy it into Bitwarden as "Supabase production
   publishable key". This one is public: it is safe in GitHub (Step 6.8a) and you may share it.
3. **Secret keys**: click **Create new secret key**, name it `engage-production-server`, then copy
   it into Bitwarden as "Supabase production secret key". It starts `sb_secret_`.
   **Never share this one or put it in GitHub.**
4. Still in Project Settings, open **Database → Connection string → Session pooler**. Copy the
   **host name** (it looks like `aws-0-eu-west-1.pooler.supabase.com`) into the same Bitwarden
   note. You will need it in Part 7.

**Job C — Let the database send login emails through Resend** (needs Step 6.2 first)
1. Click **Authentication** (the people icon) → **Emails** → the **SMTP Settings** tab.
2. Turn on **Enable custom SMTP** and fill in:
   - Sender email: `no-reply@engage.zuvoora.com`
   - Sender name: `ZUVOORA Engage`
   - Host: `smtp.resend.com`
   - Port: `465`
   - Username: `resend`
   - Password: the Resend key **`engage-production-supabase-smtp`** from Bitwarden (Step 6.2)
3. Click **Save**.
4. Go to **Authentication → Rate Limits**. Set "Rate limit for sending emails" to **30** per hour,
   then click **Save**.

**Job D — Close the side door**
1. **Project Settings → Data API**.
2. In **Exposed schemas**, remove `public` (click the little x), then click **Save**. Our app does
   not use this door, and closing it is extra safety.

Then tell Claude: **"6.1b done"**. Claude then sets the remaining login rules: sign-ups off,
two-factor login, password rules, the invitation email and the website addresses. Claude
checks everything too.

### Step 6.2 — Email keys (Resend) ✅ done 27 Nov
**Good news: the domain `engage.zuvoora.com` is already verified** (since 21 Nov), and the
staging database already sends its login emails through it. You only need three new keys.

1. Go to **resend.com** and log in.
2. Click **Domains** and check that `engage.zuvoora.com` shows **Verified** (green). If it does
   not, stop and tell Claude.
3. Click **API Keys** → **Create API Key**. Fill in:
   - Name: `engage-staging-app`
   - Permission: **Sending access** (not "Full access")
   - Domain: **engage.zuvoora.com**
   - Click **Add**. Copy the key (it starts `re_`) into Bitwarden as "Resend staging app key".
4. Do it again with the name `engage-production-app` and save it as "Resend production app key".
5. Do it again with the name `engage-production-supabase-smtp` and save it as "Resend production
   SMTP key". The production database uses this one to send login and invitation emails
   (Step 6.1b, Job C).
6. You should now see these keys in the list, plus the older one the staging database already
   uses. **Do not delete the older one**: staging login emails would stop.

Why not send from your Gmail? Email services can only send *from* a domain you own. Emails come
from `ZUVOORA Engage <no-reply@engage.zuvoora.com>`, and your Gmail **receives** the alerts. You
type your Gmail into the server settings yourself in Part 7; it is never written into the code.
A clinic's emails to patients show **the clinic's name**, and a patient's "Reply" goes **to the
clinic**.

The free Resend plan allows **100 emails a day**, shared by everything. That is enough to start.

### Step 6.2b — Official addresses that forward to your Gmail (optional, later)
This lets you show `support@engage.zuvoora.com` today, with the emails arriving in your Gmail.
**Do this together with Claude**, because it adds email records to Cloudflare and must not
touch the records Resend already uses.
1. Cloudflare → **zuvoora.com** → **Email** → **Email Routing**.
2. Follow the screens. Add your Gmail as the **destination address**, then click the
   confirmation link Google emails you.
3. Create an address such as `support@engage.zuvoora.com`, forwarding to your Gmail.

### Step 6.3 — AI keys with a spending limit (OpenRouter) ✅ done 26 Nov
Two keys, `engage-staging` ($1 limit) and `engage-production` ($5 limit), saved in Bitwarden.
Confirm the limits in the quick checks above.

### Step 6.4 — Backup storage (Backblaze B2) ✅ done 26 Nov
A bucket with Object Lock and a **write-only** key `engage-server-backup`. The keyID and
applicationKey are in Bitwarden. Confirm both settings in the quick checks above. Also write down
(not secret, Bitwarden note is fine) the **bucket name** and the **Endpoint** shown on the bucket
page (it looks like `s3.eu-central-003.backblazeb2.com`). Claude needs both later; they are
safe to tell Claude.

### Step 6.5 — Backup encryption key (on your laptop) ✅ done 27 Nov

> ✅ The public key (`age1ht2k...6uklp`) is saved in `deploy/backup/age-recipients.txt`; its
> checksum was verified. **Make sure** the private key file is on **two USB sticks and in
> Bitwarden**, and that you deleted it from Documents and emptied the Recycle Bin.
Think of it as a padlock and its key. The server gets the **padlock** (the public key): it can
lock backups but never open them. Only **you** keep the **key** (the private key), so only you
can open a backup.

1. Open **PowerShell** on your laptop. This is your laptop, not the server.
2. Install the small "age" program by typing this and pressing Enter:
   ```powershell
   winget install FiloSottile.age
   ```
   If it asks to agree to terms, type `Y` and press Enter.
3. **Close PowerShell and open it again** so it can find the new program.
4. Make the padlock and key:
   ```powershell
   age-keygen -o $HOME\Documents\engage-backup-key.txt
   ```
5. It prints one line that starts with `Public key: age1...`. **Copy that whole line and send it
   to Claude.** It is the padlock, and it is safe to share.
6. The file `Documents\engage-backup-key.txt` is the **key**. Keep it very safe:
   - Copy it to **two USB sticks**, kept in two different places (for example home and office).
   - In Bitwarden, make a new item "Engage backup private key" and attach the file (or open it in
     Notepad and paste its text into a secure note).
   - Then delete the file from Documents, and empty the Recycle Bin.
   - ⚠️ If this key is lost, **nobody can ever open the backups, not even you**.

If `winget` is not found: download age from
**github.com/FiloSottile/age/releases**. Pick the file ending `windows-amd64.zip`, unzip it, and
run `age-keygen.exe -o ...` from inside that folder.

### Step 6.6 — Uptime alerts (UptimeRobot) ✅ done 27 Nov

> ✅ Account created; first monitor `zuvoora.com`. The Engage monitors are added after deployment.
UptimeRobot checks the website every few minutes and emails you if it stops answering.
1. Go to **uptimerobot.com** → **Register for FREE**. The sign-up page (27 Nov) asks for a
   **"Website to monitor"** first, before the account:
   - **Website to monitor:** type `zuvoora.com`. Nothing of Engage is online yet, and your main
     site is real and yours, so it is a harmless first check. You can delete or keep it later.
   - **Create your account:** the easiest way is the **Google** button with your Gmail. Your
     Google account already has two-factor login, so there is no new password to manage. Or type
     your Gmail, click **Register**, and follow the email link to set a password (saved in
     Bitwarden).
2. If you used email: open the confirmation email and click its link.
3. If you registered by email and password, turn on two-factor login: profile → **Security**. With
   Google sign-in, Google's two-factor login already protects it.
4. Open **Integrations / Alert contacts**. Your email is already there. Add your phone number
   too, if offered for free.
5. **Do not add monitors yet.** There is nothing online to watch. Claude gives you the exact
   addresses after deployment.

### Step 6.7 — Test booking accounts (Cal.com and Calendly) ✅ done 27 Nov

> ✅ Free test accounts with an "Eye test (TEST)" event type. No API keys yet: Claude asks for them
> during staging testing (6F).
These are **pretend clinic calendars** for testing. Never use a real clinic's account for tests.
1. **Cal.com:** go to **cal.com** → **Sign up** (free) with your Gmail. Choose a username such as
   `zuvoora-test`.
   - Open **Event Types** → **New** → title `Eye test (TEST)`, 30 minutes → **Continue** → **Save**.
   - In **Availability**, make sure some weekday hours are open, for example Mon–Fri 9:00–17:00.
2. **Calendly:** go to **calendly.com** → **Sign up** (free) with your Gmail.
   - Create an event type `Eye test (TEST)`, 30 minutes, with weekday hours.
   - Note: connecting Calendly to our app may need a paid Calendly plan for webhooks. Claude
     checks this when staging is live; do not pay for anything now.
3. Save both logins in Bitwarden. **Do not create API keys yet.** Claude tells you when, during
   staging testing.

### Step 6.8 — Two GitHub settings
**6.8a — Put four public values into GitHub** ✅ done 27 Nov
These let GitHub build the app for each database. They are **public** values, not secrets.
1. Go to **github.com** → your repository **ZUVOORA-ENGAGE** → **Settings** (top right of the
   repository) → left menu **Secrets and variables** → **Actions**.
2. Click the **Variables** tab. ⚠️ Not the "Secrets" tab.
3. Click **New repository variable** and add these four, one at a time (Name, then Value, then
   **Add variable**):

   | Name | Value |
   |---|---|
   | `STAGING_SUPABASE_URL` | `https://fjgthmmntjqdcrkajfaf.supabase.co` |
   | `STAGING_SUPABASE_PUBLISHABLE_KEY` | the staging project's **publishable** key (Supabase → project "ZUVOORA ENGAGE" → Project Settings → API Keys; starts `sb_publishable_`) |
   | `PRODUCTION_SUPABASE_URL` | `https://zitwanfosyhtjmfqjlsm.supabase.co` |
   | `PRODUCTION_SUPABASE_PUBLISHABLE_KEY` | the production **publishable** key (Step 6.1b, Job B) |

4. ⚠️ **Never** put a key starting `sb_secret_` into GitHub. The build checks for this and stops.

**6.8b — Make the images downloadable (after the first release; Claude will say when)**
GitHub profile → **Packages** → for each `zuvoora-engage-...` package → **Package settings** →
**Change visibility** → **Public**. The images contain no secrets (decision D8).

> 🛑 **STOP.** Tell Claude which tasks are done (for example "tasks 1–5 done"), and send the
> `age1...` public line from Step 6.5.

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

## Part 8 — Web addresses and the padlock (stage 6D)

**What we are building, in plain words.** When someone types `engage.zuvoora.com`:
1. **Cloudflare** answers first. It shows the visitor the padlock 🔒 and blocks attacks.
2. Cloudflare passes the visit on to **your server**, over a second locked connection.
3. On your server, **Caddy** (the "doorman" program) receives it and hands it to the right part of
   the app.

Three extra locks make sure **only Cloudflare** can talk to your server:
- the **Origin Certificate**, the server's own ID card, which Cloudflare trusts;
- **Authenticated Origin Pulls**, where Cloudflare shows *its* ID card, and Caddy refuses anyone
  without it;
- **Full (strict)**, where Cloudflare refuses to talk to a server whose ID card is wrong.

**Golden rules for this part**
- Do the steps **in order**, and tell Claude after each group (8.1, 8.2, …).
- In Cloudflare, **never touch** the existing records `send.engage`, `resend._domainkey.engage`,
  `rsend.engage` or `_dmarc.engage` (email), nor anything else already there.
- Server commands: **one line at a time**, and run `sudo -v` first (Part 2b).
- The certificate's **private key** goes from Cloudflare → Bitwarden → the server. **Never into the
  chat.**

When this part is finished, the four addresses show a padlock but still say **"502 Bad Gateway"**.
That is correct: the app itself is installed in Part 9 (stage 6E).

---

### Step 8.1 — Make the server's ID card (Cloudflare Origin Certificate) · 5 min
1. Log in at **dash.cloudflare.com** → click **zuvoora.com**.
2. Left menu: **SSL/TLS** → **Origin Server**.
3. Click **Create Certificate**.
4. Choose **"Generate private key and CSR with Cloudflare"**. Private key type: **ECC**.
5. **Hostnames:** Cloudflare pre-fills `*.zuvoora.com` and `zuvoora.com`. **Remove both**: click
   the little x on each. Then type these four, pressing Enter after each:
   ```text
   engage.zuvoora.com
   api-engage.zuvoora.com
   staging-engage.zuvoora.com
   staging-api-engage.zuvoora.com
   ```
   This way the card only works for Engage and nothing else on your domain.
6. **Certificate validity:** 15 years (the default). Click **Create**.
7. You now see two boxes, with **Key format: PEM**:
   - **Origin Certificate** (starts `-----BEGIN CERTIFICATE-----`)
   - **Private Key** (starts `-----BEGIN PRIVATE KEY-----`). ⚠️ **Shown only once.**
8. In **Bitwarden**, create a **Secure note** named **"Engage Cloudflare origin certificate"**.
   Paste the **Origin Certificate** text into it, then add a line `----- KEY -----`, then paste the
   **Private Key** text below it. **Save.** Copy each box with its copy button, so you get every
   line.
9. Only after it is saved in Bitwarden, click **OK** in Cloudflare.

✅ Tell Claude: **"8.1 done"**.

### Step 8.2 — Put the ID card on the server · 10 min
1. In PowerShell: `ssh engage-vps`, then type your key passphrase.
2. Unlock admin commands: `sudo -v`, then the engageadmin password.
3. Make the safe folder (one line):
   ```bash
   sudo install -d -m 700 -o root -g root /opt/zuvoora-engage/proxy /opt/zuvoora-engage/proxy/certs
   ```
4. Open an empty file for the certificate:
   ```bash
   sudo nano /opt/zuvoora-engage/proxy/certs/origin.pem
   ```
   - In Bitwarden, copy **only the certificate part**, from `-----BEGIN CERTIFICATE-----` to
     `-----END CERTIFICATE-----`, including those two lines.
   - **Right-click once** in the PowerShell window to paste.
   - Save: **Ctrl+O**, then **Enter**. Exit: **Ctrl+X**.
5. Same for the private key:
   ```bash
   sudo nano /opt/zuvoora-engage/proxy/certs/origin-key.pem
   ```
   Paste **only** the key part, from `-----BEGIN PRIVATE KEY-----` to
   `-----END PRIVATE KEY-----`. Save (Ctrl+O, Enter) and exit (Ctrl+X).
6. Download Cloudflare's public ID card. It's public, and Claude checked it is genuine: valid
   until 2029.
   ```bash
   sudo curl -fsSL https://developers.cloudflare.com/ssl/static/authenticated_origin_pull_ca.pem -o /opt/zuvoora-engage/proxy/certs/cloudflare-origin-pull-ca.pem
   ```
7. Lock the files so only the administrator can read them:
   ```bash
   sudo sh -c 'chmod 600 /opt/zuvoora-engage/proxy/certs/*.pem'
   (Run it inside `sudo sh -c`, because your normal user cannot see into the locked folder to
   expand `*.pem`.)
   ```
8. Check everything. This prints **no secrets**, only names and dates:
   ```bash
   sudo ls -l /opt/zuvoora-engage/proxy/certs && sudo openssl x509 -in /opt/zuvoora-engage/proxy/certs/origin.pem -noout -subject -enddate && sudo openssl pkey -in /opt/zuvoora-engage/proxy/certs/origin-key.pem -noout && echo "KEY OK"
   ```
   Expected:
   - three files, each starting `-rw-------  1 root root`;
   - a line `subject=... CloudFlare Origin Certificate`;
   - a line `notAfter=` about 15 years ahead;
   - **`KEY OK`**.

✅ Send Claude the output of step 8. It contains no secrets.

### Step 8.3 — Download the app's deployment files to the server · 5 min
The project is public on GitHub, so no password is needed.
1. One line:
   ```bash
   sudo git clone https://github.com/dr-nzube-anthony-anyanwu/ZUVOORA-ENGAGE.git /opt/zuvoora-engage/app
   ```
2. Check:
   ```bash
   sudo git -C /opt/zuvoora-engage/app log --oneline -1
   ```
   It prints one line with a short code and a message. Send it to Claude.

### Step 8.4 — Create the two private networks and start the doorman (Caddy) · 5 min
1. The networks: one line each. These are the fixed "private roads" between the doorman and the
   app.
   ```bash
   sudo docker network create --driver bridge --subnet 10.73.0.0/24 engage-edge-prod
   ```
   ```bash
   sudo docker network create --driver bridge --subnet 10.73.10.0/24 engage-edge-staging
   ```
2. Start Caddy. Use the full path: `/opt/zuvoora-engage` is locked to the administrator, so a
   plain `cd` into it is refused, and that is on purpose.
   ```bash
   sudo docker compose -p engage-proxy -f /opt/zuvoora-engage/app/deploy/proxy/compose.yml up -d --wait
   ```
   It downloads Caddy (about 20 seconds) and should end with `Container engage-proxy Healthy`.
3. Check:
   ```bash
   sudo docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
   ```
   Expected: `engage-proxy`, `Up ... (healthy)`, with ports `80` and `443`.

✅ Send Claude the outputs of steps 2 and 3.

### Step 8.5 — Add the four web addresses (Cloudflare DNS) · 5 min
1. Cloudflare → **zuvoora.com** → **DNS** → **Records** → **Add record**.
2. Fill in, then click **Save**:
   - Type: **A**
   - Name: `engage`
   - IPv4 address: your server's IP, from Bitwarden (it starts with `84.`)
   - Proxy status: **Proxied** (the cloud must be **orange**)
   - TTL: Auto
3. Repeat for `api-engage`, `staging-engage` and `staging-api-engage`: the same IP, **Proxied**.
4. Check the list: four new **A** records with **orange clouds**. The email records are untouched.

### Step 8.6 — Make Cloudflare strict for these four addresses only · 5 min
This sets **Full (strict)** for Engage without changing anything else on `zuvoora.com`.
1. Cloudflare → **zuvoora.com** → left menu **Rules** → **Overview** → **Create rule** →
   **Configuration Rule**. (Or Rules → **Configuration Rules** → **Create rule**.)
2. Rule name: `Engage strict TLS`
3. **If incoming requests match…** choose **Custom filter expression**, then click **Edit
   expression** and paste:
   ```text
   (http.host in {"engage.zuvoora.com" "api-engage.zuvoora.com" "staging-engage.zuvoora.com" "staging-api-engage.zuvoora.com"})
   ```
4. **Then the settings are…**: find **SSL** → click **+ Add** → choose **Strict**.
5. Click **Deploy**.

### Step 8.7 — Make Cloudflare show its ID card (Authenticated Origin Pulls) · 1 min
1. Cloudflare → **SSL/TLS** → **Origin Server**.
2. Find **Authenticated Origin Pulls** and switch it **On**.

This is safe for the rest of your domain: other servers simply ignore Cloudflare's ID card.

### Step 8.8 — Do not let the "bot fighter" block calendars · 1 min
1. Cloudflare → **Security** → **Bots** (sometimes under **Security → Settings**).
2. If **Bot Fight Mode** is **On**, switch it **Off**. It blocks automatic visitors, and that would
   include Cal.com and Calendly sending booking updates to the API. Our app has its own limits.
3. Tell Claude whether it was on or off.

### Step 8.9 — Test the padlocks · 2 min
Open each address in your browser:
- `https://engage.zuvoora.com`
- `https://api-engage.zuvoora.com`
- `https://staging-engage.zuvoora.com`
- `https://staging-api-engage.zuvoora.com`

✅ **Expected:** a padlock 🔒 in the address bar, and a page saying **"Bad gateway"** (error 502).
**That is correct for now:** the doorman works, and the app itself is installed in Part 9.

❌ If you see **"Error 526: Invalid SSL certificate"** or **"525: SSL handshake failed"**, the ID
card is wrong. Redo 8.1–8.2, or ask Claude. If you see **"521"**, Caddy is not running; redo 8.4.

Tell Claude what each of the four showed. Claude also checks from outside that nobody can reach
your server **directly** without Cloudflare.

### Step 8.10 — A login gate in front of the staging dashboard (Cloudflare Access) · 10 min
This makes `staging-engage.zuvoora.com` ask for a code sent to **your** email before anything
shows. It stops strangers from seeing the practice copy.
1. Cloudflare dashboard → left menu **Zero Trust**. The first time, it asks you to:
   - choose a **team name**, for example `zuvoora`;
   - choose the **Free** plan.
   ⚠️ If it insists on a payment card for the Free plan, **stop and tell Claude**. Do not pay for
   anything.
2. In Zero Trust: **Access** → **Applications** → **Add an application** → **Self-hosted**.
3. Application name: `Engage staging dashboard`. Session duration: **24 hours**.
4. **Public hostname / Application domain:** subdomain `staging-engage`, domain `zuvoora.com`.
5. **Policy:** name `Founder only`, Action **Allow**, rule **Include → Emails →** your Gmail address.
6. **Login methods:** **One-time PIN** (a code sent to your email).
7. Save. Then open `https://staging-engage.zuvoora.com` in a private browser window. It should ask
   for your email, send you a code, and after the code show the "Bad gateway" page. That is
   correct for now.

Only the staging **dashboard** gets this gate. The staging **API** must stay open, because the
chat widget and the calendars need to reach it.

✅ **Part 8 is done when** 8.1–8.10 are finished and Claude has confirmed the outside checks.

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
