# NEXVARY USB-USIM Lab (0.1.0)

Cross-platform, local-only laboratory diagnostics for recycled cellular USB modems.
This is a **hardware compatibility tool**, not a finished VoWiFi implementation.
It does **not** perform USIM AKA, open arbitrary APDU channels, send SMS, unlock
SIMs, bypass Android carrier privileges, deploy the gateway, or claim carrier support.

## Windows

Open PowerShell in the repository checkout:

```powershell
cd tools/usim-lab
py -m pip install -r requirements.txt
py -m nexvary_usim_lab gui
```

To run without the modem: `py -m nexvary_usim_lab demo`

Find serial ports: `py -m nexvary_usim_lab ports`

Read-only test: `py -m nexvary_usim_lab probe --port COM3 --export report.json`

## Ubuntu / Debian

```bash
cd tools/usim-lab
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m nexvary_usim_lab ports
python -m nexvary_usim_lab gui
```

Use the GUI only in a graphical desktop session; on a headless Ubuntu host
use `ports` / `probe`. On Linux the user needs permission to access the serial
device. Do not blindly run as root or change host serial services.

## What gets tested?

A bounded, fixed read-only AT command list: basic connection, vendor, model,
firmware, SIM-ready status, masked ICCID (when supported), signal, registration,
and **test-form probes** for CSIM/CGLA/CCHO/CRSM. A negative `=?` reply
does not prove the actual command is absent. Even a positive test-form reply
does not prove APDU or USIM AKA works.

The optional `pcsc` command lists PC/SC readers if `pyscard` is installed.
It does not connect to cards or send APDUs. The offline `demo` is prominently
marked simulated; it never substitutes for a physical modem.

The report masks contiguous 12–22 digit decimal identifiers and does not query
IMSI, phone numbers, messages, Ki or OP/OPc. Avoid sharing full Windows hardware
IDs or unredacted third-party diagnostic logs.

## Windows build

GitHub Actions in `.github/workflows/usim-lab.yml` builds a Windows
`NEXVARY-USIM-Lab.exe` artifact with PyInstaller and separately runs
unit tests on Windows and Ubuntu. A passing CI job is not hardware proof.
No installer is produced in the first milestone.

## Next gates

1. Test actual Huawei/ZTE/etc. modem VID:PID and AT port, record masked results.
2. Establish **authorized** local USIM/ISIM access and read-only APDU tests;
   distinguish physical reader PC/SC from vendor-specific AT or QMI UIM.
3. Build a per-device, fail-closed AKA adapter for authorized challenge material,
   using on-card calculation only. Never persist secrets or expose raw APDUs
   through a web API. Adapt transport with mutual authentication and consent.
4. Review all upstream third-party source and licensing before combining code.
5. Independently verify ePDG, SWu/IPsec, IMS registration and real calls.

The existing `server/engine/nexvary_aka_backend.py` remains unchanged: its
phone authorization contract must not be bypassed by a laboratory utility.

## Optional actual APDU transport check

When the card owner explicitly consents, `python -m nexvary_usim_lab
select-mf --port COM3 --consent` sends exactly the fixed, non-persistent
SELECT MF APDU `00 A4 00 00 02 3F 00` via `AT+CSIM`. Only the
ISO-7816 status word is returned, never raw response bytes. Some devices
do not support this command, or require another application/channel context.
A successful SELECT does **not** establish USIM AKA or VoWiFi support.
The desktop GUI offers the same one-shot, consented test.
