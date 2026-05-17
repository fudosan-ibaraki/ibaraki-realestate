"""
茨城県 不動産価格分析ツール - Step 2e
ハザードマップ（洪水浸水想定区域）をSQLiteに取り込む

【使い方】
1. A31-21_08_GML.zip を同じフォルダに置く
2. python step2e_import_hazard.py を実行する

【浸水深ランクの意味】
1: 0.5m未満
2: 0.5〜1.0m
3: 1.0〜2.0m
4: 2.0〜3.0m
5: 3.0〜4.0m
6: 4.0〜5.0m
7: 5.0m以上
8: 10m以上（特に危険）
"""

import sqlite3
import json
import zipfile
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

DB_PATH  = Path("ibaraki_realestate.db")
ZIP_FILE = "A31-21_08_GML.zip"

# 浸水深ランクの説明
FLOOD_RANK = {
    1: "0.5m未満",
    2: "0.5〜1.0m",
    3: "1.0〜2.0m",
    4: "2.0〜3.0m",
    5: "3.0〜4.0m",
    6: "4.0〜5.0m",
    7: "5.0〜10.0m",
    8: "10m以上",
}


def init_db(conn):
    conn.executescript("""
        DROP TABLE IF EXISTS hazard_flood;
        CREATE TABLE IF NOT EXISTS hazard_flood (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            area_code       TEXT,       -- エリアコード
            river_name      TEXT,       -- 河川名
            flood_rank      INTEGER,    -- 浸水深ランク（1〜8）
            flood_depth     TEXT,       -- 浸水深の説明
            pref_name       TEXT,       -- 都道府県名
            centroid_lon    REAL,       -- ポリゴン重心経度
            centroid_lat    REAL,       -- ポリゴン重心緯度
            source_file     TEXT,
            imported_at     TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_hz_rank   ON hazard_flood(flood_rank);
        CREATE INDEX IF NOT EXISTS idx_hz_loc    ON hazard_flood(centroid_lat, centroid_lon);
        CREATE INDEX IF NOT EXISTS idx_hz_river  ON hazard_flood(river_name);
    """)
    conn.commit()
    log.info("hazard_flood テーブル初期化完了")


def calc_centroid(coordinates):
    """ポリゴンの重心を計算する"""
    try:
        # 外周リングの座標を使う
        ring = coordinates[0]
        lons = [c[0] for c in ring]
        lats = [c[1] for c in ring]
        return round(sum(lons)/len(lons), 6), round(sum(lats)/len(lats), 6)
    except (IndexError, TypeError):
        return None, None


def main():
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    zip_path = Path(ZIP_FILE)
    if not zip_path.exists():
        log.error(f"ファイルが見つかりません: {ZIP_FILE}")
        return

    log.info(f"処理中: {ZIP_FILE}")
    total = 0

    with zipfile.ZipFile(zip_path, "r") as zf:
        geojson_files = [n for n in zf.namelist() if n.endswith(".geojson")]
        log.info(f"GeoJSONファイル数: {len(geojson_files)}")

        for fname in geojson_files:
            data    = json.loads(zf.read(fname).decode("utf-8"))
            records = []

            for feature in data["features"]:
                props = feature["properties"]
                geom  = feature["geometry"]

                # 重心を計算
                if geom and geom.get("type") == "Polygon":
                    lon, lat = calc_centroid(geom["coordinates"])
                elif geom and geom.get("type") == "MultiPolygon":
                    # MultiPolygonは最初のポリゴンの重心
                    lon, lat = calc_centroid(geom["coordinates"][0])
                else:
                    lon, lat = None, None

                flood_rank = props.get("A31_103")
                records.append({
                    "area_code":    str(props.get("A31_101", "")).strip(),
                    "river_name":   str(props.get("A31_102", "")).strip(),
                    "flood_rank":   flood_rank,
                    "flood_depth":  FLOOD_RANK.get(flood_rank, "不明"),
                    "pref_name":    str(props.get("A31_104", "")).strip(),
                    "centroid_lon": lon,
                    "centroid_lat": lat,
                    "source_file":  fname,
                })

            if records:
                columns      = list(records[0].keys())
                placeholders = ",".join(["?" for _ in columns])
                conn.executemany(
                    f"INSERT INTO hazard_flood ({','.join(columns)}) VALUES ({placeholders})",
                    [tuple(r[c] for c in columns) for r in records]
                )
                conn.commit()
                total += len(records)

    log.info(f"→ {total}件 保存完了")

    import pandas as pd
    df = pd.read_sql("""
        SELECT
            river_name  AS 河川名,
            flood_depth AS 浸水深,
            COUNT(*)    AS ポリゴン数
        FROM hazard_flood
        GROUP BY river_name, flood_rank
        ORDER BY river_name, flood_rank DESC
    """, conn)

    print("\n【ハザードマップ データ サマリー】")
    print(df.to_string(index=False))
    conn.close()
    log.info("完了！")


if __name__ == "__main__":
    main()
