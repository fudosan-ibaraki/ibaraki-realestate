"""
茨城県 不動産価格分析ツール - Step 2f
OpenStreetMapから施設データを取得してSQLiteに取り込む

【使い方】
python step2f_import_facilities.py

【取得する施設】
- コンビニ
- スーパー
- 病院・クリニック
- 学校
- 銀行・ATM

【ライセンス】
OpenStreetMap contributors (ODbL)
商用利用時は「© OpenStreetMap contributors」の表示が必要
"""

import sqlite3
import logging
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

DB_PATH = Path("ibaraki_realestate.db")

# 取得する施設の定義
FACILITY_TAGS = [
    {
        "category": "コンビニ",
        "tags": {"shop": "convenience"},
    },
    {
        "category": "スーパー",
        "tags": {"shop": "supermarket"},
    },
    {
        "category": "病院",
        "tags": {"amenity": "hospital"},
    },
    {
        "category": "クリニック",
        "tags": {"amenity": "clinic"},
    },
    {
        "category": "小学校",
        "tags": {"amenity": "school"},
    },
    {
        "category": "銀行",
        "tags": {"amenity": "bank"},
    },
    {
        "category": "ATM",
        "tags": {"amenity": "atm"},
    },
]


def init_db(conn):
    conn.executescript("""
        DROP TABLE IF EXISTS facilities;
        CREATE TABLE IF NOT EXISTS facilities (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT,       -- 施設名
            category    TEXT,       -- カテゴリ（コンビニ・スーパーなど）
            longitude   REAL,       -- 経度
            latitude    REAL,       -- 緯度
            imported_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_fac_cat ON facilities(category);
        CREATE INDEX IF NOT EXISTS idx_fac_loc ON facilities(latitude, longitude);
    """)
    conn.commit()
    log.info("facilities テーブル初期化完了")


def main():
    try:
        import osmnx as ox
    except ImportError:
        log.error("osmnxがインストールされていません: python -m pip install osmnx")
        return

    conn = sqlite3.connect(DB_PATH)
    init_db(conn)
    total = 0

    for facility in FACILITY_TAGS:
        category = facility["category"]
        tags     = facility["tags"]

        log.info(f"取得中: {category}")
        try:
            gdf = ox.features_from_place("Ibaraki, Japan", tags=tags)

            if gdf is None or len(gdf) == 0:
                log.info(f"  → データなし")
                continue

            records = []
            for _, row in gdf.iterrows():
                geom = row.geometry
                # 重心座標を取得
                try:
                    lon = geom.centroid.x
                    lat = geom.centroid.y
                except Exception:
                    continue

                name = row.get("name", "") or ""
                records.append({
                    "name":      str(name).strip(),
                    "category":  category,
                    "longitude": round(lon, 6),
                    "latitude":  round(lat, 6),
                })

            if records:
                columns      = list(records[0].keys())
                placeholders = ",".join(["?" for _ in columns])
                conn.executemany(
                    f"INSERT INTO facilities ({','.join(columns)}) VALUES ({placeholders})",
                    [tuple(r[c] for c in columns) for r in records]
                )
                conn.commit()
                total += len(records)
                log.info(f"  → {len(records)}件 保存完了")

            time.sleep(1)  # APIへの負荷軽減

        except Exception as e:
            log.warning(f"  → エラー: {e}")
            continue

    log.info(f"完了！合計: {total}件")

    import pandas as pd
    df = pd.read_sql("""
        SELECT category AS カテゴリ, COUNT(*) AS 件数
        FROM facilities
        GROUP BY category
        ORDER BY 件数 DESC
    """, conn)

    print("\n【施設データ サマリー】")
    print(df.to_string(index=False))
    conn.close()


if __name__ == "__main__":
    main()
