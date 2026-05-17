"""
茨城県 不動産価格分析 - グラフ08
公示地点500m以内 年別乖離率推移（折れ線グラフ）タブ切り替え

【実行】
python graph_08_deviation_trend.py
"""

import sqlite3
import pandas as pd
import json
from pathlib import Path

DB_PATH = Path("ibaraki_realestate.db")
OUTPUT  = Path("graph_08_deviation_trend.html")

COLORS = [
    "#E74C3C","#3498DB","#2ECC71","#F39C12","#9B59B6",
    "#1ABC9C","#E67E22","#34495E","#E91E63","#00BCD4",
    "#8BC34A","#FF5722","#607D8B","#795548","#FF9800",
    "#673AB7","#009688","#2196F3","#4CAF50","#FFC107",
    "#9C27B0","#03A9F4","#8D6E63","#546E7A","#CDDC39",
    "#FF4081","#00E5FF","#FF6D00","#304FFE","#00BFA5",
    "#D50000","#0091EA","#00C853","#AA00FF","#C51162",
    "#2962FF","#00B8D4","#64DD17","#FFAB00","#6D4C41",
]


def get_data(conn, trade_type: str) -> pd.DataFrame:
    return pd.read_sql(f"""
        SELECT
            city_name                               AS 市区町村,
            year                                    AS 年,
            COUNT(*)                                AS 件数,
            ROUND(AVG(land_deviation_rate), 1)      AS 平均乖離率_percent,
            ROUND(AVG(land_value) / 10000, 1)       AS 平均土地代_万円,
            ROUND(AVG(nearest_lp_price))            AS 平均公示地価_円m2
        FROM csv_transactions
        WHERE trade_type LIKE '%{trade_type}%'
          AND land_deviation_rate IS NOT NULL
          AND nearest_lp_dist <= 500
          AND year IS NOT NULL
        GROUP BY city_name, year
        HAVING 件数 >= 3
        ORDER BY city_name, year
    """, conn)


def df_to_json(df: pd.DataFrame) -> str:
    cities    = sorted(df["市区町村"].unique().tolist())
    city_data = {}
    for city in cities:
        dc = df[df["市区町村"] == city].sort_values("年")
        city_data[city] = {
            "x":        dc["年"].tolist(),
            "y":        dc["平均乖離率_percent"].tolist(),
            "count":    dc["件数"].tolist(),
            "land":     dc["平均土地代_万円"].tolist(),
            "lp_price": dc["平均公示地価_円m2"].tolist(),
        }
    return json.dumps(city_data, ensure_ascii=False)


def make_checkboxes(cities: list, all_cities: list) -> str:
    html = ""
    for city in cities:
        i     = all_cities.index(city)
        color = COLORS[i % len(COLORS)]
        html += f"""
        <label class="cb-label">
            <input type="checkbox" class="city-cb" value="{city}" checked onchange="updateGraph()">
            <span class="cb-color" style="background:{color}"></span>
            {city}
        </label>"""
    return html


def main():
    conn = sqlite3.connect(DB_PATH)
    df_m = get_data(conn, "マンション")
    df_l = get_data(conn, "宅地")
    conn.close()

    cities_m    = sorted(df_m["市区町村"].unique().tolist())
    cities_l    = sorted(df_l["市区町村"].unique().tolist())
    all_cities  = sorted(set(cities_m + cities_l))

    print(f"マンション: {len(cities_m)}市区町村 / 宅地: {len(cities_l)}市区町村")

    data_m_json     = df_to_json(df_m)
    data_l_json     = df_to_json(df_l)
    colors_json     = json.dumps(COLORS)
    cities_m_json   = json.dumps(cities_m,   ensure_ascii=False)
    cities_l_json   = json.dumps(cities_l,   ensure_ascii=False)
    all_cities_json = json.dumps(all_cities, ensure_ascii=False)

    cb_mansion_html = make_checkboxes(cities_m, all_cities)
    cb_land_html    = make_checkboxes(cities_l, all_cities)

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <title>茨城県 乖離率推移</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: 'Helvetica Neue', Arial, sans-serif; background: #F8F9FA; }}
        .header {{
            background: linear-gradient(135deg, #1a237e, #1565C0);
            color: white; padding: 20px 28px;
        }}
        .header h1 {{ font-size: 20px; font-weight: 600; margin-bottom: 4px; }}
        .header p  {{ font-size: 12px; opacity: 0.75; }}
        .tab-bar {{
            display: flex; background: white;
            border-bottom: 2px solid #E0E0E0; padding: 0 24px;
        }}
        .tab-btn {{
            padding: 12px 24px; border: none; background: transparent;
            font-size: 14px; font-weight: 500; color: #888; cursor: pointer;
            border-bottom: 3px solid transparent; margin-bottom: -2px;
            transition: all 0.2s;
        }}
        .tab-btn:hover  {{ color: #1565C0; }}
        .tab-btn.active {{ color: #1565C0; border-bottom: 3px solid #1565C0; }}
        .main {{
            display: flex; gap: 0; padding: 16px;
            min-height: calc(100vh - 160px);
        }}
        .sidebar {{
            width: 180px; flex-shrink: 0;
            background: white; border-radius: 10px;
            padding: 12px; margin-right: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.06);
            max-height: 680px; overflow-y: auto;
        }}
        .sidebar-title {{
            font-size: 12px; font-weight: 700; color: #555;
            margin-bottom: 8px; padding-bottom: 6px;
            border-bottom: 1px solid #EEE;
        }}
        .note {{
            font-size: 10px; color: #999;
            margin-bottom: 8px; line-height: 1.4;
        }}
        .ctrl-btns {{
            display: flex; gap: 4px; margin-bottom: 10px;
        }}
        .ctrl-btn {{
            flex: 1; padding: 5px 0; border: 1px solid #DDD;
            border-radius: 4px; background: white;
            font-size: 11px; cursor: pointer; color: #555;
            transition: all 0.15s;
        }}
        .ctrl-btn:hover {{ background: #F0F7FF; border-color: #1565C0; color: #1565C0; }}
        .cb-list {{ display: none; }}
        .cb-list.active {{ display: block; }}
        .cb-label {{
            display: flex; align-items: center; gap: 6px;
            padding: 4px 2px; font-size: 12px; cursor: pointer;
            border-radius: 4px; transition: background 0.1s;
        }}
        .cb-label:hover {{ background: #F5F5F5; }}
        .cb-color {{ width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; }}
        .city-cb {{ cursor: pointer; flex-shrink: 0; }}
        .graph-area {{
            flex: 1; background: white; border-radius: 10px;
            padding: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        }}
        .footer {{
            text-align: center; padding: 12px;
            font-size: 11px; color: #AAA;
            border-top: 1px solid #EEE; margin-top: 8px;
        }}
    </style>
</head>
<body>

<div class="header">
    <h1>📊 茨城県 年別 乖離率推移（公示地点500m以内）</h1>
    <p>乖離率 = (土地代㎡単価 - 公示地価㎡単価) / 公示地価㎡単価 × 100　※建物価値は減価償却で算出</p>
</div>

<div class="tab-bar">
    <button class="tab-btn active" onclick="switchTab('mansion', this)">🏢 中古マンション</button>
    <button class="tab-btn"        onclick="switchTab('land', this)">🏠 宅地（土地と建物）</button>
</div>

<div class="main">
    <div class="sidebar">
        <div class="sidebar-title">📍 市区町村を選択</div>
        <div class="note">※公示地点500m以内の<br>データのみ表示</div>
        <div class="ctrl-btns">
            <button class="ctrl-btn" onclick="selectAll(true)">全選択</button>
            <button class="ctrl-btn" onclick="selectAll(false)">全解除</button>
        </div>
        <div id="cb-mansion" class="cb-list active">{cb_mansion_html}</div>
        <div id="cb-land"    class="cb-list">{cb_land_html}</div>
    </div>

    <div class="graph-area">
        <div id="graph" style="width:100%; height:640px;"></div>
    </div>
</div>

<div class="footer">
    このサービスは、国土交通省不動産情報ライブラリのAPI機能を使用していますが、
    提供情報の最新性・正確性・完全性等が保証されたものではありません。
</div>

<script>
const DATA_M     = {data_m_json};
const DATA_L     = {data_l_json};
const COLORS     = {colors_json};
const CITIES_M   = {cities_m_json};
const CITIES_L   = {cities_l_json};
const ALL_CITIES = {all_cities_json};

let currentTab = 'mansion';

function getCheckedCities() {{
    const listId = currentTab === 'mansion' ? 'cb-mansion' : 'cb-land';
    return Array.from(
        document.querySelectorAll(`#${{listId}} .city-cb:checked`)
    ).map(cb => cb.value);
}}

function updateGraph() {{
    const checked = getCheckedCities();
    const data    = currentTab === 'mansion' ? DATA_M : DATA_L;
    const cities  = currentTab === 'mansion' ? CITIES_M : CITIES_L;
    const title   = currentTab === 'mansion'
        ? '茨城県 中古マンション 年別乖離率推移（公示地点500m以内）'
        : '茨城県 宅地（土地と建物） 年別乖離率推移（公示地点500m以内）';

    const traces = [];
    cities.forEach(city => {{
        if (!checked.includes(city) || !data[city]) return;
        const colorIdx = ALL_CITIES.indexOf(city);
        const color    = COLORS[colorIdx % COLORS.length];

        traces.push({{
            x: data[city].x,
            y: data[city].y,
            name: city,
            mode: 'lines+markers',
            line: {{ color: color, width: 2 }},
            marker: {{ size: 7, color: color }},
            hovertemplate: data[city].x.map((yr, i) =>
                `<b>${{city}}</b><br>` +
                `年: ${{yr}}年<br>` +
                `乖離率: ${{data[city].y[i]}}%<br>` +
                `平均土地代: ${{data[city].land[i]}}万円<br>` +
                `公示地価: ${{data[city].lp_price[i] ? data[city].lp_price[i].toLocaleString() : '-'}}円/㎡<br>` +
                `件数: ${{data[city].count[i]}}件<extra></extra>`
            ),
        }});
    }});

    // ゼロライン（基準線）
    const allYears = [2020, 2021, 2022, 2023, 2024, 2025];

    Plotly.react('graph', traces, {{
        title: {{ text: title, font: {{ size: 16 }}, x: 0.5, xanchor: 'center' }},
        xaxis: {{
            title: '年',
            tickmode: 'linear', tick0: 2020, dtick: 1,
            gridcolor: '#EEEEEE',
        }},
        yaxis: {{
            title: '乖離率（%）',
            gridcolor: '#EEEEEE',
            zeroline: true,
            zerolinecolor: '#999',
            zerolinewidth: 2,
        }},
        hovermode: 'x unified',
        showlegend: false,
        plot_bgcolor: 'white',
        paper_bgcolor: 'white',
        margin: {{ l:70, r:20, t:70, b:60 }},
        shapes: [{{
            type: 'line',
            x0: 2019.5, x1: 2025.5,
            y0: 0, y1: 0,
            line: {{ color: '#999', width: 1.5, dash: 'dash' }}
        }}],
        annotations: [{{
            x: 2019.6, y: 0,
            text: '← 割安  割高 →',
            showarrow: false,
            font: {{ size: 10, color: '#999' }},
            xanchor: 'left', yanchor: 'bottom',
        }}],
    }});
}}

function switchTab(tab, btn) {{
    currentTab = tab;
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    document.querySelectorAll('.cb-list').forEach(el => el.classList.remove('active'));
    document.getElementById('cb-' + tab).classList.add('active');
    updateGraph();
}}

function selectAll(checked) {{
    const listId = currentTab === 'mansion' ? 'cb-mansion' : 'cb-land';
    document.querySelectorAll(`#${{listId}} .city-cb`).forEach(cb => cb.checked = checked);
    updateGraph();
}}

updateGraph();
</script>
</body>
</html>"""

    OUTPUT.write_text(html, encoding="utf-8")
    print(f"\n✅ {OUTPUT.resolve()} をブラウザで開いてください！")


if __name__ == "__main__":
    main()
