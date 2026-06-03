import asyncio
import base64
import html
import os
import re
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path

import json
import numpy as np
import pandas as pd
import plotly.express as px
from plotly.utils import PlotlyJSONEncoder
import toga
from app_config import (  # noqa: E402
    get_configured_username,
    set_configured_username,
)
from run import DEFAULT_DEBUGGER_ADDRESS, DEFAULT_USER_DATA_DIR, perform_beer_fetch_workflow  # noqa: E402
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from untappd_beer_history.plot_heatmap import (
    build_beer_info_by_location,
    build_location_heatmap_figure,
)
from untappd_beer_history import __version__


def default_runtime_data_dir() -> Path:
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Untappd Beer History"
    return home / ".local" / "share" / "untappd-beer-history"


os.environ.setdefault("UNTAPPD_DATA_DIR", str(default_runtime_data_dir()))
Path(os.environ["UNTAPPD_DATA_DIR"]).mkdir(parents=True, exist_ok=True)

from app_runtime import (  # noqa: E402
    DEFAULT_OUTPUT,
    ProcessManager,
    TaskCancelled,
    open_export_folder_path,
)
from untapped_selenium import quit_driver  # noqa: E402


def decode_plotly_binary_arrays(value):
    if isinstance(value, dict):
        if set(value) == {"dtype", "bdata"}:
            data = base64.b64decode(value["bdata"])
            return np.frombuffer(data, dtype=np.dtype(value["dtype"])).tolist()
        return {key: decode_plotly_binary_arrays(item) for key, item in value.items()}
    if isinstance(value, list):
        return [decode_plotly_binary_arrays(item) for item in value]
    return value


def close_browser_tabs_for_url(target_url: str) -> tuple[bool, str]:
    """Best-effort close for the report tab opened in the user's browser."""
    if sys.platform != "darwin" or not target_url:
        return False, "Browser tab auto-close is only implemented on macOS."

    target_path = ""
    target_name = ""
    if target_url.startswith("file://"):
        try:
            from urllib.parse import unquote, urlparse

            parsed = urlparse(target_url)
            target_path = unquote(parsed.path)
            target_name = Path(target_path).name
        except Exception:
            target_path = ""
            target_name = ""

    script = """
on run argv
  set targetUrl to item 1 of argv
  set targetPath to item 2 of argv
  set targetName to item 3 of argv
  set didClose to false
  tell application "System Events"
    set runningApps to name of application processes
  end tell

  if runningApps contains "Arc" then
    tell application "Arc"
      repeat with browserWindow in windows
        repeat with browserTab in tabs of browserWindow
          try
            set tabUrl to URL of browserTab
            if my shouldClose(tabUrl, targetUrl, targetPath, targetName) then
              close browserTab
              set didClose to true
            end if
          end try
        end repeat
      end repeat
    end tell
  end if

  if runningApps contains "Brave Browser" then
    tell application "Brave Browser"
      repeat with browserWindow in windows
        repeat with browserTab in tabs of browserWindow
          try
            set tabUrl to URL of browserTab
            if my shouldClose(tabUrl, targetUrl, targetPath, targetName) then
              close browserTab
              set didClose to true
            end if
          end try
        end repeat
      end repeat
    end tell
  end if

  if runningApps contains "Safari" then
    tell application "Safari"
      repeat with browserWindow in windows
        repeat with browserTab in tabs of browserWindow
          try
            set tabUrl to URL of browserTab
            if my shouldClose(tabUrl, targetUrl, targetPath, targetName) then
              close browserTab
              set didClose to true
            end if
          end try
        end repeat
      end repeat
    end tell
  end if

  if runningApps contains "Google Chrome" then
    tell application "Google Chrome"
      repeat with browserWindow in windows
        repeat with browserTab in tabs of browserWindow
          try
            set tabUrl to URL of browserTab
            if my shouldClose(tabUrl, targetUrl, targetPath, targetName) then
              close browserTab
              set didClose to true
            end if
          end try
        end repeat
      end repeat
    end tell
  end if

  if runningApps contains "Microsoft Edge" then
    tell application "Microsoft Edge"
      repeat with browserWindow in windows
        repeat with browserTab in tabs of browserWindow
          try
            set tabUrl to URL of browserTab
            if my shouldClose(tabUrl, targetUrl, targetPath, targetName) then
              close browserTab
              set didClose to true
            end if
          end try
        end repeat
      end repeat
    end tell
  end if

  return didClose
end run

on shouldClose(tabUrl, targetUrl, targetPath, targetName)
  if tabUrl starts with targetUrl then return true
  if targetPath is not "" and tabUrl contains targetPath then return true
  if targetName is not "" and tabUrl contains targetName then return true
  return false
end shouldClose
"""
    try:
        result = subprocess.run(
            ["osascript", "-e", script, target_url, target_path, target_name],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except Exception as exc:
        return False, str(exc)

    did_close = result.stdout.strip().lower() == "true"
    if did_close:
        return True, ""
    reason = (result.stderr or "").strip() or "No matching browser tab found."
    return False, reason


def build_stamp() -> str:
    app_file = Path(__file__).resolve()
    build_time = datetime.fromtimestamp(app_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    mode = "Bundled app" if "/Resources/app/" in str(app_file) else "Source"
    return f"Version {__version__} | {mode} | {build_time}"


class UntappdBeerHistoryApp(toga.App):
    def startup(self):
        self.manager = ProcessManager()
        self.build_stamp_text = build_stamp()
        self.username_input = toga.TextInput(
            value=get_configured_username(""),
            placeholder="Untappd username",
            style=Pack(flex=1),
        )
        self.backstop_input = toga.TextInput(
            placeholder="Optional total",
            style=Pack(width=160),
        )
        self.friend_username_input = toga.TextInput(
            placeholder="Friend username",
            style=Pack(flex=1),
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
                self._row("Friend Username", self.friend_username_input),
                self._row("Backstop Total", self.backstop_input),
                self._row(
                    "Output CSV",
                    self.output_input,
                    toga.Button("Browse", on_press=self.choose_output, style=Pack(width=100)),
                ),
                self.build_label,
                self._button_row(
                    toga.Button("Update Data", on_press=self.refresh_only, style=Pack(flex=1)),
                    toga.Button("Clean Run", on_press=self.clean_run, style=Pack(flex=1)),
                    toga.Button("Statistics", on_press=self.show_statistics, style=Pack(flex=1)),
                ),
                self._button_row(
                    toga.Button("Compare Against Friends", on_press=self.compare_against_friends, style=Pack(flex=1)),
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

        username = self.username_input.value.strip()
        output_path = Path((self.output_input.value or str(DEFAULT_OUTPUT)).strip() or str(DEFAULT_OUTPUT))
        if username and not output_path.exists():
            self.refresh_only()

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
                elif event_type == "info":
                    title, message = payload
                    await self.main_window.dialog(toga.InfoDialog(title, message))
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

    def load_beer_history(self, source):
        source_path = Path(str(source or str(DEFAULT_OUTPUT)).strip()).expanduser()
        if not source_path.exists():
            raise FileNotFoundError(f"Beer history file not found: {source_path}")

        df = pd.read_csv(source_path)
        required_columns = [
            "Beer Name",
            "Producer",
            "Producer Location",
            "Consumed Location",
            "Lat",
            "Long",
            "Beer Type",
            "My Rating",
            "Global Rating",
            "First Date",
            "Recent Date",
        ]
        missing = [column for column in required_columns if column not in df.columns]
        if missing:
            raise ValueError(f"Missing required columns: {', '.join(missing)}")

        df["Map Location"] = df["Consumed Location"]
        df["Lat"] = pd.to_numeric(df["Lat"], errors="coerce")
        df["Long"] = pd.to_numeric(df["Long"], errors="coerce")

        df["My Rating"] = pd.to_numeric(df["My Rating"], errors="coerce")
        df["Global Rating"] = pd.to_numeric(df["Global Rating"], errors="coerce")
        df["First Date"] = pd.to_datetime(df["First Date"], errors="coerce")
        df["Recent Date"] = pd.to_datetime(df["Recent Date"], errors="coerce")

        if "Total Checkins" in df.columns:
            df["Total Checkins"] = pd.to_numeric(df["Total Checkins"], errors="coerce").fillna(0).astype(int)
        elif "total_checkins" in df.columns:
            df["Total Checkins"] = pd.to_numeric(df["total_checkins"], errors="coerce").fillna(0).astype(int)
        else:
            df["Total Checkins"] = pd.NA

        return df

    def render_statistics_html(
        self,
        df,
        map_fragment_name: str,
        estimated_seconds: int,
        stop_marker_name: str,
    ):
        now = datetime.now()

        total_beers = len(df)
        total_producers = df["Producer"].fillna("").replace("", pd.NA).dropna().nunique()
        total_locations = df["Map Location"].fillna("").replace("", pd.NA).dropna().nunique()
        total_checkins = total_beers  # Each beer represents a checkin

        first_date = df["First Date"].min()
        recent_date = df["Recent Date"].max()
        date_range = (
            f"{first_date.date()} → {recent_date.date()}"
            if pd.notna(first_date) and pd.notna(recent_date)
            else "Unknown"
        )

        all_time_days = 1
        if pd.notna(first_date) and pd.notna(recent_date) and recent_date > first_date:
            all_time_days = max(1, (recent_date - first_date).days)

        avg_all_time = total_checkins / all_time_days if all_time_days else None

        year_start = datetime(now.year, 1, 1)
        ytd_mask = df["Recent Date"] >= pd.Timestamp(year_start)
        ytd_checkins = ytd_mask.sum()
        ytd_days = max(1, (now - year_start).days)
        avg_ytd = ytd_checkins / ytd_days if ytd_days else None

        def count_by_period(label, days):
            threshold = now - timedelta(days=days)
            recent = df[df["Recent Date"] >= threshold]
            first_seen = df[df["First Date"] >= threshold]
            return {
                "label": label,
                "recent_beers": len(recent),
                "new_beers": first_seen["Beer Name"].nunique(),
                "new_locations": first_seen["Map Location"].fillna("").replace("", pd.NA).dropna().nunique(),
                "period_days": days,
            }

        periods = [
            count_by_period("Last 7 days", 7),
            count_by_period("Last 30 days", 30),
            count_by_period("Last 365 days", 365),
        ]

        ytd_new = df[df["First Date"] >= pd.Timestamp(year_start)]
        ytd_summary = {
            "label": "Year to Date",
            "recent_beers": len(df[df["Recent Date"] >= pd.Timestamp(year_start)]),
            "new_beers": ytd_new["Beer Name"].nunique(),
            "new_locations": ytd_new["Map Location"].fillna("").replace("", pd.NA).dropna().nunique(),
            "period_days": ytd_days,
        }

        location_summary_text = (
            f"{total_locations:,} unique locations found. "
            "Click a point on the map to show beers checked in around that city."
        )

        map_html_template = """
        <div class='chart-container'>
          <h3>Location Map</h3>
          <div id='location-map-container'>
            <div id='location-map-loading' style='padding: 24px;'>
              <p><strong>Loading location map…</strong></p>
              <p id='location-map-elapsed'>Elapsed: 0 seconds | Progress: 0%</p>
              <div style='height: 10px; overflow: hidden; background: #e5e7eb; border-radius: 999px; margin: 12px 0;'>
                <div id='location-map-progress-fill' style='height: 100%; width: 0%; background: #2563eb; transition: width 0.2s ease;'></div>
              </div>
              <p id='location-map-estimate'>Estimated remaining: approx {ESTIMATED_SECONDS} seconds.</p>
              <p>If the map does not appear, wait a few more seconds.</p>
            </div>
          </div>
        </div>
        <script>
        const MAP_FRAGMENT_URL = '{MAP_FRAGMENT_NAME}';
        const MAP_STOP_URL = '{STOP_MARKER_NAME}';
        const ESTIMATED_MAP_SECONDS = {ESTIMATED_SECONDS};

        let elapsedSeconds = 0;
        function pluralizeSeconds(value) {
          return `${value} second${value === 1 ? '' : 's'}`;
        }
        function updateLoadingProgress(forcePercent) {
          const elapsedEl = document.getElementById('location-map-elapsed');
          const estimateEl = document.getElementById('location-map-estimate');
          const fillEl = document.getElementById('location-map-progress-fill');
          const remainingSeconds = Math.max(0, ESTIMATED_MAP_SECONDS - elapsedSeconds);
          const percent = forcePercent ?? Math.min(99, Math.floor((elapsedSeconds / Math.max(1, ESTIMATED_MAP_SECONDS)) * 100));

          if (elapsedEl) {
            elapsedEl.textContent = `Elapsed: ${pluralizeSeconds(elapsedSeconds)} | Progress: ${percent}%`;
          }
          if (fillEl) {
            fillEl.style.width = `${percent}%`;
          }
          if (estimateEl) {
            if (remainingSeconds > 0) {
              estimateEl.textContent = `Estimated remaining: approx ${pluralizeSeconds(remainingSeconds)}.`;
            } else {
              estimateEl.textContent = 'Still loading the map… this may take a little longer.';
            }
          }
        }
        updateLoadingProgress();
        const progressTimer = setInterval(() => {
          elapsedSeconds += 1;
          updateLoadingProgress();
        }, 1000);

        function showStoppedMessage() {
          clearInterval(progressTimer);
          clearInterval(stopPollTimer);
          const container = document.getElementById('location-map-container');
          if (container) {
            container.innerHTML = '<div style="padding:24px;"><p><strong>Map generation stopped.</strong></p><p>The app requested this statistics tab to close.</p></div>';
          }
          setTimeout(() => window.close(), 250);
        }

        async function checkStopMarker() {
          try {
            const response = await fetch(MAP_STOP_URL, { cache: 'no-store' });
            if (response.ok) {
              showStoppedMessage();
            }
          } catch (err) {
          }
        }
        const stopPollTimer = setInterval(checkStopMarker, 1000);

        function renderTable(rows, location) {
          const container = document.getElementById('beer-table');
          if (!container) return;

          let html = '<div style="font-family: Arial, sans-serif; margin: 18px 0;">';
          if (!rows || rows.length === 0) {
            html += '<p><strong>No beers found for ' + (location || 'this location') + '</strong></p>';
          } else {
            html += '<h3>Beers for ' + location + '</h3>';
            html += '<table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse; width: 100%; font-size: 13px;">';
            html += '<thead><tr>';
            const cols = ['Beer Name','Producer','Producer Location','Consumed Location','Beer Type','My Rating','Global Rating','First Date','Recent Date'];
            cols.forEach(col => html += '<th style="text-align:left; background:#f2f2f2;">' + col + '</th>');
            html += '</tr></thead><tbody>';
            rows.forEach(row => {
              html += '<tr>';
              cols.forEach(col => html += '<td>' + (row[col] || '') + '</td>');
              html += '</tr>';
            });
            html += '</tbody></table>';
          }
          html += '</div>';
          container.innerHTML = html;
        }

        function getLocationFromPoint(point) {
          if (!point) return null;
          if (point.customdata) {
            return Array.isArray(point.customdata) ? point.customdata[0] : point.customdata;
          }
          if (point.hovertext) return point.hovertext;
          if (point.text) return point.text;
          return null;
        }

        function injectMapFragmentScript(onLoad, onError) {
          const previous = document.getElementById('location-map-fragment-script');
          if (previous) {
            previous.remove();
          }
          const script = document.createElement('script');
          script.id = 'location-map-fragment-script';
          script.src = `${MAP_FRAGMENT_URL}?t=${Date.now()}`;
          script.onload = onLoad;
          script.onerror = onError;
          document.body.appendChild(script);
        }

        async function loadMapFragment() {
          const container = document.getElementById('location-map-container');
          if (!container) return;

          injectMapFragmentScript(async function() {
            const fragment = window.__UNTAPPD_BEER_MAP_FRAGMENT__;
            if (!fragment || !fragment.figure) {
              setTimeout(loadMapFragment, 2000);
              return;
            }

            container.innerHTML = '<div id="location-map-plot" style="width:100%;height:700px;"></div><div id="beer-table"></div>';
            const mapDiv = document.getElementById('location-map-plot');
            const figure = fragment.figure;
            await Plotly.newPlot(mapDiv, figure.data, figure.layout, figure.config || {});
            const beerInfo = fragment.beer_info || {};
            mapDiv.on('plotly_click', function(event) {
              if (!event || !event.points || !event.points.length) return;
              const location = getLocationFromPoint(event.points[0]);
              const rows = beerInfo[location] || [];
              renderTable(rows, location);
            });
            renderTable([], '');
            clearInterval(progressTimer);
            clearInterval(stopPollTimer);
            updateLoadingProgress(100);
          }, function() {
            setTimeout(loadMapFragment, 2000);
          });
        }

        loadMapFragment();
        </script>
        """
        map_html = (
            map_html_template
            .replace('{MAP_FRAGMENT_NAME}', map_fragment_name)
            .replace('{STOP_MARKER_NAME}', stop_marker_name)
            .replace('{ESTIMATED_SECONDS}', str(estimated_seconds))
        )

        def top_items(summary_df, group_by, max_items=6):
            key = group_by[0] if isinstance(group_by, (list, tuple)) else group_by
            rating_col = "My Rating" if summary_df["My Rating"].notna().any() else "Global Rating"
            grouped = (
                summary_df.dropna(subset=[rating_col])
                .groupby(group_by)
                .agg(avg_rating=(rating_col, "mean"), count=("Beer Name", "size"))
                .reset_index()
            )
            grouped["avg_rating"] = grouped["avg_rating"].round(2)
            grouped = grouped.sort_values(["avg_rating", "count"], ascending=[False, False]).head(max_items)
            grouped = grouped.rename(columns={key: "item"})
            return grouped[["item", "avg_rating", "count"]].to_dict("records")

        def top_beers(summary_df, max_items=6):
            rating_col = "My Rating" if summary_df["My Rating"].notna().any() else "Global Rating"
            grouped = (
                summary_df.dropna(subset=[rating_col])
                .groupby(["Beer Name"])
                .agg(
                    avg_rating=(rating_col, "mean"),
                    count=("Beer Name", "size"),
                    producer=("Producer", "first"),
                    beer_type=("Beer Type", "first"),
                )
                .reset_index()
            )
            grouped["avg_rating"] = grouped["avg_rating"].round(2)
            grouped = grouped.sort_values(["avg_rating", "count"], ascending=[False, False]).head(max_items)
            grouped = grouped.rename(columns={"Beer Name": "item"})
            return grouped[["item", "producer", "beer_type", "avg_rating", "count"]].to_dict("records")

        def build_period_metrics(label, data_frame):
            return {
                "label": label,
                "top_drinks": top_beers(data_frame),
                "top_producers": top_items(data_frame, ["Producer"]),
                "top_locations": top_items(data_frame, ["Map Location"]),
                "top_beer_types": top_items(data_frame, ["Beer Type"]),
            }

        period_frames = {
            "Last 7 days": df[df["Recent Date"] >= now - timedelta(days=7)],
            "Last 30 days": df[df["Recent Date"] >= now - timedelta(days=30)],
            "Last 365 days": df[df["Recent Date"] >= now - timedelta(days=365)],
            "Year to Date": df[df["Recent Date"] >= pd.Timestamp(year_start)],
        }
        period_metrics = {label: build_period_metrics(label, frame) for label, frame in period_frames.items()}

        period_data = periods + [ytd_summary]
        period_df = pd.DataFrame(period_data)
        
        new_beers_chart = px.bar(
            period_df, 
            x="label", 
            y="new_beers", 
            title="New Beers by Period",
            labels={"label": "Period", "new_beers": "New Beers"}
        ).to_html(full_html=False, include_plotlyjs=False)
        
        new_locations_chart = px.bar(
            period_df, 
            x="label", 
            y="new_locations", 
            title="New Locations by Period",
            labels={"label": "Period", "new_locations": "New Locations"}
        ).to_html(full_html=False, include_plotlyjs=False)

        period_metrics_json = json.dumps(period_metrics)

        html_parts = [
            "<!DOCTYPE html>",
            "<html lang='en'>",
            "<head>",
            "<meta charset='utf-8'>",
            "<meta name='viewport' content='width=device-width, initial-scale=1'>",
            "<title>Untappd Beer Statistics</title>",
            "<style>",
            "body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; padding: 24px; background: #f7f7f7; color: #111; }",
            "h1, h2, h3 { margin-top: 1.2rem; margin-bottom: 0.5rem; }",
            "p { line-height: 1.6; }",
            "table { border-collapse: collapse; width: 100%; margin-bottom: 1.5rem; }",
            "th, td { padding: 10px 12px; border: 1px solid #ddd; text-align: left; }",
            "th { background: #f1f1f1; }",
            ".metric-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin-bottom: 1.5rem; }",
            ".metric-card { background: white; border: 1px solid #ddd; border-radius: 12px; padding: 16px; }",
            ".metric-card strong { display: block; margin-bottom: 0.8rem; font-size: 1rem; color: #333; }",
            ".chart-container { margin-bottom: 1.5rem; background: white; border: 1px solid #ddd; border-radius: 12px; padding: 12px; }",
            "</style>",
            "<script src='https://cdn.plot.ly/plotly-3.5.0.min.js'></script>",
            "</head>",

            "<body>",
            "<h1>Untappd Beer Statistics</h1>",
            f"<p>Source CSV: {len(df):,} beers | {total_producers} producers | {total_locations} locations</p>",
            f"<p><strong>Date range:</strong> {date_range}</p>",
            f"<p><strong>Location summary:</strong> {location_summary_text}</p>",
        ]

        html_parts.append("<div class='metric-grid'>")
        html_parts.append(self._metric_card("Total Beers", f"{total_beers:,}"))
        html_parts.append(self._metric_card("Total Producers", f"{total_producers:,}"))
        html_parts.append(self._metric_card("Total Locations", f"{total_locations:,}"))
        html_parts.append(self._metric_card("Total Checkins", f"{total_checkins:,}"))
        html_parts.append(self._metric_card("Avg Checkins / Day", f"{avg_all_time:.2f}" if avg_all_time else "—"))
        html_parts.append("</div>")

        html_parts.append("<h2>Time Window Summary</h2>")
        html_parts.append("<table>")
        html_parts.append("<thead><tr><th>Window</th><th>Recent Beers</th><th>New Drinks</th><th>New Places</th><th>Days</th></tr></thead>")
        html_parts.append("<tbody>")
        for summary in period_data:
            html_parts.append(
                f"<tr><td>{summary['label']}</td><td>{summary['recent_beers']:,}</td>"
                f"<td>{summary['new_beers']:,}</td><td>{summary['new_locations']:,}</td>"
                f"<td>{summary['period_days']:,}</td></tr>"
            )
        html_parts.append("</tbody></table>")

        if avg_ytd is not None:
            html_parts.append(f"<p><strong>YTD average checkins/day:</strong> {avg_ytd:.2f}</p>")

        html_parts.append("<h2>Charts</h2>")
        html_parts.append("<div class='chart-container'><h3>New Beers by Period</h3>")
        html_parts.append(new_beers_chart)
        html_parts.append("</div>")
        html_parts.append("<div class='chart-container'><h3>New Locations by Period</h3>")
        html_parts.append(new_locations_chart)
        html_parts.append("</div>")

        html_parts.append("<div class='chart-container'><h3>Rating-based Top Items</h3>")
        html_parts.append("<label for='period-select'>Report window:</label> ")
        html_parts.append("<select id='period-select'>")
        html_parts.append("<option value='Last 7 days'>Last 7 days</option>")
        html_parts.append("<option value='Last 30 days'>Last 30 days</option>")
        html_parts.append("<option value='Last 365 days'>Last 365 days</option>")
        html_parts.append("<option value='Year to Date'>Year to Date</option>")
        html_parts.append("</select>")
        html_parts.append("<div id='period-stats'></div>")
        html_parts.append("</div>")

        html_parts.append("<h2>Location Map</h2>")
        html_parts.append("<div class='chart-container'><h3>Map Overview</h3>")
        html_parts.append(map_html)
        html_parts.append("</div>")

        html_parts.append("<script>")
        html_parts.append(f"const PERIOD_METRICS = {period_metrics_json};")
        html_parts.append("const periodSelect = document.getElementById('period-select');")
        html_parts.append("const periodStats = document.getElementById('period-stats');")
        html_parts.append("function renderMetricsTable(items) {")
        html_parts.append("  if (!items || !items.length) return '<p>No data available.</p>'; ")
        html_parts.append("  const rows = items.map(item => { return `<tr><td>${item.item || 'Unknown'}</td><td>${item.avg_rating ?? '—'}</td><td>${item.count ?? '—'}</td></tr>`; });")
        html_parts.append("  return `<table><thead><tr><th>Name</th><th>Avg Rating</th><th>Count</th></tr></thead><tbody>${rows.join('')}</tbody></table>`;")
        html_parts.append("}")
        html_parts.append("function renderPeriodStats(label) {")
        html_parts.append("  const data = PERIOD_METRICS[label];")
        html_parts.append("  if (!data) { periodStats.innerHTML = '<p>Period summary not available.</p>'; return; }")
        html_parts.append("  periodStats.innerHTML = `<div class='metric-grid'><div class='metric-card'><strong>Window</strong><div>${data.label}</div></div><div class='metric-card'><strong>Top Drinks</strong>${renderMetricsTable(data.top_drinks)}</div><div class='metric-card'><strong>Top Producers</strong>${renderMetricsTable(data.top_producers)}</div><div class='metric-card'><strong>Top Locations</strong>${renderMetricsTable(data.top_locations)}</div><div class='metric-card'><strong>Top Beer Types</strong>${renderMetricsTable(data.top_beer_types)}</div></div>`;")
        html_parts.append("}")
        html_parts.append("periodSelect.addEventListener('change', function() { renderPeriodStats(this.value); });")
        html_parts.append("renderPeriodStats(periodSelect.value);")
        html_parts.append("</script>")
        html_parts.append("<footer><p>Generated by Untappd Beer History native app.</p></footer>")
        html_parts.append("</body></html>")
        return "\n".join(html_parts)

    def _map_fragment_filename(self) -> str:
        return "beer_map_fragment.js"

    def _map_stop_marker_filename(self) -> str:
        return "beer_statistics_stop.json"

    def _estimate_map_build_seconds(self, df: pd.DataFrame) -> int:
        map_df = self._map_dataframe(df)
        location_count = (
            map_df["Map Location"].fillna("").replace("", pd.NA).dropna().nunique()
            if "Map Location" in map_df.columns
            else 0
        )
        return max(5, min(120, int(round(4 + location_count * 0.35))))

    def build_map_fragment(self, df: pd.DataFrame, fragment_path: Path, stop_requested=None):
        map_df = self._map_dataframe(df)
        beer_info = build_beer_info_by_location(map_df, location_column="Map Location")
        unique_location_count = (
            map_df["Map Location"].fillna("").replace("", pd.NA).dropna().nunique()
            if "Map Location" in map_df.columns
            else 0
        )
        try:
            fig = build_location_heatmap_figure(
                map_df,
                stop_requested=stop_requested,
                location_column="Map Location",
            )
        except TaskCancelled:
            return

        mapped_location_count = 0
        if fig.data:
            mapped_locations = getattr(fig.data[-1], "customdata", None)
            if mapped_locations is not None:
                mapped_location_count = len(mapped_locations)
        print(
            f"Resolved {mapped_location_count:,} of {unique_location_count:,} locations for the map "
            "using stored venue coordinates."
        )

        fragment = {
            "figure": decode_plotly_binary_arrays(fig.to_plotly_json()),
            "beer_info": beer_info,
        }
        fragment_json = json.dumps(fragment, cls=PlotlyJSONEncoder)
        fragment_path.write_text(
            f"window.__UNTAPPD_BEER_MAP_FRAGMENT__ = {fragment_json};\n",
            encoding="utf-8",
        )

    def _map_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        if "Map Location" not in df.columns:
            return df
        locations = df["Map Location"].fillna("").astype(str).str.strip()
        return df[
            locations.ne("")
            & ~locations.str.casefold().eq("untappd at home")
            & df["Lat"].notna()
            & df["Long"].notna()
        ].copy()

    def build_statistics_report(self, source):
        source_path = Path(str(source or str(DEFAULT_OUTPUT)).strip()).expanduser()
        df = self.load_beer_history(source_path)
        data_dir_value = os.environ.get("UNTAPPD_DATA_DIR", "").strip()
        if data_dir_value:
            data_dir = Path(data_dir_value).expanduser()
        else:
            data_dir = Path(DEFAULT_OUTPUT).expanduser().parent
        data_dir.mkdir(parents=True, exist_ok=True)

        report_path = data_dir / "beer_statistics.html"
        fragment_path = data_dir / self._map_fragment_filename()
        stop_marker_path = data_dir / self._map_stop_marker_filename()
        if fragment_path.exists():
            fragment_path.unlink()
        if stop_marker_path.exists():
            stop_marker_path.unlink()

        html = self.render_statistics_html(
            df,
            self._map_fragment_filename(),
            estimated_seconds=self._estimate_map_build_seconds(df),
            stop_marker_name=self._map_stop_marker_filename(),
        )
        from cli_statistics import inject_rating_profile

        html = inject_rating_profile(html, df)
        report_path.write_text(html, encoding="utf-8")
        return report_path, fragment_path, stop_marker_path

    def _metric_card(self, label, value):
        return f"<div class='metric-card'><strong>{label}</strong><div>{value}</div></div>"

    def _friend_output_path(self, base_output: str, friend_username: str) -> Path:
        base_path = Path(str(base_output or str(DEFAULT_OUTPUT)).strip()).expanduser()
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", friend_username.strip()).strip("_")
        safe_name = safe_name or "friend"
        return base_path.parent / f"{safe_name}_beers.csv"

    def _monthly_checkin_rows(self, df: pd.DataFrame, label: str, year: int) -> pd.DataFrame:
        dated = df.copy()
        dated = dated[dated["Recent Date"].notna()].copy()
        dated = dated[dated["Recent Date"].dt.year == year]
        month_index = pd.date_range(f"{year}-01-01", f"{year}-12-01", freq="MS")
        if dated.empty:
            counts = pd.Series(0, index=month_index)
        else:
            counts = dated.groupby(dated["Recent Date"].dt.to_period("M").dt.to_timestamp()).size()
            counts = counts.reindex(month_index, fill_value=0)
        return pd.DataFrame(
            {
                "Month": month_index,
                "Month Label": [month.strftime("%b") for month in month_index],
                "Recorded Check-ins": counts.astype(int).values,
                "User": label,
            }
        )

    def _rating_profile_summary(self, df: pd.DataFrame, label: str) -> dict:
        from cli_statistics import CONTRARIAN_THRESHOLD, _normalized_style_diversity

        ratings = df.copy()
        ratings["My Rating"] = pd.to_numeric(ratings["My Rating"], errors="coerce")
        ratings["Global Rating"] = pd.to_numeric(ratings["Global Rating"], errors="coerce")
        complete = ratings.dropna(subset=["My Rating", "Global Rating"]).copy()
        if complete.empty:
            return {
                "User": label,
                "Avg Per-Beer Rating Gap": None,
                "Rating Bias": None,
                "Contrarian Score": None,
                "Style Diversity Index": None,
                "Rated Rows": 0,
                "Total Rows": len(df),
            }

        rating_gap = (complete["My Rating"] - complete["Global Rating"]).abs()
        rating_bias = complete["My Rating"] - complete["Global Rating"]
        styles = ratings["Beer Type"].fillna("").astype(str).str.strip()
        styles = styles[styles.ne("")]
        diversity = _normalized_style_diversity(styles.value_counts())

        return {
            "User": label,
            "Avg Per-Beer Rating Gap": rating_gap.mean(),
            "Rating Bias": rating_bias.mean(),
            "Contrarian Score": (rating_gap >= CONTRARIAN_THRESHOLD).mean() * 100,
            "Style Diversity Index": diversity,
            "Rated Rows": len(complete),
            "Total Rows": len(df),
        }

    def _rating_distribution_rows(self, df: pd.DataFrame, label: str) -> pd.DataFrame:
        rating_bins = [step / 4 for step in range(0, 21)]
        ratings = pd.to_numeric(df["My Rating"], errors="coerce").dropna()
        ratings = (ratings * 4).round() / 4
        ratings = ratings[(ratings >= 0) & (ratings <= 5)]
        counts = ratings.value_counts().reindex(rating_bins, fill_value=0).sort_index()
        distribution = counts.rename_axis("My Rating").reset_index(name="Beer Count")
        distribution["User"] = label
        return distribution

    def build_friend_comparison_report(
        self,
        username: str,
        user_df: pd.DataFrame,
        friend_username: str,
        friend_df: pd.DataFrame,
    ) -> Path:
        data_dir_value = os.environ.get("UNTAPPD_DATA_DIR", "").strip()
        data_dir = Path(data_dir_value).expanduser() if data_dir_value else Path(DEFAULT_OUTPUT).expanduser().parent
        data_dir.mkdir(parents=True, exist_ok=True)
        report_path = data_dir / "beer_friend_comparison.html"
        year = datetime.now().year

        labels = [username, friend_username]
        total_df = pd.DataFrame(
            {
                "User": labels,
                "Recorded Check-ins": [len(user_df), len(friend_df)],
            }
        )
        monthly = pd.concat(
            [
                self._monthly_checkin_rows(user_df, username, year),
                self._monthly_checkin_rows(friend_df, friend_username, year),
            ],
            ignore_index=True,
        )
        rating_profile = pd.DataFrame(
            [
                self._rating_profile_summary(user_df, username),
                self._rating_profile_summary(friend_df, friend_username),
            ]
        )
        rating_distribution = pd.concat(
            [
                self._rating_distribution_rows(user_df, username),
                self._rating_distribution_rows(friend_df, friend_username),
            ],
            ignore_index=True,
        )

        total_chart = px.bar(
            total_df,
            x="User",
            y="Recorded Check-ins",
            title="Total Recorded Check-ins",
            text="Recorded Check-ins",
        ).to_html(full_html=False, include_plotlyjs=False)
        monthly_chart = px.line(
            monthly,
            x="Month Label",
            y="Recorded Check-ins",
            color="User",
            markers=True,
            title=f"Monthly Recorded Check-ins ({year})",
            labels={"Month Label": "Month"},
        ).to_html(full_html=False, include_plotlyjs=False)
        rating_profile_ratings_chart = px.bar(
            rating_profile,
            x="User",
            y=["Avg Per-Beer Rating Gap", "Rating Bias"],
            barmode="group",
            title="Rating Profile Comparison: Rating Scale",
            labels={"value": "Metric Value", "variable": "Metric"},
        ).to_html(full_html=False, include_plotlyjs=False)
        rating_profile_index_chart = px.bar(
            rating_profile,
            x="User",
            y=["Style Diversity Index", "Contrarian Score"],
            barmode="group",
            title="Rating Profile Comparison: Index and Percent",
            labels={"value": "Metric Value", "variable": "Metric"},
        ).to_html(full_html=False, include_plotlyjs=False)
        if rating_distribution.empty:
            rating_distribution_chart = "<p><em>No personal ratings are available for either user.</em></p>"
        else:
            rating_distribution_fig = px.line(
                rating_distribution,
                x="My Rating",
                y="Beer Count",
                color="User",
                markers=True,
                title="Rating Distribution Overlay",
                labels={"My Rating": "Personal Rating"},
            )
            rating_distribution_fig.update_xaxes(
                tickmode="array",
                tickvals=[step / 4 for step in range(0, 21)],
                tickformat=".2f",
                range=[-0.05, 5.05],
            )
            rating_distribution_chart = rating_distribution_fig.to_html(full_html=False, include_plotlyjs=False)

        def profile_cards(summary_df: pd.DataFrame) -> str:
            cards = []
            for _, row in summary_df.iterrows():
                user = html.escape(str(row["User"]))
                rated_rows = f"{int(row['Rated Rows']):,} of {int(row['Total Rows']):,}"
                cards.append(
                    self._metric_card(
                        f"{user} Avg Gap",
                        "—" if pd.isna(row["Avg Per-Beer Rating Gap"]) else f"{row['Avg Per-Beer Rating Gap']:.2f}",
                    )
                )
                cards.append(
                    self._metric_card(
                        f"{user} Rating Bias",
                        "—" if pd.isna(row["Rating Bias"]) else f"{row['Rating Bias']:.2f}",
                    )
                )
                cards.append(
                    self._metric_card(
                        f"{user} Contrarian Score",
                        "—" if pd.isna(row["Contrarian Score"]) else f"{row['Contrarian Score']:.1f}%",
                    )
                )
                cards.append(
                    self._metric_card(
                        f"{user} Style Diversity",
                        "—" if pd.isna(row["Style Diversity Index"]) else f"{row['Style Diversity Index']:.1f}",
                    )
                )
                cards.append(self._metric_card(f"{user} Rated Rows", rated_rows))
            return "\n".join(cards)

        html_text = "\n".join(
            [
                "<!DOCTYPE html>",
                "<html lang='en'>",
                "<head>",
                "<meta charset='utf-8'>",
                "<meta name='viewport' content='width=device-width, initial-scale=1'>",
                "<title>Untappd Friend Comparison</title>",
                "<style>",
                "body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; padding: 24px; background: #f7f7f7; color: #111; }",
                "h1, h2, h3 { margin-top: 1.2rem; margin-bottom: 0.5rem; }",
                "p { line-height: 1.6; }",
                ".metric-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin-bottom: 1.5rem; }",
                ".metric-card { background: white; border: 1px solid #ddd; border-radius: 12px; padding: 16px; }",
                ".metric-card strong { display: block; margin-bottom: 0.8rem; font-size: 1rem; color: #333; }",
                ".chart-container { margin-bottom: 1.5rem; background: white; border: 1px solid #ddd; border-radius: 12px; padding: 12px; }",
                "</style>",
                "<script src='https://cdn.plot.ly/plotly-3.5.0.min.js'></script>",
                "</head>",
                "<body>",
                "<h1>Untappd Friend Comparison</h1>",
                f"<p>Comparing {html.escape(username)} against {html.escape(friend_username)}.</p>",
                "<div class='metric-grid'>",
                self._metric_card(f"{html.escape(username)} Total", f"{len(user_df):,}"),
                self._metric_card(f"{html.escape(friend_username)} Total", f"{len(friend_df):,}"),
                "</div>",
                "<h2>Rating Profile</h2>",
                "<div class='metric-grid'>",
                profile_cards(rating_profile),
                "</div>",
                "<h2>Charts</h2>",
                "<div class='chart-container'><h3>Total Check-ins</h3>",
                total_chart,
                "</div>",
                "<div class='chart-container'><h3>Check-ins by Month</h3>",
                monthly_chart,
                "</div>",
                "<div class='chart-container'><h3>Rating Profile Comparison: Rating Scale</h3>",
                rating_profile_ratings_chart,
                "</div>",
                "<div class='chart-container'><h3>Rating Profile Comparison: Index and Percent</h3>",
                rating_profile_index_chart,
                "</div>",
                "<div class='chart-container'><h3>Rating Distribution Overlay</h3>",
                rating_distribution_chart,
                "</div>",
                "<footer><p>Generated by Untappd Beer History native app.</p></footer>",
                "</body></html>",
            ]
        )
        report_path.write_text(html_text, encoding="utf-8")
        return report_path

    def show_statistics(self, widget=None):
        try:
            options = self._collect_workflow_options()
        except Exception as exc:
            self._show_error("Statistics Failed", str(exc))
            return

        source_path = Path(str(options["output"] or str(DEFAULT_OUTPUT)).strip()).expanduser()
        df = self.load_beer_history(source_path)
        report_path, fragment_path, stop_marker_path = self.build_statistics_report(options["output"])
        report_url = report_path.as_uri()

        stop_event = threading.Event()

        def worker():
            try:
                self.build_map_fragment(df, fragment_path, stop_requested=stop_event.is_set)
            except Exception:
                pass

        def stop_fn():
            stop_event.set()
            try:
                stop_marker_path.write_text(
                    json.dumps({"stopped": True, "stopped_at": datetime.now().isoformat()}),
                    encoding="utf-8",
                )
            except Exception:
                pass
            did_close, close_reason = close_browser_tabs_for_url(report_url)
            if did_close:
                self.manager.events.put(("log", "Closed statistics tab.\n"))
            else:
                self.manager.events.put(("log", f"Could not auto-close statistics tab: {close_reason}\n"))

        webbrowser.open(report_url)
        self.manager.events.put(("log", "\nGenerating statistics report...\n"))
        try:
            self.manager.start_callable(worker, "Generating statistics...", stop_fn=stop_fn)
        except RuntimeError as exc:
            self._show_error("Task Already Running", str(exc))

    def compare_against_friends(self, widget=None):
        try:
            options = self._collect_workflow_options()
        except Exception as exc:
            self._show_error("Compare Failed", str(exc))
            return

        friend_username = (self.friend_username_input.value or "").strip()
        if not friend_username:
            self._show_error("Compare Failed", "Please enter a friend username.")
            return
        if friend_username.casefold() == options["username"].casefold():
            self._show_error("Compare Failed", "Friend username must be different from your username.")
            return

        source_path = Path(str(options["output"] or str(DEFAULT_OUTPUT)).strip()).expanduser()
        if not source_path.exists():
            self._show_error("Compare Failed", f"Your beer history file does not exist yet: {source_path}")
            return

        friend_output = self._friend_output_path(options["output"], friend_username)
        stop_event = threading.Event()
        active_driver = {"driver": None}

        def stop_fn():
            stop_event.set()
            driver = active_driver.get("driver")
            if driver is not None:
                try:
                    quit_driver(driver)
                except Exception:
                    pass

        def worker():
            self.manager.events.put(("log", f"\nFetching comparison data for {friend_username}...\n"))
            perform_beer_fetch_workflow(
                username=friend_username,
                debugger_address=options["debugger_address"],
                output=str(friend_output),
                backstop_total=options["backstop_total"],
                user_data_dir=options["user_data_dir"],
                clean_run=True,
                stop_requested=stop_event.is_set,
                on_driver_ready=lambda driver: active_driver.__setitem__("driver", driver),
            )
            user_df = self.load_beer_history(source_path)
            friend_df = self.load_beer_history(friend_output)
            report_path = self.build_friend_comparison_report(
                options["username"],
                user_df,
                friend_username,
                friend_df,
            )
            webbrowser.open(report_path.as_uri())
            self.manager.events.put(("log", f"Opened friend comparison report: {report_path}\n"))

        try:
            self.manager.start_callable(worker, f"Comparing against {friend_username}...", stop_fn=stop_fn)
        except RuntimeError as exc:
            self._show_error("Task Already Running", str(exc))

    def _start_refresh(self, clean_run: bool = False):
        try:
            options = self._collect_workflow_options()
        except ValueError as exc:
            self._show_error("Invalid Input", str(exc))
            return

        stop_event = threading.Event()
        active_driver = {"driver": None}

        def stop_fn():
            stop_event.set()
            driver = active_driver.get("driver")
            if driver is not None:
                try:
                    quit_driver(driver)
                except Exception:
                    pass

        def worker():
            perform_beer_fetch_workflow(
                username=options["username"],
                debugger_address=options["debugger_address"],
                output=options["output"],
                backstop_total=options["backstop_total"],
                user_data_dir=options["user_data_dir"],
                clean_run=clean_run,
                stop_requested=stop_event.is_set,
                on_driver_ready=lambda driver: active_driver.__setitem__("driver", driver),
            )

        status_text = "Clean run: fetching all beer data..." if clean_run else "Refreshing beer data..."
        try:
            self.manager.start_callable(worker, status_text, stop_fn=stop_fn)
        except RuntimeError as exc:
            self._show_error("Task Already Running", str(exc))

    def refresh_only(self, widget=None):
        self._start_refresh(clean_run=False)

    def clean_run(self, widget=None):
        self._start_refresh(clean_run=True)

    def open_export_folder(self, widget=None):
        try:
            open_export_folder_path(self.output_input.value or str(DEFAULT_OUTPUT))
        except Exception as exc:
            self._show_error("Open Folder Failed", str(exc))

    def stop_process(self, widget=None):
        if self.manager.stop():
            return
        self._show_error("Nothing Running", "There is no active task to stop.")


def main():
    return UntappdBeerHistoryApp(
        formal_name="Untappd Beer History",
        app_id="com.yacubusbishcus.untappdbeerhistory",
    )
