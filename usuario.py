import sqlite3

conn = sqlite3.connect("database.db")

for row in conn.execute("SELECT id, nombre, telefono FROM usuarios"):
    print(row)

conn.close()