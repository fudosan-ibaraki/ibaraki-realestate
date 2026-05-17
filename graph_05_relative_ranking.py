"""
茨城県 不動産価格分析 - グラフ05
地区別 割安・割高ランキング（縦棒グラフ）タブ切り替え

【実行】
python graph_05_relative_ranking.py
"""

import sqlite3
import pandas as pd
import json
from pathlib import Path

DB_PATH = Path("ibaraki_realestate.db")
OUTPUT  = Path("graph_05_relative_ranking.html")


def get_data(conn, trade_type: str) -> pd.DataFrame:
    return pd.read_sql(f"""
        WITH city_avg AS (
            SELECT city_name, AVG(price_per_sqm) AS avg_sqm
            FROM csv_transactions
            WHERE price_per_sqm IS NOT NULL
              AND trade_type LIKE '%{trade_type}%'
            GROUP BY city_name
        )
        SELECT
            t.city_name || ' ' || t.district         AS 地区,
            t.city_name                              AS 市区町村,
            t.district                               AS 丁目,
            COUNT(*)                                 AS 件数,
            ROUND(AVG(t.price_per_sqm))              AS 平均㎡単価,
            ROUND(c.avg_sqm)                         AS 市区町村平均㎡単価,
            ROUND((AVG(t.price_per_sqm) - c.avg_sqm)
                  / c.avg_sqm * 100, 1)              AS 相対スコア
        FROM csv_transactions t
        JOIN city_avg c ON t.city_name = c.city_name
        WHERE t.price_per_sqm IS NOT NULL
          AND t.trade_type LIKE '%{trade_type}%'
          AND t.district IS NOT NULL
          AND t.district != 'nan'
        GROUP BY t.city_name, t.district
        HAVING 件数 >= 5
        ORDER BY 相対スコア DESC
    """, conn)


def df_to_json(df: pd.DataFrame, top_n: int = 30) -> str:
    """上位・下位N件を返す"""
    top    = df.head(top_n)
    bottom = df.tail(top_n)
    combined = pd.concat([top, bottom]).drop_duplicates(subset="地区")
    combined = combined.sort_values("相対スコア", ascending=False)

    return json.dumps({
        "all": {
            "labels": df["地区"].tolist(),
            "score":  df["相対スコア"].tolist(),
            "count":  df["件数"].tolist(),
            "sqm":    df["平均㎡単価"].tolist(),
            "city_sqm": df["市区町村平均㎡単価"].tolist(),
            "city":   df["市区町村"].tolist(),
        },
        "top": {
            "labels": combined["地区"].tolist(),
            "score":  combined["相対スコア"].tolist(),
            "count":  combined["件数"].tolist(),
            "sqm":    combined["平均㎡単価"].tolist(),
            "city_sqm": combined["市区町村平均㎡単価"].tolist(),
            "city":   combined["市区町村"].tolist(),
        }
    }, ensure_ascii=False)


def main():
    conn = sqlite3.connect(DB_PATH)
    df_m = get_data(conn, "マンション")
    df_l = get_data(conn, "宅地")
    conn.close()

    print(f"マンション: {len(df_m)}地区 / 宅地: {len(df_l)}地区")

    data_m_json = df_to_json(df_m)
    data_l_json = df_to_json(df_l)

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <title>茨城県 割安・割高ランキング</title>
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
        .ctrl-bar {{
            display: flex; align-items: center; gap: 16px;
            background: white; padding: 10px 28px;
            border-bottom: 1px solid #EEE; font-size: 13px; color: #555;
            flex-wrap: wrap;
        }}
        .toggle-btn {{
            padding: 5px 16px; border: 1px solid #DDD;
            border-radius: 20px; background: white;
            font-size: 12px; cursor: pointer; color: #555;
            transition: all 0.2s;
        }}
        .toggle-btn.active {{ background: #1565C0; color: white; border-color: #1565C0; }}
        .slider-wrap {{ display: flex; align-items: center; gap: 8px; }}
        .slider-wrap input {{ width: 120px; accent-color: #1565C0; }}
        .content {{ padding: 16px 28px; }}
        .graph-card {{
            background: white; border-radius: 12px;
            padding: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        }}
        .footer {{
            text-align: center; padding: 12px;
            font-size: 11px; color: #AAA;
            border-top: 1px solid #EEE; margin-top: 16px;
        }}
        .legend {{
            display: flex; gap: 16px; font-size: 12px;
            padding: 8px 0; color: #555;
        }}
        .legend-item {{ display: flex; align-items: center; gap: 6px; }}
        .legend-color {{
            width: 14px; height: 14px; border-radius: 3px;
        }}
    </style>
</head>
<body>

<div class="header">
    <h1>📊 茨城県 地区別 割安・割高ランキング</h1>
    <p>出典：国土交通省不動産情報ライブラリ　※相対スコア = (地区㎡単価 - 市区町村平均㎡単価) / 市区町村平均㎡単価 × 100</p>
</div>

<div class="tab-bar">
    <button class="tab-btn active" onclick="switchTab('mansion', this)">🏢 中古マンション</button>
    <button class="tab-btn"        onclick="switchTab('land', this)">🏠 宅地（土地と建物）</button>
</div>

<div class="ctrl-bar">
    <span>表示件数（上位・下位各）：</span>
    <div class="slider-wrap">
        <input type="range" id="topN" min="5" max="30" value="20" step="5" oninput="updateTopN(this.value)">
        <span id="topN-label">20件</span>
    </div>
    <div class="legend">
        <div class="legend-item">
            <div class="legend-color" style="background:#E53935"></div>割高（市区町村平均より高い）
        </div>
        <div class="legend-item">
            <div class="legend-color" style="background:#1E88E5"></div>割安（市区町村平均より安い）
        </div>
    </div>
</div>

<div class="content">
    <div class="graph-card">
        <div id="graph" style="width:100%; height:600px;"></div>
    </div>
</div>

<div class="footer">
    このサービスは、国土交通省不動産情報ライブラリのAPI機能を使用していますが、
    提供情報の最新性・正確性・完全性等が保証されたものではありません。
</div>

<script>
const DATA_M = {data_m_json};
const DATA_L = {data_l_json};

let currentTab = 'mansion';
let currentN   = 20;

function updateGraph() {{
    const allData = currentTab === 'mansion' ? DATA_M.all : DATA_L.all;
    const n       = currentN;

    // スコアでソート済みの全データから上位N・下位N取得
    const labels  = allData.labels;
    const scores  = allData.score;
    const total   = labels.length;

    // 上位N（割高）+ 下位N（割安）を結合
    const topIdx    = Array.from({{length: Math.min(n, total)}}, (_, i) => i);
    const bottomIdx = Array.from({{length: Math.min(n, total)}}, (_, i) => total - 1 - i).reverse();
    const allIdx    = [...new Set([...topIdx, ...bottomIdx])];
    allIdx.sort((a, b) => scores[b] - scores[a]);

    const dispLabels = allIdx.map(i => labels[i]);
    const dispScores = allIdx.map(i => scores[i]);
    const dispCount  = allIdx.map(i => allData.count[i]);
    const dispSqm    = allIdx.map(i => allData.sqm[i]);
    const dispCitySqm= allIdx.map(i => allData.city_sqm[i]);
    const dispCity   = allIdx.map(i => allData.city[i]);
    const dispColors = dispScores.map(s => s >= 0 ? '#E53935' : '#1E88E5');

    const title = currentTab === 'mansion'
        ? '茨城県 中古マンション 地区別 割高・割安ランキング'
        : '茨城県 宅地（土地と建物） 地区別 割高・割安ランキング';

    Plotly.react('graph', [{{
        x: dispLabels,
        y: dispScores,
        type: 'bar',
        marker: {{ color: dispColors }},
        text: dispScores.map(s => s.toFixed(1) + '%'),
        textposition: 'outside',
        hovertemplate: dispLabels.map((l, i) =>
            `<b>${{l}}</b><br>` +
            `相対スコア: ${{dispScores[i].toFixed(1)}}%<br>` +
            `地区㎡単価: ${{dispSqm[i].toLocaleString()}}円<br>` +
            `市区町村平均: ${{dispCitySqm[i].toLocaleString()}}円<br>` +
            `件数: ${{dispCount[i]}}件<extra></extra>`
        ),
        name: '',
    }}], {{
        title: {{ text: title, font: {{ size: 16 }}, x: 0.5, xanchor: 'center' }},
        xaxis: {{
            title: '地区',
            tickangle: -40,
            tickfont: {{ size: 10 }},
            gridcolor: '#EEEEEE',
        }},
        yaxis: {{
            title: '相対スコア（%）',
            gridcolor: '#EEEEEE',
            zeroline: true,
            zerolinecolor: '#999',
            zerolinewidth: 1.5,
            range: [
                Math.min(...dispScores) * 1.25,
                Math.max(...dispScores) * 1.25
            ],
        }},
        plot_bgcolor: 'white',
        paper_bgcolor: 'white',
        showlegend: false,
        margin: {{ l:70, r:30, t:80, b:120 }},
        bargap: 0.2,
        shapes: [{{
            type: 'line', x0: -0.5, x1: dispLabels.length - 0.5,
            y0: 0, y1: 0,
            line: {{ color: '#999', width: 1.5, dash: 'dash' }}
        }}],
    }});
}}

function switchTab(tab, btn) {{
    currentTab = tab;
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    updateGraph();
}}

function updateTopN(val) {{
    currentN = parseInt(val);
    document.getElementById('topN-label').textContent = val + '件';
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
