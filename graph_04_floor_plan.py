"""
茨城県 不動産価格分析 - グラフ04
間取り別 件数割合・平均価格（円グラフ）

【実行】
python graph_04_floor_plan.py
"""

import sqlite3
import pandas as pd
import json
from pathlib import Path

DB_PATH = Path("ibaraki_realestate.db")
OUTPUT  = Path("graph_04_floor_plan.html")

COLORS = [
    "#7986CB","#4DB6AC","#F06292","#FFB74D","#A1887F",
    "#90A4AE","#81C784","#CE93D8","#80DEEA","#BCAAA4",
    "#B0BEC5","#EF9A9A","#FFF176",
]


def get_data(conn) -> pd.DataFrame:
    df = pd.read_sql("""
        SELECT
            floor_plan                          AS 間取り,
            COUNT(*)                            AS 件数,
            ROUND(AVG(trade_price) / 10000, 1)  AS 平均価格_万円,
            ROUND(AVG(price_per_sqm))           AS 平均㎡単価_円,
            ROUND(AVG(area), 1)                 AS 平均面積_m2
        FROM csv_transactions
        WHERE trade_type LIKE '%マンション%'
          AND trade_price IS NOT NULL
          AND floor_plan IS NOT NULL
          AND floor_plan != 'nan'
        GROUP BY floor_plan
        HAVING 件数 >= 10
        ORDER BY 件数 DESC
    """, conn)
    return df


def main():
    conn = sqlite3.connect(DB_PATH)
    df   = get_data(conn)
    conn.close()

    print(f"間取り種別数: {len(df)}")

    data_json   = json.dumps({
        "labels": df["間取り"].tolist(),
        "count":  df["件数"].tolist(),
        "price":  df["平均価格_万円"].tolist(),
        "sqm":    df["平均㎡単価_円"].tolist(),
        "area":   df["平均面積_m2"].tolist(),
    }, ensure_ascii=False)
    colors_json = json.dumps(COLORS)

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <title>茨城県 間取り別価格</title>
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
        .toggle-btn.active {{ background: #1565C0; color: white; border-color: #1565C0; }}
        .content {{ padding: 20px 28px; }}
        .graph-card {{
            background: white; border-radius: 12px;
            padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        }}
        .graphs-row {{
            display: flex; gap: 16px;
        }}
        .graph-half {{ flex: 1; }}
        .footer {{
            text-align: center; padding: 12px;
            font-size: 11px; color: #AAA;
            border-top: 1px solid #EEE; margin-top: 16px;
        }}
    </style>
</head>
<body>

<div class="header">
    <h1>🏢 茨城県 中古マンション 間取り別 分析</h1>
    <p>出典：国土交通省不動産情報ライブラリ</p>
</div>

<div class="toggle-bar">
    <span>価格表示：</span>
    <button class="toggle-btn active" onclick="switchMetric('price', this)">平均価格（万円）</button>
    <button class="toggle-btn"        onclick="switchMetric('sqm', this)">㎡単価（円）</button>
</div>

<div class="content">
    <div class="graph-card">
        <div class="graphs-row">
            <div class="graph-half">
                <div id="graph-count" style="width:100%; height:520px;"></div>
            </div>
            <div class="graph-half">
                <div id="graph-price" style="width:100%; height:520px;"></div>
            </div>
        </div>
    </div>
</div>

<div class="footer">
    このサービスは、国土交通省不動産情報ライブラリのAPI機能を使用していますが、
    提供情報の最新性・正確性・完全性等が保証されたものではありません。
</div>

<script>
const DATA   = {data_json};
const COLORS = {colors_json};

let currentMetric = 'price';

function updateGraph() {{
    const isPrice  = currentMetric === 'price';
    const priceVal = isPrice ? DATA.price : DATA.sqm;
    const priceLabel = isPrice ? '平均価格（万円）' : '㎡単価（円）';

    // 左：件数割合
    Plotly.react('graph-count', [{{
        type: 'pie',
        labels: DATA.labels,
        values: DATA.count,
        marker: {{ colors: COLORS }},
        textinfo: 'label+percent',
        textposition: 'outside',
        hovertemplate: '<b>%{{label}}</b><br>' +
            '件数: %{{value}}件<br>' +
            '割合: %{{percent}}<br>' +
            '平均面積: ' + DATA.area.map((a,i) => a + '㎡')[0] + '<extra></extra>',
        customdata: DATA.labels.map((l, i) => [
            DATA.count[i],
            DATA.price[i],
            DATA.sqm[i],
            DATA.area[i],
        ]),
        hovertemplate: DATA.labels.map((l, i) =>
            `<b>${{l}}</b><br>` +
            `件数: ${{DATA.count[i].toLocaleString()}}件<br>` +
            `割合: %{{percent}}<br>` +
            `平均価格: ${{DATA.price[i]}}万円<br>` +
            `㎡単価: ${{DATA.sqm[i].toLocaleString()}}円<br>` +
            `平均面積: ${{DATA.area[i]}}㎡<extra></extra>`
        ),
    }}], {{
        title: {{ text: '間取り別 取引件数割合', font: {{ size: 15 }}, x: 0.5 }},
        showlegend: true,
        legend: {{ orientation: 'v', x: 1.02, y: 0.5 }},
        paper_bgcolor: 'white',
        margin: {{ l:20, r:120, t:60, b:20 }},
    }});

    // 右：平均価格
    Plotly.react('graph-price', [{{
        type: 'pie',
        labels: DATA.labels,
        values: priceVal,
        marker: {{ colors: COLORS }},
        textinfo: 'label+value',
        textposition: 'outside',
        hovertemplate: DATA.labels.map((l, i) =>
            `<b>${{l}}</b><br>` +
            `${{priceLabel}}: ${{priceVal[i].toLocaleString()}}<br>` +
            `件数: ${{DATA.count[i].toLocaleString()}}件<br>` +
            `平均面積: ${{DATA.area[i]}}㎡<extra></extra>`
        ),
    }}], {{
        title: {{ text: '間取り別 ' + priceLabel, font: {{ size: 15 }}, x: 0.5 }},
        showlegend: false,
        paper_bgcolor: 'white',
        margin: {{ l:20, r:20, t:60, b:20 }},
    }});
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
