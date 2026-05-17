"""
茨城県 不動産価格分析 - グラフ06
利便性スコア帯別 平均価格（マンション・宅地 色分け）

【実行】
python graph_06_convenience.py
"""

import sqlite3
import pandas as pd
import json
from pathlib import Path

DB_PATH = Path("ibaraki_realestate.db")
OUTPUT  = Path("graph_06_convenience.html")

SCORE_ORDER = ["0〜20点","21〜40点","41〜60点","61〜80点","81〜100点"]


def get_data(conn, trade_type: str, label: str) -> pd.DataFrame:
    df = pd.read_sql(f"""
        SELECT
            CASE
                WHEN convenience_score <= 20 THEN '0〜20点'
                WHEN convenience_score <= 40 THEN '21〜40点'
                WHEN convenience_score <= 60 THEN '41〜60点'
                WHEN convenience_score <= 80 THEN '61〜80点'
                ELSE '81〜100点'
            END                                     AS スコア帯,
            COUNT(*)                                AS 件数,
            ROUND(AVG(trade_price) / 10000, 1)      AS 平均価格_万円,
            ROUND(AVG(price_per_sqm))               AS 平均㎡単価_円
        FROM csv_transactions
        WHERE trade_type LIKE '%{trade_type}%'
          AND trade_price IS NOT NULL
          AND convenience_score IS NOT NULL
          AND price_per_sqm IS NOT NULL
        GROUP BY スコア帯
    """, conn)
    df["スコア帯"] = pd.Categorical(df["スコア帯"], categories=SCORE_ORDER, ordered=True)
    df = df.sort_values("スコア帯").reset_index(drop=True)
    df["種別"] = label
    return df


def get_city_score(conn) -> pd.DataFrame:
    """市区町村別の平均利便性スコアを取得する"""
    return pd.read_sql("""
        SELECT
            city_name                           AS 市区町村,
            ROUND(AVG(convenience_score), 1)    AS 平均スコア,
            ROUND(AVG(conv_500m), 1)            AS コンビニ平均,
            ROUND(AVG(super_500m), 1)           AS スーパー平均,
            ROUND(AVG(hospital_1km), 1)         AS 病院平均,
            ROUND(AVG(school_1km), 1)           AS 学校平均,
            ROUND(AVG(bank_500m), 1)            AS 銀行平均,
            COUNT(*)                            AS 件数
        FROM csv_transactions
        WHERE convenience_score IS NOT NULL
        GROUP BY city_name
        HAVING 件数 >= 10
        ORDER BY 平均スコア DESC
    """, conn)



def df_to_json(df: pd.DataFrame) -> str:
    return json.dumps({
        "labels": df["スコア帯"].tolist(),
        "price":  df["平均価格_万円"].tolist(),
        "sqm":    df["平均㎡単価_円"].tolist(),
        "count":  df["件数"].tolist(),
    }, ensure_ascii=False)


def main():
    conn = sqlite3.connect(DB_PATH)
    df_m     = get_data(conn, "マンション", "中古マンション")
    df_l     = get_data(conn, "宅地",       "宅地（土地と建物）")
    df_city  = get_city_score(conn)
    conn.close()

    data_m_json    = df_to_json(df_m)
    data_l_json    = df_to_json(df_l)
    city_data_json = json.dumps({
        "labels":   df_city["市区町村"].tolist(),
        "score":    df_city["平均スコア"].tolist(),
        "conv":     df_city["コンビニ平均"].tolist(),
        "super_":   df_city["スーパー平均"].tolist(),
        "hospital": df_city["病院平均"].tolist(),
        "school":   df_city["学校平均"].tolist(),
        "bank":     df_city["銀行平均"].tolist(),
        "count":    df_city["件数"].tolist(),
    }, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <title>茨城県 利便性スコアと価格</title>
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
        .score-desc {{
            background: white; padding: 10px 28px;
            border-bottom: 1px solid #EEE;
            font-size: 12px; color: #777;
        }}
        .score-desc span {{ margin-right: 20px; }}
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
    <h1>🏪 茨城県 利便性スコア帯別 平均取引価格</h1>
    <p>出典：国土交通省不動産情報ライブラリ / © OpenStreetMap contributors</p>
</div>

<div class="score-desc">
    <span>🏪 コンビニ（500m以内）：1軒10点</span>
    <span>🛒 スーパー（500m以内）：1軒15点</span>
    <span>🏥 病院・クリニック（1km以内）：1軒10点</span>
    <span>🏫 学校（1km以内）：1軒5点</span>
    <span>🏦 銀行・ATM（500m以内）：1軒5点</span>
    <span>最大100点</span>
</div>

<div class="ctrl-bar">
    <span>表示切替：</span>
    <button class="toggle-btn active" onclick="switchMetric('price', this)">平均価格（万円）</button>
    <button class="toggle-btn"        onclick="switchMetric('sqm', this)">㎡単価（円）</button>
</div>

<div class="content">
    <div class="graph-card">
        <div id="graph" style="width:100%; height:560px;"></div>
    </div>

    <!-- 市区町村別 平均利便性スコア -->
    <div class="graph-card" style="margin-top:16px;">
        <div id="graph-city" style="width:100%; height:560px;"></div>
    </div>
</div>

<div class="footer">
    このサービスは、国土交通省不動産情報ライブラリのAPI機能を使用していますが、
    提供情報の最新性・正確性・完全性等が保証されたものではありません。
</div>

<script>
const DATA_M    = {data_m_json};
const DATA_L    = {data_l_json};
const CITY_DATA = {city_data_json};

let currentMetric = 'price';

// 市区町村別スコアグラフ（初期表示のみ）
function drawCityScore() {{
    const colors = CITY_DATA.score.map(s =>
        s >= 60 ? '#1565C0' :
        s >= 40 ? '#1E88E5' :
        s >= 20 ? '#64B5F6' : '#BBDEFB'
    );

    Plotly.react('graph-city', [{{
        x: CITY_DATA.labels,
        y: CITY_DATA.score,
        type: 'bar',
        marker: {{ color: colors }},
        text: CITY_DATA.score.map(s => s + '点'),
        textposition: 'outside',
        hovertemplate: CITY_DATA.labels.map((l, i) =>
            `<b>${{l}}</b><br>` +
            `平均スコア: ${{CITY_DATA.score[i]}}点<br>` +
            `コンビニ: ${{CITY_DATA.conv[i]}}軒<br>` +
            `スーパー: ${{CITY_DATA.super_[i]}}軒<br>` +
            `病院: ${{CITY_DATA.hospital[i]}}軒<br>` +
            `学校: ${{CITY_DATA.school[i]}}軒<br>` +
            `銀行: ${{CITY_DATA.bank[i]}}軒<br>` +
            `件数: ${{CITY_DATA.count[i].toLocaleString()}}件<extra></extra>`
        ),
        name: '',
    }}], {{
        title: {{
            text: '茨城県 市区町村別 平均利便性スコア（100点満点）',
            font: {{ size: 16 }}, x: 0.5, xanchor: 'center'
        }},
        xaxis: {{
            title: '市区町村',
            tickangle: -40,
            tickfont: {{ size: 11 }},
            gridcolor: '#EEEEEE',
        }},
        yaxis: {{
            title: '平均利便性スコア（点）',
            gridcolor: '#EEEEEE',
            zeroline: false,
            range: [0, Math.max(...CITY_DATA.score) * 1.25],
        }},
        plot_bgcolor: 'white',
        paper_bgcolor: 'white',
        showlegend: false,
        margin: {{ l:70, r:30, t:80, b:120 }},
        bargap: 0.3,
    }});
}}

function updateGraph() {{
    const isPrice = currentMetric === 'price';
    const yKey    = isPrice ? 'price' : 'sqm';
    const yTitle  = isPrice ? '平均取引価格（万円）' : '平均㎡単価（円）';

    const allY = [...DATA_M[yKey], ...DATA_L[yKey]];

    const traces = [
        {{
            x: DATA_M.labels,
            y: DATA_M[yKey],
            name: '🏢 中古マンション',
            type: 'bar',
            marker: {{ color: '#3F51B5' }},
            text: DATA_M[yKey].map((v, i) =>
                `${{isPrice ? v + '万円' : v.toLocaleString() + '円'}}<br>(${{DATA_M.count[i].toLocaleString()}}件)`
            ),
            textposition: 'outside',
            hovertemplate: DATA_M.labels.map((l, i) =>
                `<b>中古マンション ${{l}}</b><br>` +
                (isPrice ? `平均価格: ${{DATA_M.price[i]}}万円` : `㎡単価: ${{DATA_M.sqm[i].toLocaleString()}}円`) +
                `<br>件数: ${{DATA_M.count[i].toLocaleString()}}件<extra></extra>`
            ),
        }},
        {{
            x: DATA_L.labels,
            y: DATA_L[yKey],
            name: '🏠 宅地（土地と建物）',
            type: 'bar',
            marker: {{ color: '#43A047' }},
            text: DATA_L[yKey].map((v, i) =>
                `${{isPrice ? v + '万円' : v.toLocaleString() + '円'}}<br>(${{DATA_L.count[i].toLocaleString()}}件)`
            ),
            textposition: 'outside',
            hovertemplate: DATA_L.labels.map((l, i) =>
                `<b>宅地 ${{l}}</b><br>` +
                (isPrice ? `平均価格: ${{DATA_L.price[i]}}万円` : `㎡単価: ${{DATA_L.sqm[i].toLocaleString()}}円`) +
                `<br>件数: ${{DATA_L.count[i].toLocaleString()}}件<extra></extra>`
            ),
        }},
    ];

    Plotly.react('graph', traces, {{
        title: {{
            text: '茨城県 利便性スコア帯別 ' + (isPrice ? '平均価格' : '平均㎡単価'),
            font: {{ size: 16 }}, x: 0.5, xanchor: 'center'
        }},
        xaxis: {{
            title: '利便性スコア帯（100点満点）',
            categoryorder: 'array',
            categoryarray: DATA_M.labels,
            gridcolor: '#EEEEEE',
        }},
        yaxis: {{
            title: yTitle,
            gridcolor: '#EEEEEE',
            zeroline: false,
            range: [0, Math.max(...allY) * 1.25],
        }},
        barmode: 'group',
        bargap: 0.2,
        bargroupgap: 0.05,
        plot_bgcolor: 'white',
        paper_bgcolor: 'white',
        legend: {{
            orientation: 'h',
            x: 0.5, xanchor: 'center', y: -0.15
        }},
        margin: {{ l:70, r:30, t:80, b:80 }},
    }});
}}

function switchMetric(metric, btn) {{
    currentMetric = metric;
    document.querySelectorAll('.toggle-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    updateGraph();
}}

updateGraph();
drawCityScore();
</script>
</body>
</html>"""

    OUTPUT.write_text(html, encoding="utf-8")
    print(f"\n✅ {OUTPUT.resolve()} をブラウザで開いてください！")


if __name__ == "__main__":
    main()
