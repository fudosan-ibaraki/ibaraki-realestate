"""
茨城県 不動産価格分析ツール - Step 3a
Google Maps Geocoding APIで地区名を座標に変換する

【使い方】
1. GOOGLE_API_KEY にAPIキーを設定する
2. python step3a_geocoding.py を実行する

【注意】
- 1,825地区分のリクエストで約$9（月$200無料枠内）
- 途中で止まっても再実行すると続きから再開します
"""

import sqlite3
import time
import logging
import requests
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

DB_PATH = Path("ibaraki_realestate.db")

# ★ここにAPIキーを貼り付けてください
GOOGLE_API_KEY = "AIzaSyD0K0dMXPrWwb7twCm7KiVmIl1dEi_pj_U"

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"


def init_db(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS geocode_cache (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            city_name   TEXT NOT NULL,
            district    TEXT NOT NULL,
            longitude   REAL,
            latitude    REAL,
            status      TEXT DEFAULT 'ok',
            fetched_at  TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(city_name, district)
        );
        CREATE INDEX IF NOT EXISTS idx_gc_city ON geocode_cache(city_name, district);
    """)
    conn.commit()
    log.info("geocode_cache テーブル初期化完了")


def geocode(city_name: str, district: str) -> tuple:
    """Google Maps Geocoding APIで座標を取得する"""
    queries = [
        f"茨城県{city_name}{district}",
        f"茨城県{city_name}",
    ]

    for query in queries:
        try:
            resp = requests.get(
                GEOCODE_URL,
                params={
                    "address": query,
                    "key":     GOOGLE_API_KEY,
                    "region":  "jp",
                    "language":"ja",
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

            if data["status"] == "OK":
                loc = data["results"][0]["geometry"]["location"]
                return loc["lng"], loc["lat"], "ok"
            elif data["status"] == "ZERO_RESULTS":
                continue
            else:
                log.warning(f"  APIエラー: {data['status']} ({query})")
                return None, None, "error"

        except Exception as e:
            log.warning(f"  エラー: {query} → {e}")
            time.sleep(1)
            continue

    return None, None, "not_found"


def already_cached(conn, city_name: str, district: str) -> bool:
    cur = conn.execute(
        "SELECT 1 FROM geocode_cache WHERE city_name=? AND district=?",
        (city_name, district)
    )
    return cur.fetchone() is not None


def main():
    if GOOGLE_API_KEY == "YOUR_API_KEY_HERE":
        log.error("APIキーを設定してください！GOOGLE_API_KEY = '...'")
        return

    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    import pandas as pd

    # 未処理の地区名を取得
    df = pd.read_sql("""
        SELECT DISTINCT city_name, district
        FROM csv_transactions
        python -c "
import sqlite3
conn = sqlite3.connect('ibaraki_realestate.db')
conn.execute('ALTER TABLE csv_transactions ADD COLUMN longitude REAL')
conn.execute('ALTER TABLE csv_transactions ADD COLUMN latitude REAL')
conn.commit()
print('列追加完了')
conn.close()
"
        WHERE district IS NOT NULL
          AND district != ''
          AND district != 'nan'
        ORDER BY city_name, district
    """, conn)

    log.info(f"総地区数: {len(df)}")

    cached = conn.execute("SELECT COUNT(*) FROM geocode_cache").fetchone()[0]
    log.info(f"取得済み: {cached}件 / 残り: {len(df) - cached}件")

    done = 0
    for _, row in df.iterrows():
        city_name = row["city_name"]
        district  = row["district"]

        if already_cached(conn, city_name, district):
            continue

        lon, lat, status = geocode(city_name, district)

        conn.execute(
            """INSERT OR IGNORE INTO geocode_cache
               (city_name, district, longitude, latitude, status)
               VALUES (?, ?, ?, ?, ?)""",
            (city_name, district, lon, lat, status)
        )
        conn.commit()
        done += 1

        if done % 100 == 0:
            log.info(f"進捗: {done}件完了")

        time.sleep(0.1)  # Google APIは速いので0.1秒でOK

    # 結果サマリー
    df_result = pd.read_sql("""
        SELECT status, COUNT(*) as 件数
        FROM geocode_cache
        GROUP BY status
    """, conn)

    print("\n【ジオコーディング結果】")
    print(df_result.to_string(index=False))

    # 取引データに座標を反映
    log.info("取引データに座標を反映中...")
    conn.execute("""
        UPDATE csv_transactions
        SET longitude = (
            SELECT gc.longitude FROM geocode_cache gc
            WHERE gc.city_name = csv_transactions.city_name
              AND gc.district  = csv_transactions.district
        ),
        latitude = (
            SELECT gc.latitude FROM geocode_cache gc
            WHERE gc.city_name = csv_transactions.city_name
              AND gc.district  = csv_transactions.district
        )
        WHERE district IS NOT NULL
    """)
    conn.commit()

    cur = conn.execute("""
        SELECT COUNT(*) FROM csv_transactions
        WHERE longitude IS NOT NULL AND latitude IS NOT NULL
    """)
    log.info(f"座標反映完了: {cur.fetchone()[0]}件")
    conn.close()
    log.info("完了！")


if __name__ == "__main__":
    main()
