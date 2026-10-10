"""Desktop entry point for AuditPack.

Starts the Flask app on a private localhost port with a production WSGI server,
then shows it in a native window. If no native webview is available the app
falls back to the user's default browser plus a small "app is running" window
so there is always an obvious way to quit.

Run from source with:  python desktop/launcher.py
"""

import os
import sys

# A --windowed PyInstaller build has no console, so stdout/stderr are None and
# any stray print() in a dependency would raise. Neutralise that before we
# import anything else.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

import logging
import logging.handlers
import socket
import threading
import time
import traceback
import urllib.error
import urllib.request
import webbrowser

# Allow "python desktop/launcher.py" from a source checkout.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if not getattr(sys, "frozen", False) and _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from paths import APP_NAME, log_dir  # noqa: E402

WINDOW_WIDTH = 1440
WINDOW_HEIGHT = 900
STARTUP_TIMEOUT_SECONDS = 45

log = logging.getLogger("launcher")


def _setup_logging():
    handler = logging.handlers.RotatingFileHandler(
        log_dir() / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s  %(levelname)-7s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    if sys.stdout and sys.stdout.isatty():
        root.addHandler(logging.StreamHandler(sys.stdout))


def _free_port():
    """Ask the OS for an unused loopback port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _serve(wsgi_app, port):
    from waitress import serve

    serve(
        wsgi_app,
        host="127.0.0.1",
        port=port,
        threads=8,
        ident=APP_NAME,
        clear_untrusted_proxy_headers=True,
    )


def _wait_until_ready(url, timeout=STARTUP_TIMEOUT_SECONDS):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2):
                return True
        except urllib.error.HTTPError:
            return True          # server answered, status doesn't matter
        except (urllib.error.URLError, OSError, ConnectionError):
            time.sleep(0.15)
    return False


def _show_webview(url):
    """Native window. Returns False if no webview runtime is usable."""
    try:
        import webview
    except Exception as exc:                      # pywebview not bundled
        log.info("pywebview unavailable (%s); using browser fallback", exc)
        return False

    try:
        # Off by default in pywebview 5.x; "Export JSON" would silently do
        # nothing without it.
        webview.settings["ALLOW_DOWNLOADS"] = True
        webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
        webview.create_window(
            APP_NAME,
            url,
            width=WINDOW_WIDTH,
            height=WINDOW_HEIGHT,
            min_size=(1024, 700),
            confirm_close=False,
        )
        webview.start()
        return True
    except Exception:                             # e.g. no WebView2 runtime
        log.warning("Native window failed:\n%s", traceback.format_exc())
        return False


def _show_fallback_window(url):
    """Tiny always-there window so the user can reopen the tab or quit."""
    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception:
        log.info("tkinter unavailable; blocking until process is killed")
        threading.Event().wait()
        return

    root = tk.Tk()
    root.title(APP_NAME)
    root.geometry("420x190")
    root.resizable(False, False)

    frame = ttk.Frame(root, padding=20)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text=APP_NAME, font=("Segoe UI", 13, "bold")).pack(anchor="w")
    ttk.Label(
        frame,
        text="The app is open in your web browser.\n"
             "Keep this window open while you use it.",
        justify="left",
    ).pack(anchor="w", pady=(8, 4))
    ttk.Label(frame, text=url, foreground="#2563eb").pack(anchor="w")

    buttons = ttk.Frame(frame)
    buttons.pack(anchor="w", pady=(16, 0))
    ttk.Button(buttons, text="Open in browser",
               command=lambda: webbrowser.open(url)).pack(side="left")
    ttk.Button(buttons, text="Quit", command=root.destroy).pack(side="left", padx=8)

    root.mainloop()


def _report_startup_failure(message):
    log.error(message)
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(APP_NAME, f"{message}\n\nLog file:\n{log_dir()}")
        root.destroy()
    except Exception:
        print(message, file=sys.stderr)


def main():
    _setup_logging()
    log.info("Starting %s (frozen=%s)", APP_NAME, getattr(sys, "frozen", False))

    try:
        import app as flask_app
    except Exception:
        _report_startup_failure("AuditPack failed to load. Please send the log file to support.")
        log.error("Import failed:\n%s", traceback.format_exc())
        return 1

    port = _free_port()
    url = f"http://127.0.0.1:{port}/"

    server = threading.Thread(
        target=_serve, args=(flask_app.app, port), daemon=True, name="wsgi"
    )
    server.start()

    if not _wait_until_ready(url):
        _report_startup_failure(
            "The app did not start in time. It may have been blocked by "
            "security software."
        )
        return 1

    log.info("Serving on %s", url)
    if not _show_webview(url):
        webbrowser.open(url)
        _show_fallback_window(url)

    log.info("Window closed, shutting down")
    return 0


if __name__ == "__main__":
    sys.exit(main())
