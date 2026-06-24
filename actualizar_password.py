import sqlite3

hash_nuevo = "scrypt:32768:8:1$5GpYwbeYVro8tZYW$e39f088f1e4061af771049c3f0d2ec038ad2c71f895de45c3eabb5fa645552c70a72f2a757010057f0905746e6bb13f4a9f49161dfe45eed74c623bfdc78cb1c"

telefono = "9513928223"

conn = sqlite3.connect("database.db")

cursor = conn.cursor()
cursor.execute(
    "UPDATE usuarios SET password=? WHERE telefono=?",
    (hash_nuevo, telefono)
)

conn.commit()

print("Filas modificadas:", cursor.rowcount)

conn.close()