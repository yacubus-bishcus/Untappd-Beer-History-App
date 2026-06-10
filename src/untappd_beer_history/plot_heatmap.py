import json
from pathlib import Path
from typing import Callable

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio

from app_runtime import TaskCancelled


def build_beer_info_by_location(
    df: pd.DataFrame,
    location_column: str,
) -> dict[str, list[dict[str, str]]]:
    """Build a lookup table of beers grouped by location."""
    columns = [
        'Beer Name',
        'Producer',
        'Consumed Location',
        'Lat',
        'Long',
        'Beer Type',
        'My Rating',
        'Global Rating',
        'Recent Date',
    ]
    beer_info: dict[str, list[dict[str, str]]] = {}

    for location, group in df.groupby(location_column):
        beer_info[location] = [
            {
                col: str(row[col]) if col in row and pd.notna(row[col]) else ''
                for col in columns
            }
            for _, row in group.iterrows()
        ]

    return beer_info


def build_location_heatmap_figure(
    df: pd.DataFrame,
    location_column: str,
    stop_requested: Callable[[], bool] | None = None,
) -> go.Figure:
    """Build a Plotly location heatmap figure from stored venue coordinates."""
    if location_column not in df.columns or 'Beer Name' not in df.columns:
        raise ValueError(f'DataFrame must include {location_column} and Beer Name columns')
    if 'Lat' not in df.columns or 'Long' not in df.columns:
        raise ValueError('DataFrame must include Lat and Long columns')

    df = df.copy()
    df['lat'] = pd.to_numeric(df['Lat'], errors='coerce')
    df['lon'] = pd.to_numeric(df['Long'], errors='coerce')

    for _ in df[location_column].dropna().unique():
        if stop_requested and stop_requested():
            raise TaskCancelled()

    location_counts = (
        df.dropna(subset=['lat', 'lon'])
        .groupby(location_column, as_index=False)
        .agg(count=('Beer Name', 'size'), lat=('lat', 'first'), lon=('lon', 'first'))
        .rename(columns={location_column: 'Location'})
    )

    fig = px.density_map(
        location_counts,
        lat='lat',
        lon='lon',
        z='count',
        radius=25,
        hover_name='Location',
        hover_data={'count': True, 'lat': False, 'lon': False},
        custom_data=['Location'],
        title='Beer Location Heatmap',
    )

    fig.update_traces(
        hovertemplate='<b>%{hovertext}</b><br>count=%{z}<extra></extra>'
    )

    fig.add_trace(
        go.Scattermap(
            lat=location_counts['lat'],
            lon=location_counts['lon'],
            mode='markers',
            marker=dict(size=10, color='rgba(0,0,0,0.4)'),
            customdata=location_counts['Location'],
            hovertemplate='%{customdata}<extra></extra>',
            showlegend=False,
        )
    )

    fig.update_layout(
        map_style='open-street-map',
        map_center={'lat': 39.5, 'lon': -98.35},
        map_zoom=3,
        margin=dict(b=140),
        height=700,
        clickmode='event+select',
    )

    return fig


def build_location_heatmap_html(fig, beer_info: dict) -> str:
    """Return HTML for a plotly map with an interactive beer details table."""
    script = """
    const beerInfo = __BEER_INFO__;

    function renderTable(rows, location) {
        const container = document.getElementById('beer-table');
        if (!container) return;

        let html = '<div style="font-family: Arial, sans-serif; margin: 18px 0;">';
        if (!rows || rows.length === 0) {
            html += '<p><strong>No beers found for ' + location + '</strong></p>';
        } else {
            html += '<h3>Beers for ' + location + '</h3>';
            html += '<table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse; width: 100%; font-size: 13px;">';
            html += '<thead><tr>';
            const cols = ['Beer Name','Producer','Consumed Location','Beer Type','My Rating','Global Rating','Recent Date'];
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
        if (point.hovertext) {
            return point.hovertext;
        }
        if (point.text) {
            return point.text;
        }
        return null;
    }

    function onClick(data) {
        if (!data || !data.points || data.points.length === 0) return;
        const location = getLocationFromPoint(data.points[0]);
        const rows = beerInfo[location] || [];
        renderTable(rows, location);
    }

    const container = document.createElement('div');
    container.id = 'beer-table';
    document.body.appendChild(container);

    const graphDiv = document.querySelector('.plotly-graph-div');
    if (graphDiv) {
        graphDiv.on('plotly_click', onClick);
    }
    """.replace('__BEER_INFO__', json.dumps(beer_info))

    return pio.to_html(
        fig,
        full_html=False,
        include_plotlyjs=False,
        post_script=script,
    )
