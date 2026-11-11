import sqlite3

conn = sqlite3.connect('climate_data.db')
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    temperature REAL,
    humidity REAL,
    ppm REAL,
    device_id TEXT
)
''')

conn.commit()
conn.close()
print("База данных и таблица созданы.")