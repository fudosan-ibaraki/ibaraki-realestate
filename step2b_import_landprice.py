"""
茨城県 不動産価格分析ツール - Step 2b（改訂版）
地価公示データ（2026年GMLzip）から2020〜2026年分を展開してSQLiteに取り込む

【使い方】
1. L01-26_08_GML.zip を同じフォルダに置く
2. python step2b_import_landprice.py を実行する
"""

import sqlite3
import json
import zipfile
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

DB_PATH  = Path("ibaraki_realestate.db")
ZIP_FILE = "L01-26_08_GML.zip"

YEAR_COLUMNS = {
    2020: "L01_093",
    2021: "L01_094",
    2022: "L01_095",
    2023: "L01_096",
    2024: "L01_097",
    2025: "L01_098",
    2026: "L01_008",
}
TARGET_YEARS = list(range(2020, 2027))


def init_db(conn):
    conn.executescript("""
        DROP TABLE IF EXISTS land_prices;
        CREATE TABLE IF NOT EXISTS land_prices (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            year                INTEGER,
            city_code           TEXT,
            city_name           TEXT,
            address             TEXT,
            land_price          INTEGER,
            use_type            TEXT,
            station_distance    REAL,
            city_planning       TEXT,
            building_coverage   REAL,
            floor_area_ratio    REAL,
            area_description    TEXT,
            longitude           REAL,
            latitude            REAL,
            source_file         TEXT,
            imported_at         TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_lp_year  ON land_prices(year);
        CREATE INDEX IF NOT EXISTS idx_lp_city  ON land_prices(city_code);
        CREATE INDEX IF NOT EXISTS idx_lp_use   ON land_prices(use_type);
        CREATE INDEX IF NOT EXISTS idx_lp_price ON land_prices(land_price);
    """)
    conn.commit()
    log.info("land_prices テーブル初期化完了")


def to_int(val):
    try:
        return int(val) if val not in (None, "", "_", False, "false") else None
    except (ValueError, TypeError):
        return None

def to_float(val):
    try:
        return float(val) if val not in (None, "", "_", False, "false") else None
    except (ValueError, TypeError):
        return None


def parse_geojson(geojson_data, source_file):
    data    = json.loads(geojson_data)
    records = []
    for feature in data.get("features", []):
        props = feature.get("properties", {})
        geom  = feature.get("geometry", {})
        lon, lat = None, None
        if geom and geom.get("type") == "Point":
            coords = geom.get("coordinates", [])
            if len(coords) >= 2:
                lon, lat = coords[0], coords[1]
        base = {
            "city_code":         str(props.get("L01_001", "")).strip(),
            "city_name":         str(props.get("L01_024", "")).strip(),
            "address":           str(props.get("L01_025", "")).strip(),
            "use_type":          str(props.get("L01_028", "")).strip(),
            "station_distance":  to_float(props.get("L01_050")),
            "city_planning":     str(props.get("L01_051", "")).strip(),
            "building_coverage": to_float(props.get("L01_057")),
            "floor_area_ratio":  to_float(props.get("L01_058")),
            "area_description":  str(props.get("L01_047", "")).strip(),
            "longitude":         lon,
            "latitude":          lat,
            "source_file":       source_file,
        }
        for year in TARGET_YEARS:
            col        = YEAR_COLUMNS.get(year)
            land_price = to_int(props.get(col)) if col else None
            if not land_price or land_price <= 0:
                continue
            records.append({**base, "year": year, "land_price": land_price})
    return records


def save_records(conn, records):
    if not records:
        return 0
    columns      = list(records[0].keys())
    placeholders = ",".join(["?" for _ in columns])
    sql          = f"INSERT INTO land_prices ({','.join(columns)}) VALUES ({placeholders})"
    conn.executemany(sql, [tuple(r[c] for c in columns) for r in records])
    conn.commit()
    return len(records)


def main():
    conn     = sqlite3.connect(DB_PATH)
    init_db(conn)
    zip_path = Path(ZIP_FILE)
    if not zip_path.exists():
        log.error(f"ファイルが見つかりません: {ZIP_FILE}")
        return
    log.info(f"処理中: {ZIP_FILE}")
    with zipfile.ZipFile(zip_path, "r") as zf:
        geojson_name = next((n for n in zf.namelist() if n.endswith(".geojson")), None)
        if not geojson_name:
            log.error("GeoJSONファイルが見つかりません")
            return
        geojson_data = zf.read(geojson_name).decode("utf-8")
        records      = parse_geojson(geojson_data, ZIP_FILE)
        saved        = save_records(conn, records)
        log.info(f"→ {saved}件 保存完了")

    import pandas as pd
    df = pd.read_sql("""
        SELECT year AS 年, COUNT(*) AS 地点数,
               ROUND(AVG(land_price)) AS 平均地価_円m2,
               ROUND(MIN(land_price)) AS 最安値_円m2,
               ROUND(MAX(land_price)) AS 最高値_円m2
        FROM land_prices WHERE use_type LIKE '%住宅%'
        GROUP BY year ORDER BY year
    """, conn)
    print("\n【地価公示 年別サマリー（住宅地）】")
    print(df.to_string(index=False))

    df2 = pd.read_sql("""
        SELECT city_name AS 市区町村, ROUND(AVG(land_price)) AS 平均地価_円m2, COUNT(*) AS 地点数
        FROM land_prices WHERE use_type LIKE '%住宅%' AND year = 2026
        GROUP BY city_name ORDER BY 平均地価_円m2 DESC LIMIT 15
    """, conn)
    print("\n【2026年 市区町村別 平均地価（住宅地・上位15）】")
    print(df2.to_string(index=False))
    conn.close()
    log.info("完了！")

if __name__ == "__main__":
    main()
