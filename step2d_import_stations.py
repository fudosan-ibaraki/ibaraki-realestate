"""
茨城県 不動産価格分析ツール - Step 2d
駅データ（国土数値情報N02）をSQLiteに取り込む

【使い方】
1. N02-24_GML.zip を同じフォルダに置く
2. python step2d_import_stations.py を実行する
"""

import sqlite3
import json
import zipfile
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

DB_PATH  = Path("ibaraki_realestate.db")
ZIP_FILE = "N02-24_GML.zip"

# 茨城県の緯度経度範囲
LAT_MIN, LAT_MAX = 35.7, 36.9
LON_MIN, LON_MAX = 139.7, 140.9


def init_db(conn):
    conn.executescript("""
        DROP TABLE IF EXISTS stations;
        CREATE TABLE IF NOT EXISTS stations (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            station     TEXT,       -- 駅名
            line        TEXT,       -- 路線名
            company     TEXT,       -- 運営会社
            longitude   REAL,       -- 経度
            latitude    REAL,       -- 緯度
            imported_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_st_name ON stations(station);
        CREATE INDEX IF NOT EXISTS idx_st_loc  ON stations(latitude, longitude);
    """)
    conn.commit()
    log.info("stations テーブル初期化完了")


def main():
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    zip_path = Path(ZIP_FILE)
    if not zip_path.exists():
        log.error(f"ファイルが見つかりません: {ZIP_FILE}")
        return

    log.info(f"処理中: {ZIP_FILE}")
    with zipfile.ZipFile(zip_path, "r") as zf:
        station_file = next(
            (n for n in zf.namelist() if "Station" in n and n.endswith(".geojson")), None
        )
        if not station_file:
            log.error("駅GeoJSONが見つかりません")
            return

        data    = json.loads(zf.read(station_file).decode("utf-8"))
        records = []
        seen    = set()

        for feature in data["features"]:
            props  = feature["properties"]
            coords = feature["geometry"]["coordinates"]

            # LineStringの中心点を計算
            lons = [c[0] for c in coords]
            lats = [c[1] for c in coords]
            lon  = sum(lons) / len(lons)
            lat  = sum(lats) / len(lats)

            # 茨城県の範囲外は除外
            if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
                continue

            station = props.get("N02_005", "").strip()
            line    = props.get("N02_003", "").strip()
            company = props.get("N02_004", "").strip()

            # 重複除外（同じ駅名+路線名）
            key = (station, line)
            if key in seen:
                continue
            seen.add(key)

            records.append({
                "station":   station,
                "line":      line,
                "company":   company,
                "longitude": round(lon, 6),
                "latitude":  round(lat, 6),
            })

    if not records:
        log.error("茨城県内の駅が見つかりませんでした")
        return

    columns      = list(records[0].keys())
    placeholders = ",".join(["?" for _ in columns])
    conn.executemany(
        f"INSERT INTO stations ({','.join(columns)}) VALUES ({placeholders})",
        [tuple(r[c] for c in columns) for r in records]
    )
    conn.commit()
    log.info(f"→ {len(records)}駅 保存完了")

    import pandas as pd
    df = pd.read_sql("""
        SELECT line AS 路線, company AS 運営会社, COUNT(*) AS 駅数
        FROM stations
        GROUP BY line, company
        ORDER BY 駅数 DESC
    """, conn)

    print("\n【茨城県内 路線別駅数】")
    print(df.to_string(index=False))
    conn.close()
    log.info("完了！")


if __name__ == "__main__":
    main()
