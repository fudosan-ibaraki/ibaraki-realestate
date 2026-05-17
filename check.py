import sqlite3, pandas as pd
conn = sqlite3.connect('ibaraki_realestate.db')
df = pd.read_sql("""
    SELECT city_name, year, COUNT(*) as 件数,
           ROUND(AVG(trade_price)/10000,1) as 平均価格
    FROM csv_transactions
    WHERE trade_type LIKE '%マンション%'
      AND trade_price IS NOT NULL
      AND year IS NOT NULL
    GROUP BY city_name, year
    HAVING 件数 >= 3
    LIMIT 10
""", conn)
print(df.to_string(index=False))
conn.close()