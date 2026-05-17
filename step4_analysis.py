"""
茨城県 不動産価格分析ツール - Step 4
総合分析レポート

【分析内容】
1. エリア別価格トレンド（マンション・宅地）
2. 築年数と価格の関係
3. 駅距離と価格の関係
4. 間取り別価格
5. エリア内での相対比較（割安・割高スコア）
"""

import sqlite3
import pandas as pd
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

DB_PATH = Path("ibaraki_realestate.db")


def get_conn():
    return sqlite3.connect(DB_PATH)


# ── 分析1: エリア別価格トレンド ───────────────────────────
def analysis_area_trend(conn):
    log.info("分析1: エリア別価格トレンド")

    # マンション
    df_mansion = pd.read_sql("""
        SELECT
            city_name   AS 市区町村,
            year        AS 年,
            COUNT(*)    AS 件数,
            ROUND(AVG(trade_price)/10000, 1) AS 平均価格_万円,
            ROUND(AVG(price_per_sqm))        AS 平均㎡単価_円
        FROM csv_transactions
        WHERE trade_type LIKE '%マンション%'
          AND trade_price IS NOT NULL
          AND year IS NOT NULL
        GROUP BY city_name, year
        HAVING 件数 >= 3
        ORDER BY city_name, year
    """, conn)

    # 宅地
    df_land = pd.read_sql("""
        SELECT
            city_name   AS 市区町村,
            year        AS 年,
            COUNT(*)    AS 件数,
            ROUND(AVG(trade_price)/10000, 1) AS 平均価格_万円,
            ROUND(AVG(price_per_sqm))        AS 平均㎡単価_円
        FROM csv_transactions
        WHERE trade_type LIKE '%宅地%'
          AND trade_price IS NOT NULL
          AND year IS NOT NULL
        GROUP BY city_name, year
        HAVING 件数 >= 3
        ORDER BY city_name, year
    """, conn)

    return df_mansion, df_land


# ── 分析2: 築年数と価格の関係 ────────────────────────────
def analysis_building_age(conn):
    log.info("分析2: 築年数と価格の関係")

    df_mansion = pd.read_sql("""
        SELECT
            CASE
                WHEN (2024 - building_year) <= 5   THEN '築5年以内'
                WHEN (2024 - building_year) <= 10  THEN '築6〜10年'
                WHEN (2024 - building_year) <= 20  THEN '築11〜20年'
                WHEN (2024 - building_year) <= 30  THEN '築21〜30年'
                WHEN (2024 - building_year) <= 40  THEN '築31〜40年'
                ELSE '築41年以上'
            END AS 築年数区分,
            COUNT(*)                            AS 件数,
            ROUND(AVG(trade_price)/10000, 1)    AS 平均価格_万円,
            ROUND(AVG(price_per_sqm))           AS 平均㎡単価_円,
            ROUND(AVG(area), 1)                 AS 平均面積_m2
        FROM csv_transactions
        WHERE trade_type LIKE '%マンション%'
          AND trade_price IS NOT NULL
          AND building_year IS NOT NULL
          AND building_year > 1900
        GROUP BY 築年数区分
        ORDER BY MIN(2024 - building_year)
    """, conn)

    df_land = pd.read_sql("""
        SELECT
            CASE
                WHEN (2024 - building_year) <= 5   THEN '築5年以内'
                WHEN (2024 - building_year) <= 10  THEN '築6〜10年'
                WHEN (2024 - building_year) <= 20  THEN '築11〜20年'
                WHEN (2024 - building_year) <= 30  THEN '築21〜30年'
                WHEN (2024 - building_year) <= 40  THEN '築31〜40年'
                ELSE '築41年以上'
            END AS 築年数区分,
            COUNT(*)                            AS 件数,
            ROUND(AVG(trade_price)/10000, 1)    AS 平均価格_万円,
            ROUND(AVG(price_per_sqm))           AS 平均㎡単価_円
        FROM csv_transactions
        WHERE trade_type LIKE '%宅地%'
          AND trade_price IS NOT NULL
          AND building_year IS NOT NULL
          AND building_year > 1900
        GROUP BY 築年数区分
        ORDER BY MIN(2024 - building_year)
    """, conn)

    return df_mansion, df_land


# ── 分析3: 駅距離と価格の関係 ────────────────────────────
def analysis_station_distance(conn):
    log.info("分析3: 駅距離と価格の関係")

    df_mansion = pd.read_sql("""
        SELECT
            CASE
                WHEN nearest_station_dist <= 500  THEN '500m以内'
                WHEN nearest_station_dist <= 1000 THEN '500m〜1km'
                WHEN nearest_station_dist <= 2000 THEN '1〜2km'
                WHEN nearest_station_dist <= 3000 THEN '2〜3km'
                ELSE '3km超'
            END AS 駅距離,
            COUNT(*)                            AS 件数,
            ROUND(AVG(trade_price)/10000, 1)    AS 平均価格_万円,
            ROUND(AVG(price_per_sqm))           AS 平均㎡単価_円
        FROM csv_transactions
        WHERE trade_type LIKE '%マンション%'
          AND trade_price IS NOT NULL
          AND nearest_station_dist IS NOT NULL
        GROUP BY 駅距離
        ORDER BY MIN(nearest_station_dist)
    """, conn)

    df_land = pd.read_sql("""
        SELECT
            CASE
                WHEN nearest_station_dist <= 500  THEN '500m以内'
                WHEN nearest_station_dist <= 1000 THEN '500m〜1km'
                WHEN nearest_station_dist <= 2000 THEN '1〜2km'
                WHEN nearest_station_dist <= 3000 THEN '2〜3km'
                ELSE '3km超'
            END AS 駅距離,
            COUNT(*)                            AS 件数,
            ROUND(AVG(trade_price)/10000, 1)    AS 平均価格_万円,
            ROUND(AVG(price_per_sqm))           AS 平均㎡単価_円
        FROM csv_transactions
        WHERE trade_type LIKE '%宅地%'
          AND trade_price IS NOT NULL
          AND nearest_station_dist IS NOT NULL
        GROUP BY 駅距離
        ORDER BY MIN(nearest_station_dist)
    """, conn)

    return df_mansion, df_land


# ── 分析4: 間取り別価格 ───────────────────────────────────
def analysis_floor_plan(conn):
    log.info("分析4: 間取り別価格")

    df_mansion = pd.read_sql("""
        SELECT
            floor_plan                          AS 間取り,
            COUNT(*)                            AS 件数,
            ROUND(AVG(trade_price)/10000, 1)    AS 平均価格_万円,
            ROUND(AVG(price_per_sqm))           AS 平均㎡単価_円,
            ROUND(AVG(area), 1)                 AS 平均面積_m2
        FROM csv_transactions
        WHERE trade_type LIKE '%マンション%'
          AND trade_price IS NOT NULL
          AND floor_plan IS NOT NULL
          AND floor_plan != 'nan'
        GROUP BY floor_plan
        HAVING 件数 >= 10
        ORDER BY 平均価格_万円 DESC
        LIMIT 15
    """, conn)

    df_land = pd.read_sql("""
        SELECT
            floor_plan                          AS 間取り,
            COUNT(*)                            AS 件数,
            ROUND(AVG(trade_price)/10000, 1)    AS 平均価格_万円,
            ROUND(AVG(price_per_sqm))           AS 平均㎡単価_円,
            ROUND(AVG(area), 1)                 AS 平均面積_m2
        FROM csv_transactions
        WHERE trade_type LIKE '%宅地%'
          AND trade_price IS NOT NULL
          AND floor_plan IS NOT NULL
          AND floor_plan != 'nan'
        GROUP BY floor_plan
        HAVING 件数 >= 10
        ORDER BY 平均価格_万円 DESC
        LIMIT 15
    """, conn)

    return df_mansion, df_land


# ── 分析5: エリア内での相対比較（割安・割高スコア） ────────
def analysis_relative_price(conn):
    log.info("分析5: エリア内相対比較")

    df_mansion = pd.read_sql("""
        WITH city_avg AS (
            SELECT
                city_name,
                AVG(price_per_sqm) AS avg_sqm
            FROM csv_transactions
            WHERE trade_type LIKE '%マンション%'
              AND price_per_sqm IS NOT NULL
            GROUP BY city_name
        )
        SELECT
            t.city_name                         AS 市区町村,
            t.district                          AS 地区,
            COUNT(*)                            AS 件数,
            ROUND(AVG(t.price_per_sqm))         AS 地区平均㎡単価,
            ROUND(c.avg_sqm)                    AS 市区町村平均㎡単価,
            ROUND((AVG(t.price_per_sqm) - c.avg_sqm)
                  / c.avg_sqm * 100, 1)         AS 相対スコア_percent
        FROM csv_transactions t
        JOIN city_avg c ON t.city_name = c.city_name
        WHERE t.trade_type LIKE '%マンション%'
          AND t.price_per_sqm IS NOT NULL
        GROUP BY t.city_name, t.district
        HAVING 件数 >= 5
        ORDER BY 相対スコア_percent DESC
        LIMIT 20
    """, conn)

    df_land = pd.read_sql("""
        WITH city_avg AS (
            SELECT
                city_name,
                AVG(price_per_sqm) AS avg_sqm
            FROM csv_transactions
            WHERE trade_type LIKE '%宅地%'
              AND price_per_sqm IS NOT NULL
            GROUP BY city_name
        )
        SELECT
            t.city_name                         AS 市区町村,
            t.district                          AS 地区,
            COUNT(*)                            AS 件数,
            ROUND(AVG(t.price_per_sqm))         AS 地区平均㎡単価,
            ROUND(c.avg_sqm)                    AS 市区町村平均㎡単価,
            ROUND((AVG(t.price_per_sqm) - c.avg_sqm)
                  / c.avg_sqm * 100, 1)         AS 相対スコア_percent
        FROM csv_transactions t
        JOIN city_avg c ON t.city_name = c.city_name
        WHERE t.trade_type LIKE '%宅地%'
          AND t.price_per_sqm IS NOT NULL
        GROUP BY t.city_name, t.district
        HAVING 件数 >= 5
        ORDER BY 相対スコア_percent DESC
        LIMIT 20
    """, conn)

    return df_mansion, df_land


# ── メイン ────────────────────────────────────────────────
def main():
    conn = get_conn()

    print("\n" + "="*60)
    print("茨城県 不動産価格総合分析レポート")
    print("="*60)

    # 分析1
    m1, l1 = analysis_area_trend(conn)
    print("\n【1-1】エリア別価格トレンド（マンション・上位10都市）")
    top_cities = m1.groupby("市区町村")["件数"].sum().nlargest(10).index
    print(m1[m1["市区町村"].isin(top_cities)].to_string(index=False))
    print("\n【1-2】エリア別価格トレンド（宅地・上位10都市）")
    top_cities_l = l1.groupby("市区町村")["件数"].sum().nlargest(10).index
    print(l1[l1["市区町村"].isin(top_cities_l)].to_string(index=False))

    # 分析2
    m2, l2 = analysis_building_age(conn)
    print("\n【2-1】築年数と価格の関係（マンション）")
    print(m2.to_string(index=False))
    print("\n【2-2】築年数と価格の関係（宅地）")
    print(l2.to_string(index=False))

    # 分析3
    m3, l3 = analysis_station_distance(conn)
    print("\n【3-1】駅距離と価格の関係（マンション）")
    print(m3.to_string(index=False))
    print("\n【3-2】駅距離と価格の関係（宅地）")
    print(l3.to_string(index=False))

    # 分析4
    m4, l4 = analysis_floor_plan(conn)
    print("\n【4-1】間取り別価格（マンション）")
    print(m4.to_string(index=False))
    print("\n【4-2】間取り別価格（宅地）")
    print(l4.to_string(index=False))

    # 分析5
    m5, l5 = analysis_relative_price(conn)
    print("\n【5-1】エリア内相対比較 割高地区TOP20（マンション）")
    print(m5.to_string(index=False))
    print("\n【5-2】エリア内相対比較 割高地区TOP20（宅地）")
    print(l5.to_string(index=False))

    # Excelに保存
    output = Path("analysis_result.xlsx")
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        m1.to_excel(writer, sheet_name="1_エリアトレンド_マンション", index=False)
        l1.to_excel(writer, sheet_name="1_エリアトレンド_宅地",       index=False)
        m2.to_excel(writer, sheet_name="2_築年数_マンション",          index=False)
        l2.to_excel(writer, sheet_name="2_築年数_宅地",                index=False)
        m3.to_excel(writer, sheet_name="3_駅距離_マンション",          index=False)
        l3.to_excel(writer, sheet_name="3_駅距離_宅地",                index=False)
        m4.to_excel(writer, sheet_name="4_間取り_マンション",          index=False)
        l4.to_excel(writer, sheet_name="4_間取り_宅地",                index=False)
        m5.to_excel(writer, sheet_name="5_相対比較_マンション",        index=False)
        l5.to_excel(writer, sheet_name="5_相対比較_宅地",              index=False)

    log.info(f"Excelに保存完了: {output.resolve()}")
    print(f"\n結果を {output} に保存しました！")
    conn.close()


if __name__ == "__main__":
    main()
