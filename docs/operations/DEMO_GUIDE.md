# ZUVOORA Engage — Demo Guide (step by step)

This guide walks you through showing ZUVOORA Engage **from start to finish** on your own computer:
starting it, preparing a sample clinic, and then demonstrating everything a patient, a
receptionist, a clinic owner and ZubeVision can do. Every step says **what to click**, **what you
will see**, and **what to say** to your audience.

Everything here is a **local demonstration** with a sample clinic called *Lumen Eye Clinic
(sample)*. It uses made-up data only. Never type real patient information into a demo.

---

## Contents
1. [The story you are telling](#1-the-story-you-are-telling)
2. [Before the demo day (one time only)](#2-before-the-demo-day-one-time-only)
3. [Start everything (each demo)](#3-start-everything-each-demo)
4. [Prepare the sample clinic](#4-prepare-the-sample-clinic)
5. [Set up your browser windows](#5-set-up-your-browser-windows)
6. [The demo, act by act](#6-the-demo-act-by-act)
   - [Act 1 — The public website](#act-1--the-public-website-3-minutes)
   - [Act 2 — The patient's experience](#act-2--the-patients-experience-6-minutes)
   - [Act 3 — The front desk (receptionist)](#act-3--the-front-desk-receptionist-4-minutes)
   - [Act 4 — The clinic owner or manager](#act-4--the-clinic-owner-or-manager-8-minutes)
   - [Act 5 — ZubeVision's platform console](#act-5--zubevisions-platform-console-5-minutes)
   - [Act 6 — Closing: safety, trust and next steps](#act-6--closing-safety-trust-and-next-steps-2-minutes)
7. [Optional extras](#7-optional-extras)
8. [After the demo: stop, reset, run again](#8-after-the-demo-stop-reset-run-again)
9. [If something goes wrong](#9-if-something-goes-wrong)
10. [Questions your audience may ask](#10-questions-your-audience-may-ask)
11. [One-page cheat sheet](#11-one-page-cheat-sheet)

---

## 1. The story you are telling

**One sentence:** *ZUVOORA Engage turns an eye clinic's website into a digital front desk that
answers patients' questions, books appointments and hands over to the clinic team — using only
information the clinic has approved.*

**The story (say this at the start):**
> "It's 10:47 at night. Someone visits your clinic's website. They want to know if you do glaucoma
> screening, what an eye test costs, and whether they can book for Saturday. Your reception team
> has gone home. Today, they see a phone number — and maybe they go elsewhere. Let me show you
> what happens with ZUVOORA Engage."

**Who sees what in this demo:**

| Person | What they use | What they care about |
|---|---|---|
| A patient | The chat on the clinic's website | Quick, clear answers; easy booking; reaching a person |
| A receptionist | The dashboard: Inbox and Appointments | Call-back requests and bookings in one place |
| The clinic owner or manager | The whole dashboard | Control over what is said, results, cost, team |
| ZubeVision (you) | The platform console | Clinics, plans, demo requests |

**Total time:** about 25–30 minutes. You can shorten it by skipping Acts 4 or 5.

---

## 2. Before the demo day (one time only)

Do this once, a day before your first demo, so nothing surprises you.

### 2.1 Check your computer
1. Make sure **Docker Desktop** is installed. Open it and wait until it says it is **running**.
2. Make sure the project has had its **first-time setup** (installing everything). If you are not
   sure, follow [README → First-time setup](../../README.md#first-time-setup). You only ever do that
   once per computer.

### 2.2 Put an authenticator app on your phone
The ZubeVision platform console is protected by **two-factor authentication** (a 6-digit code from
your phone). Install one of these free apps on your phone:
- Google Authenticator, Microsoft Authenticator or Authy.

You will scan a QR code with it during the demo (Act 5).

### 2.3 Do a full practice run
Go through this whole guide once on your own. It takes about 45 minutes the first time and makes
the real demo smooth.

---

## 3. Start everything (each demo)

You need **six PowerShell windows** (terminals). In VS Code: menu **Terminal → New Terminal**, and
use the **+** button for more. Give each one a job, in this order. Wait for each to be "ready"
before starting the next.

> Tip: if your SSD gets a different drive letter, replace `D:` below with the right letter.

### Terminal 1 — the database
```powershell
cd D:\technologies\ZUVOORA-ENGAGE
npm run db:start
```
**Ready when:** it finishes and shows some local addresses (30–60 seconds).

### Terminal 2 — a practice booking calendar
This is a pretend Cal.com calendar on your computer, so you can demo booking without the internet
and without touching a real calendar.
```powershell
cd D:\technologies\ZUVOORA-ENGAGE
npm run demo:calendar
```
**Ready when:** the window stays open with no error (it prints nothing — that is normal).

### Terminal 3 — the API (the "engine")
The first line tells the API to use the practice calendar from Terminal 2.
```powershell
cd D:\technologies\ZUVOORA-ENGAGE\apps\api
$env:CALCOM_API_URL = "http://127.0.0.1:4181"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8073
```
**Ready when:** it shows `Application startup complete`.

### Terminal 4 — the website and dashboard
```powershell
cd D:\technologies\ZUVOORA-ENGAGE\apps\web
npm run dev
```
**Ready when:** it shows `Ready`. The first page you open may take a few seconds to appear.

### Terminal 5 — the background worker (emails and reminders)
```powershell
cd D:\technologies\ZUVOORA-ENGAGE\apps\api
.\.venv\Scripts\python.exe -m app.worker
```
**Ready when:** the window stays open. On this computer, emails are **not really sent** — the
worker writes a line in this window each time it would send one (you can show this in Act 3).

### Terminal 6 — prepare the clinic and open the sample clinic website
Continue in section 4.

---

## 4. Prepare the sample clinic

In **Terminal 6**:
```powershell
cd D:\technologies\ZUVOORA-ENGAGE
npm run demo:setup
```
After a few seconds you will see a box like this:

```
ZUVOORA Engage - local demo is ready (clinic created)
Accounts (synthetic, local only - passwords change every time you run this):

  ZubeVision platform admin
    email:    demo.admin@example.com
    password: ••••••••••••••

  Clinic owner (Lumen Eye Clinic)
    email:    lumen.owner@example.com
    password: ••••••••••••••

  Receptionist (Lumen Eye Clinic)
    email:    lumen.reception@example.com
    password: ••••••••••••••
```

1. **Copy the three emails and passwords into a note** (for example Notepad). You will need them.
   The passwords are new every time you run `demo:setup`.
2. What this command did for you:
   - created the three demo accounts;
   - created **Lumen Eye Clinic (sample)** on the **Professional** plan, already active;
   - published its profile, a branch with opening hours, 4 services with prices and 6 common
     questions;
   - switched the chat on and allowed it on a sample clinic website on your computer.

Now start the sample clinic website, still in **Terminal 6**:
```powershell
npm run demo:site
```
**Ready when:** it shows `Sample clinic website: http://lumen-eye-clinic.localhost:4180`.

> The sample website uses the name `lumen-eye-clinic.localhost`. Browsers automatically treat any
> name ending in `.localhost` as "this computer", so it works without internet. On real clinic
> websites, the clinic proves the website is theirs with a DNS record instead (shown in Act 4).

### Connect the practice calendar (2 minutes, before your audience arrives)
Online booking needs the clinic's calendar connected. Do this once (it stays connected for later
demos unless you reset everything):
1. Open `http://localhost:3073/login` and sign in as **lumen.owner@example.com**.
2. Click **Lumen Eye Clinic (sample)**, then **Scheduling** in the left menu.
3. **Scheduling service:** Cal.com. **API key:** `cal_e2e_test_key_0000000001` (the practice
   calendar's key). Click **Connect**. You see **Connected**.
4. Under **Appointment types patients can book**, tick **Offer Eye exam**, type
   `Comprehensive eye examination` in **Name patients see for Eye exam**, and click **Save
   appointment types**. You see *"Appointment types saved."*
5. Click **Sign out** (bottom of the left menu).

---

## 5. Set up your browser windows

The system keeps **one signed-in person per browser window type**. To show different people side
by side, use separate windows:

| Window | How to open it | Who you will be |
|---|---|---|
| **A** | Chrome, normal window | The patient (sample clinic website) and the public website |
| **B** | Chrome, **Incognito** window (Ctrl+Shift+N) | The clinic owner |
| **C** | **Microsoft Edge**, normal window | The receptionist |
| **D** | Edge, **InPrivate** window (Ctrl+Shift+N) | ZubeVision platform admin |

Open these addresses now so they are ready:
- Window A: `http://localhost:3073` (public website) and a second tab
  `http://lumen-eye-clinic.localhost:4180` (sample clinic website)
- Windows B, C and D: `http://localhost:3073/login`

> Make the browser zoom 110–125% (Ctrl and +) if you are presenting on a projector.

---

## 6. The demo, act by act

### Act 1 — The public website (3 minutes)

**Window A**, tab `http://localhost:3073`.

1. **Show the top of the page.** Read the headline:
   *"Your clinic is caring for patients. Who's welcoming the next one?"*
   - **Say:** "This is the ZUVOORA Engage website. It explains the product to clinic owners."
2. **Scroll slowly** through the sections and point out:
   - **The story** ("10:47 PM") — the problem every clinic recognises.
   - **The challenge** and **the solution** — your website already exists; Engage adds the front
     desk.
   - **Features** — answers, approved knowledge, appointments, human support, analytics, team.
3. **Open a few questions** in the dark section *"Powerful technology shouldn't mean giving up
   control."* Click **"Could it give patients incorrect medical advice?"**.
   - **Say:** "We answer the worries clinics have before they ask."
4. **Try the scripted demo** in *"See the experience your patients could have."* Click
   **"My eye suddenly went dark — what should I do?"**.
   - **You see:** urgent guidance, and a note "never a diagnosis".
5. **Show Plans.** Four plans: Essentials, Professional, Premium, Full ZUVOORA.
   - **Say:** "Every plan includes the assistant and live booking. WhatsApp and voice are marked
     *Coming soon* — we only sell what works today."
6. **Request a demo** (this is how real clinics will contact you):
   1. Click **Request a demo** (top right).
   2. Fill in: Your name `Ada Example`, Clinic `Sample Optics`, Work email `ada@example.com`,
      City `Abuja`, Interested in `Joining the pilot programme`.
   3. Tick **"I agree that ZubeVision Technologies Ltd. may contact me…"**.
   4. Click **Send request**.
   - **You see:** "Thank you — we've received your request." You will find it again in Act 5.

### Act 2 — The patient's experience (6 minutes)

**Window A**, tab `http://lumen-eye-clinic.localhost:4180`.

- **Say:** "This is a clinic's normal website. They added Engage by pasting **one line of code**.
  Now I'm a patient, at night."

1. Click the round **Chat with us** button at the bottom right.
   - **You see:** a chat window with the clinic's name and a greeting.
2. **Ask about opening hours.** Type and press **Send**:
   `What time do you open on Saturday?`
   - **You see:** *"Lumen Eye Clinic — Victoria Island: open 09:00–13:00 on Saturday …"*
   - **Say:** "That answer comes straight from the hours the clinic published — including
     holidays."
3. **Ask about prices:** `How much is an eye examination?`
   - **You see:** the clinic's services with prices (₦25,000 for the eye examination, and others).
4. **Ask a common question:** `Do I need someone to drive me home after dilation?`
   - **You see:** the clinic's own approved answer, word for word.
5. **Show safety — an emergency:** `My eye suddenly went dark, what should I do?`
   - **You see:** *"This sounds like it could be urgent. I can't assess symptoms…"* plus the
     clinic's emergency instructions and phone number.
   - **Say:** "Emergencies always get safety guidance first. It never tries to diagnose."
6. **Show safety — medical advice:** `Which eye drops should I use for dry eyes?`
   - **You see:** *"I'm not able to give medical advice… A clinician at Lumen Eye Clinic can
     help…"*
   - **Say:** "It's an administrative assistant. Medical questions go to your clinicians."
7. **Book an appointment.**
   1. Click **Book an appointment** (under the message box).
   2. Choose **Comprehensive eye examination · 30 min**.
   3. Choose a time (times are shown in your time zone).
   4. Fill in **Full name** `Ada Demo`, **Email** `ada.demo@example.com`, tick the consent box.
   5. Click **Book this time**.
   - **You see:** *"Booked: Comprehensive eye examination on … A confirmation email is on its
     way."*
   - **Say:** "The booking went into the clinic's own calendar. We only say *booked* after the
     calendar confirms it — never before."
8. **Show honesty — something the clinic hasn't published:** `Do you sell hearing aids?`
   - **You see:** *"I'm sorry, I don't have that information… Would you like the clinic team to
     contact you?"* and a short form **"Ask the clinic team to contact you"** opens.
   - **Say:** "It doesn't make things up. When it doesn't know, it offers a person."
9. **Ask for a call-back.** In that form: **Phone** `+234 801 000 0000`, tick **"I agree that the
   clinic may use these details…"**, click **Send my details**.
   - **You see:** a message that the clinic team has your details.
   - (If the form is not open, click **Contact the clinic team** under the message box first — it
     is always available.)
10. Point at the small line at the bottom of the chat: *"Automated assistant for clinic
    information — not medical advice…"*.

### Act 3 — The front desk (receptionist) (4 minutes)

**Window C** (Edge), `http://localhost:3073/login`.

1. Sign in with **lumen.reception@example.com** and its password from your note. Click **Sign in**.
2. On **Your clinics**, click **Lumen Eye Clinic (sample)**.
   - **Say:** "This is what the front desk sees in the morning."
3. Click **Inbox** in the left menu.
   - **You see:** the call-back request from Act 2, with the phone number. The **Inbox** item in
     the menu shows a red number for new requests.
4. Open the request by clicking **Visitor (no name given)** (or the name the patient typed).
   - **You see:** the contact card (phone link you can tap on a phone) and the **whole
     conversation**, including how each answer was produced.
5. Click **I'm handling this**, then (after "calling" the patient) **Mark as resolved**.
   - **Say:** "Nothing falls through the cracks: new, in progress, resolved."
6. Click **Appointments** in the left menu.
   - **You see:** Ada Demo's booking with its time and status.
   - **Say:** "Bookings made through the website chat appear here automatically."
7. Show the **receptionist's limits**: open **Services** — the forms are greyed out with
   *"You have read-only access."* There is no **Plan & usage** or **Analytics** for receptionists.
   - **Say:** "Each person only gets what their role needs."
8. (Optional) Show **Terminal 5** (the worker): a line like
   `email_not_sent mode=log … key=booking_confirmation/…` appeared when the patient booked.
   - **Say:** "In real use, that's the patient's confirmation email, plus reminders before the
     appointment. Here on the laptop we only log them."

### Act 4 — The clinic owner or manager (8 minutes)

**Window B** (Chrome Incognito), `http://localhost:3073/login`.

1. Sign in with **lumen.owner@example.com** and its password. Open **Lumen Eye Clinic (sample)**.
2. **Overview.**
   - **You see:** *"Setup checklist · 5 of 6"* with a progress bar, and the line *"Let's teach
     Engage about your clinic."*
   - **Say:** "Getting started is a short checklist: profile, hours, services, questions,
     documents, website."
3. **Change an answer live — the best moment of the demo.**
   1. Click **FAQs**. Open **"Is there parking at the clinic?"**.
   2. Change the answer to `Yes, free parking for 20 cars behind the building, plus street parking.`
   3. Click **Save draft**, then click **Publish revision …** (the button shows the revision
      number).
   4. Go to **Window A**, in the chat ask: `Is there parking at the clinic?`
   - **You see:** the new answer immediately.
   - **Say:** "You stay in control of every word. Drafts are never shown to patients — only
     what you publish."
4. **Branches & hours.** Open the branch and show the opening-hours editor (each day, and a
   holiday on 25 December). (You don't need to change anything.)
5. **Services.** Show the four services with prices and durations.
6. **Documents** — upload clinic material:
   1. Click **Documents**. Title `Preparing for your visit`.
   2. Choose a small text file (for example a `.txt` you create with Notepad containing a few
      sentences about what to bring).
   3. Click **Upload**. You land on the document page with **Awaiting review**.
   4. Click **Review**, read the extracted text, click **Approve and publish**.
   - **Say:** "PDF, Word and text work. Photos and scanned price lists can be read by AI too
     (see *Optional extras*). Nothing is used until someone approves it."
7. **Website domains.** Show `lumen-eye-clinic.localhost` as **verified**.
   - **Say:** "For a real clinic website, we show a DNS record to add once. The chat then only
     works on that website — nobody can copy it onto another site."
   - (Optional) Type a host name like `www.yourclinic.com` and click **Add domain** to show the
     exact DNS record a clinic would add. Then click **Remove** to tidy up.
8. **Chat widget.** Show **Status** (on), the **Embed snippet** (the one line a clinic pastes) and
   the **Greeting**. Change the greeting, click **Save greeting**, and reopen the chat in Window A
   to show the new greeting.
9. **Scheduling.** Show **Connected** (you connected the practice calendar in section 4), the
   appointment types patients can book, and the reminder setting.
   - **Say:** "The clinic keeps its own Cal.com calendar — it just pastes its Cal.com key here and
     chooses which appointment types patients may book. Engage only offers times that are really
     free, and the API key is stored encrypted and never shown again."
10. **Team.** Show the members. Invite someone:
    1. **Email** `new.staff@example.com`, **Role** `Receptionist`, click **Send invitation**.
    2. Open **Mailpit** at `http://127.0.0.1:54324` — the invitation email is there.
    - **Say:** "Accounts are by invitation only. There is no public sign-up."
11. **Analytics.** Show the counts (conversations, how questions were answered, call-backs,
    bookings) and, because this clinic is on Professional, **Daily activity** and **Topics the
    assistant could not answer** (topics appear after the same thing is asked at least twice).
    - **Say:** "You see what patients ask, what was answered, and what to add next."
12. **Plan & usage.** Show the plan, what's included, and this month's usage against limits.

### Act 5 — ZubeVision's platform console (5 minutes)

**Window D** (Edge InPrivate), `http://localhost:3073/login`.

1. Sign in with **demo.admin@example.com** and its password.
2. **Two-factor authentication (first time only):**
   1. You are taken to **Two-factor authentication** with a **QR code**.
   2. On your phone, open your authenticator app → add account → scan the QR code.
   3. Type the **6-digit code** from the app into **Code** and click **Verify**.
   - Next time you sign in, you only type the code (no QR code).
   - **Say:** "ZubeVision staff always need a second factor."
3. On **Your clinics**, click **Open platform tools**.
4. **Clinics & plans.** Show **This month**: paying clinics, estimated monthly revenue, AI cost, and
   each clinic's usage.
5. **Create a new clinic** (this is how you onboard a real clinic):
   1. In **Create a clinic**: **Clinic name** `Bright Vision Optics`, **Owner's email**
      `owner@brightvision.example.com`, **Starting plan** `Essentials`.
   2. Click **Create clinic**. **You see:** *"Bright Vision Optics created. The owner has been
      emailed an invitation."*
   3. Open **Mailpit** (`http://127.0.0.1:54324`): the invitation email *"You have been invited to
      ZUVOORA Engage"* is there. (The owner would click it, set a password and start the checklist.)
   4. Find **Bright Vision Optics** further down: it shows **Clinic pending**. Click **Activate
      clinic** → it shows **Clinic active**.
   - **Say:** "We set up the clinic, the owner gets an email, and we switch it on when they're
     ready."
6. **Plans change features — live.**
   1. In the **Lumen Eye Clinic (sample)** box, change **Plan** to `Essentials` and click **Save
      subscription**.
   2. In **Window B** (owner), refresh **Plan & usage**: reminders now show *Not in this plan*.
      **Scheduling** no longer offers the 2-hour reminder option.
   3. Change it back to `Professional` and save.
   - **Say:** "Plans are enforced by the system itself — not just hidden buttons."
7. **Plan catalogue.** Show the four plans, their limits and prices (prices are for your records;
   no payment is taken).
8. **Demo requests.** Click **Demo requests**: the request from Act 1 is there with the contact
   details. Change **Status** to `Contacted` and click **Save status**.
   - **Say:** "Every enquiry from the website lands here. Contact details never go out by email."

### Act 6 — Closing: safety, trust and next steps (2 minutes)

Summarise in your own words:
- **Answers only from what the clinic approved**; it says "I don't know" instead of guessing.
- **Emergencies first, no medical advice**, a person always one click away.
- **Bookings in the clinic's own calendar**, confirmed only when the calendar confirms.
- **Each clinic's information is kept separate** from every other clinic, enforced in the
  database and tested automatically.
- **Invitation-only accounts, roles, two-factor authentication for administrators**, and a record
  of important changes.
- **Honest roadmap:** WhatsApp, voice and the wider ZUVOORA ecosystem are coming, not claimed.

Then invite them to the **pilot programme** and to **Request a demo** on the website.

---

## 7. Optional extras

### 7.1 Turn on real AI answers
By default the assistant uses the clinic's published information **without** an AI model (that is
what you saw above). To also show AI answers (for example, answering from approved documents in
natural language):
1. Open `apps\api\.env` in VS Code.
2. Add two lines (use your **own** OpenRouter key with a small spending limit; never share it):
   ```
   AI_ENABLED=true
   OPENROUTER_API_KEY=your-own-key
   ```
3. Stop the API (Ctrl+C in Terminal 3) and start it again with the same commands.
- Costs are tiny (fractions of a US cent per answer) and capped: $0.20 per clinic per day,
  $0.50 per day and $2 per month for the whole platform.
- To switch off again, set `AI_ENABLED=false` and restart the API.

### 7.2 Read photos and scanned documents with AI
Same as 7.1, but add `AI_VISION_ENABLED=true` (and the key). Then in **Documents** you can upload
a photo (`.jpg`, `.png`) of a price list. The text is read by AI, marked **Read by AI**, and still
needs approval. Use a made-up price list — never anything with patient information.

### 7.3 Use a real Cal.com account instead of the practice calendar
Start Terminal 3 **without** the `$env:CALCOM_API_URL` line and connect with a real Cal.com API key
in **Scheduling**. Bookings will then appear in that real calendar — use a test account.

---

## 8. After the demo: stop, reset, run again

**Stop everything:** press **Ctrl+C** in terminals 2, 3, 4, 5 and 6. Then in Terminal 1:
```powershell
npm run db:stop
```
Your local data is kept for next time.

**Next demo:** start again from [section 3](#3-start-everything-each-demo). Running
`npm run demo:setup` again **does not** create a second clinic — it just gives the three demo
accounts **new passwords** (copy them again). Conversations, bookings and changes from earlier
demos are still there.

**Start completely fresh** (removes ALL local data, including anything you created by hand —
local only, never the cloud):
```powershell
cd D:\technologies\ZUVOORA-ENGAGE
npm run db:reset
npm run demo:setup
```
After a reset, the platform admin sets up two-factor again (a new QR code). In your authenticator
app, delete the old "ZUVOORA Engage" entry first.

---

## 9. If something goes wrong

| What you see | What to do |
|---|---|
| `demo:setup` says *"The local database is not running"* | Start Terminal 1 (`npm run db:start`) and wait until it finishes. |
| `demo:setup` says *"The API is not running"* | Start Terminal 3 and wait for `Application startup complete`. |
| The sample clinic website says *"No demo clinic"* | Run `npm run demo:setup` first, then reload the page. |
| The chat button never appears on the sample website | Check Terminal 3 (API) is running; reload the page. Use the exact address `http://lumen-eye-clinic.localhost:4180`. |
| The chat says *"This chat is not available on this website"* | You opened a different address (for example `localhost:4180`). Use `http://lumen-eye-clinic.localhost:4180`. |
| **Book an appointment** is missing in the chat | The calendar is not connected yet: do [Connect the practice calendar](#connect-the-practice-calendar-2-minutes-before-your-audience-arrives) and keep Terminal 2 running. |
| Connecting the calendar says the key was not accepted | Terminal 2 (`npm run demo:calendar`) must be running, and Terminal 3 must have been started **after** the `$env:CALCOM_API_URL` line. |
| Dashboard shows *"The Engage service is unavailable"* | Terminal 3 (API) stopped — start it again. |
| *"Port … already in use"* | A previous copy is still running. Close old terminals, or see [Local Development → Troubleshooting](LOCAL_DEVELOPMENT.md#troubleshooting). |
| Sign-in fails | Passwords change every time you run `demo:setup` — use the newest ones. |
| The two-factor code is refused | Make sure your phone's clock is set automatically; type the current code. |
| Platform tools say *"need an MFA-verified platform administrator"* | Sign out and sign in again, then enter the 6-digit code. |
| An answer is the polite *"I don't have that information"* | That is correct behaviour when the clinic hasn't published it. Rephrase closer to the FAQ wording, or add an FAQ (Act 4 step 3). |

---

## 10. Questions your audience may ask

- **"Does it replace my receptionist?"** No — it handles routine website questions and booking, and
  hands everything else to your team through the Inbox.
- **"Could it say something wrong about medicine?"** It is built not to give medical advice at
  all: emergencies get safety guidance, medical questions go to your clinicians, and answers come
  only from what you approved.
- **"Do we need a new website?"** No. You verify your website once and paste one line of code.
- **"Can another clinic see our data?"** No. Each clinic's data is separated by the database
  itself, and this is tested automatically.
- **"Which calendar do we need?"** Cal.com today (Calendly is built and being tested).
- **"WhatsApp? Voice?"** On the roadmap, marked *Coming soon*; we only promise what works.
- **"What does it cost?"** Four plans; pricing is shared during the demo (see the plan catalogue).
- **"Where is our data?"** In a managed, access-controlled database; the hosting set-up for live
  clinics is confirmed before launch. AI (if switched on) goes through providers that do not keep
  or train on the data. (A formal privacy notice is being prepared.)

---

## 11. One-page cheat sheet

**Start (6 terminals):**
1. `npm run db:start` (repo root)
2. `npm run demo:calendar` (repo root)
3. `apps\api`: `$env:CALCOM_API_URL = "http://127.0.0.1:4181"` then
   `.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8073`
4. `apps\web`: `npm run dev`
5. `apps\api`: `.\.venv\Scripts\python.exe -m app.worker`
6. repo root: `npm run demo:setup` (copy passwords) then `npm run demo:site`
7. Once: sign in as the owner → **Scheduling** → connect the practice calendar → offer Eye exam

**Addresses:**

| What | Address |
|---|---|
| Public website | http://localhost:3073 |
| Sign in | http://localhost:3073/login |
| Sample clinic website (patient chat) | http://lumen-eye-clinic.localhost:4180 |
| Mailpit (local emails) | http://127.0.0.1:54324 |
| Supabase Studio (local database) | http://127.0.0.1:54323 |

**Accounts:** `demo.admin@example.com` (platform, needs authenticator app),
`lumen.owner@example.com` (owner), `lumen.reception@example.com` (receptionist) — passwords from
`demo:setup`.

**Practice calendar key:** `cal_e2e_test_key_0000000001`

**Chat questions that show the value:**
1. `What time do you open on Saturday?`
2. `How much is an eye examination?`
3. `Do I need someone to drive me home after dilation?`
4. `My eye suddenly went dark, what should I do?`
5. `Which eye drops should I use for dry eyes?`
6. **Book an appointment** → Comprehensive eye examination
7. `Do you sell hearing aids?` → call-back form

**Stop:** Ctrl+C in terminals 2–6, then `npm run db:stop`.
