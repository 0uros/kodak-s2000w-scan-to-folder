# Kodak Alaris S2000w Web API: field notes

What we learned while making a Kodak Alaris **S2080w** scan to a network folder without a PC. These notes
should also apply to the **S2060w** and S2040 (same S2000w series). Tested on firmware **210503** (2021) and
**230802** (Dec 2023, the latest when this was written).

## The official documentation

Kodak Alaris published a **"WebAPI Toolkit"** for its network scanners: guide *A-61872, "WebAPI Guide for
Alaris Network Enabled Scanners"* (September 2023), an "Easy Start" PDF and Python examples
(`KaBgbScanningApp.py`, the "Big Green Button" app, is the closest to this project).

It is **no longer on Kodak's site**: the old download link returns "Page Not Found". The Internet Archive
kept a copy of version 2.2 (2023-10-13, 37 MB):

<https://web.archive.org/web/20250108033544/https://resources.kodakalaris.com/docimaging/drivers/Kodak_Alaris_WebAPI%20_Toolkit_v2.2.20231013115131.zip>

It is not included in this repository because it has no license that allows redistribution.

## The hidden "FTP destinations" do not work

The scanner's embedded web page has a hidden **Destinations** tab: Kodak removed it from the menu
(`setup.html` has a "remove destination tab" comment), but `/scripts/ftp.js` and the endpoints are still there:

| Call | Result on firmware 210503 and 230802 |
|---|---|
| `GET /api/scanner/DestInfo?PCID=Destination:FTP-1234-5678-90ABCD&ADMIN_PASSWORD=` | Always `"NumDests":"0"` |
| `POST /api/scanner/destftp` (JSON profile: FTP site, user, password, batch name, color, DPI, duplex, skip blanks, auto start; `ButtonNumber` is 1-based in the web code) | **HTTP 200** and echoes the profile back, but **nothing is stored**: the list stays empty and nothing shows up on the panel |
| `POST /api/scanner/testFTP?PCID=...&ButtonNumber=1` | **501 Not Implemented** |

FTP is not mentioned in any firmware release note nor in the official API guide. It looks like an unfinished
feature. **Don't waste time on it.** The scanners also have no eSCL/AirScan (`/eSCL/ScannerCapabilities` is
404), so SANE's `airscan` backend cannot drive them either.

## What works: the session API

All calls are HTTPS on the scanner's IP (self-signed certificate). Request bodies are JSON.

```
POST   /api/session                         {"OCPUserName": "Scan to Front Desk"}   → {"SessionId": "..."}
PUT    /api/session?SessionId=ID            {"Configuration": {"DPI":300, "ScanSide":"Duplex", ...}}
POST   /api/session/StartScan?SessionId=ID
GET    /api/session/status?SessionId=ID     → {"Status": {"State", "NumImagesScanned", "PaperDetected", ...}}
GET    /api/session/image/N?SessionId=ID    → image/jpeg (N = 1, 2, ...)
DELETE /api/session/image/N?SessionId=ID    → frees scanner memory
DELETE /api/session?SessionId=ID            → ends the session, scanner is free again
GET    /api/scanner/status                  → state and OCPUserName, no session needed
GET    /api/scanner/capabilities?V2         → every setting and its allowed values
```

- **`OCPUserName`** is shown on the scanner's panel (OCP = Operator Control Panel) while the session is open.
  Use it to tell people where their scan will go.
- After `StartScan` the scanner waits for paper. With `"AutoStart": 1` it starts when paper is loaded; the
  panel may still ask the user to confirm. `PaperDetected` tells you whether there is paper in the feeder.
- **Images arrive while scanning**: poll status about once per second, download `image/N` up to
  `NumImagesScanned`, then `DELETE` it so long batches do not fill the scanner's memory.
- Each face is a separate JPEG: duplex gives two images per sheet, front then back. 300 dpi color A4 is about
  2474×3516 px and 180–550 KB.
- When `State` becomes `Done Scanning`, the batch is complete.

### Gotchas

1. **`NumImagesScanned` restarts at 0 on every `StartScan`.** Keep the image counter per batch, not per
   session. Otherwise the second batch is never downloaded (we lost one batch this way during testing).
2. **One session serves many batches.** After `Done Scanning`, call `StartScan` again in the same session.
3. **The session times out after 5 minutes without session calls.** `GET /api/session/status` renews it;
   `GET /api/scanner/status` does not.
4. **A session locks the scanner.** Any other client (Smart Touch, TWAIN driver, another script) gets
   **HTTP 423 Locked** until the session ends or times out. That is why this project dedicates a scanner to a
   folder.
5. **HTTP 408** on session creation means the scanner is waking up from sleep: retry after a second.
6. **`SkipBlankPages: 1` did not drop blank backs in color mode** on our S2080w units. This project removes
   blank pages itself: a blank sheet had 0.0002 % dark pixels, the lightest real page 2.1 %.
7. Validation is strict on newer firmware: numbers must be numbers (`"AutoStart": 1`, not `"1"`), or you get
   HTTP 406.

## Timings measured on a real S2080w

| Batch | Scanner → server | PDF with Spanish OCR (4 vCPU container) |
|---|---|---|
| 1 sheet, duplex | 2 s | 3.5 s |
| 4 pages (+1 blank skipped) | immediate | 10 s |
| 15 pages | immediate | 34–35 s |
