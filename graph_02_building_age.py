"""
茨城県 不動産価格分析 - グラフ02
築年数別 平均価格・件数（マンション・宅地）タブ切り替え

【実行】
python graph_02_building_age.py
"""

import sqlite3
import pandas as pd
import json
from pathlib import Path

DB_PATH = Path("ibaraki_realestate.db")
OUTPUT  = Path("graph_02_building_age.html")

AGE_ORDER = ["築5年以内","築6〜10年","築11〜20年","築21〜30年","築31〜40年","築41年以上"]

AGE_COLORS = [
    "#1565C0","#1976D2","#1E88E5","#42A5F5","#90CAF9","#BBDEFB"
]


def get_data(conn, trade_type: str) -> pd.DataFrame:
    df = pd.read_sql(f"""
        SELECT
            CASE
                WHEN (2024 - building_year) <= 5  THEN '築5年以内'
                WHEN (2024 - building_year) <= 10 THEN '築6〜10年'
                WHEN (2024 - building_year) <= 20 THEN '築11〜20年'
                WHEN (2024 - building_year) <= 30 THEN '築21〜30年'
                WHEN (2024 - building_year) <= 40 THEN '築31〜40年'
                ELSE '築41年以上'
            END                                     AS 築年数区分,
            COUNT(*)                                AS 件数,
            ROUND(AVG(trade_price) / 10000, 1)      AS 平均価格_万円,
            ROUND(AVG(price_per_sqm))               AS 平均㎡単価_円,
            ROUND(AVG(area), 1)                     AS 平均面積_m2
        FROM csv_transactions
        WHERE trade_type LIKE '%{trade_type}%'
          AND trade_price IS NOT NULL
          AND building_year IS NOT NULL
          AND building_year > 1900
          AND building_year <= 2024
        GROUP BY 築年数区分
    """, conn)
    df["築年数区分"] = pd.Categorical(df["築年数区分"], categories=AGE_ORDER, ordered=True)
    return df.sort_values("築年数区分").reset_index(drop=True)


def df_to_json(df: pd.DataFrame) -> str:
    return json.dumps({
        "labels":    df["築年数区分"].tolist(),
        "price":     df["平均価格_万円"].tolist(),
        "sqm":       df["平均㎡単価_円"].tolist(),
        "count":     df["件数"].tolist(),
        "area":      df["平均面積_m2"].tolist(),
    }, ensure_ascii=False)


def main():
    conn = sqlite3.connect(DB_PATH)
    df_m = get_data(conn, "マンション")
    df_l = get_data(conn, "宅地")
    conn.close()

    data_m_json    = df_to_json(df_m)
    data_l_json    = df_to_json(df_l)
    colors_json    = json.dumps(AGE_COLORS)
    age_order_json = json.dumps(AGE_ORDER, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <title>茨城県 築年数別価格</title>
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

        .toggle-bar {{
            display: flex; align-items: center; gap: 12px;
            background: white; padding: 10px 28px;
            border-bottom: 1px solid #EEE;
            font-size: 13px; color: #555;
        }}
        .toggle-btn {{
            padding: 5px 16px; border: 1px solid #DDD;
            border-radius: 20px; background: white;
            font-size: 12px; cursor: pointer; color: #555;
            transition: all 0.2s;
        }}
        .toggle-btn.active {{
            background: #1565C0; color: white; border-color: #1565C0;
        }}

        .content {{ padding: 20px 28px; }}
        .graph-card {{
            background: white; border-radius: 12px;
            padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        }}
        .footer {{
            text-align: center; padding: 12px;
            font-size: 11px; color: #AAA; border-top: 1px solid #EEE;
            margin-top: 16px;
        }}
    </style>
</head>
<body>

<div class="header">
    <h1>🏗️ 茨城県 築年数別 平均取引価格</h1>
    <p>出典：国土交通省不動産情報ライブラリ</p>
</div>

<div class="tab-bar">
    <button class="tab-btn active" onclick="switchTab('mansion', this)">🏢 中古マンション</button>
    <button class="tab-btn"        onclick="switchTab('land', this)">🏠 宅地（土地と建物）</button>
</div>

<div class="toggle-bar">
    <span>表示切替：</span>
    <button class="toggle-btn active" onclick="switchMetric('price', this)">平均価格（万円）</button>
    <button class="toggle-btn"        onclick="switchMetric('sqm', this)">㎡単価（円）</button>
</div>

<div class="content">
    <div class="graph-card">
        <div id="graph" style="width:100%; height:620px;"></div>
    </div>
</div>

<div class="footer">
    このサービスは、国土交通省不動産情報ライブラリのAPI機能を使用していますが、
    提供情報の最新性・正確性・完全性等が保証されたものではありません。
</div>

<script>
const DATA_M  = {data_m_json};
const DATA_L  = {data_l_json};
const COLORS  = {colors_json};

let currentTab    = 'mansion';
let currentMetric = 'price';

function updateGraph() {{
    const data   = currentTab === 'mansion' ? DATA_M : DATA_L;
    const isPrice = currentMetric === 'price';
    const yValues = isPrice ? data.price : data.sqm;
    const yTitle  = isPrice ? '平均取引価格（万円）' : '平均㎡単価（円）';
    const title   = currentTab === 'mansion'
        ? '茨城県 中古マンション 築年数別 ' + (isPrice ? '平均価格' : '平均㎡単価')
        : '茨城県 宅地（土地と建物） 築年数別 ' + (isPrice ? '平均価格' : '平均㎡単価');

    const traces = [
        {{
            x: data.labels,
            y: yValues,
            type: 'bar',
            marker: {{ color: COLORS }},
            text: yValues.map((v, i) =>
                `${{isPrice ? v + '万円' : v.toLocaleString() + '円'}}<br>(${{data.count[i].toLocaleString()}}件)`
            ),
            textposition: 'outside',
            hovertemplate: data.labels.map((l, i) =>
                `<b>${{l}}</b><br>` +
                (isPrice ? `平均価格: ${{data.price[i]}}万円` : `㎡単価: ${{data.sqm[i].toLocaleString()}}円`) + `<br>` +
                `件数: ${{data.count[i].toLocaleString()}}件<br>` +
                `平均面積: ${{data.area[i]}}㎡<extra></extra>`
            ),
            name: '',
        }},
    ];

    const layout = {{
        title: {{ text: title, font: {{ size: 16 }}, x: 0.5, xanchor: 'center' }},
        xaxis: {{
            title: '築年数',
            categoryorder: 'array',
            categoryarray: data.labels,
            gridcolor: '#EEEEEE',
        }},
        yaxis: {{
            title: yTitle,
            gridcolor: '#EEEEEE',
            zeroline: false,
            range: [0, Math.max(...yValues) * 1.25],
        }},
        plot_bgcolor: 'white',
        paper_bgcolor: 'white',
        showlegend: false,
        margin: {{ l:70, r:30, t:80, b:60 }},
        bargap: 0.3,
    }};

    Plotly.react('graph', traces, layout);
}}

function switchTab(tab, btn) {{
    currentTab = tab;
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    updateGraph();
}}

function switchMetric(metric, btn) {{
    currentMetric = metric;
    document.querySelectorAll('.toggle-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
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
