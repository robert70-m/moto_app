import sqlite3
from werkzeug.security import generate_password_hash

telefono = "9513928223"
nueva_password = "m123="

hash_nuevo = generate_password_hash(nueva_password)

ruta_db = r"C:\Users\herna\Desktop\MOTOAPPV02\database.db"

conn = sqlite3.connect(ruta_db)

conn.execute(
    "UPDATE usuarios SET password=? WHERE telefono=?",
    (hash_nuevo, telefono)
)

conn.commit()
conn.close()

print("Contraseña actualizada en BD correcta")