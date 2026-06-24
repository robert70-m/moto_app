import sqlite3

conn = sqlite3.connect(r"C:\Users\herna\Desktop\MOTOAPPV02\database.db")

for fila in conn.execute("PRAGMA table_info(usuarios)"):
    print(fila)

conn.close()

input("ENTER para salir...")