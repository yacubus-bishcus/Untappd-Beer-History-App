import html
import math
import threading
import webbrowser
from pathlib import Path

import pandas as pd
import plotly.express as px


PROFILE_SECTION_MARKER = "<h2>Time Window Summary</h2>"
CONTRARIAN_THRESHOLD = 0.75


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


def _build_rating_distribution_chart(ratings: pd.DataFrame) -> str:
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
        return _empty_chart_message("No personal rating values are available for the distribution chart.")

    distribution["My Rating"] = distribution["My Rating"].map(lambda value: f"{value:.2f}")
    fig = px.bar(
        distribution,
        x="My Rating",
        y="Beer Count",
        title="Rating Distribution",
        labels={"My Rating": "Your Rating", "Beer Count": "Beer Count"},
    )
    return fig.to_html(full_html=False, include_plotlyjs=False)


def _build_rating_bias_by_style_chart(ratings: pd.DataFrame) -> tuple[str, str]:
    style_ratings = ratings.dropna(subset=["Beer Type", "My Rating", "Global Rating"]).copy()
    if style_ratings.empty:
        return (
            _empty_chart_message("Not enough style and rating data is available for rating bias by style."),
            "Rating bias by style groups beers by Beer Type and averages My Rating minus Global Rating.",
        )

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
    fig = px.bar(
        filtered,
        x="avg_bias",
        y="Beer Type",
        orientation="h",
        title="Rating Bias by Style",
        labels={"avg_bias": "Avg Bias: My Rating - Global Rating", "Beer Type": "Beer Style"},
        hover_data={"beer_count": True, "abs_bias": False},
    )
    explanation = (
        "Rating bias by style shows where your taste differs from the crowd. "
        "Positive values mean you rate that style higher than the global average; negative values mean you rate it lower. "
        + min_count_note
    )
    return fig.to_html(full_html=False, include_plotlyjs=False), explanation


def _build_drinking_timeline_chart(df: pd.DataFrame) -> str:
    if "Recent Date" not in df.columns:
        return _empty_chart_message("Recent Date is missing, so the drinking activity timeline cannot be built.")

    timeline = df.copy()
    timeline["Recent Date"] = pd.to_datetime(timeline["Recent Date"], errors="coerce")
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
        return overall_text, _empty_chart_message("Recent Date is missing, so year-by-year style diversity cannot be charted."), ""

    dated = df.copy()
    dated["Recent Date"] = pd.to_datetime(dated["Recent Date"], errors="coerce")
    dated["Beer Type"] = dated["Beer Type"].fillna("").astype(str).str.strip()
    dated = dated[dated["Recent Date"].notna() & dated["Beer Type"].ne("")]
    if dated.empty:
        return overall_text, _empty_chart_message("Not enough dated beer-style data is available for style diversity by year."), ""

    dated["Year"] = dated["Recent Date"].dt.year
    yearly_rows = []
    for year, year_df in dated.groupby("Year"):
        diversity = _normalized_style_diversity(year_df["Beer Type"].value_counts())
        yearly_rows.append(
            {
                "Year": int(year),
                "Style Diversity Index": diversity,
                "Beer Count": len(year_df),
                "Unique Styles": year_df["Beer Type"].nunique(),
            }
        )
    yearly = pd.DataFrame(yearly_rows).dropna(subset=["Style Diversity Index"])
    if yearly.empty:
        return overall_text, _empty_chart_message("Not enough data is available for style diversity by year."), ""

    fig = px.line(
        yearly,
        x="Year",
        y="Style Diversity Index",
        markers=True,
        title="Style Diversity Index by Year",
        labels={"Style Diversity Index": "Style Diversity Index (0-100)"},
        hover_data={"Beer Count": True, "Unique Styles": True},
    )
    return overall_text, fig.to_html(full_html=False, include_plotlyjs=False), ""


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

    bias_chart, bias_explanation = _build_rating_bias_by_style_chart(complete)
    distribution_chart = _build_rating_distribution_chart(complete)
    timeline_chart = _build_drinking_timeline_chart(ratings)

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
        "<div class='chart-container'><h3>Rating Bias by Style</h3>",
        _paragraph(bias_explanation),
        bias_chart,
        "</div>",
        "<div class='chart-container'><h3>Rating Distribution</h3>",
        _paragraph("Rating distribution shows your personal grading curve: how many beers you gave each rating value."),
        distribution_chart,
        "</div>",
        "<div class='chart-container'><h3>Timeline of Drinking Activity</h3>",
        _paragraph("The drinking activity timeline counts beers by month using Recent Date, helping reveal high-activity periods, gaps, and seasonal patterns."),
        timeline_chart,
        "</div>",
        "<div class='chart-container'><h3>Style Diversity Index</h3>",
        _paragraph("The yearly style diversity chart shows whether your drinking became more style-diverse or more concentrated over time."),
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
        return html_text.replace(PROFILE_SECTION_MARKER, section + "\n" + PROFILE_SECTION_MARKER, 1)
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

    html_text = report_path.read_text(encoding="utf-8")
    report_path.write_text(inject_rating_profile(html_text, df), encoding="utf-8")

    def build_map_fragment():
        try:
            report_builder.build_map_fragment(df, fragment_path)
        except Exception as exc:
            print(f"Warning: Could not build statistics map fragment: {exc}")

    threading.Thread(target=build_map_fragment, daemon=True).start()
    webbrowser.open(report_path.as_uri())
    print(f"Opened statistics report: {report_path}")
    return report_path
