#!/usr/bin/env python3
"""Turn each finished scan batch into a searchable PDF in the scanner's shared folder.

inbox/<scanner>/<date>/ (page images)  ->  shared/<share>/<date>.pdf

- Blank pages are dropped here (the scanner's own SkipBlankPages did not drop them in color mode).
- img2pdf builds the PDF without recompressing; ocrmypdf adds the text layer.
- If OCR fails, the PDF is saved anyway without text: a scan is never lost.
- Original images move to inbox/.processed/ (systemd-tmpfiles deletes them after 7 days).
"""
import json, os, shutil, subprocess, tempfile, time
from PIL import Image, ImageOps

CONFIG = os.environ.get("SCAN_TO_FOLDER_CONFIG", "/etc/kodak-scan-to-folder/config.json")
STALE_PARTIAL = 15 * 60  # a ".partial" batch untouched for 15 min was cut off: process it anyway
# A page is blank when less than this percentage of its pixels is darker than INK_LEVEL/255,
# ignoring 4 % of each border. Measured on real scans: blank sheet 0.0002 %, lightest real page 2.1 %.
INK_LEVEL = 160


def log(*a):
    print(*a, flush=True)


def ink(path):
    im = ImageOps.grayscale(Image.open(path))
    w, h = im.size
    im = im.crop((w * 4 // 100, h * 4 // 100, w * 96 // 100, h * 96 // 100)).reduce(4)
    hist = im.histogram()
    return sum(hist[:INK_LEVEL]) * 100 / (im.size[0] * im.size[1])


def drop_blank(batch, pages, threshold):
    kept = []
    for p in pages:
        try:
            if ink(os.path.join(batch, p)) >= threshold:
                kept.append(p)
        except Exception:
            kept.append(p)  # if it cannot be measured, keep it
    return kept or pages  # an all-blank batch is kept as is


def free_name(folder, base):
    path, n = os.path.join(folder, base + ".pdf"), 2
    while os.path.exists(path):
        path = os.path.join(folder, f"{base} ({n}).pdf"); n += 1
    return path


def process(config, scanner, out_dir, batch):
    data = config.get("data_dir", "/srv/scans")
    name = os.path.basename(batch).removesuffix(".partial")
    pages = sorted(f for f in os.listdir(batch) if f.lower().endswith((".jpg", ".jpeg", ".tif", ".tiff")))
    if not pages:
        shutil.rmtree(batch); return
    total = len(pages)
    pages = drop_blank(batch, pages, config.get("blank_page_threshold_percent", 0.02))
    blanks = f", {total - len(pages)} blank skipped" if len(pages) < total else ""
    os.makedirs(out_dir, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=os.path.join(data, "shared"), prefix=".work-") as tmp:
        raw, final = os.path.join(tmp, "raw.pdf"), os.path.join(tmp, "final.pdf")
        subprocess.run(["img2pdf", *[os.path.join(batch, p) for p in pages], "-o", raw], check=True)
        t0 = time.time()
        ocr = subprocess.run(["ocrmypdf", "-q", "-l", config.get("ocr_language", "eng"), "--rotate-pages",
                              "--optimize", "1", "--output-type", "pdf", "--jobs", "2", raw, final],
                             capture_output=True, text=True, timeout=1800)
        if ocr.returncode == 0:
            chosen, detail = final, f"OCR in {time.time() - t0:.0f} s"
        else:
            chosen, detail = raw, f"NO OCR (ocrmypdf {ocr.returncode}: {ocr.stderr.strip()[-200:]})"
        target = free_name(out_dir, name)
        os.chmod(chosen, 0o660)
        shutil.move(chosen, target)
    done = os.path.join(data, "inbox", ".processed", scanner)
    os.makedirs(done, exist_ok=True)
    shutil.move(batch, os.path.join(done, os.path.basename(batch)))
    log(f"{scanner}: {os.path.basename(target)} - {len(pages)} pages{blanks}, {detail}")


def pending(config):
    data = config.get("data_dir", "/srv/scans")
    for scanner, s in config["scanners"].items():
        folder = os.path.join(data, "inbox", scanner)
        if not os.path.isdir(folder):
            continue
        for d in sorted(os.listdir(folder)):
            path = os.path.join(folder, d)
            if d.startswith(".") or not os.path.isdir(path):
                continue
            if d.endswith(".partial"):
                last = max([os.path.getmtime(path)] + [os.path.getmtime(os.path.join(path, f)) for f in os.listdir(path)])
                if time.time() - last < STALE_PARTIAL:
                    continue
            yield scanner, os.path.join(data, "shared", s["share"]), path


log("scan-to-pdf running")
while True:
    config = json.load(open(CONFIG))
    for scanner, out_dir, batch in pending(config):
        try:
            process(config, scanner, out_dir, batch)
        except Exception as e:  # the batch stays in the inbox and is retried on the next pass
            log(f"{scanner}: failed {os.path.basename(batch)}: {e}")
            time.sleep(30)
    time.sleep(3)
