import sqlite3

conn = sqlite3.connect("database.db")

telefono = "9513928223"

conn.execute(
    "UPDATE usuarios SET password='' WHERE telefono=?",
    (telefono,)
)

conn.commit()
conn.close()

print("password reseteada")