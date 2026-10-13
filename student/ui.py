"""Student-side user interface.

Classroom software must be visible to the student: they should always know the
machine can be monitored or locked by the teacher. This module provides a small
UI abstraction with two implementations:

* ``TkStudentUI`` — a real on-screen UI (a persistent status banner, a
  full-screen lock overlay and message pop-ups) used when Tkinter and a display
  are available.
* ``HeadlessStudentUI`` — a logging-only fallback for servers / CI where no
  display exists.

``create_ui()`` picks the best available implementation.
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Callable, Optional

log = logging.getLogger("student.ui")


class StudentUI:
    """Interface implemented by every UI backend."""

    def start(self) -> None: ...
    def stop(self) -> None: ...
    def set_connected(self, connected: bool, room: str = "") -> None: ...
    def show_lock(self, title: str, body: str) -> None: ...
    def hide_lock(self) -> None: ...
    def show_message(self, title: str, text: str) -> None: ...
    def run_forever(self, on_ready: Optional[Callable[[], None]] = None) -> None: ...


class HeadlessStudentUI(StudentUI):
    """No display: just log what a real UI would show."""

    def __init__(self) -> None:
        self._locked = False
        self._stop = threading.Event()

    def set_connected(self, connected: bool, room: str = "") -> None:
        log.info("status: %s (room=%s)", "connected" if connected else "offline", room)

    def show_lock(self, title: str, body: str) -> None:
        self._locked = True
        log.info("LOCK SCREEN shown: %s - %s", title, body)

    def hide_lock(self) -> None:
        self._locked = False
        log.info("lock screen hidden")

    def show_message(self, title: str, text: str) -> None:
        log.info("MESSAGE from teacher [%s]: %s", title, text)

    def run_forever(self, on_ready: Optional[Callable[[], None]] = None) -> None:
        if on_ready:
            on_ready()
        self._stop.wait()

    def stop(self) -> None:
        self._stop.set()


class TkStudentUI(StudentUI):
    """Real Tkinter UI. All Tk calls run on the thread that owns the mainloop."""

    def __init__(self) -> None:
        import tkinter as tk  # noqa: F401  (import guarded by create_ui)

        self._tk = __import__("tkinter")
        self._root = None
        self._lock_win = None
        self._banner = None
        self._actions: "queue.Queue[Callable[[], None]]" = queue.Queue()

    # The Tk mainloop thread polls this queue so other threads can schedule work.
    def _pump(self) -> None:
        try:
            while True:
                action = self._actions.get_nowait()
                try:
                    action()
                except Exception:  # pragma: no cover - defensive
                    log.exception("ui action failed")
        except queue.Empty:
            pass
        if self._root is not None:
            self._root.after(50, self._pump)

    def _schedule(self, fn: Callable[[], None]) -> None:
        self._actions.put(fn)

    def run_forever(self, on_ready: Optional[Callable[[], None]] = None) -> None:
        tk = self._tk
        self._root = tk.Tk()
        self._root.title("Classroom Agent")
        self._root.geometry("320x70+20+20")
        self._root.attributes("-topmost", True)
        self._banner = tk.Label(
            self._root,
            text="Classroom Agent — connecting…",
            font=("Helvetica", 11),
            fg="white",
            bg="#1f6feb",
            padx=12,
            pady=12,
            justify="left",
            anchor="w",
        )
        self._banner.pack(fill="both", expand=True)
        self._pump()
        if on_ready:
            on_ready()
        self._root.mainloop()

    def set_connected(self, connected: bool, room: str = "") -> None:
        def _do() -> None:
            if not self._banner:
                return
            if connected:
                self._banner.config(
                    text=f"Classroom Agent — connected\nRoom: {room}", bg="#1f6feb"
                )
            else:
                self._banner.config(text="Classroom Agent — offline", bg="#6e7681")

        self._schedule(_do)

    def show_lock(self, title: str, body: str) -> None:
        tk = self._tk

        def _do() -> None:
            if self._lock_win is not None:
                return
            win = tk.Toplevel(self._root)
            win.attributes("-fullscreen", True)
            win.attributes("-topmost", True)
            win.configure(bg="#0d1117")
            win.protocol("WM_DELETE_WINDOW", lambda: None)
            tk.Label(
                win, text="🔒", font=("Helvetica", 72), fg="white", bg="#0d1117"
            ).pack(pady=(120, 10))
            tk.Label(
                win, text=title, font=("Helvetica", 28, "bold"),
                fg="white", bg="#0d1117",
            ).pack(pady=10)
            tk.Label(
                win, text=body, font=("Helvetica", 16), fg="#c9d1d9",
                bg="#0d1117", wraplength=700, justify="center",
            ).pack(pady=10)
            self._lock_win = win

        self._schedule(_do)

    def hide_lock(self) -> None:
        def _do() -> None:
            if self._lock_win is not None:
                self._lock_win.destroy()
                self._lock_win = None

        self._schedule(_do)

    def show_message(self, title: str, text: str) -> None:
        tk = self._tk

        def _do() -> None:
            win = tk.Toplevel(self._root)
            win.title(title or "Message from teacher")
            win.attributes("-topmost", True)
            win.configure(bg="white")
            tk.Label(
                win, text=title or "Message from teacher",
                font=("Helvetica", 14, "bold"), bg="white", fg="#1f6feb",
            ).pack(padx=20, pady=(18, 6))
            tk.Label(
                win, text=text, font=("Helvetica", 12), bg="white",
                wraplength=380, justify="left",
            ).pack(padx=20, pady=6)
            tk.Button(win, text="OK", command=win.destroy, width=10).pack(pady=14)

        self._schedule(_do)

    def stop(self) -> None:
        def _do() -> None:
            if self._root is not None:
                self._root.quit()

        self._schedule(_do)


def create_ui() -> StudentUI:
    """Return a Tk UI if a display is usable, else a headless fallback."""
    try:
        import tkinter as tk

        root = tk.Tk()
        root.destroy()
        return TkStudentUI()
    except Exception as exc:  # no display, no tkinter, etc.
        log.info("falling back to headless UI (%s)", exc)
        return HeadlessStudentUI()
