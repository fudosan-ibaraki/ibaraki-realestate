"""
茨城県 不動産価格分析ツール - Step 3d（修正版）
空間結合③: 取引データ × ハザードマップ
"""

import sqlite3
import logging
import math
import pandas as pd
from pathlib import Path
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

DB_PATH   = Path("ibaraki_realestate.db")
GRID_SIZE = 0.01


def haversine(lon1, lat1, lon2, lat2) -> float:
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi    = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def build_grid(records):
    grid = defaultdict(list)
    for r in records:
        gx = int(r["centroid_lon"] / GRID_SIZE)
        gy = int(r["centroid_lat"] / GRID_SIZE)
        grid[(gx, gy)].append(r)
    return grid


def find_nearest(lon, lat, grid, search_range=5):
    """グリッドを使って近隣のハザード地点だけ距離計算する"""
    gx = int(lon / GRID_SIZE)
    gy = int(lat / GRID_SIZE)
    min_dist = float("inf")
    for dx in range(-search_range, search_range + 1):
        for dy in range(-search_range, search_range + 1):
            for r in grid.get((gx + dx, gy + dy), []):
                dist = haversine(lon, lat, r["centroid_lon"], r["centroid_lat"])
                if dist < min_dist:
                    min_dist = dist
    return min_dist


def init_db(conn):
    cur  = conn.execute("PRAGMA table_info(csv_transactions)")
    cols = [row[1] for row in cur.fetchall()]
    for col, dtype in [("hazard_dist", "REAL"), ("hazard_risk", "TEXT")]:
        if col not in cols:
            conn.execute(f"ALTER TABLE csv_transactions ADD COLUMN {col} {dtype}")
    conn.commit()
    log.info("列追加完了")


def main():
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    df_hazard = pd.read_sql("""
        SELECT centroid_lon, centroid_lat
        FROM hazard_flood
        WHERE centroid_lon IS NOT NULL AND centroid_lat IS NOT NULL
    """, conn)
    log.info(f"ハザードマップ地点数: {len(df_hazard)}")

    log.info("グリッドインデックス構築中...")
    grid = build_grid(df_hazard.to_dict("records"))
    log.info(f"グリッド数: {len(grid)}")

    df_trans = pd.read_sql("""
        SELECT id, longitude, latitude
        FROM csv_transactions
        WHERE longitude IS NOT NULL
          AND latitude IS NOT NULL
          AND hazard_risk IS NULL
    """, conn)
    log.info(f"処理対象: {len(df_trans)}件")

    batch      = []
    batch_size = 500

    for i, row in df_trans.iterrows():
        lon, lat = row["longitude"], row["latitude"]
        min_dist = find_nearest(lon, lat, grid)

        # 距離が無限大（近くにハザード地点なし）の場合はなし
        if math.isinf(min_dist):
            risk     = "なし"
            min_dist = 99999.0
        elif min_dist <= 100:
            risk = "高"
        elif min_dist <= 300:
            risk = "中"
        elif min_dist <= 500:
            risk = "低"
        else:
            risk = "なし"

        batch.append((round(min_dist), risk, row["id"]))

        if len(batch) >= batch_size:
            conn.executemany("""
                UPDATE csv_transactions
                SET hazard_dist = ?, hazard_risk = ?
                WHERE id = ?
            """, batch)
            conn.commit()
            log.info(f"進捗: {i+1}件完了")
            batch = []

    if batch:
        conn.executemany("""
            UPDATE csv_transactions
            SET hazard_dist = ?, hazard_risk = ?
            WHERE id = ?
        """, batch)
        conn.commit()

    # サマリー
    df_result = pd.read_sql("""
        SELECT
            hazard_risk                         AS リスク,
            COUNT(*)                            AS 件数,
            ROUND(AVG(trade_price) / 10000, 1)  AS 平均価格_万円
        FROM csv_transactions
        WHERE hazard_risk IS NOT NULL
          AND trade_price IS NOT NULL
        GROUP BY hazard_risk
        ORDER BY CASE hazard_risk
            WHEN '高' THEN 1 WHEN '中' THEN 2
            WHEN '低' THEN 3 ELSE 4 END
    """, conn)

    print("\n【浸水リスク別 取引サマリー】")
    print(df_result.to_string(index=False))

    df_area = pd.read_sql("""
        SELECT
            city_name AS 市区町村,
            SUM(CASE WHEN hazard_risk='高' THEN 1 ELSE 0 END) AS 高リスク,
            SUM(CASE WHEN hazard_risk='中' THEN 1 ELSE 0 END) AS 中リスク,
            SUM(CASE WHEN hazard_risk='低' THEN 1 ELSE 0 END) AS 低リスク,
            SUM(CASE WHEN hazard_risk='なし' THEN 1 ELSE 0 END) AS なし,
            COUNT(*) AS 総件数
        FROM csv_transactions
        WHERE hazard_risk IS NOT NULL
        GROUP BY city_name
        ORDER BY 高リスク DESC
        LIMIT 15
    """, conn)

    print("\n【市区町村別 浸水リスク分布（上位15）】")
    print(df_area.to_string(index=False))

    conn.close()
    log.info("空間結合③完了！")


if __name__ == "__main__":
    main()
