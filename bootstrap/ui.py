"""Minimal tkinter progress window shown during bootstrap.

The actual bootstrap work runs on a background thread; this window only
ever touches Tk widgets from the main thread, via a polled queue.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable


class ProgressWindow:
    def __init__(self, title: str) -> None:
        self.root = tk.Tk()
        self.root.title(title)
        self.root.geometry("440x150")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", lambda: None)  # ignore manual close during setup

        self.status_var = tk.StringVar(value="Starting...")
        label = tk.Label(
            self.root, textvariable=self.status_var, wraplength=400, justify="left", padx=18, pady=18
        )
        label.pack(fill="x")

        self.progress = ttk.Progressbar(self.root, mode="indeterminate")
        self.progress.pack(fill="x", padx=18, pady=(0, 18))
        self.progress.start(10)

        self._queue: "queue.Queue[tuple[str, object]]" = queue.Queue()
        self._closed = False

    def set_status(self, text: str) -> None:
        self._queue.put(("status", text))

    def finish(self) -> None:
        self._queue.put(("finish", None))

    def fail(self, title: str, message: str) -> None:
        self._queue.put(("fail", (title, message)))

    def _poll(self) -> None:
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "status":
                    self.status_var.set(str(payload))
                elif kind == "finish":
                    self._closed = True
                    self.root.destroy()
                    return
                elif kind == "fail":
                    title, message = payload  # type: ignore[misc]
                    self.progress.stop()
                    messagebox.showerror(title, message, parent=self.root)
                    self._closed = True
                    self.root.destroy()
                    return
        except queue.Empty:
            pass
        if not self._closed:
            self.root.after(100, self._poll)

    def run(self, worker: Callable[[], None]) -> None:
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        self.root.after(100, self._poll)
        self.root.mainloop()
