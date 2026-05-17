"""
茨城県 不動産価格分析ツール - 減価償却・土地代分離・乖離率計算

【概要】
建物の法定耐用年数と残存価値率から建物価値を概算し、
取引価格から土地代を分離して公示地価との乖離率を算出する。

【計算式】
残存価値率 = MAX(1 - 経過年数 / 法定耐用年数, 0.05)  ← 最低5%は残る
建物価値   = 建物再調達単価(円/㎡) × 面積(㎡) × 残存価値率
土地代     = 取引価格 - 建物価値
乖離率(%) = (土地代/㎡ - 公示地価/㎡) / 公示地価/㎡ × 100

【実行】
python depreciation.py
"""

import sqlite3
import pandas as pd
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

DB_PATH = Path("ibaraki_realestate.db")

# ── 構造別 法定耐用年数 ───────────────────────────────────
USEFUL_LIFE = {
    # RC・SRC
    "ＲＣ":       47,
    "ＳＲＣ":      47,
    "RC":         47,
    "SRC":        47,
    # 鉄骨
    "鉄骨造":     34,
    "Ｓ":         34,
    "軽量鉄骨":   19,
    # 木造
    "木造":       22,
    "Ｗ":         22,
    # その他
    "その他":     22,
}

# ── 構造別・年別 建物再調達単価（円/㎡）────────────────
# 国土交通省建築着工統計・建設物価調査会データを参考にした概算値
RECONSTRUCTION_COST_BY_YEAR = {
    "ＲＣ": {
        2020: 220000,
        2021: 230000,
        2022: 250000,
        2023: 265000,
        2024: 280000,
        2025: 290000,
        2026: 295000,
    },
    "ＳＲＣ": {
        2020: 250000,
        2021: 260000,
        2022: 280000,
        2023: 295000,
        2024: 310000,
        2025: 320000,
        2026: 325000,
    },
    "鉄骨造": {
        2020: 160000,
        2021: 170000,
        2022: 185000,
        2023: 195000,
        2024: 205000,
        2025: 210000,
        2026: 215000,
    },
    "軽量鉄骨": {
        2020: 130000,
        2021: 138000,
        2022: 150000,
        2023: 158000,
        2024: 165000,
        2025: 170000,
        2026: 173000,
    },
    "木造": {
        2020: 130000,
        2021: 138000,
        2022: 150000,
        2023: 158000,
        2024: 165000,
        2025: 170000,
        2026: 173000,
    },
    "その他": {
        2020: 130000,
        2021: 138000,
        2022: 150000,
        2023: 158000,
        2024: 165000,
        2025: 170000,
        2026: 173000,
    },
}

# 構造名の正規化マップ
STRUCTURE_MAP = {
    "ＲＣ":   "ＲＣ",
    "RC":     "ＲＣ",
    "ＳＲＣ": "ＳＲＣ",
    "SRC":    "ＳＲＣ",
    "鉄骨造": "鉄骨造",
    "Ｓ":     "鉄骨造",
    "軽量鉄骨":"軽量鉄骨",
    "木造":   "木造",
    "Ｗ":     "木造",
}

# 最低残存価値率（スクラップ価値）
MIN_RESIDUAL_RATE = 0.05


def get_useful_life(structure: str) -> int:
    """構造から法定耐用年数を返す"""
    if not structure or str(structure) == "nan":
        return 22  # デフォルト: 木造
    s = str(structure).strip()
    for key, life in USEFUL_LIFE.items():
        if key in s:
            return life
    return 22


def get_reconstruction_cost(structure: str, trade_year: int) -> int:
    """構造と取引年から建物再調達単価（円/㎡）を返す"""
    if not structure or str(structure) == "nan":
        key = "その他"
    else:
        s   = str(structure).strip()
        key = "その他"
        for skey, mapped in STRUCTURE_MAP.items():
            if skey in s:
                key = mapped
                break

    year_map = RECONSTRUCTION_COST_BY_YEAR.get(key, RECONSTRUCTION_COST_BY_YEAR["その他"])

    # 対象年がない場合は最近年か最古年で補完
    if trade_year in year_map:
        return year_map[trade_year]
    elif trade_year < min(year_map.keys()):
        return year_map[min(year_map.keys())]
    else:
        return year_map[max(year_map.keys())]


def calc_residual_rate(building_year: int, trade_year: int, useful_life: int) -> float:
    """
    建物の残存価値率を計算する
    残存価値率 = MAX(1 - 経過年数 / 法定耐用年数, MIN_RESIDUAL_RATE)
    """
    if not building_year or not trade_year:
        return None
    elapsed = trade_year - building_year
    if elapsed < 0:
        return 1.0  # 建築年より前の取引（データ異常）
    rate = 1.0 - elapsed / useful_life
    return max(rate, MIN_RESIDUAL_RATE)


def estimate_building_value(
    structure: str,
    building_year: int,
    trade_year: int,
    area: float,
) -> float | None:
    """
    建物価値を概算する（円）

    Args:
        structure:     建物構造（例: "ＲＣ"）
        building_year: 建築年（例: 2000）
        trade_year:    取引年（例: 2024）
        area:          面積（㎡）

    Returns:
        建物価値（円）または None
    """
    if not area or area <= 0:
        return None

    useful_life   = get_useful_life(structure)
    recon_cost    = get_reconstruction_cost(structure, trade_year)
    residual_rate = calc_residual_rate(building_year, trade_year, useful_life)

    if residual_rate is None:
        return None

    building_value = recon_cost * area * residual_rate
    return round(building_value)


def calc_land_value(trade_price: int, building_value: float) -> float | None:
    """
    取引価格から建物価値を引いて土地代を算出する（円）
    土地代がマイナスの場合はNoneを返す（データ異常）
    """
    if trade_price is None or building_value is None:
        return None
    land = trade_price - building_value
    return round(land) if land > 0 else None


def calc_deviation_rate(land_price_per_sqm: float, published_price: float) -> float | None:
    """
    土地代と公示地価の乖離率を計算する（%）
    乖離率 = (土地代/㎡ - 公示地価/㎡) / 公示地価/㎡ × 100
    プラス = 公示地価より割高
    マイナス = 公示地価より割安
    """
    if not land_price_per_sqm or not published_price or published_price <= 0:
        return None
    return round((land_price_per_sqm - published_price) / published_price * 100, 1)


# ── DBに適用 ──────────────────────────────────────────────
def apply_to_db(conn: sqlite3.Connection):
    """全取引データに建物価値・土地代・乖離率を計算してDBに保存する"""

    # 列が存在しなければ追加
    cur  = conn.execute("PRAGMA table_info(csv_transactions)")
    cols = [row[1] for row in cur.fetchall()]
    new_cols = [
        ("building_value",      "INTEGER"),  # 建物価値（円）
        ("land_value",          "INTEGER"),  # 土地代（円）
        ("land_price_per_sqm",  "REAL"),     # 土地代の㎡単価（円）
        ("land_deviation_rate", "REAL"),     # 公示地価との乖離率（%）
        ("residual_rate",       "REAL"),     # 残存価値率
        ("useful_life",         "INTEGER"),  # 法定耐用年数
    ]
    for col, dtype in new_cols:
        if col not in cols:
            conn.execute(f"ALTER TABLE csv_transactions ADD COLUMN {col} {dtype}")
    conn.commit()
    log.info("列追加完了")

    # データ取得（total_floor_areaも取得）
    df = pd.read_sql("""
        SELECT id, trade_price, area, total_floor_area,
               building_structure, trade_type,
               building_year, year, nearest_lp_price
        FROM csv_transactions
        WHERE trade_price IS NOT NULL
          AND area IS NOT NULL
          AND area > 0
          AND building_year IS NOT NULL
          AND building_year > 1900
          AND land_deviation_rate IS NULL
    """, conn)
    log.info(f"処理対象: {len(df)}件")

    batch      = []
    batch_size = 500

    for _, row in df.iterrows():
        structure    = row["building_structure"]
        building_year= int(row["building_year"]) if row["building_year"] else None
        trade_year   = int(row["year"]) if row["year"] else None
        area         = row["area"]           # 土地面積（宅地）or 専有面積（マンション）
        floor_area   = row["total_floor_area"]  # 延床面積（宅地のみ）
        trade_price  = row["trade_price"]
        lp_price     = row["nearest_lp_price"]
        trade_type   = row["trade_type"] or ""

        # 建物価値の計算に使う面積を種別で分ける
        # マンション: 専有面積（area）
        # 宅地: 延床面積（total_floor_area）があればそれを使う
        is_mansion   = "マンション" in str(trade_type)
        building_area = area if is_mansion else (floor_area if floor_area and floor_area > 0 else area)

        # 土地代㎡単価の計算に使う面積
        # マンション: 専有面積（area）
        # 宅地: 土地面積（area）
        land_area = area

        useful_life   = get_useful_life(structure)
        residual_rate = calc_residual_rate(building_year, trade_year, useful_life)
        building_val  = estimate_building_value(structure, building_year, trade_year, building_area)
        land_val      = calc_land_value(trade_price, building_val)

        # 土地代の㎡単価
        land_per_sqm = round(land_val / land_area) if land_val and land_area > 0 else None

        # 乖離率（土地代㎡単価 vs 公示地価㎡単価）
        deviation = calc_deviation_rate(land_per_sqm, lp_price)

        batch.append((
            building_val,
            land_val,
            land_per_sqm,
            deviation,
            round(residual_rate, 3) if residual_rate else None,
            useful_life,
            int(row["id"])
        ))

        if len(batch) >= batch_size:
            conn.executemany("""
                UPDATE csv_transactions
                SET building_value      = ?,
                    land_value          = ?,
                    land_price_per_sqm  = ?,
                    land_deviation_rate = ?,
                    residual_rate       = ?,
                    useful_life         = ?
                WHERE id = ?
            """, batch)
            conn.commit()
            batch = []

    if batch:
        conn.executemany("""
            UPDATE csv_transactions
            SET building_value      = ?,
                land_value          = ?,
                land_price_per_sqm  = ?,
                land_deviation_rate = ?,
                residual_rate       = ?,
                useful_life         = ?
            WHERE id = ?
        """, batch)
        conn.commit()

    log.info("計算完了！")


def main():
    conn = sqlite3.connect(DB_PATH)
    apply_to_db(conn)

    # サマリー
    df = pd.read_sql("""
        SELECT
            city_name                               AS 市区町村,
            trade_type                              AS 種別,
            COUNT(*)                                AS 件数,
            ROUND(AVG(residual_rate) * 100, 1)      AS 平均残存価値率_percent,
            ROUND(AVG(building_value) / 10000)      AS 平均建物価値_万円,
            ROUND(AVG(land_value) / 10000)          AS 平均土地代_万円,
            ROUND(AVG(land_deviation_rate), 1)      AS 平均乖離率_percent
        FROM csv_transactions
        WHERE land_deviation_rate IS NOT NULL
        GROUP BY city_name, trade_type
        HAVING 件数 >= 10
        ORDER BY 平均乖離率_percent
        LIMIT 20
    """, conn)

    print("\n【土地代ベース乖離率 サマリー（割安順・上位20）】")
    print(df.to_string(index=False))

    # 乖離率の分布確認
    df2 = pd.read_sql("""
        SELECT
            CASE
                WHEN land_deviation_rate < -50  THEN '-50%以下（割安）'
                WHEN land_deviation_rate < -20  THEN '-50〜-20%'
                WHEN land_deviation_rate < 0    THEN '-20〜0%'
                WHEN land_deviation_rate < 20   THEN '0〜20%'
                WHEN land_deviation_rate < 50   THEN '20〜50%'
                ELSE '50%超（割高）'
            END AS 乖離率区分,
            COUNT(*) AS 件数
        FROM csv_transactions
        WHERE land_deviation_rate IS NOT NULL
        GROUP BY 乖離率区分
        ORDER BY MIN(land_deviation_rate)
    """, conn)

    print("\n【乖離率の分布】")
    print(df2.to_string(index=False))

    conn.close()
    log.info("完了！")


if __name__ == "__main__":
    main()
