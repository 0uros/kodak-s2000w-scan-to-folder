#!/usr/bin/env bash
# Install kodak-s2000w-scan-to-folder on a Debian 12/13 or Ubuntu 22.04+ server (VM, LXC container or bare metal).
#
#   sudo ./install.sh                         # first run: creates the config and asks you to edit it
#   sudo nano /etc/kodak-scan-to-folder/config.json
#   sudo ./install.sh                         # asks for each Samba password
#   sudo ./install.sh < passwords.txt         # or reads "user: password" lines (one per Samba user)
#
# Safe to run again: it updates programs, shares and services and keeps existing passwords unless new
# ones are given. Set NO_SYSTEMD=1 to skip enabling services (containers without systemd, tests).
set -euo pipefail
cd "$(dirname "$0")"
CONFIG=/etc/kodak-scan-to-folder/config.json
APP=/opt/kodak-scan-to-folder
step() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
[ "$(id -u)" -eq 0 ] || { echo "Run as root (sudo)."; exit 1; }

# Passwords from stdin are read first, so apt cannot swallow them.
declare -A PASSWORD=()
if [ ! -t 0 ]; then
  while IFS= read -r line; do
    [[ "$line" =~ ^([a-z0-9_-]+):\ (.+)$ ]] && PASSWORD[${BASH_REMATCH[1]}]="${BASH_REMATCH[2]}"
  done
  exec </dev/null
fi

step "Packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq || echo "(apt-get update reported errors; continuing)"
apt-get install -y -qq --no-install-recommends python3 python3-requests python3-pil img2pdf ocrmypdf \
  tesseract-ocr tesseract-ocr-eng samba >/dev/null

step "Configuration"
if [ ! -f "$CONFIG" ]; then
  install -d -m 755 "$(dirname "$CONFIG")"
  install -m 644 config.example.json "$CONFIG"
  echo "Created $CONFIG from the example. Edit it (scanner IPs, panel text, share names, OCR language)"
  echo "and run this installer again."
  exit 0
fi
# Everything below is derived from the config.
eval "$(python3 -I - "$CONFIG" <<'PY'
import json, re, shlex, sys
c = json.load(open(sys.argv[1]))
assert c.get("scanners"), "config has no scanners"
for k, s in c["scanners"].items():
    assert re.fullmatch(r"[a-z0-9_-]+", k), f"scanner name {k!r}: use lowercase letters, digits, - or _"
    assert re.fullmatch(r"[A-Za-z0-9_-]+", s["share"]), f"share {s['share']!r}: letters, digits, - or _"
    for key in ("ip", "panel_text", "share"):
        assert key in s, f"scanner {k!r} has no {key!r}"
print("DATA=" + shlex.quote(c.get("data_dir", "/srv/scans")))
print("ADMIN=" + shlex.quote(c.get("admin_user", "support")))
print("SCANNERS=(" + " ".join(shlex.quote(k) for k in c["scanners"]) + ")")
print("declare -A SHARE=(" + " ".join(f"[{k}]={shlex.quote(s['share'])}" for k, s in c["scanners"].items()) + ")")
print("OCR_LANG=" + shlex.quote(c.get("ocr_language", "eng")))
PY
)"
echo "Scanners: ${SCANNERS[*]}  |  data: $DATA  |  admin user: $ADMIN  |  OCR: $OCR_LANG"
for lang in ${OCR_LANG//+/ }; do
  [ "$lang" = eng ] || apt-get install -y -qq "tesseract-ocr-$lang" >/dev/null
done

step "Service user and folders"
id scans >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin scans
install -d -o scans -g scans -m 2770 "$DATA/inbox" "$DATA/inbox/.processed" "$DATA/shared"
chmod 755 "$DATA"
for s in "${SCANNERS[@]}"; do
  install -d -o scans -g scans -m 2770 "$DATA/inbox/$s" "$DATA/shared/${SHARE[$s]}"
done

step "Programs and services"
install -d -m 755 "$APP"
install -m 755 kodak-session.py scan-to-pdf.py "$APP/"
install -d -m 755 /etc/systemd/system /etc/tmpfiles.d
for unit in kodak-session@.service scan-to-pdf.service; do
  sed "s#@DATA@#$DATA#g; s#@APP@#$APP#g" "systemd/$unit" > "/etc/systemd/system/$unit"
done
sed "s#@DATA@#$DATA#g" systemd/tmpfiles.conf > /etc/tmpfiles.d/kodak-scan-to-folder.conf

step "Samba"
[ -f /etc/samba/smb.conf.before-scan-to-folder ] || cp /etc/samba/smb.conf /etc/samba/smb.conf.before-scan-to-folder
{
  cat samba/smb.conf.global
  for s in "${SCANNERS[@]}"; do
    printf '\n[%s]\n   path = %s\n   valid users = %s %s\n   read only = no\n   browseable = yes\n' \
      "${SHARE[$s]}" "$DATA/shared/${SHARE[$s]}" "$s" "$ADMIN"
  done
} > /etc/samba/smb.conf
testparm -s >/dev/null 2>&1 || { testparm -s; exit 1; }

step "Samba users"
for u in "${SCANNERS[@]}" "$ADMIN"; do
  id "$u" >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin "$u"
  if [ -n "${PASSWORD[$u]:-}" ]; then
    printf '%s\n%s\n' "${PASSWORD[$u]}" "${PASSWORD[$u]}" | smbpasswd -s -a "$u" >/dev/null
    echo "$u: password set"
  elif pdbedit -L 2>/dev/null | grep -q "^$u:"; then
    echo "$u: keeps its current password (change it with: smbpasswd $u)"
  elif [ -t 1 ] && [ -r /dev/tty ]; then
    echo "Samba password for $u:"; smbpasswd -a "$u" </dev/tty
  else
    echo "Missing password for $u (give it as '$u: password' on stdin)"; exit 1
  fi
done

if [ "${NO_SYSTEMD:-0}" = 1 ]; then
  echo; echo "NO_SYSTEMD=1: services not enabled."; exit 0
fi

step "Starting"
systemctl daemon-reload
systemctl disable --now nmbd 2>/dev/null || true
systemctl enable --now smbd scan-to-pdf
systemctl restart smbd scan-to-pdf
for s in "${SCANNERS[@]}"; do systemctl enable --now "kodak-session@$s"; systemctl restart "kodak-session@$s"; done
sleep 5
journalctl -q --no-pager -n 10 -u scan-to-pdf -u 'kodak-session@*'
echo
echo "Done. Live log: journalctl -f -u scan-to-pdf -u 'kodak-session@*'"
