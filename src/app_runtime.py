import contextlib
import io
import os
import queue
import subprocess
import sys
import threading
import traceback
from pathlib import Path
from typing import Callable, Optional

from paths import DEFAULT_OUTPUT_PATH, PROJECT_ROOT


DEFAULT_OUTPUT = DEFAULT_OUTPUT_PATH


class TaskCancelled(Exception):
    pass


class ProcessManager:
    def __init__(self):
        self.callable_thread = None
        self.stop_callable: Optional[Callable[[], None]] = None
        self.stop_requested = False
        self.events = queue.Queue()

    def start_callable(self, worker_fn, status_text: str, stop_fn: Optional[Callable[[], None]] = None):
        if self.callable_thread and self.callable_thread.is_alive():
            raise RuntimeError("Wait for the current task to finish or stop it first.")

        self.stop_requested = False
        self.events.put(("busy", True))
        self.events.put(("status", status_text))
        self.stop_callable = stop_fn

        manager = self

        class QueueWriter(io.TextIOBase):
            def write(self, text):
                if text:
                    manager.events.put(("log", text))
                return len(text)

            def flush(self):
                return None

        def worker():
            stream = QueueWriter()
            try:
                with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
                    worker_fn()
                if self.stop_requested:
                    self.events.put(("log", "\nTask stopped.\n"))
                    self.events.put(("info", ("Task Stopped", "The running task has stopped.")))
                else:
                    self.events.put(("log", "\nTask finished successfully.\n"))
                self.events.put(("status", "Ready"))
                self.events.put(("busy", False))
            except TaskCancelled:
                self.events.put(("log", "\nTask stopped.\n"))
                self.events.put(("info", ("Task Stopped", "The running task has stopped.")))
                self.events.put(("status", "Ready"))
                self.events.put(("busy", False))
            except Exception:
                self.events.put(("log", f"\n{traceback.format_exc()}\n"))
                self.events.put(("status", "Ready"))
                self.events.put(("busy", False))
            finally:
                self.stop_callable = None
                self.callable_thread = None
                self.stop_requested = False

        self.callable_thread = threading.Thread(target=worker, daemon=True)
        self.callable_thread.start()

    def stop(self):
        if self.callable_thread and self.callable_thread.is_alive():
            self.stop_requested = True
            self.events.put(("status", "Stopping task..."))
            self.events.put(("log", "\nRequested task stop.\n"))
            if self.stop_callable is not None:
                self.stop_callable()
                return True
            self.events.put(("log", "This task does not support cooperative stop.\n"))
            self.stop_requested = False
            return False
        return False


def open_export_folder_path(output: str):
    target = Path(output).expanduser().resolve().parent
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(target)], cwd=str(PROJECT_ROOT))
    elif sys.platform == "win32":
        os.startfile(str(target))  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", str(target)], cwd=str(PROJECT_ROOT))
