import html
import json
import math
import threading
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
from plotly.utils import PlotlyJSONEncoder


PROFILE_SECTION_MARKER = "<h2>Charts</h2>"
CONTRARIAN_THRESHOLD = 0.75
RATING_WINDOWS = [
    ("Last 7 days", "7d"),
    ("Last 30 days", "30d"),
    ("Last 6 months", "6mo"),
    ("Last 365 days", "365d"),
    ("Year to Date", "ytd"),
]


def _format_number(value, digits=2):
    if value is None or pd.isna(value):
        return "—"
    return f"{value:.{digits}f}"


def _metric_card(label: str, value: str) -> str:
    return f"<div class='metric-card'><strong>{html.escape(label)}</strong><div>{html.escape(value)}</div></div>"


def _paragraph(text: str) -> str:
    return f"<p>{html.escape(text)}</p>"


def _empty_chart_message(message: str) -> str:
    return f"<p><em>{html.escape(message)}</em></p>"


def _normalize_date_column(df: pd.DataFrame) -> pd.DataFrame:
    dated = df.copy()
    if "Recent Date" in dated.columns:
        dated["Recent Date"] = pd.to_datetime(dated["Recent Date"], errors="coerce")
    return dated


def _window_frame(df: pd.DataFrame, window_key: str, now: datetime) -> pd.DataFrame:
    if "Recent Date" not in df.columns:
        return df.iloc[0:0].copy()
    dated = df[df["Recent Date"].notna()].copy()
    if window_key == "7d":
        return dated[dated["Recent Date"] >= now - timedelta(days=7)]
    if window_key == "30d":
        return dated[dated["Recent Date"] >= now - timedelta(days=30)]
    if window_key == "6mo":
        return dated[dated["Recent Date"] >= now - timedelta(days=183)]
    if window_key == "365d":
        return dated[dated["Recent Date"] >= now - timedelta(days=365)]
    if window_key == "ytd":
        return dated[dated["Recent Date"] >= pd.Timestamp(datetime(now.year, 1, 1))]
    return dated


def _normalized_style_diversity(style_counts: pd.Series) -> float | None:
    """
    Return normalized Shannon diversity on a 0-100 scale.

    0 means all beers are in one style. 100 means beers are evenly spread across
    the observed styles. This captures both variety and balance.
    """
    style_counts = style_counts.dropna()
    style_counts = style_counts[style_counts > 0]
    style_count = len(style_counts)
    total = style_counts.sum()
    if style_count <= 1 or total <= 0:
        return 0.0 if total > 0 else None

    proportions = style_counts / total
    entropy = -sum(p * math.log(p) for p in proportions if p > 0)
    max_entropy = math.log(style_count)
    if max_entropy <= 0:
        return 0.0
    return (entropy / max_entropy) * 100


def _rating_distribution_data(ratings: pd.DataFrame) -> list[dict]:
    distribution = (
        ratings["My Rating"]
        .dropna()
        .round(2)
        .value_counts()
        .sort_index()
        .rename_axis("My Rating")
        .reset_index(name="Beer Count")
    )
    if distribution.empty:
        return []
    distribution["My Rating"] = distribution["My Rating"].map(lambda value: f"{value:.2f}")
    return distribution.to_dict("records")


def _rating_bias_by_style_data(ratings: pd.DataFrame) -> tuple[list[dict], str]:
    style_ratings = ratings.dropna(subset=["Beer Type", "My Rating", "Global Rating"]).copy()
    if style_ratings.empty:
        return [], "Not enough style and rating data is available for rating bias by style."

    grouped = (
        style_ratings.assign(rating_bias=style_ratings["My Rating"] - style_ratings["Global Rating"])
        .groupby("Beer Type", dropna=True)
        .agg(avg_bias=("rating_bias", "mean"), beer_count=("Beer Name", "size"))
        .reset_index()
    )
    preferred_min_count = 3
    filtered = grouped[grouped["beer_count"] >= preferred_min_count]
    if filtered.empty:
        filtered = grouped
        min_count_note = "Styles with at least one rated beer are shown because no style had three or more rated beers."
    else:
        min_count_note = "Styles with at least three rated beers are shown to reduce one-off noise."

    filtered = filtered.assign(abs_bias=filtered["avg_bias"].abs())
    filtered = filtered.sort_values("abs_bias", ascending=False).head(20).sort_values("avg_bias")
    return filtered.to_dict("records"), min_count_note


def _build_rating_window_payload(ratings: pd.DataFrame) -> dict:
    now = datetime.now()
    dated = _normalize_date_column(ratings)
    payload = {}
    for label, key in RATING_WINDOWS:
        frame = _window_frame(dated, key, now)
        complete = frame.dropna(subset=["My Rating", "Global Rating"]).copy()
        distribution_rows = _rating_distribution_data(complete)
        bias_rows, min_count_note = _rating_bias_by_style_data(complete)
        payload[key] = {
            "label": label,
            "distribution": distribution_rows,
            "bias_by_style": bias_rows,
            "distribution_empty": "No personal ratings are available for this time window.",
            "bias_empty": "Not enough personal/global rating and style data is available for this time window.",
            "bias_note": min_count_note,
            "rated_rows": int(len(complete)),
            "total_rows": int(len(frame)),
        }
    return payload


def _build_drinking_timeline_chart(df: pd.DataFrame) -> str:
    if "Recent Date" not in df.columns:
        return _empty_chart_message("Recent Date is missing, so the drinking activity timeline cannot be built.")

    timeline = _normalize_date_column(df)
    timeline = timeline.dropna(subset=["Recent Date"])
    if timeline.empty:
        return _empty_chart_message("No valid Recent Date values are available for the drinking activity timeline.")

    timeline["Month"] = timeline["Recent Date"].dt.to_period("M").dt.to_timestamp()
    monthly = timeline.groupby("Month").size().reset_index(name="Beer Count")
    fig = px.bar(
        monthly,
        x="Month",
        y="Beer Count",
        title="Timeline of Drinking Activity",
        labels={"Month": "Month", "Beer Count": "Beer Count"},
    )
    return fig.to_html(full_html=False, include_plotlyjs=False)


def _build_style_diversity_chart(df: pd.DataFrame) -> tuple[str, str, str]:
    if "Beer Type" not in df.columns:
        return "—", _empty_chart_message("Beer Type is missing, so style diversity cannot be calculated."), ""

    styles = df["Beer Type"].fillna("").astype(str).str.strip()
    styles = styles[styles.ne("")]
    overall_score = _normalized_style_diversity(styles.value_counts())
    overall_text = _format_number(overall_score, digits=1) if overall_score is not None else "—"

    if "Recent Date" not in df.columns:
        return overall_text, _empty_chart_message("Recent Date is missing, so monthly style diversity cannot be charted."), ""

    dated = _normalize_date_column(df)
    dated["Beer Type"] = dated["Beer Type"].fillna("").astype(str).str.strip()
    dated = dated[dated["Recent Date"].notna() & dated["Beer Type"].ne("")]
    if dated.empty:
        return overall_text, _empty_chart_message("Not enough dated beer-style data is available for monthly style diversity."), ""

    current_year = datetime.now().year
    dated = dated[dated["Recent Date"].dt.year == current_year].copy()
    if dated.empty:
        return overall_text, _empty_chart_message(f"No dated beer-style data is available for {current_year}."), ""

    dated["Month"] = dated["Recent Date"].dt.to_period("M").dt.to_timestamp()
    monthly_rows = []
    for month, month_df in dated.groupby("Month"):
        diversity = _normalized_style_diversity(month_df["Beer Type"].value_counts())
        monthly_rows.append(
            {
                "Month": month,
                "Style Diversity Index": diversity,
                "Beer Count": len(month_df),
                "Unique Styles": month_df["Beer Type"].nunique(),
            }
        )
    monthly = pd.DataFrame(monthly_rows).dropna(subset=["Style Diversity Index"])
    if monthly.empty:
        return overall_text, _empty_chart_message(f"Not enough data is available for monthly style diversity in {current_year}."), ""

    monthly = monthly.sort_values("Month")
    monthly["Month Label"] = monthly["Month"].dt.strftime("%b")

    fig = px.line(
        monthly,
        x="Month Label",
        y="Style Diversity Index",
        markers=True,
        title=f"Style Diversity Index by Month ({current_year})",
        labels={"Month Label": "Month", "Style Diversity Index": "Style Diversity Index (0-100)"},
        hover_data={"Beer Count": True, "Unique Styles": True},
    )
    return overall_text, fig.to_html(full_html=False, include_plotlyjs=False), ""


def _interactive_rating_charts_html(ratings: pd.DataFrame) -> str:
    payload = _build_rating_window_payload(ratings)
    payload_json = json.dumps(payload, cls=PlotlyJSONEncoder)
    options = "".join(
        f"<option value='{key}'>{html.escape(label)}</option>" for label, key in RATING_WINDOWS
    )
    return f"""
<div class='chart-container'><h3>Rating Distribution</h3>
{_paragraph('Rating distribution shows your personal grading curve: how many beers you gave each rating value. Use the menu to evaluate recent periods or year-to-date behavior.')}
<label for='rating-distribution-window'>Evaluation window:</label>
<select id='rating-distribution-window'>{options}</select>
<div id='rating-distribution-chart' style='width:100%; min-height:420px;'></div>
<div id='rating-distribution-note'></div>
</div>
<div class='chart-container'><h3>Rating Bias by Style</h3>
{_paragraph('Rating bias by style shows where your taste differs from the crowd. Positive values mean you rate that style higher than the global average; negative values mean you rate it lower.')}
<label for='rating-bias-window'>Evaluation window:</label>
<select id='rating-bias-window'>{options}</select>
<div id='rating-bias-chart' style='width:100%; min-height:520px;'></div>
<div id='rating-bias-note'></div>
</div>
<script>
const RATING_WINDOW_DATA = {payload_json};
function renderEmptyChart(containerId, message) {{
  const container = document.getElementById(containerId);
  if (!container) return;
  container.innerHTML = `<p><em>${{message}}</em></p>`;
}}
function renderRatingDistribution(windowKey) {{
  const data = RATING_WINDOW_DATA[windowKey];
  const note = document.getElementById('rating-distribution-note');
  if (!data || !data.distribution || data.distribution.length === 0) {{
    renderEmptyChart('rating-distribution-chart', data ? data.distribution_empty : 'No data available.');
    if (note) note.innerHTML = '';
    return;
  }}
  const trace = {{
    type: 'bar',
    x: data.distribution.map(row => row['My Rating']),
    y: data.distribution.map(row => row['Beer Count']),
    hovertemplate: 'Rating %{{x}}<br>Beer Count: %{{y}}<extra></extra>'
  }};
  Plotly.newPlot('rating-distribution-chart', [trace], {{
    title: `Rating Distribution — ${{data.label}}`,
    xaxis: {{title: 'Your Rating'}},
    yaxis: {{title: 'Beer Count'}},
    margin: {{l: 60, r: 30, t: 60, b: 70}}
  }}, {{responsive: true}});
  if (note) note.innerHTML = `<p><strong>Rows used:</strong> ${{data.rated_rows}} rated rows out of ${{data.total_rows}} rows in this window.</p>`;
}}
function renderRatingBias(windowKey) {{
  const data = RATING_WINDOW_DATA[windowKey];
  const note = document.getElementById('rating-bias-note');
  if (!data || !data.bias_by_style || data.bias_by_style.length === 0) {{
    renderEmptyChart('rating-bias-chart', data ? data.bias_empty : 'No data available.');
    if (note) note.innerHTML = '';
    return;
  }}
  const rows = data.bias_by_style;
  const trace = {{
    type: 'bar',
    orientation: 'h',
    x: rows.map(row => row.avg_bias),
    y: rows.map(row => row['Beer Type']),
    customdata: rows.map(row => row.beer_count),
    hovertemplate: 'Style: %{{y}}<br>Avg Bias: %{{x:.2f}}<br>Beer Count: %{{customdata}}<extra></extra>'
  }};
  Plotly.newPlot('rating-bias-chart', [trace], {{
    title: `Rating Bias by Style — ${{data.label}}`,
    xaxis: {{title: 'Avg Bias: My Rating - Global Rating'}},
    yaxis: {{title: 'Beer Style', automargin: true}},
    margin: {{l: 190, r: 30, t: 60, b: 70}}
  }}, {{responsive: true}});
  if (note) note.innerHTML = `<p>${{data.bias_note}} <strong>Rows used:</strong> ${{data.rated_rows}} rated rows out of ${{data.total_rows}} rows in this window.</p>`;
}}
function syncRatingWindows(sourceId, targetId, value) {{
  const target = document.getElementById(targetId);
  if (target && target.value !== value) target.value = value;
}}
const distributionSelect = document.getElementById('rating-distribution-window');
const biasSelect = document.getElementById('rating-bias-window');
if (distributionSelect) {{
  distributionSelect.addEventListener('change', function() {{
    syncRatingWindows('rating-distribution-window', 'rating-bias-window', this.value);
    renderRatingDistribution(this.value);
    renderRatingBias(this.value);
  }});
}}
if (biasSelect) {{
  biasSelect.addEventListener('change', function() {{
    syncRatingWindows('rating-bias-window', 'rating-distribution-window', this.value);
    renderRatingDistribution(this.value);
    renderRatingBias(this.value);
  }});
}}
renderRatingDistribution('7d');
renderRatingBias('7d');
</script>
"""


def build_rating_profile_section(df: pd.DataFrame) -> str:
    """Build the beer-consumer rating profile section for the statistics page."""
    required_columns = ["My Rating", "Global Rating"]
    if any(column not in df.columns for column in required_columns):
        return ""

    ratings = df.copy()
    ratings["My Rating"] = pd.to_numeric(ratings["My Rating"], errors="coerce")
    ratings["Global Rating"] = pd.to_numeric(ratings["Global Rating"], errors="coerce")
    complete = ratings.dropna(subset=["My Rating", "Global Rating"]).copy()

    if complete.empty:
        return """
<h2>Rating Profile</h2>
<div class='metric-grid'>
  <div class='metric-card'><strong>Rating Profile</strong><div>Not enough beers have both personal and global ratings yet.</div></div>
</div>
"""

    complete["rating_gap"] = (complete["My Rating"] - complete["Global Rating"]).abs()
    complete["rating_bias"] = complete["My Rating"] - complete["Global Rating"]

    avg_gap = complete["rating_gap"].mean()
    rating_bias = complete["rating_bias"].mean()
    contrarian_score = (complete["rating_gap"] >= CONTRARIAN_THRESHOLD).mean() * 100
    style_diversity_text, diversity_chart, _ = _build_style_diversity_chart(ratings)

    if rating_bias > 0:
        bias_read = "You are more generous than the Untappd crowd on average."
    elif rating_bias < 0:
        bias_read = "You are tougher than the Untappd crowd on average."
    else:
        bias_read = "Your average rating bias is neutral against the Untappd crowd."

    timeline_chart = _build_drinking_timeline_chart(ratings)
    interactive_rating_charts = _interactive_rating_charts_html(ratings)

    cards = [
        _metric_card("Avg Per-Beer Rating Gap", _format_number(avg_gap)),
        _metric_card("Rating Bias", _format_number(rating_bias)),
        _metric_card("Contrarian Score", f"{_format_number(contrarian_score, digits=1)}%"),
        _metric_card("Style Diversity Index", style_diversity_text),
        _metric_card("Rated Beer Rows", f"{len(complete):,} of {len(df):,}"),
    ]

    section_parts = [
        "<h2>Rating Profile</h2>",
        "<div class='metric-grid'>",
        *cards,
        "</div>",
        _paragraph(
            "Avg Per-Beer Rating Gap is the average absolute difference between your rating and the global rating for the same beer. Lower means your ratings are closer to the crowd beer-by-beer."
        ),
        _paragraph(
            "Rating Bias is the average of My Rating minus Global Rating. Positive means you rate beers higher than the crowd; negative means you rate them lower. "
            + bias_read
        ),
        _paragraph(
            f"Contrarian Score is the percent of rated beers where your rating differs from the global rating by at least {CONTRARIAN_THRESHOLD:.2f} points. Higher means you strongly disagree with the crowd more often."
        ),
        _paragraph(
            "Style Diversity Index uses normalized Shannon diversity on a 0-100 scale. It rises when you drink across more beer styles and when those styles are more evenly represented."
        ),
        "<h2>Charts</h2>",
        interactive_rating_charts,
        "<div class='chart-container'><h3>Timeline of Drinking Activity</h3>",
        _paragraph("The drinking activity timeline counts beers by month using Recent Date, helping reveal high-activity periods, gaps, and seasonal patterns."),
        timeline_chart,
        "</div>",
        "<div class='chart-container'><h3>Style Diversity Index by Month</h3>",
        _paragraph("The monthly style diversity chart shows whether this year's drinking is becoming more style-diverse or more concentrated month by month."),
        diversity_chart,
        "</div>",
    ]
    return "\n".join(section_parts) + "\n"


def inject_rating_profile(html_text: str, df: pd.DataFrame) -> str:
    if "<h2>Rating Profile</h2>" in html_text:
        return html_text
    section = build_rating_profile_section(df)
    if not section:
        return html_text
    if PROFILE_SECTION_MARKER in html_text:
        return html_text.replace(PROFILE_SECTION_MARKER, section, 1)
    return html_text.replace("<h2>Charts</h2>", section + "\n<h2>Charts</h2>", 1)


def open_statistics_report(source) -> Path:
    """
    Build and open the browser statistics report from CLI without launching the full native app.
    """
    source_path = Path(str(source)).expanduser()
    from untappd_beer_history.app import UntappdBeerHistoryApp

    report_builder = UntappdBeerHistoryApp.__new__(UntappdBeerHistoryApp)
    df = report_builder.load_beer_history(source_path)
    report_path, fragment_path, _stop_marker_path = report_builder.build_statistics_report(source_path)

    def build_map_fragment():
        try:
            report_builder.build_map_fragment(df, fragment_path)
        except Exception as exc:
            print(f"Warning: Could not build statistics map fragment: {exc}")

    threading.Thread(target=build_map_fragment, daemon=True).start()
    webbrowser.open(report_path.as_uri())
    print(f"Opened statistics report: {report_path}")
    return report_path
