import sqlite3
from werkzeug.security import generate_password_hash

def crear_usuario_admin():
    # Configuración de los datos del administrador
    nombre = "Administrador"
    telefono = "9513928223"
    password_plana = "m123="  # <--- Cambia esto por la contraseña que quieras
    tipo = "admin"
    
    # Generar el hash seguro de la contraseña
    password_hash = generate_password_hash(password_plana)
    
    # Conectar a la base de datos
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    try:
        # Insertar el usuario en la tabla 'usuarios'
        query = """
        INSERT INTO usuarios (nombre, telefono, password, tipo, activo)
        VALUES (?, ?, ?, ?, ?)
        """
        # Dejamos los campos de vehículo y coordenadas vacíos (NULL) ya que es un admin
        cursor.execute(query, (nombre, telefono, password_hash, tipo, 1))
        
        # Guardar los cambios
        conn.commit()
        print(f"¡Usuario administrador creado con éxito!")
        print(f"Teléfono: {telefono}")
        print(f"Hash generado: {password_hash[:30]}...")

    except sqlite3.Error as e:
        print(f"Error al insertar en la base de datos: {e}")
        conn.rollback()
        
    finally:
        # Cerrar la conexión
        conn.close()

if __name__ == "__main__":
    crear_usuario_admin()