import sqlite3, pandas as pd
conn = sqlite3.connect('../ibaraki_realestate.db')
df = pd.read_sql("""
    SELECT trade_price, area, building_year,
           nearest_station_name, nearest_station_dist,
           hazard_risk, district, year, floor_plan
    FROM csv_transactions
    WHERE city_name = 'つくば市'
      AND trade_type LIKE '%マンション%'
      AND area BETWEEN 60 AND 90
    LIMIT 5
""", conn)
print(df.to_string())
conn.close()