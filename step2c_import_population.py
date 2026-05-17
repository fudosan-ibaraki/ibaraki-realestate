"""
茨城県 不動産価格分析ツール - Step 2c
国勢調査2020年 人口データをSQLiteに取り込む

【使い方】
1. b01_01.xlsx を同じフォルダに置く
2. python step2c_import_population.py を実行する
"""

import sqlite3
import pandas as pd
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

DB_PATH   = Path("ibaraki_realestate.db")
XLSX_FILE = "b01_01.xlsx"


def init_db(conn):
    conn.executescript("""
        DROP TABLE IF EXISTS population;
        CREATE TABLE IF NOT EXISTS population (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            year              INTEGER,
            city_code         TEXT,
            city_name         TEXT,
            population        INTEGER,
            population_male   INTEGER,
            population_female INTEGER,
            population_2015   INTEGER,
            pop_change_5y     INTEGER,
            pop_change_rate   REAL,
            households        INTEGER,
            area_km2          REAL,
            pop_density       REAL,
            imported_at       TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_pop_city ON population(city_code);
        CREATE INDEX IF NOT EXISTS idx_pop_year ON population(year);
    """)
    conn.commit()
    log.info("population テーブル初期化完了")


def to_int(val):
    try:
        v = str(val).replace(",", "").strip()
        return int(float(v)) if v not in ("nan", "-", "") else None
    except (ValueError, TypeError):
        return None

def to_float(val):
    try:
        v = str(val).replace(",", "").strip()
        return float(v) if v not in ("nan", "-", "") else None
    except (ValueError, TypeError):
        return None


def main():
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    xlsx_path = Path(XLSX_FILE)
    if not xlsx_path.exists():
        log.error(f"ファイルが見つかりません: {XLSX_FILE}")
        return

    log.info(f"読み込み中: {XLSX_FILE}")
    df_raw = pd.read_excel(xlsx_path, header=None, skiprows=7, dtype=str)
    df_raw.columns = range(len(df_raw.columns))

    # 茨城県（08）だけ抽出
    df_ibaraki = df_raw[df_raw[4].astype(str).str.startswith("08_")].copy()
    log.info(f"茨城県のデータ: {len(df_ibaraki)}行")

    records = []
    for _, row in df_ibaraki.iterrows():
        city_code = str(row[5]).strip()
        city_name = str(row[6]).strip()

        # 都道府県全体の行は除外
        if city_code in ("08000", "nan", "") or city_name in ("nan", ""):
            continue

        # 地域名の番号プレフィックスを除去（例: "0123_水戸市" → "水戸市"）
        if "_" in city_name:
            city_name = city_name.split("_", 1)[1]

        record = {
            "year":             2020,
            "city_code":        city_code,
            "city_name":        city_name,
            "population":       to_int(row[7]),
            "population_male":  to_int(row[8]),
            "population_female":to_int(row[9]),
            "population_2015":  to_int(row[10]),
            "pop_change_5y":    to_int(row[11]),
            "pop_change_rate":  to_float(row[12]),
            "households":       to_int(row[16]),
            "area_km2":         to_float(row[14]),
            "pop_density":      to_float(row[15]),
        }
        if record["population"]:
            records.append(record)

    if not records:
        log.error("茨城県のデータが取得できませんでした")
        return

    df_out = pd.DataFrame(records)
    df_out.to_sql("population", conn, if_exists="append", index=False, chunksize=100)
    log.info(f"→ {len(df_out)}件 保存完了")

    # プレビュー
    df_preview = pd.read_sql("""
        SELECT
            city_name                   AS 市区町村,
            population                  AS 人口,
            pop_change_5y               AS 5年増減数,
            ROUND(pop_change_rate, 2)   AS 増減率_percent,
            ROUND(pop_density)          AS 人口密度_km2
        FROM population
        ORDER BY pop_change_rate DESC
        LIMIT 20
    """, conn)

    print("\n【人口データ プレビュー（増減率順・上位20）】")
    print(df_preview.to_string(index=False))
    conn.close()
    log.info("完了！")


if __name__ == "__main__":
    main()
