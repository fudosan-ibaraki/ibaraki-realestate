"""
茨城県 不動産価格分析ツール - Step 3e
空間結合④: 取引データ × 施設データ

【処理内容】
取引物件の座標から半径500m・1km以内の施設数をカウントして
利便性スコアを計算する
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
GRID_SIZE = 0.01  # 約1km

# 半径（m）
RADIUS_500  = 500
RADIUS_1000 = 1000


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
        gx = int(r["longitude"] / GRID_SIZE)
        gy = int(r["latitude"]  / GRID_SIZE)
        grid[(gx, gy)].append(r)
    return grid


def count_nearby(lon, lat, grid, radius, search_range=2):
    """指定半径内の施設をカテゴリ別にカウントする"""
    gx = int(lon / GRID_SIZE)
    gy = int(lat / GRID_SIZE)
    counts = defaultdict(int)
    for dx in range(-search_range, search_range + 1):
        for dy in range(-search_range, search_range + 1):
            for r in grid.get((gx + dx, gy + dy), []):
                dist = haversine(lon, lat, r["longitude"], r["latitude"])
                if dist <= radius:
                    counts[r["category"]] += 1
    return counts


def init_db(conn):
    cur  = conn.execute("PRAGMA table_info(csv_transactions)")
    cols = [row[1] for row in cur.fetchall()]
    new_cols = [
        ("conv_500m",       "INTEGER"),  # 500m以内コンビニ数
        ("super_500m",      "INTEGER"),  # 500m以内スーパー数
        ("hospital_1km",    "INTEGER"),  # 1km以内病院数
        ("school_1km",      "INTEGER"),  # 1km以内学校数
        ("bank_500m",       "INTEGER"),  # 500m以内銀行数
        ("convenience_score","REAL"),    # 利便性スコア
    ]
    for col, dtype in new_cols:
        if col not in cols:
            conn.execute(f"ALTER TABLE csv_transactions ADD COLUMN {col} {dtype}")
    conn.commit()
    log.info("列追加完了")


def main():
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    # 施設データを読み込む
    df_fac = pd.read_sql("""
        SELECT name, category, longitude, latitude
        FROM facilities
        WHERE longitude IS NOT NULL AND latitude IS NOT NULL
    """, conn)
    log.info(f"施設数: {len(df_fac)}")

    grid = build_grid(df_fac.to_dict("records"))
    log.info(f"グリッド数: {len(grid)}")

    # 取引データを取得
    df_trans = pd.read_sql("""
        SELECT id, longitude, latitude
        FROM csv_transactions
        WHERE longitude IS NOT NULL
          AND latitude IS NOT NULL
          AND convenience_score IS NULL
    """, conn)
    log.info(f"処理対象: {len(df_trans)}件")

    batch      = []
    batch_size = 500

    for i, row in df_trans.iterrows():
        lon, lat = row["longitude"], row["latitude"]

        # 500m以内の施設数
        counts_500  = count_nearby(lon, lat, grid, RADIUS_500)
        # 1km以内の施設数
        counts_1000 = count_nearby(lon, lat, grid, RADIUS_1000)

        conv    = counts_500.get("コンビニ", 0)
        sup     = counts_500.get("スーパー", 0)
        hosp    = counts_1000.get("病院", 0) + counts_1000.get("クリニック", 0)
        school  = counts_1000.get("小学校", 0)
        bank    = counts_500.get("銀行", 0) + counts_500.get("ATM", 0)

        # 利便性スコア（各施設に重みをつけて100点満点）
        score = min(100, (
            conv   * 10 +   # コンビニ: 1軒10点
            sup    * 15 +   # スーパー: 1軒15点
            hosp   * 10 +   # 病院: 1軒10点
            school *  5 +   # 学校: 1軒5点
            bank   *  5     # 銀行: 1軒5点
        ))

        batch.append((conv, sup, hosp, school, bank, score, row["id"]))

        if len(batch) >= batch_size:
            conn.executemany("""
                UPDATE csv_transactions
                SET conv_500m        = ?,
                    super_500m       = ?,
                    hospital_1km     = ?,
                    school_1km       = ?,
                    bank_500m        = ?,
                    convenience_score = ?
                WHERE id = ?
            """, batch)
            conn.commit()
            log.info(f"進捗: {i+1}件完了")
            batch = []

    if batch:
        conn.executemany("""
            UPDATE csv_transactions
            SET conv_500m        = ?,
                super_500m       = ?,
                hospital_1km     = ?,
                school_1km       = ?,
                bank_500m        = ?,
                convenience_score = ?
            WHERE id = ?
        """, batch)
        conn.commit()

    # サマリー
    df_result = pd.read_sql("""
        SELECT
            city_name                           AS 市区町村,
            ROUND(AVG(convenience_score), 1)    AS 平均利便性スコア,
            ROUND(AVG(conv_500m), 1)            AS 平均コンビニ数,
            ROUND(AVG(super_500m), 1)           AS 平均スーパー数,
            ROUND(AVG(hospital_1km), 1)         AS 平均病院数,
            COUNT(*)                            AS 件数
        FROM csv_transactions
        WHERE convenience_score IS NOT NULL
        GROUP BY city_name
        HAVING 件数 >= 10
        ORDER BY 平均利便性スコア DESC
        LIMIT 15
    """, conn)

    print("\n【市区町村別 利便性スコア（上位15）】")
    print(df_result.to_string(index=False))

    conn.close()
    log.info("空間結合④完了！")


if __name__ == "__main__":
    main()
