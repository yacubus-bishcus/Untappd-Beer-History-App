import queue
import subprocess
import sys
import threading
from pathlib import Path

from app_config import get_configured_username, set_configured_username


APP_DIR = Path(__file__).resolve().parent
RUN_SCRIPT = APP_DIR / "run.py"
DEFAULT_OUTPUT = APP_DIR / "my_beers.csv"


class ProcessManager:
    def __init__(self):
        self.process = None
        self.events = queue.Queue()

    def start(self, command, status_text: str):
        if self.process and self.process.poll() is None:
            raise RuntimeError("Wait for the current task to finish or stop it first.")

        self.events.put(("status", status_text))
        self.events.put(("log", f"\n$ {' '.join(command)}\n"))

        def worker():
            try:
                self.process = subprocess.Popen(
                    command,
                    cwd=str(APP_DIR),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                assert self.process.stdout is not None
                for line in self.process.stdout:
                    self.events.put(("log", line))
                return_code = self.process.wait()
                self.events.put(("log", f"\nProcess finished with exit code {return_code}.\n"))
                self.events.put(("status", "Ready"))
            except Exception as exc:
                self.events.put(("log", f"\nLauncher error: {exc}\n"))
                self.events.put(("status", "Ready"))
            finally:
                self.process = None

        threading.Thread(target=worker, daemon=True).start()

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.events.put(("status", "Stopping task..."))
            self.events.put(("log", "\nRequested process stop.\n"))
            return True
        return False


def build_common_args(username: str, output: str, backstop: str):
    args = []
    username = username.strip()
    if not username:
        raise ValueError("Please enter your Untappd username.")
    set_configured_username(username)
    args.extend(["--username", username])

    output = output.strip()
    if output:
        args.extend(["--output", output])

    backstop = backstop.strip()
    if backstop:
        if not backstop.isdigit():
            raise ValueError("Backstop Total must be a whole number.")
        args.extend(["--backstop-total", backstop])
    return args


def maybe_start_initial_sync(start_refresh_and_open, username_getter, output_getter):
    username = username_getter().strip()
    output_path = Path(output_getter().strip() or DEFAULT_OUTPUT)
    if username and not output_path.exists():
        start_refresh_and_open()


def open_export_folder_path(output: str):
    target = Path(output).expanduser().resolve().parent
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(target)])
    elif sys.platform.startswith("win"):
        subprocess.Popen(["explorer", str(target)])
    else:
        subprocess.Popen(["xdg-open", str(target)])


PYOBJC_AVAILABLE = False
if sys.platform == "darwin":
    try:
        import objc  # type: ignore
        from AppKit import (  # type: ignore
            NSApp,
            NSApplication,
            NSApplicationActivateIgnoringOtherApps,
            NSBackingStoreBuffered,
            NSBezelStyleRounded,
            NSButton,
            NSMakeRect,
            NSOpenPanel,
            NSRunningApplication,
            NSSavePanel,
            NSScrollView,
            NSScreen,
            NSTextField,
            NSTextView,
            NSViewWidthSizable,
            NSViewHeightSizable,
            NSWindow,
            NSWindowStyleMaskClosable,
            NSWindowStyleMaskMiniaturizable,
            NSWindowStyleMaskResizable,
            NSWindowStyleMaskTitled,
        )
        from Foundation import NSObject, NSTimer, NSMakeSize  # type: ignore

        PYOBJC_AVAILABLE = True
    except Exception:
        PYOBJC_AVAILABLE = False


if PYOBJC_AVAILABLE:
    class MacDesktopLauncher(NSObject):
        def init(self):
            self = objc.super(MacDesktopLauncher, self).init()
            if self is None:
                return None
            self.manager = ProcessManager()
            self.username = get_configured_username("")
            self.backstop = ""
            self.output = str(DEFAULT_OUTPUT)
            self.status = "Ready"
            self.timer = None
            self.window = None
            return self

        def applicationDidFinishLaunching_(self, notification):
            self.build_window()
            self.start_event_poller()
            self.window.makeKeyAndOrderFront_(None)
            NSRunningApplication.currentApplication().activateWithOptions_(
                NSApplicationActivateIgnoringOtherApps
            )
            self.performSelector_withObject_afterDelay_("finishFirstLaunchSetup:", None, 0.1)

        def applicationShouldTerminateAfterLastWindowClosed_(self, app):
            return True

        def build_window(self):
            rect = NSMakeRect(100.0, 100.0, 760.0, 560.0)
            style = (
                NSWindowStyleMaskTitled
                | NSWindowStyleMaskClosable
                | NSWindowStyleMaskMiniaturizable
                | NSWindowStyleMaskResizable
            )
            self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
                rect, style, NSBackingStoreBuffered, False
            )
            self.window.setTitle_("Untappd Beer History")
            self.window.setMinSize_(NSMakeSize(720.0, 520.0))

            content = self.window.contentView()

            self.title_label = self._make_label(20, 518, 360, 28, "Untappd Beer History", size=22)
            content.addSubview_(self.title_label)

            self.subtitle_label = self._make_label(
                20,
                492,
                680,
                20,
                "Refresh your beer export, then open the Streamlit dashboard from one desktop window.",
                size=12,
            )
            content.addSubview_(self.subtitle_label)

            content.addSubview_(self._make_label(20, 448, 120, 20, "Username"))
            self.username_field = self._make_text_field(150, 444, 540, 26, self.username)
            content.addSubview_(self.username_field)

            content.addSubview_(self._make_label(20, 410, 120, 20, "Backstop Total"))
            self.backstop_field = self._make_text_field(150, 406, 540, 26, self.backstop)
            content.addSubview_(self.backstop_field)

            content.addSubview_(self._make_label(20, 372, 120, 20, "Output CSV"))
            self.output_field = self._make_text_field(150, 368, 450, 26, self.output)
            content.addSubview_(self.output_field)
            content.addSubview_(self._make_button(610, 366, 80, 30, "Browse", "chooseOutput:"))

            content.addSubview_(self._make_button(20, 318, 220, 34, "Open Dashboard", "openDashboard:"))
            content.addSubview_(
                self._make_button(260, 318, 220, 34, "Refresh Data + Dashboard", "refreshAndOpen:")
            )
            content.addSubview_(self._make_button(500, 318, 190, 34, "Refresh Data Only", "refreshOnly:"))

            content.addSubview_(self._make_button(20, 278, 220, 30, "Open Export Folder", "openExportFolder:"))
            content.addSubview_(self._make_button(260, 278, 220, 30, "Stop Running Task", "stopProcess:"))

            self.status_label = self._make_label(20, 246, 680, 20, self.status, size=12)
            content.addSubview_(self.status_label)

            scroll = NSScrollView.alloc().initWithFrame_(NSMakeRect(20, 20, 720, 210))
            scroll.setHasVerticalScroller_(True)
            scroll.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)

            self.log_view = NSTextView.alloc().initWithFrame_(NSMakeRect(0, 0, 720, 210))
            self.log_view.setEditable_(False)
            self.log_view.setString_("Launcher ready.\n")
            scroll.setDocumentView_(self.log_view)
            content.addSubview_(scroll)

        def _make_label(self, x, y, width, height, text, size=13):
            label = NSTextField.alloc().initWithFrame_(NSMakeRect(x, y, width, height))
            label.setBezeled_(False)
            label.setDrawsBackground_(False)
            label.setEditable_(False)
            label.setSelectable_(False)
            label.setStringValue_(text)
            font = label.font().fontWithSize_(size)
            if font is not None:
                label.setFont_(font)
            return label

        def _make_text_field(self, x, y, width, height, value):
            field = NSTextField.alloc().initWithFrame_(NSMakeRect(x, y, width, height))
            field.setStringValue_(value or "")
            return field

        def _make_button(self, x, y, width, height, title, action):
            button = NSButton.alloc().initWithFrame_(NSMakeRect(x, y, width, height))
            button.setTitle_(title)
            button.setTarget_(self)
            button.setAction_(action)
            button.setBezelStyle_(NSBezelStyleRounded)
            return button

        def start_event_poller(self):
            self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                0.15, self, "pollEvents:", None, True
            )

        def pollEvents_(self, timer):
            while True:
                try:
                    event_type, payload = self.manager.events.get_nowait()
                except queue.Empty:
                    break

                if event_type == "log":
                    self.append_log(payload)
                elif event_type == "status":
                    self.status_label.setStringValue_(payload)

        def append_log(self, text):
            current = self.log_view.string() or ""
            self.log_view.setString_(current + text)
            self.log_view.scrollRangeToVisible_((len(self.log_view.string()), 0))

        def collect_common_args(self):
            return build_common_args(
                self.username_field.stringValue(),
                self.output_field.stringValue(),
                self.backstop_field.stringValue(),
            )

        def finishFirstLaunchSetup_(self, sender):
            username = self.username_field.stringValue().strip()
            if not username:
                username = self.prompt_for_username()
                if not username:
                    NSApp.terminate_(None)
                    return
                self.username_field.setStringValue_(username)
                set_configured_username(username)

            maybe_start_initial_sync(
                self._start_initial_refresh,
                lambda: self.username_field.stringValue(),
                lambda: self.output_field.stringValue(),
            )

        def prompt_for_username(self):
            from AppKit import NSAlert  # type: ignore

            alert = NSAlert.alloc().init()
            alert.setMessageText_("Welcome to Untappd Beer History")
            alert.setInformativeText_("Enter your Untappd username to configure the app.")
            alert.addButtonWithTitle_("Continue")
            alert.addButtonWithTitle_("Quit")

            input_field = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 260, 24))
            alert.setAccessoryView_(input_field)

            response = alert.runModal()
            if response != 1000:
                return None
            return input_field.stringValue().strip()

        def _start_initial_refresh(self):
            self.refreshAndOpen_(None)

        def _start_process(self, command, status_text):
            try:
                self.manager.start(command, status_text)
            except RuntimeError as exc:
                self.show_info("Task Already Running", str(exc))

        def show_error(self, title, message):
            from AppKit import NSAlert  # type: ignore

            alert = NSAlert.alloc().init()
            alert.setMessageText_(title)
            alert.setInformativeText_(message)
            alert.runModal()

        def show_info(self, title, message):
            self.show_error(title, message)

        def chooseOutput_(self, sender):
            panel = NSSavePanel.savePanel()
            panel.setCanCreateDirectories_(True)
            panel.setPrompt_("Save CSV")
            panel.setNameFieldStringValue_(Path(self.output_field.stringValue() or DEFAULT_OUTPUT).name)
            if panel.runModal() == 1000:
                self.output_field.setStringValue_(panel.URL().path())

        def openDashboard_(self, sender):
            command = [sys.executable, str(RUN_SCRIPT), "streamlit"]
            self._start_process(command, "Opening dashboard...")

        def refreshOnly_(self, sender):
            try:
                command = [sys.executable, str(RUN_SCRIPT), "selenium-fetch-beers", *self.collect_common_args()]
            except ValueError as exc:
                self.show_error("Invalid Input", str(exc))
                return
            self._start_process(command, "Refreshing beer data...")

        def refreshAndOpen_(self, sender):
            try:
                command = [sys.executable, str(RUN_SCRIPT), "run-default", *self.collect_common_args(), "--update"]
            except ValueError as exc:
                self.show_error("Invalid Input", str(exc))
                return
            self._start_process(command, "Refreshing beer data and opening dashboard...")

        def openExportFolder_(self, sender):
            open_export_folder_path(self.output_field.stringValue())

        def stopProcess_(self, sender):
            if not self.manager.stop():
                self.show_info("Nothing Running", "There is no active task to stop.")


def run_macos_launcher():
    app = NSApplication.sharedApplication()
    delegate = MacDesktopLauncher.alloc().init()
    app.setDelegate_(delegate)
    app.run()


class TkDesktopLauncher:
    def __init__(self):
        import tkinter as tk
        from tkinter import filedialog, messagebox, simpledialog, ttk

        self.tk = tk
        self.filedialog = filedialog
        self.messagebox = messagebox
        self.simpledialog = simpledialog
        self.ttk = ttk
        self.manager = ProcessManager()

        self.root = tk.Tk()
        self.root.title("Untappd Beer History")
        self.root.geometry("760x560")
        self.root.minsize(720, 520)

        self.username_var = tk.StringVar(value=get_configured_username(""))
        self.backstop_var = tk.StringVar()
        self.output_var = tk.StringVar(value=str(DEFAULT_OUTPUT))
        self.status_var = tk.StringVar(value="Ready")

        self._build_ui()
        self.root.after(150, self._drain_events)
        self.root.after(100, self._finish_first_launch_setup)

    def _build_ui(self):
        container = self.ttk.Frame(self.root, padding=16)
        container.pack(fill="both", expand=True)

        title = self.ttk.Label(container, text="Untappd Beer History", font=("Helvetica", 22, "bold"))
        title.pack(anchor="w")

        subtitle = self.ttk.Label(
            container,
            text="Refresh your beer export, then open the Streamlit dashboard from one desktop window.",
        )
        subtitle.pack(anchor="w", pady=(4, 16))

        form = self.ttk.Frame(container)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)

        self.ttk.Label(form, text="Username").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=6)
        self.ttk.Entry(form, textvariable=self.username_var).grid(row=0, column=1, sticky="ew", pady=6)

        self.ttk.Label(form, text="Backstop Total").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=6)
        self.ttk.Entry(form, textvariable=self.backstop_var).grid(row=1, column=1, sticky="ew", pady=6)

        self.ttk.Label(form, text="Output CSV").grid(row=2, column=0, sticky="w", padx=(0, 10), pady=6)
        output_row = self.ttk.Frame(form)
        output_row.grid(row=2, column=1, sticky="ew", pady=6)
        output_row.columnconfigure(0, weight=1)
        self.ttk.Entry(output_row, textvariable=self.output_var).grid(row=0, column=0, sticky="ew")
        self.ttk.Button(output_row, text="Browse", command=self._choose_output).grid(row=0, column=1, padx=(8, 0))

        actions = self.ttk.Frame(container)
        actions.pack(fill="x", pady=(18, 12))
        actions.columnconfigure((0, 1, 2), weight=1)
        self.ttk.Button(actions, text="Open Dashboard", command=self.open_dashboard).grid(
            row=0, column=0, sticky="ew", padx=(0, 8)
        )
        self.ttk.Button(actions, text="Refresh Data + Dashboard", command=self.refresh_and_open).grid(
            row=0, column=1, sticky="ew", padx=8
        )
        self.ttk.Button(actions, text="Refresh Data Only", command=self.refresh_only).grid(
            row=0, column=2, sticky="ew", padx=(8, 0)
        )

        secondary = self.ttk.Frame(container)
        secondary.pack(fill="x", pady=(0, 12))
        secondary.columnconfigure((0, 1), weight=1)
        self.ttk.Button(secondary, text="Open Export Folder", command=self.open_export_folder).grid(
            row=0, column=0, sticky="ew", padx=(0, 8)
        )
        self.ttk.Button(secondary, text="Stop Running Task", command=self.stop_process).grid(
            row=0, column=1, sticky="ew", padx=(8, 0)
        )

        self.ttk.Label(container, textvariable=self.status_var, foreground="#6b7280").pack(anchor="w", pady=(0, 8))

        self.log = self.tk.Text(
            container,
            wrap="word",
            height=18,
            bg="#101418",
            fg="#e5eef5",
            insertbackground="#e5eef5",
        )
        self.log.pack(fill="both", expand=True)
        self.log.insert("end", "Launcher ready.\n")
        self.log.configure(state="disabled")

    def _choose_output(self):
        target = self.filedialog.asksaveasfilename(
            title="Choose output CSV",
            initialdir=str(APP_DIR),
            initialfile=Path(self.output_var.get()).name,
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
        )
        if target:
            self.output_var.set(target)

    def _append_log(self, text: str):
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _drain_events(self):
        while True:
            try:
                event_type, payload = self.manager.events.get_nowait()
            except queue.Empty:
                break
            if event_type == "log":
                self._append_log(payload)
            elif event_type == "status":
                self.status_var.set(payload)
        self.root.after(150, self._drain_events)

    def _collect_common_args(self):
        return build_common_args(
            self.username_var.get(),
            self.output_var.get(),
            self.backstop_var.get(),
        )

    def _finish_first_launch_setup(self):
        username = self.username_var.get().strip()
        if not username:
            username = self.simpledialog.askstring(
                "Untappd Username",
                "Enter your Untappd username:",
                parent=self.root,
            )
            if not username:
                self.root.destroy()
                return
            self.username_var.set(username)
            set_configured_username(username)

        maybe_start_initial_sync(
            self.refresh_and_open,
            lambda: self.username_var.get(),
            lambda: self.output_var.get(),
        )

    def _start_process(self, command, status_text):
        try:
            self.manager.start(command, status_text)
        except RuntimeError as exc:
            self.messagebox.showinfo("Task Already Running", str(exc))

    def open_dashboard(self):
        command = [sys.executable, str(RUN_SCRIPT), "streamlit"]
        self._start_process(command, "Opening dashboard...")

    def refresh_only(self):
        try:
            command = [sys.executable, str(RUN_SCRIPT), "selenium-fetch-beers", *self._collect_common_args()]
        except ValueError as exc:
            self.messagebox.showerror("Invalid Input", str(exc))
            return
        self._start_process(command, "Refreshing beer data...")

    def refresh_and_open(self):
        try:
            command = [sys.executable, str(RUN_SCRIPT), "run-default", *self._collect_common_args(), "--update"]
        except ValueError as exc:
            self.messagebox.showerror("Invalid Input", str(exc))
            return
        self._start_process(command, "Refreshing beer data and opening dashboard...")

    def open_export_folder(self):
        open_export_folder_path(self.output_var.get())

    def stop_process(self):
        if not self.manager.stop():
            self.messagebox.showinfo("Nothing Running", "There is no active task to stop.")

    def run(self):
        self.root.mainloop()


def main():
    if PYOBJC_AVAILABLE and sys.platform == "darwin":
        run_macos_launcher()
        return

    import tkinter.simpledialog  # noqa: F401

    launcher = TkDesktopLauncher()
    launcher.run()


if __name__ == "__main__":
    main()
