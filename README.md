<div align="center">

# ChangeNet

**Automatic Tor-based IP Rotator**

Rotate your public (exit) IP address through the Tor network at a chosen interval,
and watch the location change live in a Tor-proxied browser.

`Author: Amir` · `Studio: Devjix` · [www.devjix.com](https://www.devjix.com)

![Python](https://img.shields.io/badge/python-3.7%2B-blue)
![Platform](https://img.shields.io/badge/platform-Kali%20Linux-informational)
![License](https://img.shields.io/badge/license-MIT-green)

</div>

---

## Overview

ChangeNet is a terminal tool for Kali Linux (and most Debian-based systems) that
periodically requests a new Tor circuit, giving you a fresh exit IP every *N*
seconds. Each rotation prints the new IP along with its geolocation (city,
country, latitude/longitude) and ISP. Optionally it opens a browser that is
pre-configured to route through the same Tor proxy, so you can see the apparent
location change on sites like **ipleak.net** or **dnsleaktest.com**.

It is intended for **authorised privacy research, anonymity testing, and
educational use**.

## Features

- **Automatic rotation** — set an interval in seconds; the exit IP changes on its own.
- **Live geolocation** — shows IP, city/country, lat/lon and ISP for every new identity.
- **Tor-proxied browser** — opens Firefox or Chromium through the Tor SOCKS proxy (with DNS routed through Tor) so location checks reflect the real exit node.
- **First-run auto-installer** — if required packages are missing, ChangeNet downloads and installs them automatically in a separate "installer" window with a progress animation and a matrix effect.
- **Self-contained Tor instance** — launches its own Tor on non-default ports; it does not touch your system Tor configuration.
- **Clean teardown** — kills Tor, closes the browser, and removes all temporary profiles on exit.

## Requirements

- Python 3.7+
- Tor (`apt install tor`)
- Python packages: `stem`, `requests`, `PySocks`

> On first run these are installed for you automatically if they are missing.

## Installation

```bash
git clone https://github.com/<your-username>/changenet.git
cd changenet

# Optional — install dependencies yourself (otherwise ChangeNet does it on first run)
sudo apt update && sudo apt install -y tor
pip3 install -r requirements.txt
```

## Usage

```bash
python3 changenet.py
```

You will be asked for:

1. **Rotation interval** in seconds (e.g. `3`).
2. Whether to **open a browser** to watch the location change, and which site to use.

Press **Ctrl+C** to stop. When the browser is open, press **F5** after each
rotation to load the new location.

Extra flags:

```bash
python3 changenet.py --matrix     # play the digital-rain effect and exit
```

## How it works

```
                 NEWNYM signal
   ChangeNet  ───────────────►  Tor control port
       │                             │
       │   every N seconds           ▼
       │                        new circuit → new exit node → new public IP
       ▼
   your traffic ──► Tor SOCKS proxy (127.0.0.1:9062) ──► Internet
```

ChangeNet launches a private Tor process with a SOCKS port and a control port.
On each interval it sends Tor a `NEWNYM` signal to build a new circuit, then
queries an IP/geolocation service **through Tor** to confirm and display the new
exit IP.

## Important notes

- **Only proxied traffic is anonymous.** ChangeNet anonymises traffic that goes
  through `127.0.0.1:9062`. The browser it opens is already configured for this;
  point any other tools at the same SOCKS proxy or they will use your real IP.
- **Tor rate limit.** Tor issues a new identity at most about once every 10
  seconds. Intervals shorter than that may occasionally return the same IP —
  ChangeNet flags these as `unchanged (Tor rate limit)`.

## Disclaimer

This tool is provided for lawful, authorised use only — such as privacy
research, anonymity testing, and education. You are responsible for complying
with all applicable laws and the terms of service of any system or site you
access. The author and Devjix accept no liability for misuse.

## License

Released under the **MIT License** — see [LICENSE](LICENSE).

---

<div align="center">
Made with care by <b>Amir</b> · <b>Devjix</b> · <a href="https://www.devjix.com">www.devjix.com</a>
</div>
