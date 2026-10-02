#!/usr/bin/env python3
"""Family Board Firestore CLI — lets Clarke read/write the shared board.

Auth: service-account OAuth token (bypasses Firestore security rules, which
require Google sign-in for app users). Default key:
a local service-account.json (keep private, never commit).
Use --key PATH for a different service-account key.

Usage:
  fb.py [--key PATH] list groceries|todos|plans|gifts
  fb.py [--key PATH] add groceries --item "Milk" [--quantity "1 gallon"] [--pickUpBy Apoorv] [--notes ...]
  fb.py [--key PATH] add todos --task "..." [--assignedTo Apoorv] [--dueDate 2026-10-01] [--notes ...]
  fb.py [--key PATH] add plans --event "..." [--date 2026-10-04] [--whoIn "Apoorv, Divya"] [--notes ...]
  fb.py [--key PATH] add gifts --idea "..." [--forWhom Apoorv] [--occasion Diwali] [--budget "$50"] [--link URL]
  fb.py [--key PATH] done|undone groceries|todos <doc-id>
  fb.py [--key PATH] delete groceries|todos|plans|gifts <doc-id>
"""
import json, os, sys, time, base64, subprocess, urllib.request, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_KEY = os.path.join(HERE, 'service-account.json')
PROJECT = os.environ.get('FAMILY_BOARD_PROJECT', 'family-board-25583')
BASE = f'https://firestore.googleapis.com/v1/projects/{PROJECT}/databases/(default)/documents'

TOGGLE = {'groceries': 'bought', 'todos': 'done'}
TITLES = {'groceries': 'item', 'todos': 'task', 'plans': 'event', 'gifts': 'idea', 'privateGifts': 'idea'}

def mint_token(key_path):
    sa = json.load(open(key_path))
    pem = '/tmp/fb-sa-key.pem'
    open(pem, 'w').write(sa['private_key'])
    os.chmod(pem, 0o600)
    def b64url(b): return base64.urlsafe_b64encode(b).rstrip(b'=').decode()
    now = int(time.time())
    h = b64url(b'{"alg":"RS256","typ":"JWT"}')
    c = b64url(json.dumps({'iss': sa['client_email'],
        'scope': 'https://www.googleapis.com/auth/cloud-platform',
        'aud': 'https://oauth2.googleapis.com/token', 'iat': now, 'exp': now + 3600}).encode())
    sig = subprocess.run(['openssl', 'dgst', '-sha256', '-sign', pem],
                         input=f'{h}.{c}'.encode(), capture_output=True).stdout
    data = urllib.parse.urlencode({
        'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
        'assertion': f'{h}.{c}.{b64url(sig)}'}).encode()
    req = urllib.request.Request('https://oauth2.googleapis.com/token', data=data, method='POST')
    last = None
    for _ in range(3):
        try:
            return json.load(urllib.request.urlopen(req, timeout=30))['access_token']
        except Exception as e:
            last = e
    raise RuntimeError(f'token mint failed: {last}')

TOKEN = None
def req(method, path, body=None, qs=''):
    global TOKEN
    if TOKEN is None:
        TOKEN = mint_token(KEY_PATH)
    url = f'{BASE}/{path}{qs}'
    data = json.dumps(body).encode() if body is not None else None
    last = None
    for _ in range(3):
        r = urllib.request.Request(url, data=data, method=method,
            headers={'Authorization': f'Bearer {TOKEN}', 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(r, timeout=30) as resp:
                return json.load(resp) if resp.status != 204 else {}
        except urllib.error.HTTPError as e:
            print('API error:', e.read().decode()[:300], file=sys.stderr); sys.exit(1)
        except Exception as e:
            last = e
    print('API error: connection failed after retries:', last, file=sys.stderr); sys.exit(1)

def fv(v):
    if isinstance(v, bool): return {'booleanValue': v}
    return {'stringValue': str(v)}

def flat(doc):
    return {k: (list(v.values())[0] if isinstance(v, dict) else v) for k, v in doc.get('fields', {}).items()}

def cmd_list(coll):
    d = req('GET', coll, qs='?pageSize=100')
    docs = d.get('documents', [])
    if not docs: print('(empty)'); return
    for doc in docs:
        f, did = flat(doc), doc['name'].split('/')[-1]
        t = TITLES[coll]
        line = f'{did}  {f.get(t,"?")}'
        if coll == 'groceries':
            line += f'  x{f.get("quantity","")}  [{"BOUGHT" if f.get("bought") else "to buy"}]'
        elif coll == 'todos':
            line += f'  [{f.get("assignedTo","")}] [{"DONE" if f.get("done") else "open"}]'
        elif coll == 'plans':
            line += f'  ({f.get("date","")})'
        elif coll in ('gifts', 'privateGifts'):
            line += f'  for {f.get("forWhom","")}'
        if f.get('addedBy'): line += f'  (by {f["addedBy"]})'
        if f.get('ownerEmail'): line += f'  [only {f["ownerEmail"]}]'
        print(line)

def cmd_add(coll, kv):
    import datetime
    fields = {k: fv(v) for k, v in kv.items()}
    fields['createdAt'] = {'timestampValue': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    if coll == 'groceries': fields.setdefault('bought', fv(False))
    if coll == 'todos': fields.setdefault('done', fv(False))
    r = req('POST', coll, {'fields': fields})
    print('added:', r['name'].split('/')[-1])

def cmd_toggle(coll, did, val):
    key = TOGGLE[coll]
    req('PATCH', f'{coll}/{did}', {'fields': {key: fv(val)}},
        qs=f'?updateMask.fieldPaths={key}')
    print(f'{did}: {key}={val}')

def cmd_delete(coll, did):
    req('DELETE', f'{coll}/{did}')
    print('deleted:', did)

if __name__ == '__main__':
    a = sys.argv[1:]
    KEY_PATH = DEFAULT_KEY
    if a[:1] == ['--key']:
        KEY_PATH = a[1]; a = a[2:]
    if len(a) < 2 or a[0] not in ('list', 'add', 'done', 'undone', 'delete'):
        sys.exit(__doc__)
    cmd, coll = a[0], a[1]
    if cmd == 'list': cmd_list(coll)
    elif cmd == 'add':
        kv = {}
        for x, y in zip(a[2::2], a[3::2]):
            kv[x.lstrip('-')] = y
        cmd_add(coll, kv)
    elif cmd in ('done', 'undone'): cmd_toggle(coll, a[2], cmd == 'done')
    elif cmd == 'delete': cmd_delete(coll, a[2])
