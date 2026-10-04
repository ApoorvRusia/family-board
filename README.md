# Family Board

A shared, mobile-first family coordination board — groceries, to-dos, plans, and gifts in one place, with real-time sync across everyone's phones. Installable as a phone app (PWA).

## Features

- **Four boards** — 🛒 Grocery List, ✅ Home To-Dos, 📅 Plans, 🎁 Gifts — with live Firestore sync (no refresh needed)
- **Google sign-in** — "Added by" attribution comes straight from each person's Google profile
- **Approval-gate membership** — new people sign in, tap *Request access*, and the board owner approves them from ⚙️ Settings. Pending requests show a badge count
- **Invite kit** — copyable board link, native phone share sheet, and QR code, all inside Settings
- **✨ AI add** — dictate or type ("milk and eggs, fix the bulb in Ruhaan's room Friday"), Gemini parses it into the right fields, you preview and remove items, then add. Supports relative dates and private gifts
- **🔒 Private gifts** — gift ideas only you can see, enforced by Firestore rules (`ownerUid`-gated `privateGifts` collection)
- **🔔 Due-date notifications** — in-app 🔔 bell with a "Coming up" sheet (overdue / due today / due tomorrow), plus push digests: a morning rundown of what's due today and an evening heads-up for tomorrow. Only sent when there's something due
- **🔁 Recurring to-dos** — set a to-do to repeat every N days (Daily / 2 / 3 / Weekly); checking it off rolls the due date forward so it never goes stale. Anyone in the house can do it — whoever checks it off advances the schedule
- **🎂 Birthdays** — a Birthdays tab (name + date, sorted by next upcoming); the 🔔 bell lists birthdays in the next 7 days, and the morning push digest reminds you on the day and a week out
- **📌 Pinned family note** — one shared banner under the header, visible on every tab, for household announcements ("Mom's visiting Friday"). Anyone approved can edit it; updates appear live with who wrote it and when
- **Per-user assistant links** — each member can link their own AI assistant behind the 💬 button

## Tech

- Frontend: single-file vanilla JS app (`public/index.html`), PWA with manifest + service worker
- Backend: Firebase Hosting, Firestore, Firebase Auth (Google provider) — all on the free Spark plan
- AI parsing: Gemini API (`gemini-3.5-flash-lite`), called client-side
- Security: Firestore rules require an approved `members/{uid}` record for all shared collections; private gifts are owner-only and the owner field is immutable

## 🔔 Notifications

Two layers:

- **In-app** — a 🔔 bell in the header shows how many open to-dos / upcoming plans are overdue, due today, or due tomorrow. Tapping it opens a "Coming up" sheet grouped by urgency. No setup needed.
- **Push digests** — a morning digest (~8 AM, items due today plus overdue to-dos) and an evening heads-up (~8 PM, items due tomorrow), delivered as phone notifications even with the app closed. A digest is only sent when there's actually something due.

**Routing:** an item assigned to someone notifies the assignee plus whoever created it. Unassigned items (or plans with an empty "who's in") notify every approved member. Each person can toggle the morning/evening digests and choose "only items involving me" under ⚙️ Settings → Notifications.

**Setup (push):**

1. Firebase Console → Project settings → **Cloud Messaging** → generate a **Web Push certificate**, then paste the key as `VAPID_KEY` in `public/index.html`.
2. Each member opens ⚙️ Settings → **Enable notifications** on their phone (registers that device's token). iPhones need the app installed to the home screen for push to work.
3. Run the sender on a schedule (it needs `service-account.json` next to it):
   ```
   # morning digest ~8 AM Pacific, evening heads-up ~8 PM Pacific
   0 8 * * * TZ=America/Los_Angeles /path/to/notify.py --slot morning
   0 20 * * * TZ=America/Los_Angeles /path/to/notify.py --slot evening
   ```
   Preview without sending: `notify.py --slot morning --dry-run`.
4. Deploy hosting (`deploy.py`) and rules (`deploy_rules.py`) so the new service worker and rule changes go live.

Private gifts never appear in digests. Stale device tokens are pruned automatically when FCM reports them unregistered.

## Run your own

1. Create a Firebase project, enable **Authentication** (Google provider), **Firestore**, and **Hosting**.
2. In `public/index.html`, paste your Firebase web config into `firebaseConfig` and your Gemini API key into `GEMINI_API_KEY` (get one at https://aistudio.google.com/apikey — leave empty to disable AI add). Restrict the key to your site's domain in Google Cloud Console.
3. Create a service account with the needed roles, download its JSON key as `service-account.json` next to the scripts (**never commit this file** — it's gitignored).
4. Deploy hosting: `python3 deploy.py`
5. Deploy Firestore rules: `python3 deploy_rules.py`
6. Make yourself the owner: in Firestore, create `members/<your-uid>` with `{ status: 'approved', role: 'owner', name, email }`. Everyone else joins via *Request access* and you approve them from ⚙️ Settings.

`fb.py` is a small CLI for reading/writing the board from a terminal or an assistant (uses the service-account key, bypassing app rules):

```
fb.py [--key PATH] list groceries|todos|plans|gifts
fb.py [--key PATH] add groceries --item "Milk" --quantity "1 gallon"
fb.py [--key PATH] done groceries <doc-id>
```

Set `FAMILY_BOARD_PROJECT` / `FAMILY_BOARD_SITE` env vars to point the scripts at your own project instead of the defaults.
