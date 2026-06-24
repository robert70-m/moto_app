import sqlite3
import os
from werkzeug.security import generate_password_hash

# 👇 OJO: aquí se obtiene la ruta REAL del archivo
db_path = os.path.join(os.getcwd(), "database.db")

print("USANDO BD EN:", db_path)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

telefono = "9513928223"
password = generate_password_hash("m123=")

cursor.execute("""
INSERT INTO usuarios (telefono, password, rol)
VALUES (?, ?, ?)
""", (telefono, password, "admin"))

conn.commit()
conn.close()

print("ADMIN CREADO")