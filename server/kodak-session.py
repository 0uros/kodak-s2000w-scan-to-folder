#!/usr/bin/env python3
"""Keep a Kodak Alaris S2000w-series scanner dedicated to a network folder.

Holds a session open through the scanner's official Web API, waits for paper (or the panel
button), downloads every page image as soon as it is scanned and, when the batch is done, hands
the batch folder to scan-to-pdf by renaming "<date>.partial" to "<date>".

Usage: kodak-session.py <scanner-name>      (reads /etc/kodak-scan-to-folder/config.json)

Behaviour learned on real S2080w units (firmware 210503 and 230802):
  - NumImagesScanned restarts at 0 on every StartScan, so image numbers are per batch.
  - One session can run many batches: call StartScan again after "Done Scanning".
  - Any session call renews the 5-minute session timeout; status is polled every 1-2 s.
  - While the session is open no PC can use the scanner (HTTP 423 for everyone else).
"""
import json, os, signal, sys, time
from datetime import datetime
import requests, urllib3

urllib3.disable_warnings()  # the scanner uses a self-signed certificate
CONFIG = os.environ.get("SCAN_TO_FOLDER_CONFIG", "/etc/kodak-scan-to-folder/config.json")

name = sys.argv[1]
config = json.load(open(CONFIG))
scanner = config["scanners"][name]
base = f"https://{scanner['ip']}/api/session"
inbox = os.path.join(config.get("data_dir", "/srv/scans"), "inbox", name)
http = requests.Session(); http.verify = False
stopping = False


def log(*a):
    print(*a, flush=True)


def on_stop(*_):
    global stopping
    stopping = True


signal.signal(signal.SIGTERM, on_stop)
signal.signal(signal.SIGINT, on_stop)


def open_session():
    """Return a SessionId, retrying while the scanner is off, waking up or busy."""
    wait, last_reason = 5, None
    while not stopping:
        try:
            r = http.post(base, data=json.dumps({"OCPUserName": scanner["panel_text"]}), timeout=15)
            if r.status_code == 200:
                sid = r.json()["SessionId"]
                body = {"Configuration": scanner.get("settings", {})}
                c = http.put(f"{base}?SessionId={sid}", data=json.dumps(body, separators=(",", ":")), timeout=15)
                if c.status_code != 200:
                    log(f"scanner rejected the settings (HTTP {c.status_code}): {c.text[:200]}")
                log(f"session open on {scanner['ip']} as \"{scanner['panel_text']}\"")
                return sid
            if r.status_code == 408:  # waking up: the guide says to retry right away
                time.sleep(1); continue
            reason = "busy, another session holds it" if r.status_code == 423 else f"HTTP {r.status_code}"
        except requests.RequestException as e:
            reason = f"no answer ({type(e).__name__})"
        if reason != last_reason:
            log(f"could not open a session: {reason}; retrying"); last_reason = reason
        time.sleep(min(wait, 60)); wait = min(wait * 2, 60)
    return None


def close_session(sid):
    try:
        http.delete(f"{base}?SessionId={sid}", timeout=10)
    except requests.RequestException:
        pass


def finish_batch(folder, pages):
    if folder and pages:
        final = folder[: -len(".partial")]
        os.rename(folder, final)
        log(f"batch ready: {os.path.basename(final)} ({pages} page images)")
    elif folder:
        os.rmdir(folder)


def serve(sid):
    """One session: batch after batch until the session drops or we are asked to stop."""
    q = f"?SessionId={sid}"
    if http.post(f"{base}/StartScan{q}", data={}, timeout=15).status_code != 200:
        return
    folder, downloaded = None, 0
    while not stopping:
        r = http.get(f"{base}/status{q}", timeout=15)
        if r.status_code != 200:
            log(f"session lost (HTTP {r.status_code})")
            break
        st = r.json()["Status"]
        scanned = int(st["NumImagesScanned"])
        while downloaded < scanned:
            n = downloaded + 1
            img = http.get(f"{base}/image/{n}{q}", timeout=60)
            if img.status_code != 200:
                log(f"could not download image {n} (HTTP {img.status_code})")
                break
            if folder is None:
                folder = os.path.join(inbox, datetime.now().strftime("%Y-%m-%d %H.%M.%S") + ".partial")
                os.makedirs(folder)
            ext = "jpg" if "jpeg" in img.headers.get("Content-Type", "") else "tif"
            with open(os.path.join(folder, f"{n:04d}.{ext}"), "wb") as f:
                f.write(img.content)
            http.delete(f"{base}/image/{n}{q}", timeout=15)  # frees scanner memory on long batches
            downloaded = n
        if st["State"] == "Done Scanning":
            finish_batch(folder, downloaded)
            folder, downloaded = None, 0
            if http.post(f"{base}/StartScan{q}", data={}, timeout=15).status_code != 200:
                break
        elif st["State"] in ("Error", "Idle", "In Session"):
            log(f"state {st['State']} (error {st.get('ErrorNum')}: {st.get('LastError')})")
            break
        busy = st["State"] == "Scanning" and (scanned or st.get("PaperDetected") == "1")
        time.sleep(1 if busy else 2)
    finish_batch(folder, downloaded)  # whatever arrived is never lost


os.makedirs(inbox, exist_ok=True)
while not stopping:
    sid = open_session()
    if not sid:
        break
    try:
        serve(sid)
    except requests.RequestException as e:
        log(f"connection to the scanner dropped ({type(e).__name__})")
    finally:
        close_session(sid)
    if not stopping:
        time.sleep(5)
log("session closed, scanner released")
