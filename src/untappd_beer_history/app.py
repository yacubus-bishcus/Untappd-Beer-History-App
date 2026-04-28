import asyncio
import os
import socket
import sys
import threading
import time
import traceback
import webbrowser
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen

import toga
from app_config import get_configured_username, set_configured_username  # noqa: E402
from paths import STREAMLIT_APP_PATH  # noqa: E402
from run import DEFAULT_DEBUGGER_ADDRESS, DEFAULT_USER_DATA_DIR, perform_beer_fetch_workflow  # noqa: E402
from streamlit.web.bootstrap import run as run_streamlit_server
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from untappd_beer_history import __version__

STREAMLIT_STARTUP_TIMEOUT = float(os.environ.get("UNTAPPD_STREAMLIT_STARTUP_TIMEOUT", "60"))


def default_runtime_data_dir() -> Path:
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Untappd Beer History"
    return home / ".local" / "share" / "untappd-beer-history"


os.environ.setdefault("UNTAPPD_DATA_DIR", str(default_runtime_data_dir()))
Path(os.environ["UNTAPPD_DATA_DIR"]).mkdir(parents=True, exist_ok=True)

from desktop_launcher import (  # noqa: E402
    DEFAULT_OUTPUT,
    ProcessManager,
    maybe_start_initial_sync,
    open_export_folder_path,
)


def build_stamp() -> str:
    app_file = Path(__file__).resolve()
    build_time = datetime.fromtimestamp(app_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    mode = "Bundled app" if "/Resources/app/" in str(app_file) else "Source"
    return f"Version {__version__} | {mode} | {build_time}"


class UntappdBeerHistoryApp(toga.App):
    def startup(self):
        self.manager = ProcessManager()
        self.build_stamp_text = build_stamp()
        self.streamlit_thread = None
        self.streamlit_port = None
        self.streamlit_ready_event = threading.Event()
        self.streamlit_error = None
        self.username_input = toga.TextInput(
            value=get_configured_username(""),
            placeholder="Untappd username",
            style=Pack(flex=1),
        )
        self.backstop_input = toga.TextInput(
            placeholder="Optional total",
            style=Pack(width=160),
        )
        self.output_input = toga.TextInput(
            value=str(DEFAULT_OUTPUT),
            placeholder="CSV output path",
            style=Pack(flex=1),
        )
        self.build_label = toga.Label(
            self.build_stamp_text,
            style=Pack(margin_top=4),
        )
        self.status_label = toga.Label("Ready", style=Pack(margin_top=8))
        self.progress = toga.ProgressBar(max=None, style=Pack(margin_top=8))
        self.log_output = toga.MultilineTextInput(
            readonly=True,
            value=f"Launcher ready.\n{self.build_stamp_text}\n",
            style=Pack(flex=1, margin_top=8),
        )

        controls = toga.Box(
            style=Pack(direction=COLUMN, margin=16, gap=10),
            children=[
                self._row("Username", self.username_input),
                self._row("Backstop Total", self.backstop_input),
                self._row(
                    "Output CSV",
                    self.output_input,
                    toga.Button("Browse", on_press=self.choose_output, style=Pack(width=100)),
                ),
                self.build_label,
                self._button_row(
                    toga.Button("Open Dashboard", on_press=self.open_dashboard, style=Pack(flex=1)),
                    toga.Button(
                        "Refresh Data + Dashboard",
                        on_press=self.refresh_and_open,
                        style=Pack(flex=1),
                    ),
                    toga.Button("Refresh Data Only", on_press=self.refresh_only, style=Pack(flex=1)),
                ),
                self._button_row(
                    toga.Button("Open Export Folder", on_press=self.open_export_folder, style=Pack(flex=1)),
                    toga.Button("Stop Running Task", on_press=self.stop_process, style=Pack(flex=1)),
                ),
                self.status_label,
                self.progress,
                self.log_output,
            ],
        )

        self.main_window = toga.MainWindow(title=self.formal_name, size=(900, 700))
        self.main_window.content = controls
        self.main_window.show()

        asyncio.create_task(self.poll_events())
        asyncio.create_task(self.finish_first_launch_setup())

    def _row(self, label_text, *widgets):
        children = [
            toga.Label(label_text, style=Pack(width=120, padding_top=8)),
            *widgets,
        ]
        return toga.Box(children=children, style=Pack(direction=ROW, gap=10))

    def _button_row(self, *buttons):
        return toga.Box(children=list(buttons), style=Pack(direction=ROW, gap=10))

    async def finish_first_launch_setup(self):
        if not self.username_input.value.strip():
            await self.main_window.dialog(
                toga.InfoDialog(
                    "Untappd Username",
                    "Enter your Untappd username in the field at the top of the window, then choose a refresh action.",
                )
            )
            return

        maybe_start_initial_sync(
            self.refresh_and_open,
            lambda: self.username_input.value,
            lambda: self.output_input.value,
        )

    async def poll_events(self):
        while True:
            while not self.manager.events.empty():
                event_type, payload = self.manager.events.get_nowait()
                if event_type == "log":
                    self.log_output.value = (self.log_output.value or "") + payload
                    self.log_output.scroll_to_bottom()
                elif event_type == "status":
                    self.status_label.text = payload
                elif event_type == "busy":
                    if payload:
                        self.progress.start()
                    else:
                        self.progress.stop()
            await asyncio.sleep(0.15)

    async def choose_output(self, widget):
        suggested = Path(self.output_input.value or DEFAULT_OUTPUT).name
        target = await self.main_window.dialog(
            toga.SaveFileDialog("Choose output CSV", suggested_filename=suggested, file_types=["csv"])
        )
        if target is not None:
            self.output_input.value = str(target)

    def _collect_workflow_options(self):
        username = (self.username_input.value or "").strip()
        if not username:
            raise ValueError("Please enter your Untappd username.")
        set_configured_username(username)

        output = (self.output_input.value or "").strip() or str(DEFAULT_OUTPUT)
        backstop_text = (self.backstop_input.value or "").strip()
        if backstop_text and not backstop_text.isdigit():
            raise ValueError("Backstop Total must be a whole number.")

        return {
            "username": username,
            "output": output,
            "backstop_total": int(backstop_text) if backstop_text else None,
            "debugger_address": DEFAULT_DEBUGGER_ADDRESS,
            "user_data_dir": DEFAULT_USER_DATA_DIR,
        }

    def _show_error(self, title: str, message: str):
        asyncio.create_task(self.main_window.dialog(toga.ErrorDialog(title, message)))

    def _start_process(self, command, status_text):
        try:
            self.manager.start(command, status_text)
        except RuntimeError as exc:
            self._show_error("Task Already Running", str(exc))

    def _start_task(self, worker_fn, status_text):
        try:
            self.manager.start_callable(worker_fn, status_text)
        except RuntimeError as exc:
            self._show_error("Task Already Running", str(exc))

    def _choose_streamlit_port(self) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return sock.getsockname()[1]

    def _wait_for_streamlit_ready(self, timeout: float = STREAMLIT_STARTUP_TIMEOUT) -> bool:
        if self.streamlit_port is None:
            return False

        deadline = time.time() + timeout
        urls_to_check = [
            f"http://127.0.0.1:{self.streamlit_port}/_stcore/health",
            f"http://127.0.0.1:{self.streamlit_port}/",
        ]
        while time.time() < deadline:
            if self.streamlit_error is not None:
                return False
            if self.streamlit_thread is not None and not self.streamlit_thread.is_alive():
                return False
            for url in urls_to_check:
                try:
                    with urlopen(url, timeout=1.0) as response:
                        if 200 <= getattr(response, "status", 200) < 500:
                            return True
                except Exception:
                    continue
            time.sleep(0.25)
        return False

    def _ensure_streamlit_server(self):
        if self.streamlit_thread and self.streamlit_thread.is_alive():
            if self._wait_for_streamlit_ready():
                return
            if self.streamlit_error is not None:
                raise RuntimeError(f"Streamlit failed to start: {self.streamlit_error}")
            raise RuntimeError("Streamlit did not become ready in time.")

        self.streamlit_port = self._choose_streamlit_port()
        self.streamlit_ready_event.clear()
        self.streamlit_error = None
        self.manager.events.put(
            (
                "log",
                f"\nStarting Streamlit on http://127.0.0.1:{self.streamlit_port} "
                f"(timeout {STREAMLIT_STARTUP_TIMEOUT:.0f}s)...\n",
            )
        )

        def streamlit_worker():
            try:
                run_streamlit_server(
                    str(STREAMLIT_APP_PATH),
                    False,
                    [],
                    {
                        "server.headless": True,
                        "server.address": "127.0.0.1",
                        "browser.gatherUsageStats": False,
                        "server.port": self.streamlit_port,
                    },
                )
            except BaseException as exc:
                self.streamlit_error = "".join(
                    traceback.format_exception(type(exc), exc, exc.__traceback__)
                ).strip()
                self.manager.events.put(("log", f"\nStreamlit startup failed:\n{self.streamlit_error}\n"))
                raise

        self.streamlit_thread = threading.Thread(target=streamlit_worker, daemon=True)
        self.streamlit_thread.start()
        if not self._wait_for_streamlit_ready():
            if self.streamlit_error is not None:
                raise RuntimeError(f"Streamlit failed to start:\n{self.streamlit_error}")
            raise RuntimeError(
                "Streamlit did not become ready in time. "
                f"Waited {STREAMLIT_STARTUP_TIMEOUT:.0f}s for http://127.0.0.1:{self.streamlit_port}."
            )

    def _open_dashboard_in_browser(self):
        self._ensure_streamlit_server()
        webbrowser.open(f"http://127.0.0.1:{self.streamlit_port}")

    def open_dashboard(self, widget=None):
        self._start_task(self._open_dashboard_in_browser, "Opening dashboard...")

    def refresh_only(self, widget=None):
        try:
            options = self._collect_workflow_options()
        except ValueError as exc:
            self._show_error("Invalid Input", str(exc))
            return

        def worker():
            perform_beer_fetch_workflow(
                username=options["username"],
                debugger_address=options["debugger_address"],
                output=options["output"],
                backstop_total=options["backstop_total"],
                user_data_dir=options["user_data_dir"],
                open_streamlit_after=False,
            )

        self._start_task(worker, "Refreshing beer data...")

    def refresh_and_open(self, widget=None):
        try:
            options = self._collect_workflow_options()
        except ValueError as exc:
            self._show_error("Invalid Input", str(exc))
            return

        def worker():
            perform_beer_fetch_workflow(
                username=options["username"],
                debugger_address=options["debugger_address"],
                output=options["output"],
                backstop_total=options["backstop_total"],
                user_data_dir=options["user_data_dir"],
                open_streamlit_after=False,
            )
            self._open_dashboard_in_browser()

        self._start_task(worker, "Refreshing beer data and opening dashboard...")

    def open_export_folder(self, widget=None):
        try:
            open_export_folder_path(self.output_input.value or str(DEFAULT_OUTPUT))
        except Exception as exc:
            self._show_error("Open Folder Failed", str(exc))

    def stop_process(self, widget=None):
        if not self.manager.stop():
            self._show_error("Nothing Running", "There is no active task to stop.")


def main():
    return UntappdBeerHistoryApp()
