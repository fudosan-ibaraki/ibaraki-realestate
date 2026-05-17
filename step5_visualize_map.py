"""
茨城県 不動産価格分析ツール - Step 5
Foliumによる地図可視化

【使い方】
1. N03-20230101_08_GML.zip を同じフォルダに置く
2. python step5_visualize_map.py を実行する
3. ibaraki_map.html をブラウザで開く

【出典】
地図タイル: 国土地理院
データ: 国土交通省不動産情報ライブラリ / © OpenStreetMap contributors
"""

import sqlite3
import folium
import pandas as pd
import json
import zipfile
import logging
from folium.plugins import HeatMap, MarkerCluster
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

DB_PATH       = Path("ibaraki_realestate.db")
BOUNDARY_ZIP  = "N03-20230101_08_GML.zip"
IBARAKI_CENTER = [36.3418, 140.4468]
ZOOM_START    = 9

GSI_TILE = "https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png"
GSI_ATTR = "出典：国土地理院 / 国土交通省不動産情報ライブラリ / © OpenStreetMap contributors"

# 茨城県内の路線
IBARAKI_LINES = [
    "水郡線", "常総線", "水戸線", "大洗鹿島線",
    "湊線", "竜ヶ崎線", "筑波山鋼索鉄道線", "鹿島線"
]
# 茨城県内のみに絞る路線（県をまたぐ路線）
CROSS_LINES = ["常磐線", "常磐新線"]


def get_conn():
    return sqlite3.connect(DB_PATH)


# ── 県境レイヤー ──────────────────────────────────────────
def add_boundary(m):
    log.info("県境レイヤー追加中...")
    zip_path = Path(BOUNDARY_ZIP)
    if not zip_path.exists():
        log.warning(f"県境ファイルが見つかりません: {BOUNDARY_ZIP}")
        return

    with zipfile.ZipFile(zip_path) as zf:
        geojson_name = next(n for n in zf.namelist() if n.endswith(".geojson"))
        geojson_data = json.loads(zf.read(geojson_name).decode("utf-8"))

    # 市区町村境界（細線）
    folium.GeoJson(
        geojson_data,
        name="🗺️ 市区町村境界",
        style_function=lambda x: {
            "fillColor":   "transparent",
            "color":       "#555555",
            "weight":      1,
            "dashArray":   "3,3",
        },
        tooltip=folium.GeoJsonTooltip(fields=["N03_004"], aliases=["市区町村:"]),
    ).add_to(m)

    # 県境（太線）— 全ポリゴンの外周を強調
    folium.GeoJson(
        geojson_data,
        name="🗺️ 県境",
        style_function=lambda x: {
            "fillColor":   "transparent",
            "color":       "#CC0000",
            "weight":      3,
            "opacity":     0.8,
        },
        show=True,
    ).add_to(m)

    log.info("  県境追加完了")


# ── レイヤー1: 価格ヒートマップ ───────────────────────────
def add_heatmap(m, conn):
    log.info("レイヤー1: 価格ヒートマップ追加中...")

    df_m = pd.read_sql("""
        SELECT latitude, longitude, trade_price
        FROM csv_transactions
        WHERE trade_type LIKE '%マンション%'
          AND latitude IS NOT NULL AND longitude IS NOT NULL
          AND trade_price IS NOT NULL
    """, conn)

    fg_m = folium.FeatureGroup(name="🏢 価格ヒートマップ（マンション）", show=True)
    HeatMap(
        [[r["latitude"], r["longitude"], r["trade_price"]/10000000] for _, r in df_m.iterrows()],
        radius=15, blur=20, min_opacity=0.3
    ).add_to(fg_m)
    fg_m.add_to(m)

    df_l = pd.read_sql("""
        SELECT latitude, longitude, trade_price
        FROM csv_transactions
        WHERE trade_type LIKE '%宅地%'
          AND latitude IS NOT NULL AND longitude IS NOT NULL
          AND trade_price IS NOT NULL
    """, conn)

    fg_l = folium.FeatureGroup(name="🏠 価格ヒートマップ（宅地）", show=False)
    HeatMap(
        [[r["latitude"], r["longitude"], r["trade_price"]/10000000] for _, r in df_l.iterrows()],
        radius=15, blur=20, min_opacity=0.3
    ).add_to(fg_l)
    fg_l.add_to(m)

    log.info(f"  マンション: {len(df_m)}件 / 宅地: {len(df_l)}件")


# ── レイヤー2: 割安・割高マップ ───────────────────────────
def add_relative_price_map(m, conn):
    log.info("レイヤー2: 割安・割高マップ追加中...")

    df = pd.read_sql("""
        WITH city_avg AS (
            SELECT city_name, AVG(price_per_sqm) AS avg_sqm
            FROM csv_transactions
            WHERE price_per_sqm IS NOT NULL
            GROUP BY city_name
        )
        SELECT
            t.city_name, t.district,
            t.latitude, t.longitude,
            t.trade_price, t.price_per_sqm,
            ROUND((t.price_per_sqm - c.avg_sqm) / c.avg_sqm * 100, 1) AS relative_score
        FROM csv_transactions t
        JOIN city_avg c ON t.city_name = c.city_name
        WHERE t.latitude IS NOT NULL
          AND t.longitude IS NOT NULL
          AND t.price_per_sqm IS NOT NULL
    """, conn)

    fg = folium.FeatureGroup(name="📊 割安・割高マップ", show=False)

    for _, r in df.iterrows():
        score = r["relative_score"]
        if score is None:
            continue
        if score >= 50:
            color = "red"
        elif score >= 20:
            color = "orange"
        elif score >= -20:
            color = "green"
        elif score >= -50:
            color = "blue"
        else:
            color = "darkblue"

        folium.CircleMarker(
            location=[r["latitude"], r["longitude"]],
            radius=4, color=color, fill=True, fill_opacity=0.6,
            popup=folium.Popup(
                f"<b>{r['city_name']} {r['district']}</b><br>"
                f"取引価格: {int(r['trade_price'])//10000}万円<br>"
                f"㎡単価: {int(r['price_per_sqm'])}円<br>"
                f"相対スコア: {score}%",
                max_width=200
            )
        ).add_to(fg)

    fg.add_to(m)
    log.info(f"  {len(df)}件追加")


# ── レイヤー3: ハザードマップ ─────────────────────────────
def add_hazard_map(m, conn):
    log.info("レイヤー3: ハザードマップ追加中...")

    df = pd.read_sql("""
        SELECT latitude, longitude, hazard_risk, trade_price, city_name, district
        FROM csv_transactions
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL
          AND hazard_risk IS NOT NULL AND hazard_risk != 'なし'
    """, conn)

    color_map = {"高": "red", "中": "orange", "低": "yellow"}
    fg = folium.FeatureGroup(name="⚠️ 浸水リスクマップ", show=False)

    for _, r in df.iterrows():
        folium.CircleMarker(
            location=[r["latitude"], r["longitude"]],
            radius=4,
            color=color_map.get(r["hazard_risk"], "gray"),
            fill=True, fill_opacity=0.6,
            popup=folium.Popup(
                f"<b>{r['city_name']} {r['district']}</b><br>"
                f"浸水リスク: {r['hazard_risk']}<br>"
                f"取引価格: {int(r['trade_price'])//10000 if r['trade_price'] else '-'}万円",
                max_width=200
            )
        ).add_to(fg)

    fg.add_to(m)
    log.info(f"  {len(df)}件追加")


# ── レイヤー4: 駅マップ ───────────────────────────────────
def add_station_map(m, conn):
    log.info("レイヤー4: 駅マップ追加中...")

    placeholders = ",".join([f"'{l}'" for l in IBARAKI_LINES])
    cross_placeholders = ",".join([f"'{l}'" for l in CROSS_LINES])

    df = pd.read_sql(f"""
        SELECT station, line, company, longitude, latitude
        FROM stations
        WHERE line IN ({placeholders})
        UNION
        SELECT station, line, company, longitude, latitude
        FROM stations
        WHERE line IN ({cross_placeholders})
          AND latitude BETWEEN 35.85 AND 36.9
          AND longitude BETWEEN 139.7 AND 140.9
    """, conn)

    fg = folium.FeatureGroup(name="🚉 駅マップ", show=False)
    mc = MarkerCluster().add_to(fg)

    for _, r in df.iterrows():
        folium.Marker(
            location=[r["latitude"], r["longitude"]],
            popup=folium.Popup(
                f"<b>{r['station']}</b><br>{r['line']}<br>{r['company']}",
                max_width=200
            ),
            icon=folium.Icon(color="blue", icon="train", prefix="fa")
        ).add_to(mc)

    fg.add_to(m)
    log.info(f"  {len(df)}駅追加")


# ── レイヤー5: 施設マップ ─────────────────────────────────
def add_facility_map(m, conn):
    log.info("レイヤー5: 施設マップ追加中...")

    category_config = {
        "コンビニ":   ("green",  "store",          "🏪 コンビニ"),
        "スーパー":   ("orange", "shopping-cart",  "🛒 スーパー"),
        "病院":       ("red",    "hospital-o",     "🏥 病院"),
        "クリニック": ("pink",   "stethoscope",    "🏥 クリニック"),
        "小学校":     ("purple", "graduation-cap", "🏫 小学校"),
        "銀行":       ("blue",   "bank",           "🏦 銀行"),
    }

    for category, (color, icon, label) in category_config.items():
        df = pd.read_sql("""
            SELECT name, longitude, latitude FROM facilities
            WHERE category = ? AND latitude IS NOT NULL
        """, conn, params=[category])

        fg = folium.FeatureGroup(name=label, show=False)
        mc = MarkerCluster().add_to(fg)

        for _, r in df.iterrows():
            folium.Marker(
                location=[r["latitude"], r["longitude"]],
                popup=r["name"] or category,
                icon=folium.Icon(color=color, icon=icon, prefix="fa")
            ).add_to(mc)

        fg.add_to(m)
        log.info(f"  {category}: {len(df)}件追加")


# ── メイン ────────────────────────────────────────────────
def main():
    conn = get_conn()

    log.info("地図を初期化中...")
    m = folium.Map(
        location=IBARAKI_CENTER,
        zoom_start=ZOOM_START,
        tiles=GSI_TILE,
        attr=GSI_ATTR,
    )

    add_boundary(m)
    add_heatmap(m, conn)
    add_relative_price_map(m, conn)
    add_hazard_map(m, conn)
    add_station_map(m, conn)
    add_facility_map(m, conn)

    folium.LayerControl(collapsed=False).add_to(m)

    # 凡例
    legend_html = """
    <div style="position:fixed;bottom:30px;left:30px;z-index:1000;
                background:white;padding:15px;border-radius:8px;
                border:1px solid #ccc;font-size:12px;">
        <b>割安・割高マップ 凡例</b><br>
        <span style="color:darkblue">●</span> 割安（-50%以下）<br>
        <span style="color:blue">●</span> やや割安（-20〜-50%）<br>
        <span style="color:green">●</span> 標準（±20%）<br>
        <span style="color:orange">●</span> やや割高（20〜50%）<br>
        <span style="color:red">●</span> 割高（50%以上）<br><br>
        <b>浸水リスク 凡例</b><br>
        <span style="color:red">●</span> 高リスク（100m以内）<br>
        <span style="color:orange">●</span> 中リスク（300m以内）<br>
        <span style="color:#cccc00">●</span> 低リスク（500m以内）
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    output = Path("ibaraki_map.html")
    m.save(str(output))
    log.info(f"地図を保存しました: {output.resolve()}")
    print(f"\n✅ {output} をブラウザで開いてください！")

    conn.close()


if __name__ == "__main__":
    main()
