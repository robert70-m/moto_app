from flask import Flask, render_template, request, redirect, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
from datetime import datetime, timedelta

base_dir = os.path.abspath(os.path.dirname(__file__))
template_dir = os.path.join(base_dir, 'templates')

app = Flask(__name__)
app.secret_key = "mi primera la app de servicio de moto mas efecinete"

ADMIN_PASSWORD = "admin1"

# ---------------------- BASE DE DATOS ----------------------
def get_db():
    # Ruta absoluta para PythonAnywhere
    conn = sqlite3.connect("/home/robert70/moto_app/database.db")
    conn.row_factory = sqlite3.Row  
    return conn

def crear_tablas():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT,
        telefono TEXT,
        password TEXT,
        tipo TEXT,
        lat REAL,
        lng REAL,
        activo INTEGER DEFAULT 1,
        fecha_pago TEXT
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS viajes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cliente_id INTEGER,
        conductor_id INTEGER,
        nombre_conductor TEXT,
        estado TEXT,
        origen TEXT,
        destino TEXT,
        lat REAL,
        lng REAL,
        lat_destino REAL,
        lng_destino REAL
    )
    """)
    conn.commit()
    conn.close()

# ---------------------- LOGIN Y REGISTRO ----------------------
@app.route("/", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        telefono = request.form["telefono"].strip()
        password = request.form["password"].strip()

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM usuarios WHERE telefono=? AND password=?",
            (telefono, password)
        ).fetchone()
        conn.close()

        if user:
            if user["tipo"] == "conductor" and user["activo"] == 0:
                error = "Tu cuenta está suspendida. Contacta al administrador ❌"
                return render_template("login.html", error=error)

            session["user_id"] = user["id"]
            session["tipo"] = user["tipo"]
            session["nombre"] = user["nombre"] 

            if user["tipo"] == "cliente":
                return redirect("/cliente")
            else:
                return redirect("/conductor")
        else:
            error = "Usuario o contraseña incorrectos ❌"

    return render_template("login.html", error=error)

@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        nombre = request.form['nombre']
        telefono = request.form['telefono']
        password = request.form['password']
        tipo = "cliente"

        conn = get_db() # Usamos get_db para consistencia
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO usuarios (nombre, telefono, password, tipo)
            VALUES (?, ?, ?, ?)
        """, (nombre, telefono, password, tipo))
        conn.commit()
        conn.close()
        return redirect('/')
    return render_template("registro.html")

# ---------------------- VISTAS PRINCIPALES ----------------------

@app.route("/cliente")
def cliente():
    if session.get("tipo") != "cliente":
        return redirect("/")

    cliente_id = session.get("user_id")
    conn = get_db()
    viaje = conn.execute("""
        SELECT id, estado FROM viajes 
        WHERE cliente_id = ? 
        AND estado IN ('pendiente','aceptado','en_camino','recogido','en_curso')
        ORDER BY id DESC LIMIT 1
    """, (cliente_id,)).fetchone()
    conn.close()

    viaje_id = viaje["id"] if viaje else None
    estado = viaje["estado"] if viaje else None

    return render_template("cliente.html", viaje_id=viaje_id, estado=estado)
# -----------------conductor --------------------------------------

@app.route("/conductor")
def conductor():
    if not session.get("user_id") or session.get("tipo") != "conductor":
        return redirect("/")

    conn = get_db()
    user = conn.execute("SELECT * FROM usuarios WHERE id=?", (session["user_id"],)).fetchone()

    # Verificación de pago y cuenta activa
    if user["fecha_pago"]:
        fecha_pago = datetime.strptime(user["fecha_pago"], "%Y-%m-%d")
        if datetime.now() > fecha_pago + timedelta(days=7):
            conn.execute("UPDATE usuarios SET activo=0 WHERE id=?", (session["user_id"],))
            conn.commit()
            conn.close()
            return "Tu acceso ha expirado. Realiza tu pago para continuar ❌"

    if user["activo"] == 0:
        conn.close()
        return "Cuenta suspendida ❌"

    # BUSQUEDA DE VIAJE: Incluimos todos los estados activos para que el mapa persista
    viaje = conn.execute("""
        SELECT id, lat, lng, lat_destino, lng_destino, origen, destino, estado
        FROM viajes 
        WHERE conductor_id = ?
        AND estado IN ('aceptado', 'en_camino', 'recogido', 'en_curso')
        ORDER BY id DESC LIMIT 1
    """, (session["user_id"],)).fetchone()   

    conn.close()

    # Si hay un viaje, cargamos la plantilla del conductor con los datos del viaje
    if viaje:
        return render_template("conductor.html", viaje=viaje, viaje_id=viaje['id'])

    # Si no hay viaje activo, lo mandamos a buscar viajes nuevos
    return redirect("/viajes_disponibles")


# -----------------solicitar ser conductor --------------------
@app.route('/solicitar_conductor')
def solicitar_conductor():
    if not session.get("user_id"):
        return redirect("/")

    conn = get_db()

    conn.execute("""
        UPDATE usuarios 
        SET solicitud_conductor=1 
        WHERE id=?
    """, (session["user_id"],))

    conn.commit()
    conn.close()

    return "Solicitud enviada ✅"

# --------------------viaje disponible  ------------------------
@app.route("/viajes_disponibles")
def viajes_disponibles():
    if session.get("tipo") != "conductor":
        return redirect("/")
    return render_template("viajes.html")

# ---------------------- LÓGICA DE VIAJES ----------------------

@app.route("/pedir_viaje", methods=["POST"])
def pedir_viaje():
    cliente_id = session.get("user_id")
    if not cliente_id:
        return redirect("/")

    conn = get_db()
    viaje_activo = conn.execute("""
        SELECT id FROM viajes 
        WHERE cliente_id = ? AND estado != 'finalizado' AND estado != 'cancelado'
    """, (cliente_id,)).fetchone()

    if viaje_activo:
        conn.close()
        return redirect("/cliente?error=viaje_en_curso")

    origen = request.form.get("origen") 
    destino = request.form.get("destino")
    lat = request.form.get("lat")
    lng = request.form.get("lng")
    lat_destino = request.form.get("lat_destino")
    lng_destino = request.form.get("lng_destino")

    conn.execute("""
        INSERT INTO viajes (cliente_id, estado, origen, destino, lat, lng, lat_destino, lng_destino)
        VALUES (?, 'pendiente', ?, ?, ?, ?, ?, ?)
    """, (cliente_id, origen, destino, lat, lng, lat_destino, lng_destino))
    conn.commit()
    conn.close()
    return redirect("/cliente")

@app.route("/cancelar_viaje/<int:id>")
def cancelar_viaje(id):
    if not session.get("user_id"):
        return redirect("/")

    conn = get_db()
    viaje = conn.execute("SELECT * FROM viajes WHERE id=?", (id,)).fetchone()
    if viaje and viaje["estado"] == "pendiente":
        conn.execute("UPDATE viajes SET estado='cancelado' WHERE id=?", (id,))
        conn.commit()
    conn.close()
    return redirect("/cliente?cancelado=1")
# --------- aceotar viaje   -------------------------

@app.route('/aceptar_viaje/<int:id>')
def aceptar_viaje(id):
    # 1. Verificación de sesión
    if not session.get("user_id"): 
        return redirect("/")
    
    conductor_id = session.get("user_id")
    
    conn = get_db()
    try:
        # 2. Validación: Solo aceptar si el viaje sigue 'pendiente'
        # Esto evita errores si otro conductor lo ganó primero
        viaje_pendiente = conn.execute(
            "SELECT id FROM viajes WHERE id = ? AND estado = 'pendiente'", 
            (id,)
        ).fetchone()

        if viaje_pendiente:
            # 3. Actualización de estado a 'en_curso'
            conn.execute("""
                UPDATE viajes 
                SET estado = 'en_curso', 
                    conductor_id = ?
                WHERE id = ?
            """, (conductor_id, id))
            conn.commit()
            
            # 4. Sincronizamos la sesión para que el mapa sepa qué ID rastrear
            session['viaje_id'] = id
        else:
            # Si el viaje ya no está pendiente, lo mandamos de regreso
            return redirect("/viajes_disponibles?error=ya_tomado")

    except Exception as e:
        print(f"Error al aceptar viaje: {e}")
        conn.rollback()
    finally:
        conn.close()
    
    # 5. Redirección final a la vista del conductor donde se carga el mapa
    return redirect('/conductor')

# ---------------------- APIS ----------------------
@app.route("/api_viajes")
def api_viajes():
    conn = get_db()
    # 🔥 AJUSTE 3: Esta es la clave para el mapa del conductor
    # Buscamos si el conductor ya tiene un viaje aceptado
    viaje_activo = conn.execute("""
        SELECT id, estado, origen, destino, lat, lng, lat_destino, lng_destino 
        FROM viajes 
        WHERE conductor_id = ? AND estado IN ('aceptado', 'en_camino', 'recogido', 'en_curso')
        ORDER BY id DESC LIMIT 1
    """, (session.get("user_id"),)).fetchone()

    viajes_pendientes = conn.execute("""
        SELECT id, estado, origen, destino, lat, lng, lat_destino, lng_destino 
        FROM viajes 
        WHERE estado='pendiente'
    """).fetchall()
    conn.close()

    return jsonify({
        "viajes": [dict(v) for v in viajes_pendientes],
        "viaje_activo": dict(viaje_activo) if viaje_activo else None
    })
@app.route("/api_estado_viaje/<int:id>")
def api_estado_viaje(id):
    conn = get_db()
    # Hacemos un JOIN para traer el nombre real del conductor desde la tabla usuarios
    v = conn.execute("""
        SELECT v.estado, u.nombre as nombre_real 
        FROM viajes v
        LEFT JOIN usuarios u ON v.conductor_id = u.id
        WHERE v.id = ?
    """, (id,)).fetchone()
    conn.close()

    if v:
        # Si hay un nombre en la tabla usuarios, lo mostramos; si no, "Buscando..."
        nombre_mostrar = v["nombre_real"] if v["nombre_real"] else "Asignando..."
        
        return jsonify({
            "estado": v["estado"],
            "conductor": nombre_mostrar
        })
    
    return jsonify({"estado": "no_encontrado"}), 404

@app.route("/actualizar_ubicacion", methods=["POST"])
def actualizar_ubicacion():
    if "user_id" not in session: return "No autorizado", 401
    lat, lng = request.form.get("lat"), request.form.get("lng")
    conn = get_db()
    conn.execute("UPDATE usuarios SET lat=?, lng=? WHERE id=?", (lat, lng, session["user_id"]))
    conn.commit()
    conn.close()
    return "OK"

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ... (Mantenemos tus rutas de ADMIN igual como estaban) ...

@app.route("/admin_login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        password = request.form["password"]
        conn = get_db()
        admin = conn.execute("SELECT * FROM admin LIMIT 1").fetchone()
        conn.close()
        if admin and check_password_hash(admin["password"], password):
            session["admin"] = True
            return redirect("/admin")
        else:
            return redirect("/admin_login?error=1")
    return render_template("admin_login.html")
# ------------------ruta admin -------------------------------------
@app.route("/admin")
def admin():
    if not session.get("admin"):
        return redirect("/admin_login")

    conn = get_db()

    conductores = conn.execute("""
        SELECT * FROM usuarios WHERE tipo='conductor'
    """).fetchall()

    solicitudes = conn.execute("""
        SELECT * FROM usuarios WHERE solicitud_conductor=1
    """).fetchall()

    conn.close()

    return render_template("admin.html", conductores=conductores, solicitudes=solicitudes)
@app.route("/aprobar/<int:id>")
def aprobar(id):
    if not session.get("admin"):
        return redirect("/admin_login")

    conn = get_db()

    conn.execute("""
        UPDATE usuarios 
        SET tipo='conductor', activo=1, solicitud_conductor=0
        WHERE id=?
    """, (id,))

    conn.commit()
    conn.close()

    return redirect("/admin")


# [EL RESTO DE TUS RUTAS DE ADMIN SE MANTIENEN IGUAL]

if __name__ == "__main__":
    with app.app_context():
        crear_tablas() 
    app.run(debug=False)