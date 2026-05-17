"""
茨城県 不動産価格分析ツール - Step 6
Plotlyによるグラフ可視化（1ページ・タブ切り替え）

【出力】
ibaraki_graphs.html — ブラウザで開くとタブ切り替えで全グラフが見られる

【実行】
python step6_visualize_graphs.py
"""

import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

DB_PATH = Path("ibaraki_realestate.db")


def get_conn():
    return sqlite3.connect(DB_PATH)


# ── グラフ1: 価格トレンド ─────────────────────────────────
def graph_price_trend(conn):
    log.info("グラフ1: 価格トレンド...")

    top_cities = pd.read_sql("""
        SELECT city_name FROM csv_transactions
        WHERE trade_price IS NOT NULL
        GROUP BY city_name ORDER BY COUNT(*) DESC LIMIT 10
    """, conn)["city_name"].tolist()

    placeholders = ",".join([f"'{c}'" for c in top_cities])

    df_m = pd.read_sql(f"""
        SELECT city_name AS 市区町村, year AS 年,
               ROUND(AVG(trade_price)/10000, 1) AS 平均価格_万円,
               COUNT(*) AS 件数
        FROM csv_transactions
        WHERE trade_type LIKE '%マンション%'
          AND trade_price IS NOT NULL AND year IS NOT NULL
          AND city_name IN ({placeholders})
        GROUP BY city_name, year HAVING 件数 >= 3
        ORDER BY city_name, year
    """, conn)

    df_l = pd.read_sql(f"""
        SELECT city_name AS 市区町村, year AS 年,
               ROUND(AVG(trade_price)/10000, 1) AS 平均価格_万円,
               COUNT(*) AS 件数
        FROM csv_transactions
        WHERE trade_type LIKE '%宅地%'
          AND trade_price IS NOT NULL AND year IS NOT NULL
          AND city_name IN ({placeholders})
        GROUP BY city_name, year HAVING 件数 >= 3
        ORDER BY city_name, year
    """, conn)

    fig = make_subplots(
        rows=2, cols=1,
        subplot_titles=("マンション 年別平均価格推移", "宅地 年別平均価格推移"),
        vertical_spacing=0.12
    )

    for city in top_cities:
        dm = df_m[df_m["市区町村"] == city]
        if not dm.empty:
            fig.add_trace(go.Scatter(
                x=dm["年"], y=dm["平均価格_万円"],
                name=city, mode="lines+markers",
                hovertemplate=f"{city}<br>%{{x}}年: %{{y}}万円<extra></extra>"
            ), row=1, col=1)

    for city in top_cities:
        dl = df_l[df_l["市区町村"] == city]
        if not dl.empty:
            fig.add_trace(go.Scatter(
                x=dl["年"], y=dl["平均価格_万円"],
                name=city, mode="lines+markers",
                showlegend=False,
                hovertemplate=f"{city}<br>%{{x}}年: %{{y}}万円<extra></extra>"
            ), row=2, col=1)

    fig.update_layout(
        title="茨城県 主要都市 不動産価格トレンド（2020〜2025年）",
        height=800, hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=-0.15)
    )
    fig.update_yaxes(title_text="平均価格（万円）")
    fig.update_xaxes(title_text="年")
    return fig


# ── グラフ2: 築年数と価格 ────────────────────────────────
def graph_building_age(conn):
    log.info("グラフ2: 築年数と価格...")

    order = ["築5年以内","築6〜10年","築11〜20年","築21〜30年","築31〜40年","築41年以上"]

    def get_df(trade_type):
        df = pd.read_sql(f"""
            SELECT
                CASE
                    WHEN (2024 - building_year) <= 5  THEN '築5年以内'
                    WHEN (2024 - building_year) <= 10 THEN '築6〜10年'
                    WHEN (2024 - building_year) <= 20 THEN '築11〜20年'
                    WHEN (2024 - building_year) <= 30 THEN '築21〜30年'
                    WHEN (2024 - building_year) <= 40 THEN '築31〜40年'
                    ELSE '築41年以上'
                END AS 築年数区分,
                ROUND(AVG(trade_price)/10000, 1) AS 平均価格_万円,
                COUNT(*) AS 件数
            FROM csv_transactions
            WHERE trade_type LIKE '%{trade_type}%'
              AND trade_price IS NOT NULL
              AND building_year IS NOT NULL AND building_year > 1900
            GROUP BY 築年数区分
        """, conn)
        df["築年数区分"] = pd.Categorical(df["築年数区分"], categories=order, ordered=True)
        return df.sort_values("築年数区分")

    df_m = get_df("マンション")
    df_l = get_df("宅地")

    fig = make_subplots(rows=1, cols=2, subplot_titles=("マンション", "宅地"))

    fig.add_trace(go.Bar(
        x=df_m["築年数区分"], y=df_m["平均価格_万円"],
        name="マンション", marker_color="#3498DB",
        text=df_m["平均価格_万円"], textposition="outside",
        hovertemplate="%{x}<br>平均価格: %{y}万円<extra></extra>"
    ), row=1, col=1)

    fig.add_trace(go.Bar(
        x=df_l["築年数区分"], y=df_l["平均価格_万円"],
        name="宅地", marker_color="#2ECC71",
        text=df_l["平均価格_万円"], textposition="outside",
        hovertemplate="%{x}<br>平均価格: %{y}万円<extra></extra>"
    ), row=1, col=2)

    fig.update_layout(
        title="茨城県 築年数別 平均取引価格",
        height=500, showlegend=False
    )
    fig.update_yaxes(title_text="平均価格（万円）")
    return fig


# ── グラフ3: 駅距離と価格 ────────────────────────────────
def graph_station_distance(conn):
    log.info("グラフ3: 駅距離と価格...")

    order = ["500m以内","500m〜1km","1〜2km","2〜3km","3km超"]

    def get_df(trade_type):
        df = pd.read_sql(f"""
            SELECT
                CASE
                    WHEN nearest_station_dist <= 500  THEN '500m以内'
                    WHEN nearest_station_dist <= 1000 THEN '500m〜1km'
                    WHEN nearest_station_dist <= 2000 THEN '1〜2km'
                    WHEN nearest_station_dist <= 3000 THEN '2〜3km'
                    ELSE '3km超'
                END AS 駅距離,
                ROUND(AVG(trade_price)/10000, 1) AS 平均価格_万円,
                COUNT(*) AS 件数
            FROM csv_transactions
            WHERE trade_type LIKE '%{trade_type}%'
              AND trade_price IS NOT NULL
              AND nearest_station_dist IS NOT NULL
            GROUP BY 駅距離
        """, conn)
        df["駅距離"] = pd.Categorical(df["駅距離"], categories=order, ordered=True)
        return df.sort_values("駅距離")

    df_m = get_df("マンション")
    df_l = get_df("宅地")

    fig = make_subplots(rows=1, cols=2, subplot_titles=("マンション", "宅地"))

    fig.add_trace(go.Bar(
        x=df_m["駅距離"], y=df_m["平均価格_万円"],
        name="マンション", marker_color="#3498DB",
        text=df_m["平均価格_万円"], textposition="outside",
        hovertemplate="%{x}<br>平均価格: %{y}万円<extra></extra>"
    ), row=1, col=1)

    fig.add_trace(go.Bar(
        x=df_l["駅距離"], y=df_l["平均価格_万円"],
        name="宅地", marker_color="#2ECC71",
        text=df_l["平均価格_万円"], textposition="outside",
        hovertemplate="%{x}<br>平均価格: %{y}万円<extra></extra>"
    ), row=1, col=2)

    fig.update_layout(
        title="茨城県 最寄り駅距離別 平均取引価格",
        height=500, showlegend=False
    )
    fig.update_yaxes(title_text="平均価格（万円）")
    return fig


# ── グラフ4: 間取り別価格 ────────────────────────────────
def graph_floor_plan(conn):
    log.info("グラフ4: 間取り別価格...")

    df_m = pd.read_sql("""
        SELECT floor_plan AS 間取り,
               ROUND(AVG(trade_price)/10000, 1) AS 平均価格_万円,
               ROUND(AVG(price_per_sqm)) AS 平均㎡単価,
               COUNT(*) AS 件数
        FROM csv_transactions
        WHERE trade_type LIKE '%マンション%'
          AND trade_price IS NOT NULL
          AND floor_plan IS NOT NULL AND floor_plan != 'nan'
        GROUP BY floor_plan HAVING 件数 >= 10
        ORDER BY 平均価格_万円 DESC
    """, conn)

    fig = make_subplots(rows=1, cols=2,
        subplot_titles=("間取り別 平均価格（万円）", "間取り別 平均㎡単価（円）"))

    fig.add_trace(go.Bar(
        y=df_m["間取り"], x=df_m["平均価格_万円"],
        orientation="h", marker_color="#3498DB",
        text=df_m["平均価格_万円"], textposition="outside",
        hovertemplate="%{y}<br>%{x}万円<extra></extra>"
    ), row=1, col=1)

    fig.add_trace(go.Bar(
        y=df_m["間取り"], x=df_m["平均㎡単価"],
        orientation="h", marker_color="#E74C3C",
        text=df_m["平均㎡単価"], textposition="outside",
        hovertemplate="%{y}<br>%{x}円/㎡<extra></extra>"
    ), row=1, col=2)

    fig.update_layout(
        title="茨城県 マンション 間取り別価格比較",
        height=500, showlegend=False
    )
    return fig


# ── グラフ5: 割安・割高ランキング ─────────────────────────
def graph_relative_ranking(conn):
    log.info("グラフ5: 割安・割高ランキング...")

    def get_df(trade_type):
        return pd.read_sql(f"""
            WITH city_avg AS (
                SELECT city_name, AVG(price_per_sqm) AS avg_sqm
                FROM csv_transactions
                WHERE price_per_sqm IS NOT NULL
                  AND trade_type LIKE '%{trade_type}%'
                GROUP BY city_name
            )
            SELECT
                t.city_name || ' ' || t.district AS エリア,
                ROUND((AVG(t.price_per_sqm) - c.avg_sqm) / c.avg_sqm * 100, 1) AS 相対スコア,
                COUNT(*) AS 件数
            FROM csv_transactions t
            JOIN city_avg c ON t.city_name = c.city_name
            WHERE t.price_per_sqm IS NOT NULL
              AND t.trade_type LIKE '%{trade_type}%'
            GROUP BY t.city_name, t.district
            HAVING 件数 >= 10
            ORDER BY 相対スコア DESC
        """, conn)

    fig = make_subplots(rows=1, cols=2,
        subplot_titles=("マンション 割安・割高ランキング", "宅地 割安・割高ランキング"))

    for df, col in [(get_df("マンション"), 1), (get_df("宅地"), 2)]:
        combined = pd.concat([df.head(10), df.tail(10)]).drop_duplicates()
        combined = combined.sort_values("相対スコア")
        colors   = ["#E74C3C" if v >= 0 else "#3498DB" for v in combined["相対スコア"]]

        fig.add_trace(go.Bar(
            y=combined["エリア"], x=combined["相対スコア"],
            orientation="h", marker_color=colors,
            text=combined["相対スコア"].astype(str) + "%",
            textposition="outside",
            hovertemplate="%{y}<br>相対スコア: %{x}%<extra></extra>"
        ), row=1, col=col)

    fig.update_layout(
        title="茨城県 エリア別 割安・割高ランキング（赤=割高 青=割安）",
        height=700, showlegend=False
    )
    fig.add_vline(x=0, line_dash="dash", line_color="gray")
    return fig


# ── グラフ6: 利便性スコアと価格の相関 ────────────────────
def graph_convenience_score(conn):
    log.info("グラフ6: 利便性スコアと価格...")

    df = pd.read_sql("""
        SELECT city_name AS 市区町村, trade_type AS 種別,
               ROUND(AVG(convenience_score), 1) AS 平均利便性スコア,
               ROUND(AVG(trade_price)/10000, 1) AS 平均価格_万円,
               COUNT(*) AS 件数
        FROM csv_transactions
        WHERE convenience_score IS NOT NULL AND trade_price IS NOT NULL
        GROUP BY city_name, trade_type HAVING 件数 >= 10
    """, conn)

    fig = px.scatter(
        df, x="平均利便性スコア", y="平均価格_万円",
        color="種別", size="件数", hover_name="市区町村",
        title="茨城県 利便性スコアと平均価格の相関",
        labels={
            "平均利便性スコア": "利便性スコア（100点満点）",
            "平均価格_万円":    "平均価格（万円）"
        },
        trendline="ols",
        color_discrete_map={"中古マンション等": "#3498DB", "宅地(土地と建物)": "#2ECC71"}
    )
    fig.update_layout(height=600)
    return fig


# ── グラフ7: 浸水リスク別価格 ────────────────────────────
def graph_hazard_price(conn):
    log.info("グラフ7: 浸水リスク別価格...")

    df = pd.read_sql("""
        SELECT hazard_risk AS 浸水リスク, trade_type AS 種別,
               trade_price / 10000.0 AS 価格_万円
        FROM csv_transactions
        WHERE hazard_risk IS NOT NULL AND trade_price IS NOT NULL AND trade_price > 0
    """, conn)

    risk_order = ["高", "中", "低", "なし"]
    df["浸水リスク"] = pd.Categorical(df["浸水リスク"], categories=risk_order, ordered=True)
    df = df.sort_values("浸水リスク")

    fig = px.box(
        df, x="浸水リスク", y="価格_万円", color="種別",
        title="茨城県 浸水リスク別 取引価格分布（箱ひげ図）",
        labels={"価格_万円": "取引価格（万円）"},
        color_discrete_map={"中古マンション等": "#3498DB", "宅地(土地と建物)": "#2ECC71"},
        points=False
    )
    fig.update_layout(height=500)
    fig.update_yaxes(range=[0, 20000])
    return fig


# ── 1ページにまとめて出力 ────────────────────────────────
def build_dashboard(figures: dict):
    log.info("ダッシュボードを構築中...")

    tabs_html = ""
    contents_html = ""

    for i, (label, fig) in enumerate(figures.items()):
        active = "active" if i == 0 else ""
        tab_id = f"tab{i}"

        tabs_html += f"""
        <button class="tab-btn {active}" onclick="showTab('{tab_id}', this)">
            {label}
        </button>"""

        graph_html = fig.to_html(
            full_html=False,
            include_plotlyjs=False,
            div_id=f"graph{i}"
        )

        display = "block" if i == 0 else "none"
        contents_html += f"""
        <div id="{tab_id}" class="tab-content" style="display:{display}">
            {graph_html}
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>茨城県 不動産価格分析ダッシュボード</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: 'Helvetica Neue', Arial, sans-serif; background: #f5f5f5; }}
        .header {{
            background: linear-gradient(135deg, #2C3E50, #3498DB);
            color: white; padding: 20px 30px;
        }}
        .header h1 {{ font-size: 22px; margin-bottom: 4px; }}
        .header p  {{ font-size: 12px; opacity: 0.8; }}
        .tab-bar {{
            background: white;
            border-bottom: 2px solid #3498DB;
            padding: 0 20px;
            display: flex; flex-wrap: wrap; gap: 4px;
        }}
        .tab-btn {{
            padding: 10px 16px;
            border: none; background: transparent;
            cursor: pointer; font-size: 13px;
            color: #555; border-bottom: 3px solid transparent;
            transition: all 0.2s;
        }}
        .tab-btn:hover  {{ color: #3498DB; }}
        .tab-btn.active {{
            color: #3498DB; font-weight: bold;
            border-bottom: 3px solid #3498DB;
        }}
        .content {{ padding: 20px; }}
        .tab-content {{ background: white; border-radius: 8px; padding: 10px; }}
        .footer {{
            text-align: center; padding: 16px;
            font-size: 11px; color: #999;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🏠 茨城県 不動産価格分析ダッシュボード</h1>
        <p>出典：国土交通省不動産情報ライブラリ / © OpenStreetMap contributors / 国土地理院</p>
    </div>
    <div class="tab-bar">
        {tabs_html}
    </div>
    <div class="content">
        {contents_html}
    </div>
    <div class="footer">
        このサービスは、国土交通省不動産情報ライブラリのAPI機能を使用していますが、
        提供情報の最新性、正確性、完全性等が保証されたものではありません。
    </div>
    <script>
        function showTab(tabId, btn) {{
            document.querySelectorAll('.tab-content').forEach(el => el.style.display = 'none');
            document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
            document.getElementById(tabId).style.display = 'block';
            btn.classList.add('active');
        }}
    </script>
</body>
</html>"""

    output = Path("ibaraki_graphs.html")
    output.write_text(html, encoding="utf-8")
    log.info(f"保存完了: {output.resolve()}")
    return output


# ── メイン ────────────────────────────────────────────────
def main():
    conn = get_conn()

    figures = {
        "📈 価格トレンド":       graph_price_trend(conn),
        "🏗️ 築年数と価格":       graph_building_age(conn),
        "🚉 駅距離と価格":       graph_station_distance(conn),
        "🏢 間取り別価格":       graph_floor_plan(conn),
        "📊 割安・割高":         graph_relative_ranking(conn),
        "🏪 利便性と価格":       graph_convenience_score(conn),
        "⚠️ 浸水リスク別価格":   graph_hazard_price(conn),
    }

    conn.close()

    output = build_dashboard(figures)
    print(f"\n✅ {output} をブラウザで開いてください！")


if __name__ == "__main__":
    main()
