# Family Board

A shared, mobile-first family coordination board — groceries, to-dos, plans, and gifts in one place, with real-time sync across everyone's phones. Installable as a phone app (PWA).

## Features

- **Four boards** — 🛒 Grocery List, ✅ Home To-Dos, 📅 Plans, 🎁 Gifts — with live Firestore sync (no refresh needed)
- **Google sign-in** — "Added by" attribution comes straight from each person's Google profile
- **Approval-gate membership** — new people sign in, tap *Request access*, and the board owner approves them from ⚙️ Settings. Pending requests show a badge count
- **Invite kit** — copyable board link, native phone share sheet, and QR code, all inside Settings
- **✨ AI add** — dictate or type ("milk and eggs, fix the bulb in Ruhaan's room Friday"), Gemini parses it into the right fields, you preview and remove items, then add. Supports relative dates and private gifts
- **🔒 Private gifts** — gift ideas only you can see, enforced by Firestore rules (`ownerUid`-gated `privateGifts` collection)
- **Per-user assistant links** — each member can link their own AI assistant behind the 💬 button

## Tech

- Frontend: single-file vanilla JS app (`public/index.html`), PWA with manifest + service worker
- Backend: Firebase Hosting, Firestore, Firebase Auth (Google provider) — all on the free Spark plan
- AI parsing: Gemini API (`gemini-3.5-flash-lite`), called client-side
- Security: Firestore rules require an approved `members/{uid}` record for all shared collections; private gifts are owner-only and the owner field is immutable

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
