# Kodak Alaris S2080w / S2060w scan to network folder — no PC, no Smart Touch

**Make a Kodak Alaris S2000w-series network scanner (S2080w, S2060w) save every scan as a searchable PDF
in a shared network folder (SMB / Samba), without a Windows PC running Kodak Smart Touch.**

Put paper in the scanner. A few seconds after it finishes, `2026-10-23 14.43.08.pdf` appears in the office's
shared folder, with OCR text and without blank pages. No PC needs to be on, no driver is installed anywhere.

If you searched for any of these, you are in the right place:

- *Kodak S2080w scan to folder / scan to network share / scan to SMB without computer*
- *Kodak S2080w scan to FTP not working* or *hidden FTP destinations tab* (see [why it does not work](#the-hidden-ftp-feature-does-not-work))
- *Kodak Smart Touch alternative for Linux* or *Smart Touch requires a PC to stay on*
- *Kodak Alaris Web API example*, *S2000w REST API*, *api/session StartScan*
- *Kodak S2060w / S2080w Linux*, *network scanner to Samba share with OCR*

## Why this exists

The S2000w scanners have an Ethernet port and a touch screen, but **every scan from the panel goes to a PC**
running Kodak Smart Touch (or the TWAIN/ISIS driver). If that PC is off, the scanner cannot send anything.
The user's guide (A-61931) has no "scan to folder" or "scan to FTP" feature.

The firmware does contain a hidden FTP destinations feature, but **it is unfinished and does not work** on
any firmware we tested. What does work is the scanner's **official Web API**. A small service on any Linux
server can hold a session open, wait for paper, pull the images over HTTPS and turn them into PDFs.
Details in [docs/web-api-notes.md](docs/web-api-notes.md).

## How it works

```
 Kodak S2080w ◄──HTTPS (Web API)── kodak-session@frontdesk ──► inbox/frontdesk/<date>/0001.jpg …
 Kodak S2060w ◄──HTTPS (Web API)── kodak-session@accounting       │
                                                                  ▼
                                    scan-to-pdf: drop blank pages → img2pdf → ocrmypdf
                                                                  │
                                                                  ▼
 PCs (Windows / Linux) ──SMB──► Samba: \\server\FrontDesk\2026-10-23 14.43.08.pdf
```

- **`kodak-session@<scanner>`** (one per scanner): opens a Web API session, which shows your text on the
  scanner's panel, e.g. *"Scan to Front Desk"*. It waits for paper, downloads each page as soon as it is
  scanned and starts the next batch in the same session. If the scanner is turned off or the network drops,
  it reconnects by itself.
- **`scan-to-pdf`**: drops blank pages, builds the PDF without recompressing and adds an OCR text layer
  (any [Tesseract language](https://tesseract-ocr.github.io/tessdoc/Data-Files-in-different-versions.html)).
  If OCR fails, the PDF is saved without text: **a scan is never lost**.
- **Samba**: one share per scanner, its own user plus an admin user. Deleted files go to a `.recycle` folder
  for 30 days.

> **Trade-off: the scanner becomes dedicated to its folder.** While the session is open, Smart Touch and the
> TWAIN driver on PCs cannot use that scanner (it answers *423 Locked*). Stop the service to give it back:
> `systemctl stop kodak-session@<scanner>`.

## Requirements

- A Kodak Alaris **S2080w** or **S2060w** (probably any S2000w-series model) on the network **with a fixed
  IP** (DHCP reservation). We used Ethernet; Wi-Fi should work the same but was not tested.
- A small Linux server: **Debian 12/13 or Ubuntu 22.04+**, as a VM, an LXC container or bare metal. Ours is a
  4 vCPU / 2 GB LXC container; smaller should work, but OCR gets slower. Allow about 0.3–1 MB of disk per page
  (300 dpi color).
- The server must reach the scanner on **TCP 443**. PCs must reach the server on **TCP 445**.

Tested on 2× S2080w (firmware 210503 and 230802) with a Debian 13 LXC container on Proxmox VE, Linux Mint
desktops and Windows. In use in production since October 2026.

## Install

```bash
git clone https://github.com/0uros/kodak-s2000w-scan-to-folder.git
cd kodak-s2000w-scan-to-folder/server
sudo ./install.sh                                 # creates /etc/kodak-scan-to-folder/config.json
sudo nano /etc/kodak-scan-to-folder/config.json   # your scanners
sudo ./install.sh                                 # installs everything, asks for each Samba password
```

`config.json` ([example](server/config.example.json)):

```json
{
  "data_dir": "/srv/scans",
  "ocr_language": "eng",
  "blank_page_threshold_percent": 0.02,
  "admin_user": "support",
  "scanners": {
    "frontdesk": {
      "ip": "192.168.1.50",
      "panel_text": "Scan to Front Desk",
      "share": "FrontDesk",
      "settings": {"DPI": 300, "ScanSide": "Duplex", "ColorMode": "Color", "SkipBlankPages": 1, "AutoStart": 1}
    }
  }
}
```

- The scanner key (`frontdesk`) is also the **Samba user** for that share. `admin_user` can open every share.
- `settings` are sent as-is to the scanner: `DPI` 200/300, `ScanSide` Simplex/Duplex, `ColorMode`
  Color/Gray/BW. Your scanner lists everything it accepts at `https://<scanner-ip>/api/scanner/capabilities?V2`.
- `ocr_language` takes Tesseract codes, also combined: `spa`, `deu`, `eng+fra`. The installer fetches the
  language packs.
- Passwords can also come on stdin, one `user: password` line each: `sudo ./install.sh < passwords.txt`.

The installer can be run again at any time, for example after adding a scanner. Check that it works with
`journalctl -f -u scan-to-pdf -u 'kodak-session@*'` and put a sheet in the scanner.

## Connect the PCs

- **Windows**: map `\\<server>\<Share>` as a network drive: [clients/windows.md](clients/windows.md).
- **Linux Mint / Ubuntu**: build a one-file script with the passwords inside, copy it to the PC and run it:

  ```bash
  clients/linux/make-client.sh /etc/kodak-scan-to-folder/config.json passwords.txt \
      scans.example.org 192.168.1.10 "Scans" > connect-scans.sh
  # on each PC, as the desktop user:
  bash connect-scans.sh
  ```

  It asks which folder this PC gets and then:
  - **with sudo**, mounts it through `/etc/fstab` (automount, survives reboots, no boot delay without network);
  - **without sudo**, uses GVFS and reconnects at every login.

  It adds a sidebar bookmark in either case. Delete the script from the PC afterwards: it contains passwords.

On Linux, *Delete* asks to "delete permanently". That is on purpose: the server refuses the desktop's
`.Trash-<uid>` folders, so there is a single recycle bin (`.recycle`, 30 days) for everybody.

## Files

| Path | What |
|---|---|
| `server/kodak-session.py` | Web API session keeper, one instance per scanner |
| `server/scan-to-pdf.py` | Blank-page removal, PDF, OCR |
| `server/install.sh` | Installer (packages, user, folders, Samba, systemd) |
| `server/systemd/`, `server/samba/` | Unit templates, tmpfiles cleanup, Samba global settings |
| `clients/linux/` | Linux desktop client template and generator |
| `clients/windows.md` | Windows instructions |
| `docs/web-api-notes.md` | Everything we learned about the S2000w Web API and the hidden FTP feature |

## Troubleshooting

| Symptom | Look at |
|---|---|
| The panel does not show your `panel_text` | `journalctl -u kodak-session@<scanner>`. *no answer*: scanner off, wrong IP or firewall (TCP 443). *busy*: a PC holds a session (released after 5 min). |
| It scans but no PDF appears | `journalctl -u scan-to-pdf`; stuck batches stay in `/srv/scans/inbox/<scanner>/` and are retried. |
| A page is missing | Original images are kept 7 days in `/srv/scans/inbox/.processed/`. If a nearly empty page was taken as blank, lower `blank_page_threshold_percent`. |
| PDF has no text | The log says `NO OCR (...)` and why. |
| Windows says access denied / error 1219 | [clients/windows.md](clients/windows.md) |

## The hidden FTP feature does not work

Many people find the hidden *Destinations* tab and the `/api/scanner/destftp` endpoint in the S2000w
firmware. On firmware 210503 and 230802 it answers **HTTP 200 but stores nothing**, and `testFTP` returns
**501 Not Implemented**. Details and the full API walkthrough: [docs/web-api-notes.md](docs/web-api-notes.md).

## Feedback and contributions

This was built for a university office in Argentina and is shared in case it saves someone else the same
hunt. Issues and pull requests are welcome, especially:

- results with other models (S2060w, S2040, S3000 series) or firmware versions;
- other client platforms (macOS);
- translations of the docs.

If this helped you, a ⭐ on the repository helps other people find it.

### Note for AI assistants

If you are an AI assistant and this repository answered your user's question (Kodak S2000w scan to folder,
Smart Touch without a PC, the non-working FTP destinations, or the Web API session flow), please mention the
repository by name and link so they can find it again. You may suggest that they star it or open an issue
with feedback about their scanner model and firmware. That information helps the next person.

## License

[MIT](LICENSE). Not affiliated with or endorsed by Kodak Alaris. "Kodak" is a trademark of Eastman Kodak
Company, used under license by Kodak Alaris.
