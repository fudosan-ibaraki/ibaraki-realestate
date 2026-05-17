"""
茨城県 不動産価格分析ツール - Step 2
ダウンロードしたCSVファイルをSQLiteに取り込む

【使い方】
1. ダウンロードしたCSVファイルをこのスクリプトと同じフォルダに入れる
2. 下の CSV_FILES にファイル名を設定する
3. python step2_import_csv.py を実行する
"""

import pandas as pd
import sqlite3
import logging
from pathlib import Path

# ── ログ設定 ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── 設定（ここを変更してください） ────────────────────────
DB_PATH = Path("ibaraki_realestate.db")

CSV_FILES = [
    # ファイル名,                              種別
    ("Ibaraki Prefecture_20201_20254.csv", "中古マンション"),
    ("Ibaraki Prefecture_20201_20204.csv", "宅地"),
    ("Ibaraki Prefecture_20211_20214.csv", "宅地"),
    ("Ibaraki Prefecture_20221_20224.csv", "宅地"),
    ("Ibaraki Prefecture_20231_20234.csv", "宅地"),
    ("Ibaraki Prefecture_20241_20254.csv", "宅地"),]


# ── 列名マッピング（CSVの列名 → DBの列名）────────────────
COLUMN_MAP = {
    "種類":           "trade_type",
    "価格情報区分":   "price_type",
    "市区町村コード": "city_code",
    "都道府県名":     "prefecture",
    "市区町村名":     "city_name",
    "地区名":         "district",
    "最寄駅：名称":   "nearest_station",
    "最寄駅：距離（分）": "minutes_to_station",
    "取引価格（総額）": "trade_price",
    "坪単価":         "price_per_tsubo",
    "間取り":         "floor_plan",
    "面積（㎡）":     "area",
    "土地の形状":     "land_shape",
    "間口":           "frontage",
    "延床面積（㎡）": "total_floor_area",
    "建築年":         "building_year",
    "建物の構造":     "building_structure",
    "用途":           "purpose",
    "今後の利用目的": "future_purpose",
    "都市計画":       "city_planning",
    "建ぺい率（％）": "building_coverage",
    "容積率（％）":   "floor_area_ratio",
    "取引時期":       "period",
    "改装":           "renovation",
    "取引の事情等":   "remarks",
}


# ── DB初期化 ──────────────────────────────────────────────
def init_db(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS csv_transactions (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_type          TEXT,
            price_type          TEXT,
            city_code           TEXT,
            prefecture          TEXT,
            city_name           TEXT,
            district            TEXT,
            nearest_station     TEXT,
            minutes_to_station  REAL,
            trade_price         INTEGER,
            price_per_tsubo     REAL,
            floor_plan          TEXT,
            area                REAL,
            land_shape          TEXT,
            frontage            REAL,
            total_floor_area    REAL,
            building_year       INTEGER,
            building_structure  TEXT,
            purpose             TEXT,
            future_purpose      TEXT,
            city_planning       TEXT,
            building_coverage   REAL,
            floor_area_ratio    REAL,
            period              TEXT,
            year                INTEGER,
            quarter             INTEGER,
            renovation          TEXT,
            remarks             TEXT,
            source_file         TEXT,
            imported_at         TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE INDEX IF NOT EXISTS idx_csv_city    ON csv_transactions(city_code);
        CREATE INDEX IF NOT EXISTS idx_csv_period  ON csv_transactions(year, quarter);
        CREATE INDEX IF NOT EXISTS idx_csv_type    ON csv_transactions(trade_type);
        CREATE INDEX IF NOT EXISTS idx_csv_price   ON csv_transactions(trade_price);
    """)
    conn.commit()
    log.info("DBテーブル初期化完了")


# ── データ変換 ────────────────────────────────────────────
def parse_period(period_str):
    """取引時期をyear・quarterに分解する（例: '2021年第3四半期' → 2021, 3）"""
    year, quarter = None, None
    if pd.isna(period_str):
        return year, quarter
    s = str(period_str)
    if "年第" in s:
        try:
            parts = s.replace("年第", " ").replace("四半期", "").split()
            year    = int(parts[0])
            quarter = int(parts[1])
        except (IndexError, ValueError):
            pass
    return year, quarter


def clean_df(df: pd.DataFrame, source_file: str) -> pd.DataFrame:
    """DataFrameを整形してDB挿入できる形にする"""

    # 列名を日本語→英語に変換（存在する列だけ）
    rename = {k: v for k, v in COLUMN_MAP.items() if k in df.columns}
    df = df.rename(columns=rename)

    # 取引時期をパース
    if "period" in df.columns:
        df[["year", "quarter"]] = df["period"].apply(
            lambda x: pd.Series(parse_period(x))
        )

    # 数値列を変換
    for col in ["trade_price", "price_per_tsubo", "area", "total_floor_area",
                "frontage", "building_coverage", "floor_area_ratio", "minutes_to_station"]:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(",", "").str.replace("㎡以上", ""),
                errors="coerce"
            )

    # 建築年を数値化（例: "1994年" → 1994）
    if "building_year" in df.columns:
        df["building_year"] = pd.to_numeric(
            df["building_year"].astype(str).str.replace("年", "").str.replace("戦前", "1945"),
            errors="coerce"
        )

    # ソースファイル名を追加
    df["source_file"] = source_file

    # DB列だけ残す
    db_cols = [
        "trade_type", "price_type", "city_code", "prefecture", "city_name",
        "district", "nearest_station", "minutes_to_station", "trade_price",
        "price_per_tsubo", "floor_plan", "area", "land_shape", "frontage",
        "total_floor_area", "building_year", "building_structure", "purpose",
        "future_purpose", "city_planning", "building_coverage", "floor_area_ratio",
        "period", "year", "quarter", "renovation", "remarks", "source_file",
    ]
    existing = [c for c in db_cols if c in df.columns]
    return df[existing]


# ── メイン ────────────────────────────────────────────────
def main():
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)
    total = 0

    for filename, label in CSV_FILES:
        path = Path(filename)
        if not path.exists():
            log.warning(f"ファイルが見つかりません: {filename} → スキップ")
            continue

        log.info(f"読み込み中: {filename}（{label}）")

        # エンコーディングを自動判定
        for enc in ["utf-8", "shift-jis", "cp932"]:
            try:
                df = pd.read_csv(path, encoding=enc)
                log.info(f"  エンコーディング: {enc} / {len(df)}行 / {len(df.columns)}列")
                break
            except (UnicodeDecodeError, Exception):
                continue
        else:
            log.error(f"  読み込み失敗: {filename}")
            continue

        df_clean = clean_df(df, filename)
        df_clean.to_sql("csv_transactions", conn, if_exists="append", index=False, chunksize=100)
        total += len(df_clean)
        log.info(f"  → {len(df_clean)}件 保存完了")

    # サマリー
    cur  = conn.execute("SELECT COUNT(*) FROM csv_transactions")
    rows = cur.fetchone()[0]
    log.info("=" * 50)
    log.info(f"完了！今回追加: {total}件 / DB合計: {rows}件")

    # 簡易プレビュー
    df_preview = pd.read_sql("""
        SELECT
            city_name,
            trade_type,
            COUNT(*)                              AS 件数,
            ROUND(AVG(trade_price) / 10000)       AS 平均価格_万円,
            ROUND(AVG(area))                      AS 平均面積_m2,
            MIN(year) || '〜' || MAX(year)        AS 期間
        FROM csv_transactions
        WHERE trade_price IS NOT NULL
        GROUP BY city_name, trade_type
        ORDER BY 件数 DESC
        LIMIT 20
    """, conn)

    print("\n【取り込みデータ プレビュー（上位20件）】")
    print(df_preview.to_string(index=False))

    conn.close()


if __name__ == "__main__":
    main()
