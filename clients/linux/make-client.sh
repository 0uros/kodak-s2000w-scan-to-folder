#!/usr/bin/env bash
# Builds a ready-to-run Linux client script with the share passwords inside.
#
#   ./make-client.sh <config.json> <passwords.txt> <server-name> <server-ip> [label] > connect-scans.sh
#
# passwords.txt has one "samba-user: password" line per scanner user (the same file install.sh reads).
# The output CONTAINS passwords: keep it private and delete it from each PC after use.
set -euo pipefail
cd "$(dirname "$0")"
[ $# -ge 4 ] || { sed -n '2,8p' "$0"; exit 1; }
python3 -I - "$@" <<'PY'
import json, re, sys
config, pwfile, server, ip = sys.argv[1:5]
label = sys.argv[5] if len(sys.argv) > 5 else "Scans"
c = json.load(open(config))
pw = dict(re.findall(r'^([a-z0-9_-]+): (.+)$', open(pwfile).read(), re.M))
q = lambda s: "'" + s.replace("'", "'\\''") + "'"
users, passwords = [], []
for user, s in c["scanners"].items():
    if user not in pw:
        sys.exit(f"no password for {user} in {pwfile}")
    users.append(f"[{s['share']}]={q(user)}"); passwords.append(f"[{s['share']}]={q(pw[user])}")
t = open("connect-share.template.sh").read()
for k, v in {"__SERVER__": server, "__SERVER_IP__": ip, "__LABEL__": label,
             "__USERS__": " ".join(users), "__PASSWORDS__": " ".join(passwords)}.items():
    t = t.replace(k, v)
sys.stdout.write(t)
PY
