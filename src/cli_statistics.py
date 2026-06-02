import html
import threading
import webbrowser
from pathlib import Path

import pandas as pd


RATE_SECTION_MARKER = "<div class='metric-grid'>"


def _format_number(value, digits=2):
    if value is None or pd.isna(value):
        return "—"
    return f"{value:.{digits}f}"


def _metric_card(label: str, value: str) -> str:
    return f"<div class='metric-card'><strong>{html.escape(label)}</strong><div>{html.escape(value)}</div></div>"


def build_rating_comparison_section(df: pd.DataFrame) -> str:
    """
    Build a small HTML section comparing the user's ratings to Untappd global ratings.

    The requested comparison score is:
        abs(global average rating - my average rating) / my total beers

    A second metric, average per-beer absolute gap, is included because it is usually
    easier to interpret than dividing the difference between two averages by total beers.
    """
    total_beers = len(df)
    rating_columns = ["My Rating", "Global Rating"]
    missing_columns = [column for column in rating_columns if column not in df.columns]
    if missing_columns:
        return ""

    ratings = df[rating_columns].apply(pd.to_numeric, errors="coerce").dropna()
    if ratings.empty or total_beers <= 0:
        return """
<h2>Rating Comparison</h2>
<div class='metric-grid'>
  <div class='metric-card'><strong>Rating Comparison</strong><div>Not enough rated beers with global ratings yet.</div></div>
</div>
"""

    my_average = ratings["My Rating"].mean()
    global_average = ratings["Global Rating"].mean()
    average_gap = abs(global_average - my_average)
    requested_score = average_gap / total_beers
    per_beer_abs_gap = (ratings["Global Rating"] - ratings["My Rating"]).abs().mean()

    if my_average > global_average:
        direction = "You rate higher than the global average."
    elif my_average < global_average:
        direction = "You rate lower than the global average."
    else:
        direction = "Your average matches the global average."

    cards = [
        _metric_card("My Avg Rating", _format_number(my_average)),
        _metric_card("Global Avg Rating", _format_number(global_average)),
        _metric_card("Absolute Avg Gap", _format_number(average_gap)),
        _metric_card("Rating Comparison Score", _format_number(requested_score, digits=5)),
        _metric_card("Avg Per-Beer Abs Gap", _format_number(per_beer_abs_gap)),
        _metric_card("Rated Beer Rows", f"{len(ratings):,} of {total_beers:,}"),
    ]

    formula = "abs(global average rating - my average rating) / my total beers"
    return (
        "<h2>Rating Comparison</h2>\n"
        "<div class='metric-grid'>\n"
        + "\n".join(cards)
        + "\n</div>\n"
        f"<p><strong>Formula:</strong> {html.escape(formula)}. "
        f"<strong>Read:</strong> {html.escape(direction)} Lower score means your overall average is closer to the global average.</p>\n"
    )


def inject_rating_comparison(html_text: str, df: pd.DataFrame) -> str:
    section = build_rating_comparison_section(df)
    if not section or section in html_text:
        return html_text
    if RATE_SECTION_MARKER in html_text:
        return html_text.replace(RATE_SECTION_MARKER, section + "\n" + RATE_SECTION_MARKER, 1)
    return html_text.replace("<h2>Time Window Summary</h2>", section + "\n<h2>Time Window Summary</h2>", 1)


def open_statistics_report(source) -> Path:
    """
    Build and open the browser statistics report from CLI without launching the full native app.
    """
    source_path = Path(str(source)).expanduser()
    from untappd_beer_history.app import UntappdBeerHistoryApp

    report_builder = UntappdBeerHistoryApp.__new__(UntappdBeerHistoryApp)
    df = report_builder.load_beer_history(source_path)
    report_path, fragment_path, _stop_marker_path = report_builder.build_statistics_report(source_path)

    html_text = report_path.read_text(encoding="utf-8")
    report_path.write_text(inject_rating_comparison(html_text, df), encoding="utf-8")

    def build_map_fragment():
        try:
            report_builder.build_map_fragment(df, fragment_path)
        except Exception as exc:
            print(f"Warning: Could not build statistics map fragment: {exc}")

    threading.Thread(target=build_map_fragment, daemon=True).start()
    webbrowser.open(report_path.as_uri())
    print(f"Opened statistics report: {report_path}")
    return report_path
