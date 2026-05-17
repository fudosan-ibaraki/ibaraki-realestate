"""
茨城県 不動産価格分析ツール - Step 3b
空間結合①: 取引データ × 最寄り駅

【使い方】
python step3b_spatial_join_station.py

【処理内容】
取引データの座標から最も近い駅を特定し、
駅名・路線名・距離(m)をDBに保存する
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
    """2点間の距離をメートルで計算する（ハーバーサイン公式）"""
    R = 6371000  # 地球の半径（m）
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi  = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def init_db(conn):
    """最寄り駅の列を追加する"""
    # 既に列があればスキップ
    cur = conn.execute("PRAGMA table_info(csv_transactions)")
    cols = [row[1] for row in cur.fetchall()]

    if "nearest_station_name" not in cols:
        conn.execute("ALTER TABLE csv_transactions ADD COLUMN nearest_station_name TEXT")
    if "nearest_station_line" not in cols:
        conn.execute("ALTER TABLE csv_transactions ADD COLUMN nearest_station_line TEXT")
    if "nearest_station_dist" not in cols:
        conn.execute("ALTER TABLE csv_transactions ADD COLUMN nearest_station_dist REAL")
    conn.commit()
    log.info("列追加完了")


def main():
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    # 駅データを全部読み込む
    df_stations = pd.read_sql("""
        SELECT station, line, longitude, latitude
        FROM stations
        WHERE longitude IS NOT NULL AND latitude IS NOT NULL
    """, conn)
    log.info(f"駅数: {len(df_stations)}")

    stations = df_stations.to_dict("records")

    # 座標がある取引データを取得
    df_trans = pd.read_sql("""
        SELECT id, longitude, latitude
        FROM csv_transactions
        WHERE longitude IS NOT NULL
          AND latitude IS NOT NULL
          AND nearest_station_name IS NULL
    """, conn)
    log.info(f"処理対象: {len(df_trans)}件")

    # バッチ処理
    batch     = []
    batch_size = 500

    for i, row in df_trans.iterrows():
        lon, lat = row["longitude"], row["latitude"]

        # 全駅との距離を計算して最短を見つける
        min_dist    = float("inf")
        nearest     = None

        for st in stations:
            dist = haversine(lon, lat, st["longitude"], st["latitude"])
            if dist < min_dist:
                min_dist = dist
                nearest  = st

        if nearest:
            batch.append((
                nearest["station"],
                nearest["line"],
                round(min_dist),
                row["id"]
            ))

        if len(batch) >= batch_size:
            conn.executemany("""
                UPDATE csv_transactions
                SET nearest_station_name = ?,
                    nearest_station_line = ?,
                    nearest_station_dist = ?
                WHERE id = ?
            """, batch)
            conn.commit()
            log.info(f"進捗: {i+1}件完了")
            batch = []

    # 残りを保存
    if batch:
        conn.executemany("""
            UPDATE csv_transactions
            SET nearest_station_name = ?,
                nearest_station_line = ?,
                nearest_station_dist = ?
            WHERE id = ?
        """, batch)
        conn.commit()

    log.info("完了！結果を確認中...")

    # プレビュー
    df_result = pd.read_sql("""
        SELECT
            city_name               AS 市区町村,
            nearest_station_name    AS 最寄り駅,
            nearest_station_line    AS 路線,
            ROUND(AVG(nearest_station_dist)) AS 平均距離_m,
            ROUND(AVG(trade_price)/10000)    AS 平均価格_万円,
            COUNT(*)                AS 件数
        FROM csv_transactions
        WHERE nearest_station_name IS NOT NULL
          AND trade_price IS NOT NULL
        GROUP BY city_name, nearest_station_name
        HAVING 件数 >= 10
        ORDER BY 平均価格_万円 DESC
        LIMIT 20
    """, conn)

    print("\n【最寄り駅別 平均価格（上位20件）】")
    print(df_result.to_string(index=False))

    conn.close()
    log.info("空間結合①完了！")


if __name__ == "__main__":
    main()
