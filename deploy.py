#!/usr/bin/env python3
"""Deploy ~/workspace/family-board-firebase/public to Firebase Hosting via REST.
Auth: service-account JWT -> oauth2 token (minted fresh each run).
"""
import gzip, hashlib, json, os, subprocess, sys, urllib.request, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
PUBLIC = os.path.join(HERE, 'public')
SA_PATH = os.path.join(HERE, 'service-account.json')
SITE = os.environ.get('FAMILY_BOARD_SITE', 'family-board-25583')
API = 'https://firebasehosting.googleapis.com/v1beta1'

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

def api(token, method, path, body=None, raw_body=None, ctype='application/json'):
    url = f'{API}{path}'
    data = None
    if body is not None:
        data = json.dumps(body).encode(); ctype = 'application/json'
    elif raw_body is not None:
        data = raw_body
    req = urllib.request.Request(url, data=data, method=method,
        headers={'Authorization': f'Bearer {token}', 'Content-Type': ctype})
    for _ in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            raise RuntimeError(f'{method} {path}: {e.read().decode()[:300]}')
        except Exception as e:
            last = e
    raise RuntimeError(f'{method} {path} failed after retries: {last}')

def main():
    token = mint_token()
    files, blobs = {}, {}
    for name in sorted(os.listdir(PUBLIC)):
        p = os.path.join(PUBLIC, name)
        if not os.path.isfile(p):
            continue
        gz = gzip.compress(open(p, 'rb').read(), compresslevel=9)
        h = hashlib.sha256(gz).hexdigest()
        files['/' + name] = h
        blobs[h] = gz
    print(f'{len(files)} files: {", ".join(sorted(files))}')
    ver = api(token, 'POST', f'/sites/{SITE}/versions', body={})
    vid = ver['name'].split('/')[-1]
    pop = api(token, 'POST', f'/sites/{SITE}/versions/{vid}:populateFiles',
              body={'files': files})
    upload_url = pop['uploadUrl']
    for h in pop.get('uploadRequiredHashes', []):
        for attempt in range(4):
            try:
                r = urllib.request.Request(f'{upload_url}/{h}', data=blobs[h], method='POST',
                    headers={'Authorization': f'Bearer {token}',
                             'Content-Type': 'application/octet-stream'})
                with urllib.request.urlopen(r, timeout=60) as resp:
                    assert resp.status == 200, f'upload {h}: HTTP {resp.status}'
                break
            except Exception as e:
                if attempt == 3:
                    raise RuntimeError(f'upload {h} failed after retries: {e}')
    print('uploaded, finalizing…')
    api(token, 'PATCH', f'/sites/{SITE}/versions/{vid}', body={'status': 'FINALIZED'})
    rel = api(token, 'POST',
              f'/projects/-/sites/{SITE}/channels/live/releases'
              f'?versionName={urllib.parse.quote(f"sites/{SITE}/versions/{vid}", safe="")}',
              body={})
    print('LIVE:', f'https://{SITE}.web.app', '| release:', rel['name'].split('/')[-1])

if __name__ == '__main__':
    main()
