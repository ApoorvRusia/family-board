#!/usr/bin/env python3
"""Deploy firestore.rules to the Family Board project via the Firebase Rules REST API.

Two steps: create a ruleset from the local file, then point the `firestore`
release at it. Auth: same service-account JWT -> oauth2 token as deploy.py.
"""
import json, os, subprocess, sys, urllib.request, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
SA_PATH = os.path.join(HERE, 'service-account.json')
RULES_PATH = os.path.join(HERE, 'firestore.rules')
PROJECT = os.environ.get('FAMILY_BOARD_PROJECT', 'family-board-25583')
API = 'https://firebaserules.googleapis.com/v1'

def b64url(b):
    import base64
    return base64.urlsafe_b64encode(b).rstrip(b'=').decode()

def mint_token():
    sa = json.load(open(SA_PATH))
    open('/tmp/sa-key.pem', 'w').write(sa['private_key'])
    import time
    now = int(time.time())
    header = b64url(b'{"alg":"RS256","typ":"JWT"}')
    claims = b64url(json.dumps({
        'iss': sa['client_email'],
        'scope': 'https://www.googleapis.com/auth/cloud-platform',
        'aud': 'https://oauth2.googleapis.com/token',
        'iat': now, 'exp': now + 3600}).encode())
    sig = subprocess.run(['openssl', 'dgst', '-sha256', '-sign', '/tmp/sa-key.pem'],
                         input=f'{header}.{claims}'.encode(), capture_output=True).stdout
    assertion = f'{header}.{claims}.{b64url(sig)}'
    data = urllib.parse.urlencode({
        'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
        'assertion': assertion}).encode()
    req = urllib.request.Request('https://oauth2.googleapis.com/token', data=data, method='POST')
    for _ in range(3):
        try:
            return json.load(urllib.request.urlopen(req, timeout=30))['access_token']
        except Exception as e:
            last = e
    raise RuntimeError(f'token mint failed: {last}')

def api(token, method, path, body=None):
    url = f'{API}{path}'
    data = json.dumps(body).encode() if body is not None else None
    last = None
    for _ in range(4):
        req = urllib.request.Request(url, data=data, method=method,
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            raise RuntimeError(f'{method} {path}: {e.read().decode()[:500]}')
        except Exception as e:
            last = e
    raise RuntimeError(f'{method} {path}: connection failed after retries: {last}')

def main():
    token = mint_token()
    content = open(RULES_PATH).read()
    rs = api(token, 'POST', f'/projects/{PROJECT}/rulesets',
             {'source': {'files': [{'name': 'firestore.rules', 'content': content}]}})
    rs_name = rs['name']
    print('ruleset:', rs_name)
    rel_name = f'projects/{PROJECT}/releases/cloud.firestore'
    rel = api(token, 'PATCH', f'/projects/{PROJECT}/releases/cloud.firestore',
              {'release': {'name': rel_name, 'rulesetName': rs_name},
               'updateMask': 'rulesetName'})
    print('released:', rel.get('rulesetName'))
    cur = api(token, 'GET', f'/projects/{PROJECT}/releases/cloud.firestore')
    assert cur.get('rulesetName') == rs_name, 'release verification failed'
    print('verified live ruleset:', cur['rulesetName'])

if __name__ == '__main__':
    main()
