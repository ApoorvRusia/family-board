#!/usr/bin/env python3
"""Family Board due-date digest sender (push via FCM).

Run one slot per cron invocation:
  notify.py --slot morning   # items due today (+ overdue todos)   ~8 AM PT
  notify.py --slot evening   # items due tomorrow                  ~8 PM PT

Only members who actually have something due get a message -- no empty
digests. Routing per item:
  - todo with assignedTo  -> assignee + creator
  - todo with no assignee -> every approved member
  - plan with whoIn       -> those members + creator
  - plan with no whoIn    -> every approved member

Per-member prefs live in members/{uid}.notifyPrefs
  { morning: true, evening: true, onlyMine: false }  (defaults when absent)
Device tokens live in members/{uid}.fcmTokens (array). Tokens FCM reports
as UNREGISTERED are pruned automatically.

Auth: service-account OAuth (same key as fb.py; gitignored, never committed).
Project overridable via FAMILY_BOARD_PROJECT. Use --dry-run to preview.
"""
import json
import os
import re
import sys
import urllib.request
import urllib.error
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fb  # noqa: E402  (auth + Firestore REST helpers)

PROJECT = os.environ.get('FAMILY_BOARD_PROJECT', 'family-board-25583')
KEY_PATH = os.environ.get('FAMILY_BOARD_KEY',
                          os.path.join(HERE, 'service-account.json'))
PT = ZoneInfo('America/Los_Angeles')
FCM_URL = f'https://fcm.googleapis.com/v1/projects/{PROJECT}/messages:send'


def fv_parse(v):
    if 'stringValue' in v:
        return v['stringValue']
    if 'booleanValue' in v:
        return v['booleanValue']
    if 'integerValue' in v:
        return int(v['integerValue'])
    if 'doubleValue' in v:
        return float(v['doubleValue'])
    if 'arrayValue' in v:
        return [fv_parse(x) for x in v['arrayValue'].get('values', [])]
    if 'mapValue' in v:
        return {k: fv_parse(x) for k, x in v['mapValue'].get('fields', {}).items()}
    return None


def doc_fields(doc):
    return {k: fv_parse(v) for k, v in doc.get('fields', {}).items()}


def first_name(n):
    n = (n or '').strip()
    return n.split()[0].lower() if n else ''


def parse_names(s):
    return [x.strip() for x in re.split(r'[,;]| and ', s or '') if x.strip()]


def fcm_send(oauth, token, title, body):
    payload = {
        'message': {
            'token': token,
            'notification': {'title': title, 'body': body},
            'webpush': {'headers': {'Urgency': 'normal'}},
        }
    }
    req = urllib.request.Request(
        FCM_URL, data=json.dumps(payload).encode(),
        headers={'Authorization': f'Bearer {oauth}',
                 'Content-Type': 'application/json; charset=utf-8'},
        method='POST')
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, ''
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:400]
    except Exception as e:  # noqa: BLE001
        return -1, str(e)[:200]


def prune_tokens(uid, keep):
    body = {'fields': {'fcmTokens': {'arrayValue': {
        'values': [{'stringValue': t} for t in keep]}}}}
    fb.req('PATCH', f'members/{uid}', body, qs='?updateMask.fieldPaths=fcmTokens')


def main():
    args = sys.argv[1:]
    slot = 'morning'
    dry_run = '--dry-run' in args
    if '--slot' in args:
        slot = args[args.index('--slot') + 1]
    if slot not in ('morning', 'evening'):
        sys.exit('slot must be morning|evening')
    if not os.path.exists(KEY_PATH):
        sys.exit(f'service account key not found: {KEY_PATH} (gitignored; see README)')

    fb.TOKEN = fb.mint_token(KEY_PATH)
    oauth = fb.TOKEN  # cloud-platform scope covers FCM

    today = datetime.now(PT).date()
    if slot == 'morning':
        title_emoji, title_word = '\u2600\ufe0f', 'Due today'
        match = lambda d: bool(d) and d <= today.isoformat()  # noqa: E731
    else:
        title_emoji, title_word = '\U0001f319', 'Due tomorrow'
        want = (today + timedelta(days=1)).isoformat()
        match = lambda d: d == want  # noqa: E731

    # ---- approved members ----
    members = {}  # uid -> dict(name, first, tokens, prefs)
    d = fb.req('GET', 'members', qs='?pageSize=200')
    for doc in d.get('documents', []):
        f = doc_fields(doc)
        if f.get('status') != 'approved':
            continue
        uid = doc['name'].split('/')[-1]
        prefs = f.get('notifyPrefs') or {}
        members[uid] = {
            'name': f.get('name', ''),
            'first': first_name(f.get('name')),
            'tokens': [t for t in (f.get('fcmTokens') or []) if t],
            'prefs': prefs,
        }
    if not members:
        print('no approved members; nothing to do')
        return

    # ---- due items ----
    # each: dict(kind, title, sub, named={first-names}, creator_uid, creator_first)
    items = []
    d = fb.req('GET', 'todos', qs='?pageSize=300')
    for doc in d.get('documents', []):
        f = doc_fields(doc)
        if f.get('done') or not match(f.get('dueDate') or ''):
            continue
        assignee = (f.get('assignedTo') or '').strip()
        items.append({
            'kind': 'todo', 'title': f.get('task') or '(untitled)',
            'sub': f' ({assignee})' if assignee else '',
            'named': {first_name(assignee)} if assignee else set(),
            'creator_uid': f.get('createdByUid') or '',
            'creator_first': first_name(f.get('createdBy')),
        })
    d = fb.req('GET', 'plans', qs='?pageSize=300')
    for doc in d.get('documents', []):
        f = doc_fields(doc)
        due = f.get('date') or ''
        if slot == 'morning':
            if due != today.isoformat():
                continue
        elif due != (today + timedelta(days=1)).isoformat():
            continue
        who = {first_name(n) for n in parse_names(f.get('whoIn')) if first_name(n)}
        items.append({
            'kind': 'plan', 'title': f.get('event') or '(untitled)',
            'sub': f" ({f.get('whoIn')})" if f.get('whoIn') else '',
            'named': who,
            'creator_uid': f.get('createdByUid') or '',
            'creator_first': first_name(f.get('createdBy')),
        })
    if not items:
        print(f'{slot}: nothing due; no digests sent')
        return

    # ---- per-member routing ----
    per_member = {uid: [] for uid in members}
    for it in items:
        involved = set()   # explicitly involved uids (for onlyMine)
        audience = set()   # uids that get it before pref filtering
        for uid, m in members.items():
            explicit = (m['first'] in it['named']
                        or (it['creator_uid'] and uid == it['creator_uid'])
                        or (it['creator_first'] and m['first'] == it['creator_first']))
            if explicit:
                involved.add(uid)
                audience.add(uid)
        if not audience:
            audience = set(members)  # unassigned / no whoIn -> everyone
        for uid in audience:
            m = members[uid]
            if not m['prefs'].get(slot, True):
                continue
            if m['prefs'].get('onlyMine') and uid not in involved:
                continue
            per_member[uid].append(it)

    # ---- send ----
    sent, pruned = 0, 0
    for uid, lst in per_member.items():
        m = members[uid]
        if not lst or not m['tokens']:
            continue
        lines = [f"\u2022 {it['title']}{it['sub']}" for it in lst[:5]]
        if len(lst) > 5:
            lines.append(f"\u2022 +{len(lst) - 5} more")
        title = f'{title_emoji} {title_word} ({len(lst)})'
        body = '\n'.join(lines)
        stale = []
        for tok in m['tokens']:
            if dry_run:
                print(f'[dry-run] -> {m["name"]}: {title} :: {body[:80]}')
                continue
            code, err = fcm_send(oauth, tok, title, body)
            if code == 200:
                sent += 1
            elif code in (400, 404) and 'UNREGISTERED' in err:
                stale.append(tok)
                print(f'stale token for {m["name"]}, pruning')
            else:
                print(f'FCM send failed for {m["name"]}: {code} {err[:120]}')
        if stale and not dry_run:
            keep = [t for t in m['tokens'] if t not in stale]
            prune_tokens(uid, keep)
            pruned += len(stale)

    print(f'{slot}: {len(items)} item(s) due, {sent} notification(s) sent, '
          f'{pruned} stale token(s) pruned')


if __name__ == '__main__':
    main()
