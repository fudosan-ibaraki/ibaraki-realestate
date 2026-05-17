"""
茨城県 不動産価格分析ツール - Step 1
国土交通省 不動産取引価格情報APIからデータを取得し、SQLiteに保存する

【APIについて】
URL: https://www.land.mlit.go.jp/webland/api.html
パラメータ:
  - type: 取引種別 (01=土地, 02=土地と建物, 03=中古マンション等, 07=農地, 08=林地)
  - city: 市区町村コード (茨城県は08000番台)
  - from: 取引時期FROM (例: 20151 = 2015年第1四半期)
  - to:   取引時期TO   (例: 20244 = 2024年第4四半期)
"""

import requests
import sqlite3
import pandas as pd
import time
import logging
from pathlib import Path
from datetime import datetime

# ── ログ設定 ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── 定数 ─────────────────────────────────────────────────
API_BASE_URL = "https://www.land.mlit.go.jp/webland/api/TradeListSearch"
DB_PATH = Path("ibaraki_realestate.db")

# 茨城県の市区町村コード（主要都市）
# 全コードは https://nlftp.mlit.go.jp/ksj/gml/codelist/AdminiBoundary_CD.xlsx を参照
IBARAKI_CITIES = {
    "08201": "水戸市",
    "08202": "日立市",
    "08203": "土浦市",
    "08204": "古河市",
    "08205": "石岡市",
    "08207": "結城市",
    "08208": "龍ヶ崎市",
    "08210": "下妻市",
    "08211": "常総市",
    "08212": "常陸太田市",
    "08214": "高萩市",
    "08215": "北茨城市",
    "08216": "笠間市",
    "08217": "取手市",
    "08219": "牛久市",
    "08220": "つくば市",
    "08221": "ひたちなか市",
    "08222": "鹿嶋市",
    "08223": "潮来市",
    "08224": "守谷市",
    "08225": "常陸大宮市",
    "08226": "那珂市",
    "08227": "筑西市",
    "08228": "坂東市",
    "08229": "稲敷市",
    "08230": "かすみがうら市",
    "08231": "桜川市",
    "08232": "神栖市",
    "08233": "行方市",
    "08234": "鉾田市",
    "08235": "つくばみらい市",
    "08236": "小美玉市",
}

# 取引種別
TRADE_TYPES = {
    "01": "土地",
    "02": "土地と建物",
    "03": "中古マンション等",
}

# 取得期間（四半期）例: 2020年Q1〜2024年Q4
FROM_QUARTER = "20201"
TO_QUARTER   = "20252"


# ── SQLite セットアップ ───────────────────────────────────
def init_db(db_path: Path) -> sqlite3.Connection:
    """DBとテーブルを初期化する"""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")  # 書き込みパフォーマンス向上
    conn.execute("PRAGMA foreign_keys=ON")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS transactions (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            -- 識別情報
            city_code           TEXT NOT NULL,
            city_name           TEXT NOT NULL,
            trade_type_code     TEXT NOT NULL,
            trade_type_name     TEXT NOT NULL,
            -- 取引情報
            trade_price         INTEGER,        -- 取引価格（円）
            price_per_unit      REAL,           -- 坪単価または㎡単価（円）
            area                REAL,           -- 面積（㎡）
            floor_plan          TEXT,           -- 間取り
            building_year       INTEGER,        -- 建築年
            building_structure  TEXT,           -- 建物構造
            -- 立地情報
            prefecture          TEXT,
            district            TEXT,           -- 地区名
            nearest_station     TEXT,           -- 最寄駅
            minutes_to_station  INTEGER,        -- 駅徒歩分
            land_shape          TEXT,           -- 土地の形状
            frontage            REAL,           -- 間口（m）
            -- 用途・法規
            purpose             TEXT,           -- 取引の事情等
            city_planning       TEXT,           -- 都市計画
            building_coverage   REAL,           -- 建蔽率（%）
            floor_area_ratio    REAL,           -- 容積率（%）
            -- 時期
            period              TEXT,           -- 取引時期（例: 2024年第1四半期）
            year                INTEGER,
            quarter             INTEGER,
            -- メタ
            fetched_at          TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE INDEX IF NOT EXISTS idx_city      ON transactions(city_code);
        CREATE INDEX IF NOT EXISTS idx_period    ON transactions(year, quarter);
        CREATE INDEX IF NOT EXISTS idx_type      ON transactions(trade_type_code);
        CREATE INDEX IF NOT EXISTS idx_price     ON transactions(trade_price);

        -- 取得ログ（再実行時のスキップ用）
        CREATE TABLE IF NOT EXISTS fetch_log (
            city_code       TEXT NOT NULL,
            trade_type_code TEXT NOT NULL,
            from_quarter    TEXT NOT NULL,
            to_quarter      TEXT NOT NULL,
            fetched_at      TEXT DEFAULT (datetime('now','localtime')),
            record_count    INTEGER,
            PRIMARY KEY (city_code, trade_type_code, from_quarter, to_quarter)
        );
    """)
    conn.commit()
    log.info(f"DB初期化完了: {db_path.resolve()}")
    return conn


# ── APIフェッチ ───────────────────────────────────────────
def fetch_transactions(
    city_code: str,
    trade_type: str,
    from_q: str,
    to_q: str,
    retry: int = 3,
) -> list[dict]:
    """国交省APIから取引データを取得する"""
    params = {
        "type": trade_type,
        "city": city_code,
        "from": from_q,
        "to":   to_q,
    }
    for attempt in range(retry):
        try:
            resp = requests.get(API_BASE_URL, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") == "OK":
                return data.get("data", [])
            else:
                log.warning(f"API status={data.get('status')} city={city_code} type={trade_type}")
                return []
        except requests.RequestException as e:
            log.warning(f"リトライ {attempt+1}/{retry}: {e}")
            time.sleep(2 ** attempt)  # 指数バックオフ
    return []


# ── データ変換 ────────────────────────────────────────────
def parse_record(row: dict, city_code: str, city_name: str, trade_type_code: str) -> dict:
    """APIレスポンスの1件をDBレコード形式に変換する"""

    def to_int(val):
        try:
            return int(str(val).replace(",", "").replace("㎡以上", "").replace("戸", ""))
        except (ValueError, TypeError):
            return None

    def to_float(val):
        try:
            return float(str(val).replace(",", ""))
        except (ValueError, TypeError):
            return None

    # 取引時期のパース（例: "2024年第1四半期" → year=2024, quarter=1）
    period = row.get("Period", "")
    year, quarter = None, None
    if "年第" in period:
        try:
            parts = period.replace("年第", " ").replace("四半期", "").split()
            year    = int(parts[0])
            quarter = int(parts[1])
        except (IndexError, ValueError):
            pass

    return {
        "city_code":          city_code,
        "city_name":          city_name,
        "trade_type_code":    trade_type_code,
        "trade_type_name":    TRADE_TYPES.get(trade_type_code, trade_type_code),
        "trade_price":        to_int(row.get("TradePrice")),
        "price_per_unit":     to_float(row.get("UnitPrice")),
        "area":               to_float(row.get("Area")),
        "floor_plan":         row.get("FloorPlan"),
        "building_year":      to_int(row.get("BuildingYear")),
        "building_structure": row.get("Structure"),
        "prefecture":         row.get("Prefecture"),
        "district":           row.get("DistrictName"),
        "nearest_station":    row.get("NearestStation"),
        "minutes_to_station": to_int(row.get("TimeToNearestStation")),
        "land_shape":         row.get("LandShape"),
        "frontage":           to_float(row.get("Frontage")),
        "purpose":            row.get("Purpose"),
        "city_planning":      row.get("CityPlanning"),
        "building_coverage":  to_float(row.get("BuildingCoverageRatio")),
        "floor_area_ratio":   to_float(row.get("FloorAreaRatio")),
        "period":             period,
        "year":               year,
        "quarter":            quarter,
    }


# ── 保存 ─────────────────────────────────────────────────
def save_to_db(conn: sqlite3.Connection, records: list[dict]) -> int:
    """レコードをDBに一括挿入する（重複は無視）"""
    if not records:
        return 0
    df = pd.DataFrame(records)
    df.to_sql("transactions", conn, if_exists="append", index=False, method="multi")
    return len(records)


def already_fetched(conn: sqlite3.Connection, city_code: str, trade_type: str) -> bool:
    """同じ条件で既に取得済みか確認する"""
    cur = conn.execute(
        "SELECT 1 FROM fetch_log WHERE city_code=? AND trade_type_code=? AND from_quarter=? AND to_quarter=?",
        (city_code, trade_type, FROM_QUARTER, TO_QUARTER),
    )
    return cur.fetchone() is not None


def log_fetch(conn: sqlite3.Connection, city_code: str, trade_type: str, count: int):
    conn.execute(
        "INSERT OR REPLACE INTO fetch_log(city_code, trade_type_code, from_quarter, to_quarter, record_count) VALUES(?,?,?,?,?)",
        (city_code, trade_type, FROM_QUARTER, TO_QUARTER, count),
    )
    conn.commit()


# ── メイン ────────────────────────────────────────────────
def main():
    conn = init_db(DB_PATH)
    total_saved = 0

    cities     = list(IBARAKI_CITIES.items())   # [(code, name), ...]
    types      = list(TRADE_TYPES.keys())        # ["01", "02", "03"]
    total_jobs = len(cities) * len(types)
    job_num    = 0

    for city_code, city_name in cities:
        for trade_type in types:
            job_num += 1
            label = f"[{job_num}/{total_jobs}] {city_name}({city_code}) 種別={TRADE_TYPES[trade_type]}"

            # 取得済みならスキップ
            if already_fetched(conn, city_code, trade_type):
                log.info(f"スキップ（取得済み）: {label}")
                continue

            log.info(f"取得中: {label}")
            raw_data = fetch_transactions(city_code, trade_type, FROM_QUARTER, TO_QUARTER)

            if raw_data:
                records = [parse_record(r, city_code, city_name, trade_type) for r in raw_data]
                saved   = save_to_db(conn, records)
                total_saved += saved
                log.info(f"  → {saved}件 保存")
            else:
                log.info(f"  → データなし")
                saved = 0

            log_fetch(conn, city_code, trade_type, saved)
            time.sleep(0.5)  # APIへの負荷軽減（礼儀）

    # サマリー
    cur  = conn.execute("SELECT COUNT(*) FROM transactions")
    rows = cur.fetchone()[0]
    log.info("=" * 50)
    log.info(f"完了！今回追加: {total_saved}件 / DB合計: {rows}件")
    log.info(f"DBファイル: {DB_PATH.resolve()}")

    # 簡易プレビュー
    df = pd.read_sql("""
        SELECT city_name, trade_type_name, COUNT(*) as count,
               ROUND(AVG(trade_price)/10000) as avg_price_man,
               MIN(year) as from_year, MAX(year) as to_year
        FROM transactions
        WHERE trade_price IS NOT NULL
        GROUP BY city_name, trade_type_name
        ORDER BY city_name, trade_type_code
    """, conn)
    print("\n【取得データ プレビュー】")
    print(df.to_string(index=False))

    conn.close()


if __name__ == "__main__":
    main()
