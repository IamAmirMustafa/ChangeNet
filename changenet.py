#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
#  ChangeNet  —  Automatic Tor-based IP Rotator
#  Rotates your public (exit) IP address through the Tor network at a chosen
#  interval, and can open a Tor-proxied browser to watch the location change.
#
#  Author : Amir
#  Studio : Devjix  ·  www.devjix.com
#  License: MIT
#
#  FOR AUTHORISED PRIVACY RESEARCH AND PERSONAL TESTING ONLY.
#  Only traffic routed through the Tor SOCKS proxy (127.0.0.1:<SocksPort>) is
#  anonymised. Point your other tools at the same proxy or they will leak your
#  real IP.
# =============================================================================

import os
import re
import sys
import time
import random
import shutil
import signal
import tempfile
import argparse
import itertools
import threading
import subprocess
import importlib.util

VERSION = "2.1"
VENDOR = "DEVJIX"
SITE = "www.devjix.com"

# ----------------------------- Configuration --------------------------------
SOCKS_PORT = 9062            # non-default to avoid clashing with system Tor
CONTROL_PORT = 9063

PIP_DEPS = {"requests": "requests", "stem": "stem", "socks": "PySocks"}
APT_DEPS = {"tor": "tor"}

IP_SERVICES = [
    "https://api.ipify.org",
    "https://ifconfig.me/ip",
    "https://icanhazip.com",
]
GEO_URL = ("http://ip-api.com/json/{ip}"
           "?fields=status,message,country,regionName,city,lat,lon,timezone,"
           "isp,org,as,proxy,hosting,query")

CHECK_SITES = {
    "1": ("https://ipleak.net", "ipleak.net           (IP + live location + DNS leak)"),
    "2": ("https://www.dnsleaktest.com", "dnsleaktest.com      (DNS + IP location)"),
    "3": ("https://check.torproject.org", "check.torproject.org (Tor confirmation)"),
}

PROXIES = {
    "http": f"socks5h://127.0.0.1:{SOCKS_PORT}",
    "https": f"socks5h://127.0.0.1:{SOCKS_PORT}",
}

# Deferred heavy imports (loaded after dependencies are ensured)
requests = None
stem_process = None
Signal = None
Controller = None

# Runtime state
tor_process = None
data_dir = None
controller = None
browser_proc = None
browser_profile = None
stop_flag = threading.Event()
ANIM = False


# ------------------------------- Colors (MailTrax style) --------------------
class C:
    R = "\033[91m"; Y = "\033[93m"; G = "\033[92m"; B = "\033[96m"; M = "\033[95m"
    D = "\033[2m"; W = "\033[1m"; X = "\033[0m"
    HI = "\033[1;30;106m"          # highlighted IP (black on bright cyan)
    ON = True

    @classmethod
    def off(cls):
        for k in ("R", "Y", "G", "B", "M", "D", "W", "X", "HI"):
            setattr(cls, k, "")
        cls.ON = False


BANNER = r"""
 ██████╗██╗  ██╗ █████╗ ███╗   ██╗ ██████╗ ███████╗███╗   ██╗███████╗████████╗
██╔════╝██║  ██║██╔══██╗████╗  ██║██╔════╝ ██╔════╝████╗  ██║██╔════╝╚══██╔══╝
██║     ███████║███████║██╔██╗ ██║██║  ███╗█████╗  ██╔██╗ ██║█████╗     ██║
██║     ██╔══██║██╔══██║██║╚██╗██║██║   ██║██╔══╝  ██║╚██╗██║██╔══╝     ██║
╚██████╗██║  ██║██║  ██║██║ ╚████║╚██████╔╝███████╗██║ ╚████║███████╗   ██║
 ╚═════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝╚══════╝   ╚═╝
""".strip("\n").split("\n")
GRADIENT = (51, 45, 39, 33, 63, 93)


def hide_cursor(): sys.stdout.write("\033[?25l"); sys.stdout.flush()
def show_cursor(): sys.stdout.write("\033[?25h"); sys.stdout.flush()
def clear(): os.system("clear" if os.name == "posix" else "cls")


def width():
    return max(60, min(shutil.get_terminal_size((80, 24)).columns - 1, 78))


def vlen(text):
    return len(re.sub(r"\033\[[0-9;]*m", "", text))


def emit(text="", delay=0.012):
    print(text)
    if ANIM:
        sys.stdout.flush()
        time.sleep(delay)


def typewrite(text, delay=0.012):
    if not ANIM:
        print(text)
        return
    for part in re.findall(r"\033\[[0-9;]*m|.", text):
        sys.stdout.write(part)
        if not part.startswith("\033"):
            sys.stdout.flush()
            time.sleep(delay)
    print()


def banner():
    print()
    for n, line in enumerate(BANNER):
        col = f"\033[1;38;5;{GRADIENT[n % len(GRADIENT)]}m" if C.ON else ""
        emit(f"  {col}{line}{C.X}", 0.06)
    typewrite(f"  {C.W}Automatic IP Rotator{C.X}  {C.D}·  powered by Tor  ·  v{VERSION}{C.X}")
    typewrite(f"  {C.D}Developed by{C.X} {C.M}{C.W}{VENDOR}{C.X}  {C.D}|{C.X}  {C.B}{SITE}{C.X}")
    emit(f"  {C.D}{'━' * (width() - 4)}{C.X}")


def section(title):
    emit()
    emit(f"  {C.B}{C.W}▌ {title}{C.X} {C.D}{'─' * max(0, width() - vlen(title) - 7)}{C.X}", 0.03)


def row(label, value, vcolor=""):
    if value not in ("", None):
        emit(f"    {C.D}{label:<13}{C.X}{vcolor}{value}{C.X}")


def panel(title, lines, colour):
    w = width() - 4
    emit(f"  {colour}╔═ {C.W}{title}{C.X}{colour} {'═' * max(0, w - vlen(title) - 4)}╗{C.X}", 0.02)
    for ln in lines:
        while vlen(ln) > w - 2:
            ln = ln[:-1]
        emit(f"  {colour}║{C.X} {ln}{' ' * (w - 2 - vlen(ln))} {colour}║{C.X}", 0.02)
    emit(f"  {colour}╚{'═' * w}╝{C.X}", 0.02)


# --------------------------- Matrix FX (unchanged) --------------------------
def matrix_rain(duration=2.5):
    """Green digital-rain effect for the given number of seconds."""
    size = shutil.get_terminal_size((80, 24))
    w, h = max(size.columns, 20), max(size.lines, 10)
    drops = [random.randint(-h, 0) for _ in range(w)]
    glyphs = "01<>[]{}#$%&*=+ABCDEF0123456789ﾊﾋｼﾅﾐｱｲｳ"
    hide_cursor()
    sys.stdout.write("\033[2J")
    end = time.time() + duration
    try:
        while time.time() < end:
            buf = []
            for i in range(w):
                y = drops[i]
                if 0 <= y < h:
                    buf.append(f"\033[{y+1};{i+1}H\033[1;92m{random.choice(glyphs)}")
                    ty = y - 1
                    if 0 <= ty < h:
                        buf.append(f"\033[{ty+1};{i+1}H\033[2;32m{random.choice(glyphs)}")
                drops[i] = y + 1
                if drops[i] > h and random.random() > 0.975:
                    drops[i] = 0
            sys.stdout.write("".join(buf) + "\033[0m")
            sys.stdout.flush()
            time.sleep(0.05)
    finally:
        sys.stdout.write("\033[0m\033[2J\033[H")
        show_cursor()


# --------------------------- Spinner (context) ------------------------------
class Spinner:
    FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, msg): self.msg = msg; self.done = False; self.t = None

    def _run(self):
        for ch in itertools.cycle(self.FRAMES):
            if self.done: break
            sys.stderr.write(f"\r\033[K  {C.B}{ch}{C.X} {self.msg} {C.D}...{C.X}")
            sys.stderr.flush(); time.sleep(0.08)

    def __enter__(self):
        if ANIM:
            self.t = threading.Thread(target=self._run, daemon=True); self.t.start()
        return self

    def __exit__(self, *a):
        self.done = True
        if self.t: self.t.join()
        sys.stderr.write("\r\033[K"); sys.stderr.flush()


# ======================= DEPENDENCY AUTO-INSTALLER ==========================
def find_missing():
    missing = []
    for import_name, pkg in PIP_DEPS.items():
        if importlib.util.find_spec(import_name) is None:
            missing.append("pip:" + pkg)
    for binary, pkg in APT_DEPS.items():
        if shutil.which(binary) is None:
            missing.append("apt:" + pkg)
    return missing


def installer_banner():
    clear()
    print()
    for n, line in enumerate(BANNER):
        col = f"\033[1;38;5;{GRADIENT[n % len(GRADIENT)]}m" if C.ON else ""
        print(f"  {col}{line}{C.X}")
    print(f"  {C.D}Dependency bootstrap  ·  {VENDOR}{C.X}")
    print(f"  {C.D}{'━' * (width() - 4)}{C.X}\n")


def _run_animated(cmd, title):
    print(f"\n  {C.B}▸ {title}{C.X}")
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, bufsize=1)
    except FileNotFoundError:
        print(f"    {C.R}command not found: {cmd[0]}{C.X}")
        return 127

    lines = []
    def reader():
        try:
            for ln in proc.stdout:
                lines.append(ln.rstrip())
        except Exception:
            pass
    t = threading.Thread(target=reader, daemon=True); t.start()

    bar_len = 30; i = 0
    while proc.poll() is None or t.is_alive():
        i += 1
        pos = i % (bar_len * 2)
        fill = pos if pos <= bar_len else bar_len * 2 - pos
        bar = "█" * fill + "░" * (bar_len - fill)
        last = (lines[-1][:46] if lines else "working...")
        sys.stdout.write(f"\r    {C.G}[{bar}]{C.X} {C.D}{last:<46}{C.X}")
        sys.stdout.flush(); time.sleep(0.05)

    rc = proc.wait()
    status = f"{C.G}{C.W}DONE{C.X}" if rc == 0 else f"{C.R}{C.W}FAILED{C.X}"
    sys.stdout.write(f"\r    {C.G}[{'█'*bar_len}]{C.X} {status}{' '*42}\n")
    return rc


def _install_one(token):
    kind, name = token.split(":", 1)
    if kind == "pip":
        rc = _run_animated([sys.executable, "-m", "pip", "install", name],
                           f"Downloading & installing Python package  ·  {name}")
        if rc != 0:
            rc = _run_animated(
                [sys.executable, "-m", "pip", "install", "--break-system-packages", name],
                f"Retry (system environment)  ·  {name}")
        return rc == 0
    else:
        is_root = hasattr(os, "geteuid") and os.geteuid() == 0
        if is_root:
            cmd = ["apt-get", "install", "-y", name]
        elif shutil.which("sudo"):
            cmd = ["sudo", "apt-get", "install", "-y", name]
        else:
            print(f"    {C.R}Need root to install '{name}'. Run: sudo apt install {name}{C.X}")
            return False
        return _run_animated(cmd, f"Downloading & installing system package  ·  {name}") == 0


def run_installer_ui(flag_path, packages):
    installer_banner()
    print(f"  {C.Y}Missing components detected. Fetching them now...{C.X}\n")
    time.sleep(0.5)
    matrix_rain(2.2)                       # <-- matrix stays
    installer_banner()

    all_ok = True
    for i, token in enumerate(packages, 1):
        print(f"  {C.D}[{i}/{len(packages)}]{C.X}", end="")
        if not _install_one(token):
            all_ok = False

    print()
    if all_ok:
        print(f"  {C.G}{C.W}✓ All dependencies installed successfully.{C.X}")
        matrix_rain(1.4)                   # <-- matrix stays
        installer_banner()
        print(f"  {C.G}{C.W}✓ Ready.{C.X}  Launching ChangeNet...\n")
        _write_flag(flag_path, "OK")
    else:
        print(f"  {C.R}{C.W}✗ Some dependencies failed to install.{C.X}")
        print(f"  {C.D}Review the log above, install them manually, then run ChangeNet again.{C.X}\n")
        _write_flag(flag_path, "FAIL")
    time.sleep(2.5)


def _write_flag(path, value):
    try:
        with open(path, "w") as f:
            f.write(value)
    except Exception:
        pass


def spawn_installer_window(flag_path, packages):
    if not os.environ.get("DISPLAY"):
        return False
    self_path = os.path.abspath(__file__)
    inner = [sys.executable, self_path, "--install", flag_path] + packages
    try:
        import shlex
        inner_str = " ".join(shlex.quote(x) for x in inner)
    except Exception:
        inner_str = " ".join(inner)

    title = "ChangeNet Installer"
    candidates = [
        ("gnome-terminal", ["gnome-terminal", f"--title={title}", "--",
                            "bash", "-lc", inner_str + "; exec bash"]),
        ("qterminal",      ["qterminal", "-e"] + inner),
        ("xfce4-terminal", ["xfce4-terminal", f"--title={title}", "--hold", "-e", inner_str]),
        ("konsole",        ["konsole", "-p", f"tabtitle={title}", "--hold", "-e"] + inner),
        ("kitty",          ["kitty", "--title", title] + inner),
        ("alacritty",      ["alacritty", "-t", title, "-e"] + inner),
        ("tilix",          ["tilix", "-t", title, "-e", inner_str]),
        ("xterm",          ["xterm", "-T", title, "-e"] + inner),
        ("x-terminal-emulator", ["x-terminal-emulator", "-T", title, "-e"] + inner),
    ]
    for name, cmd in candidates:
        if shutil.which(name):
            try:
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            except Exception:
                continue
    return False


def wait_for_flag(flag_path, timeout=900):
    status = "FAIL"
    with Spinner("Installing dependencies in a separate window (watch the installer)"):
        start = time.time()
        while time.time() - start < timeout:
            if os.path.exists(flag_path):
                try:
                    status = open(flag_path).read().strip()
                except Exception:
                    status = ""
                if status in ("OK", "FAIL"):
                    break
            time.sleep(0.4)
    return status == "OK"


def ensure_dependencies():
    missing = find_missing()
    if not missing:
        return True

    emit(f"  {C.Y}First-run setup: {len(missing)} component(s) missing.{C.X}")
    fd, flag_path = tempfile.mkstemp(prefix="changenet_flag_")
    os.close(fd)
    try:
        os.remove(flag_path)
    except Exception:
        pass

    if spawn_installer_window(flag_path, missing):
        wait_for_flag(flag_path)
    else:
        run_installer_ui(flag_path, missing)

    try:
        if os.path.exists(flag_path):
            os.remove(flag_path)
    except Exception:
        pass

    if find_missing():
        emit(f"\n  {C.R}Dependencies still missing. Please install them manually and retry.{C.X}")
        return False
    return True


def load_libs():
    global requests, stem_process, Signal, Controller
    import requests as _requests
    import stem.process as _stem_process
    from stem import Signal as _Signal
    from stem.control import Controller as _Controller
    requests = _requests
    stem_process = _stem_process
    Signal = _Signal
    Controller = _Controller


# =============================== TOR CONTROL ================================
def bootstrap_handler(line):
    if "Bootstrapped" in line:
        pct = line.split("Bootstrapped")[1].split("%")[0].strip()
        sys.stderr.write(f"\r\033[K  {C.Y}⟳{C.X} Tor bootstrapping... {C.G}{pct}%{C.X}")
        sys.stderr.flush()


def start_tor():
    global tor_process, data_dir, controller
    if shutil.which("tor") is None:
        emit(f"  {C.R}[!] 'tor' is not installed. Run: sudo apt install -y tor{C.X}")
        sys.exit(1)

    data_dir = tempfile.mkdtemp(prefix="changenet_")
    try:
        tor_process = stem_process.launch_tor_with_config(
            config={
                "SocksPort": str(SOCKS_PORT),
                "ControlPort": str(CONTROL_PORT),
                "CookieAuthentication": "1",
                "DataDirectory": data_dir,
                "Log": "notice stdout",
            },
            init_msg_handler=bootstrap_handler,
            take_ownership=True,
            timeout=90,
        )
    except Exception as e:
        emit(f"\n  {C.R}[!] Failed to launch Tor: {e}{C.X}")
        cleanup(); sys.exit(1)

    sys.stderr.write("\r\033[K"); sys.stderr.flush()
    emit(f"  {C.G}✓{C.X} Tor is ready.  {C.D}(SOCKS {C.B}127.0.0.1:{SOCKS_PORT}{C.X}{C.D}){C.X}")

    controller = Controller.from_port(port=CONTROL_PORT)
    controller.authenticate()


def new_identity():
    controller.signal(Signal.NEWNYM)
    wait = controller.get_newnym_wait()
    if wait > 0:
        time.sleep(wait)


def get_ip():
    for url in IP_SERVICES:
        try:
            r = requests.get(url, proxies=PROXIES, timeout=20)
            if r.ok and r.text.strip():
                return r.text.strip()
        except Exception:
            continue
    return None


def geo(ip):
    try:
        r = requests.get(GEO_URL.format(ip=ip), proxies=PROXIES, timeout=20)
        d = r.json()
        if d.get("status") == "success":
            return d
    except Exception:
        pass
    return None


# ========================= TOR-PROXIED BROWSER =============================
def open_check_browser(url):
    global browser_proc, browser_profile
    if not os.environ.get("DISPLAY"):
        emit(f"  {C.Y}[note]{C.X} No GUI display detected — skipping browser. "
             f"Set your browser proxy to socks5 127.0.0.1:{SOCKS_PORT} manually.")
        return

    firefox = shutil.which("firefox-esr") or shutil.which("firefox")
    if firefox:
        try:
            browser_profile = tempfile.mkdtemp(prefix="changenet_ff_")
            prefs = (
                'user_pref("network.proxy.type", 1);\n'
                'user_pref("network.proxy.socks", "127.0.0.1");\n'
                f'user_pref("network.proxy.socks_port", {SOCKS_PORT});\n'
                'user_pref("network.proxy.socks_version", 5);\n'
                'user_pref("network.proxy.socks_remote_dns", true);\n'
                'user_pref("browser.shell.checkDefaultBrowser", false);\n'
            )
            with open(os.path.join(browser_profile, "user.js"), "w") as f:
                f.write(prefs)
            browser_proc = subprocess.Popen(
                [firefox, "-profile", browser_profile, "-no-remote", "-new-instance", url],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            emit(f"  {C.G}✓{C.X} Firefox opened via Tor proxy  →  {C.B}{url}{C.X}")
            return
        except Exception as e:
            emit(f"  {C.Y}[note]{C.X} Firefox launch failed: {e}")

    chrome = (shutil.which("chromium") or shutil.which("chromium-browser")
              or shutil.which("google-chrome") or shutil.which("google-chrome-stable"))
    if chrome:
        try:
            browser_profile = tempfile.mkdtemp(prefix="changenet_cr_")
            browser_proc = subprocess.Popen(
                [chrome, f"--proxy-server=socks5://127.0.0.1:{SOCKS_PORT}",
                 f"--user-data-dir={browser_profile}",
                 "--no-first-run", "--no-default-browser-check", url],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            emit(f"  {C.G}✓{C.X} Chromium opened via Tor proxy  →  {C.B}{url}{C.X}")
            return
        except Exception as e:
            emit(f"  {C.Y}[note]{C.X} Chromium launch failed: {e}")

    emit(f"  {C.Y}[note]{C.X} No supported browser found. Install Firefox or Chromium, "
         f"or set proxy socks5 127.0.0.1:{SOCKS_PORT} manually.")


# ------------------------------- Display ------------------------------------
def show_ip(count, ip, prev_ip, browser_on):
    changed = (prev_ip is not None and ip != prev_ip)
    g = geo(ip) or {}
    status = (f"{C.G}{C.W}NEW ✓{C.X}" if changed
              else (f"{C.Y}unchanged (Tor rate limit){C.X}" if prev_ip else f"{C.G}{C.W}START{C.X}"))
    colour = C.G if (changed or not prev_ip) else C.Y

    lines = [f"{C.W}IP ADDRESS{C.X}   {C.HI} {ip} {C.X}   {status}"]
    if g.get("lat") is not None:
        place = ", ".join(x for x in (g.get("city"), g.get("regionName"), g.get("country")) if x)
        lines += [
            f"{C.D}Location{C.X}     {C.W}{place}{C.X}",
            f"{C.D}Latitude{C.X}     {C.G}{g.get('lat')}{C.X}     "
            f"{C.D}Longitude{C.X}  {C.G}{g.get('lon')}{C.X}",
            f"{C.D}Timezone{C.X}     {g.get('timezone') or '-'}",
            f"{C.D}ISP{C.X}          {g.get('isp') or '-'}",
        ]
        flags = []
        if g.get("proxy"): flags.append("proxy/VPN")
        if g.get("hosting"): flags.append("hosting/datacenter")
        if flags:
            lines.append(f"{C.D}Network{C.X}      {C.Y}{', '.join(flags)}{C.X}")
    else:
        lines.append(f"{C.D}Location{C.X}     {C.Y}lookup unavailable (offline?){C.X}")

    emit()
    panel(f"◉ EXIT IP  #{count}", lines, colour)
    if browser_on and changed:
        emit(f"  {C.D}↻ press F5 in the browser to load the new location{C.X}")


# ------------------------------ Lifecycle -----------------------------------
def cleanup():
    for proc in (browser_proc,):
        try:
            if proc: proc.terminate()
        except Exception:
            pass
    try:
        if controller: controller.close()
    except Exception:
        pass
    try:
        if tor_process: tor_process.kill()
    except Exception:
        pass
    for d in (data_dir, browser_profile):
        try:
            if d and os.path.isdir(d):
                shutil.rmtree(d, ignore_errors=True)
        except Exception:
            pass
    show_cursor()


def goodbye():
    emit(f"\n  {C.D}{'━' * (width() - 4)}{C.X}")
    typewrite(f"  {C.B}{C.W}ChangeNet stopped. Stay safe.{C.X}", 0.02)
    emit(f"  {C.D}Amir  |  {VENDOR}  |  {SITE}{C.X}\n")


def sigint_handler(sig, frame):
    stop_flag.set()


# ------------------------------- Main run -----------------------------------
def run_tool():
    clear(); banner()

    while True:
        try:
            raw = input(f"  {C.W}{C.Y}?{C.X} Rotation interval in seconds "
                        f"{C.D}(e.g. 3){C.X} {C.B}▸{C.X} ").strip()
            interval = int(raw)
            if interval < 1: raise ValueError
            break
        except (ValueError, EOFError):
            emit(f"  {C.R}[!] Enter a valid number (1 or greater).{C.X}")

    if interval < 10:
        emit(f"\n  {C.Y}[note]{C.X} Tor issues a new identity at most every {C.W}~10s{C.X}. "
             f"With a {interval}s interval the IP may sometimes repeat — this is flagged.")

    emit(f"\n  {C.W}{C.Y}?{C.X} Open a browser to watch the location change live? "
         f"{C.D}(y/n){C.X} {C.B}▸{C.X} ", 0)
    browser_on = False; site_url = None
    try:
        if input().strip().lower().startswith("y"):
            emit(f"  {C.D}Choose a site:{C.X}")
            for k, (u, label) in CHECK_SITES.items():
                emit(f"    {C.B}{k}{C.X}) {label}")
            choice = input(f"  {C.B}▸{C.X} ").strip()
            site_url = CHECK_SITES.get(choice, CHECK_SITES["1"])[0]
            browser_on = True
    except EOFError:
        pass

    emit()
    with Spinner("Connecting to the Tor network"):
        start_tor()

    if browser_on:
        open_check_browser(site_url)

    section("ROTATION")
    emit(f"  {C.G}{C.W}▶ Active{C.X} {C.D}— IP changes every{C.X} {C.W}{interval}s{C.X}  "
         f"{C.D}(Ctrl+C to stop){C.X}")

    signal.signal(signal.SIGINT, sigint_handler)

    count = 0; prev_ip = None
    while not stop_flag.is_set():
        count += 1
        with Spinner("Requesting a new identity"):
            if count > 1:
                new_identity()
            ip = get_ip()

        if ip is None:
            emit(f"  {C.R}[!] Could not fetch IP (network/Tor issue). Retrying...{C.X}")
            count -= 1
            if stop_flag.wait(timeout=3): break
            continue

        show_ip(count, ip, prev_ip, browser_on)
        prev_ip = ip
        if stop_flag.wait(timeout=interval): break

    cleanup(); goodbye()


# -------------------------------- Entry -------------------------------------
def main():
    global ANIM
    parser = argparse.ArgumentParser(
        description="ChangeNet — automatic Tor-based IP rotator (by Devjix).")
    parser.add_argument("--install", nargs="+", metavar="ARG", help=argparse.SUPPRESS)
    parser.add_argument("--matrix", action="store_true", help="Play the digital-rain effect and exit.")
    parser.add_argument("--no-color", action="store_true", help="Disable colored output.")
    parser.add_argument("--no-anim", action="store_true", help="Disable animations.")
    args = parser.parse_args()

    if args.no_color or not sys.stdout.isatty():
        C.off()
    ANIM = sys.stdout.isatty() and not args.no_anim

    if args.matrix:
        try:
            matrix_rain(5.0)
        finally:
            show_cursor()
        return

    if args.install:
        flag_path, packages = args.install[0], args.install[1:]
        try:
            run_installer_ui(flag_path, packages)
        except KeyboardInterrupt:
            _write_flag(flag_path, "FAIL")
        return

    clear(); banner()
    if not ensure_dependencies():
        sys.exit(1)
    load_libs()
    run_tool()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        cleanup(); goodbye()
    except Exception as e:
        print(f"\n{C.R}[!] Error: {e}{C.X}")
        cleanup(); sys.exit(1)
