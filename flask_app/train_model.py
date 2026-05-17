"""
Random Forest による不動産価格予測モデルの学習（改善版）

改善点:
  - マンション・宅地を別モデルで学習
  - districtを特徴量に追加
  - 外れ値除去（上下1%）
  - 対数変換で価格の歪みを補正
  - floor_planを特徴量に追加（マンションのみ）

出力: model_rf_mansion.pkl / model_rf_land.pkl

使い方:
  python train_model.py
"""

import sqlite3
import pickle
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import mean_absolute_error, r2_score

DB_PATH = Path("../ibaraki_realestate.db")


def remove_outliers(df, col, q_low=0.01, q_high=0.99):
    lo = df[col].quantile(q_low)
    hi = df[col].quantile(q_high)
    return df[(df[col] >= lo) & (df[col] <= hi)]


def fit_le(series, fill="不明"):
    le = LabelEncoder()
    le.fit(series.fillna(fill))
    return le

def safe_transform(le, val, fill="不明"):
    val = val if val in le.classes_ else fill
    if val not in le.classes_:
        val = le.classes_[0]
    return int(le.transform([val])[0])


def train_mansion(conn):
    df = pd.read_sql("""
        SELECT city_name, district, floor_plan,
               area, building_year, nearest_station_dist,
               hazard_risk, convenience_score, trade_price
        FROM csv_transactions
        WHERE trade_type LIKE '%マンション%'
          AND trade_price > 0
          AND area > 0
          AND city_name IS NOT NULL
          AND building_year IS NOT NULL
          AND building_year > 1950
    """, conn)

    print(f"  マンション 生データ: {len(df):,}件")
    df = remove_outliers(df, "trade_price")
    df = remove_outliers(df, "area")
    print(f"  外れ値除去後: {len(df):,}件")

    df["building_age"]         = (2025 - df["building_year"]).clip(0, 60)
    df["nearest_station_dist"] = df["nearest_station_dist"].fillna(df["nearest_station_dist"].median())
    df["convenience_score"]    = df["convenience_score"].fillna(df["convenience_score"].median())

    le_city     = fit_le(df["city_name"])
    le_district = fit_le(df["district"])
    le_floor    = fit_le(df["floor_plan"])
    le_hazard   = fit_le(df["hazard_risk"])

    df["city_enc"]     = le_city.transform(df["city_name"].fillna("不明"))
    df["district_enc"] = le_district.transform(df["district"].fillna("不明"))
    df["floor_enc"]    = le_floor.transform(df["floor_plan"].fillna("不明"))
    df["hazard_enc"]   = le_hazard.transform(df["hazard_risk"].fillna("不明"))

    features = ["city_enc", "district_enc", "floor_enc", "area",
                "building_age", "nearest_station_dist", "hazard_enc", "convenience_score"]

    X = df[features].values
    y = np.log1p(df["trade_price"].values)

    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=42)

    model = RandomForestRegressor(
        n_estimators=300, max_depth=25, min_samples_leaf=3,
        n_jobs=-1, random_state=42
    )
    model.fit(X_tr, y_tr)

    y_pred = np.expm1(model.predict(X_te))
    y_true = np.expm1(y_te)
    mae = mean_absolute_error(y_true, y_pred)
    r2  = r2_score(y_true, y_pred)
    print(f"  [マンション] MAE: {mae/10000:.1f}万円  R2: {r2:.3f}")

    return {
        "model": model, "features": features,
        "le_city": le_city, "le_district": le_district,
        "le_floor": le_floor, "le_hazard": le_hazard,
        "city_names":   list(le_city.classes_),
        "hazard_risks": list(le_hazard.classes_),
        "floor_plans":  list(le_floor.classes_),
        "log_target": True,
    }


def train_land(conn):
    df = pd.read_sql("""
        SELECT city_name, district,
               area, nearest_station_dist,
               hazard_risk, convenience_score, trade_price
        FROM csv_transactions
        WHERE trade_type LIKE '%宅地%'
          AND trade_price > 0
          AND area > 0
          AND city_name IS NOT NULL
    """, conn)

    print(f"  宅地 生データ: {len(df):,}件")

    # ㎡単価で学習（総額の代わり）
    df["price_per_sqm"] = df["trade_price"] / df["area"]
    df = remove_outliers(df, "price_per_sqm")
    df = remove_outliers(df, "area")
    print(f"  外れ値除去後: {len(df):,}件")

    df["nearest_station_dist"] = df["nearest_station_dist"].fillna(df["nearest_station_dist"].median())
    df["convenience_score"]    = df["convenience_score"].fillna(df["convenience_score"].median())

    le_city     = fit_le(df["city_name"])
    le_district = fit_le(df["district"])
    le_hazard   = fit_le(df["hazard_risk"])

    df["city_enc"]     = le_city.transform(df["city_name"].fillna("不明"))
    df["district_enc"] = le_district.transform(df["district"].fillna("不明"))
    df["hazard_enc"]   = le_hazard.transform(df["hazard_risk"].fillna("不明"))

    features = ["city_enc", "district_enc", "area",
                "nearest_station_dist", "hazard_enc", "convenience_score"]

    X = df[features].values
    y = np.log1p(df["price_per_sqm"].values)  # ㎡単価を対数変換

    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=42)

    model = RandomForestRegressor(
        n_estimators=300, max_depth=25, min_samples_leaf=3,
        n_jobs=-1, random_state=42
    )
    model.fit(X_tr, y_tr)

    # 評価: ㎡単価 → 総額に戻して計算
    sqm_pred = np.expm1(model.predict(X_te))
    sqm_true = np.expm1(y_te)
    area_te  = df.iloc[X_te.shape[0] * -1:]["area"].values  # 近似
    mae_sqm  = mean_absolute_error(sqm_true, sqm_pred)
    r2_sqm   = r2_score(sqm_true, sqm_pred)
    print(f"  [宅地] ㎡単価 MAE: {mae_sqm:.0f}円/㎡  R2: {r2_sqm:.3f}")
    print(f"  ※総額予測時は予測㎡単価 × 面積で算出")

    return {
        "model": model, "features": features,
        "le_city": le_city, "le_district": le_district,
        "le_hazard": le_hazard,
        "city_names":   list(le_city.classes_),
        "hazard_risks": list(le_hazard.classes_),
        "log_target": True,
        "predict_sqm": True,  # ㎡単価モデルフラグ
    }


def main():
    conn = sqlite3.connect(DB_PATH)

    print("=== マンションモデル学習 ===")
    bundle_mansion = train_mansion(conn)
    with open("model_rf_mansion.pkl", "wb") as f:
        pickle.dump(bundle_mansion, f)
    print("  -> model_rf_mansion.pkl 保存完了\n")

    print("=== 宅地モデル学習 ===")
    bundle_land = train_land(conn)
    with open("model_rf_land.pkl", "wb") as f:
        pickle.dump(bundle_land, f)
    print("  -> model_rf_land.pkl 保存完了\n")

    conn.close()
    print("完了！")


if __name__ == "__main__":
    main()
