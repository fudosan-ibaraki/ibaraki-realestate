"""
茨城県 不動産価格分析 - グラフ07
浸水リスク別 価格分布（箱ひげ図）マンション・宅地 色分け

【実行】
python graph_07_hazard.py
"""

import sqlite3
import pandas as pd
import json
from pathlib import Path

DB_PATH = Path("ibaraki_realestate.db")
OUTPUT  = Path("graph_07_hazard.html")

RISK_ORDER = ["高", "中", "低", "なし"]


def get_data(conn, trade_type: str) -> pd.DataFrame:
    return pd.read_sql(f"""
        SELECT
            hazard_risk         AS リスク,
            trade_price / 10000.0 AS 価格_万円,
            price_per_sqm       AS ㎡単価_円,
            city_name           AS 市区町村,
            district            AS 地区
        FROM csv_transactions
        WHERE trade_type LIKE '%{trade_type}%'
          AND hazard_risk IS NOT NULL
          AND trade_price IS NOT NULL
          AND trade_price > 0
          AND trade_price <= 100000000
    """, conn)


def df_to_boxplot_json(df: pd.DataFrame) -> str:
    """リスク別に価格データをまとめる"""
    result = {}
    for risk in RISK_ORDER:
        sub = df[df["リスク"] == risk]["価格_万円"].dropna()
        result[risk] = sub.tolist()
    return json.dumps(result, ensure_ascii=False)


def main():
    conn = sqlite3.connect(DB_PATH)
    df_m = get_data(conn, "マンション")
    df_l = get_data(conn, "宅地")
    conn.close()

    print(f"マンション: {len(df_m)}件 / 宅地: {len(df_l)}件")

    data_m_json    = df_to_boxplot_json(df_m)
    data_l_json    = df_to_boxplot_json(df_l)
    risk_order_json = json.dumps(RISK_ORDER, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <title>茨城県 浸水リスク別価格</title>
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
        .risk-desc {{
            background: white; padding: 10px 28px;
            border-bottom: 1px solid #EEE;
            display: flex; gap: 24px; font-size: 12px; color: #555;
            flex-wrap: wrap;
        }}
        .risk-item {{ display: flex; align-items: center; gap: 6px; }}
        .risk-dot {{
            width: 12px; height: 12px; border-radius: 50%;
        }}
        .ctrl-bar {{
            display: flex; align-items: center; gap: 12px;
            background: white; padding: 10px 28px;
            border-bottom: 1px solid #EEE; font-size: 13px; color: #555;
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
        .footer {{
            text-align: center; padding: 12px;
            font-size: 11px; color: #AAA;
            border-top: 1px solid #EEE; margin-top: 16px;
        }}
    </style>
</head>
<body>

<div class="header">
    <h1>⚠️ 茨城県 浸水リスク別 取引価格分布</h1>
    <p>出典：国土交通省不動産情報ライブラリ / 国土交通省ハザードマップ</p>
</div>

<div class="risk-desc">
    <div class="risk-item">
        <div class="risk-dot" style="background:#E53935"></div>
        高リスク：浸水エリアから100m以内
    </div>
    <div class="risk-item">
        <div class="risk-dot" style="background:#FB8C00"></div>
        中リスク：100〜300m以内
    </div>
    <div class="risk-item">
        <div class="risk-dot" style="background:#FDD835"></div>
        低リスク：300〜500m以内
    </div>
    <div class="risk-item">
        <div class="risk-dot" style="background:#43A047"></div>
        なし：500m超
    </div>
</div>

<div class="ctrl-bar">
    <span>表示切替：</span>
    <button class="toggle-btn active" onclick="switchMetric('price', this)">取引価格（万円）</button>
    <button class="toggle-btn"        onclick="switchMetric('sqm', this)">㎡単価（円）</button>
</div>

<div class="content">
    <div class="graph-card">
        <div id="graph" style="width:100%; height:580px;"></div>
    </div>
</div>

<div class="footer">
    このサービスは、国土交通省不動産情報ライブラリのAPI機能を使用していますが、
    提供情報の最新性・正確性・完全性等が保証されたものではありません。
</div>

<script>
const DATA_M     = {data_m_json};
const DATA_L     = {data_l_json};
const RISK_ORDER = {risk_order_json};

const RISK_COLORS = {{
    '高':  '#E53935',
    '中':  '#FB8C00',
    '低':  '#FDD835',
    'なし':'#43A047',
}};

let currentMetric = 'price';

function updateGraph() {{
    const isPrice = currentMetric === 'price';
    const yTitle  = isPrice ? '取引価格（万円）' : '㎡単価（円）';

    const traces = [];

    RISK_ORDER.forEach(risk => {{
        const color = RISK_COLORS[risk];

        // マンション
        traces.push({{
            type: 'box',
            y: DATA_M[risk],
            name: `${{risk}} マンション`,
            x0: risk,
            marker: {{ color: color, opacity: 0.8 }},
            line: {{ color: color }},
            fillcolor: color + '55',
            boxmean: true,
            legendgroup: risk,
            offsetgroup: 'mansion',
            hovertemplate:
                `<b>${{risk}}リスク・マンション</b><br>` +
                `最大: %{{upperfence:.0f}}万円<br>` +
                `第3四分位: %{{q3:.0f}}万円<br>` +
                `中央値: %{{median:.0f}}万円<br>` +
                `第1四分位: %{{q1:.0f}}万円<br>` +
                `最小: %{{lowerfence:.0f}}万円<extra></extra>`,
        }});

        // 宅地
        traces.push({{
            type: 'box',
            y: DATA_L[risk],
            name: `${{risk}} 宅地`,
            x0: risk,
            marker: {{ color: color, opacity: 0.5 }},
            line: {{ color: color, dash: 'dot' }},
            fillcolor: color + '22',
            boxmean: true,
            legendgroup: risk,
            offsetgroup: 'land',
            hovertemplate:
                `<b>${{risk}}リスク・宅地</b><br>` +
                `最大: %{{upperfence:.0f}}万円<br>` +
                `第3四分位: %{{q3:.0f}}万円<br>` +
                `中央値: %{{median:.0f}}万円<br>` +
                `第1四分位: %{{q1:.0f}}万円<br>` +
                `最小: %{{lowerfence:.0f}}万円<extra></extra>`,
        }});
    }});

    Plotly.react('graph', traces, {{
        title: {{
            text: '茨城県 浸水リスク別 取引価格分布（箱ひげ図）',
            font: {{ size: 16 }}, x: 0.5, xanchor: 'center'
        }},
        xaxis: {{
            title: '浸水リスク',
            categoryorder: 'array',
            categoryarray: RISK_ORDER,
            gridcolor: '#EEEEEE',
        }},
        yaxis: {{
            title: yTitle,
            gridcolor: '#EEEEEE',
            zeroline: false,
            range: [0, 20000],
        }},
        boxmode: 'group',
        plot_bgcolor: 'white',
        paper_bgcolor: 'white',
        legend: {{
            orientation: 'h',
            x: 0.5, xanchor: 'center', y: -0.15,
            traceorder: 'grouped',
        }},
        margin: {{ l:70, r:30, t:80, b:100 }},
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
