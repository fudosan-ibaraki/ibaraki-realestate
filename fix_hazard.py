import sqlite3

conn = sqlite3.connect('ibaraki_realestate.db')

result = conn.execute("SELECT COUNT(*) FROM hazard_flood WHERE flood_rank IS NULL").fetchone()
print("NULL件数:", result[0])

conn.execute("UPDATE hazard_flood SET flood_rank=8, flood_depth='10m以上' WHERE flood_rank IS NULL")
conn.commit()

result2 = conn.execute("SELECT COUNT(*) FROM hazard_flood WHERE flood_rank IS NULL").fetchone()
print("修正後NULL件数:", result2[0])

conn.close()
print("完了！")