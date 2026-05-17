"""
茨城県 不動産価格分析ツール - Step 3c
空間結合②: 取引データ × 地価公示

【使い方】
python step3c_spatial_join_landprice.py

【乖離率の計算式】
乖離率(%) = (取引価格/㎡ - 公示地価/㎡) / 公示地価/㎡ × 100
プラス = 公示地価より高く取引（割高）
マイナス = 公示地価より安く取引（割安）
"""

import sqlite3
import logging
import math
import pandas as pd
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

DB_PATH = Path("ibaraki_realestate.db")


def haversine(lon1, lat1, lon2, lat2) -> float:
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi    = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def init_db(conn):
    cur  = conn.execute("PRAGMA table_info(csv_transactions)")
    cols = [row[1] for row in cur.fetchall()]

    new_cols = [
        ("nearest_lp_dist",    "REAL"),
        ("nearest_lp_price",   "INTEGER"),
        ("nearest_lp_address", "TEXT"),
        ("price_per_sqm",      "REAL"),
        ("deviation_rate",     "REAL"),
    ]

    for col, dtype in new_cols:
        if col not in cols:
            conn.execute(f"ALTER TABLE csv_transactions ADD COLUMN {col} {dtype}")
    conn.commit()
    log.info("列追加完了")


def main():
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    # 地価公示データを読み込む
    df_lp = pd.read_sql("""
        SELECT address, land_price, longitude, latitude, year, use_type
        FROM land_prices
        WHERE longitude IS NOT NULL
          AND latitude IS NOT NULL
          AND use_type LIKE '%住宅%'
    """, conn)
    log.info(f"地価公示地点数: {len(df_lp)}")

    lp_records = df_lp.to_dict("records")

    # 取引データを取得
    df_trans = pd.read_sql("""
        SELECT id, longitude, latitude, trade_price, area, year
        FROM csv_transactions
        WHERE longitude IS NOT NULL
          AND latitude IS NOT NULL
          AND trade_price IS NOT NULL
          AND area IS NOT NULL
          AND area > 0
          AND nearest_lp_price IS NULL
    """, conn)
    log.info(f"処理対象: {len(df_trans)}件")

    batch      = []
    batch_size = 500

    for i, row in df_trans.iterrows():
        lon, lat   = row["longitude"], row["latitude"]
        trans_year = row["year"]

        # 同じ年の公示地点を優先
        lp_same_year = [lp for lp in lp_records if lp["year"] == trans_year]
        lp_pool      = lp_same_year if lp_same_year else lp_records

        # 最寄り公示地点を探す
        min_dist = float("inf")
        nearest  = None

        for lp in lp_pool:
            dist = haversine(lon, lat, lp["longitude"], lp["latitude"])
            if dist < min_dist:
                min_dist = dist
                nearest  = lp

        if nearest:
            price_per_sqm = row["trade_price"] / row["area"]
            lp_price      = nearest["land_price"]

            if lp_price and lp_price > 0:
                deviation_rate = (price_per_sqm - lp_price) / lp_price * 100
            else:
                deviation_rate = None

            batch.append((
                round(min_dist),
                lp_price,
                nearest["address"],
                round(price_per_sqm, 1),
                round(deviation_rate, 1) if deviation_rate is not None else None,
                row["id"]
            ))

        if len(batch) >= batch_size:
            conn.executemany("""
                UPDATE csv_transactions
                SET nearest_lp_dist    = ?,
                    nearest_lp_price   = ?,
                    nearest_lp_address = ?,
                    price_per_sqm      = ?,
                    deviation_rate     = ?
                WHERE id = ?
            """, batch)
            conn.commit()
            log.info(f"進捗: {i+1}件完了")
            batch = []

    if batch:
        conn.executemany("""
            UPDATE csv_transactions
            SET nearest_lp_dist    = ?,
                nearest_lp_price   = ?,
                nearest_lp_address = ?,
                price_per_sqm      = ?,
                deviation_rate     = ?
            WHERE id = ?
        """, batch)
        conn.commit()

    # 乖離率サマリー
    df_result = pd.read_sql("""
        SELECT
            city_name                           AS 市区町村,
            COUNT(*)                            AS 件数,
            ROUND(AVG(deviation_rate), 1)       AS 平均乖離率_percent,
            ROUND(MIN(deviation_rate), 1)       AS 最小乖離率,
            ROUND(MAX(deviation_rate), 1)       AS 最大乖離率,
            ROUND(AVG(nearest_lp_dist))         AS 平均公示地点距離_m
        FROM csv_transactions
        WHERE deviation_rate IS NOT NULL
        GROUP BY city_name
        HAVING 件数 >= 10
        ORDER BY 平均乖離率_percent
        LIMIT 20
    """, conn)

    print("\n【エリア別 乖離率サマリー（割安順）】")
    print(df_result.to_string(index=False))

    conn.close()
    log.info("空間結合②完了！")


if __name__ == "__main__":
    main()
