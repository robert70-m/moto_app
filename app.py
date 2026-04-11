from flask import Flask, render_template, request, redirect, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
base_dir = os.path.abspath(os.path.dirname(__file__))
template_dir = os.path.join(base_dir, 'templates')

app = Flask(__name__)
app.secret_key = "mi primera la app de  servicio de moto mas efecinete"

ADMIN_PASSWORD = "admin1"  # cámbiala por la que quieras

# ---------------------- BASE DE DATOS ----------------------
def get_db():
    # Ruta absoluta para que PythonAnywhere siempre lo encuentre
    conn = sqlite3.connect("/home/robert70/motos-app/database.db")
    conn.row_factory = sqlite3.Row  
    return conn

def crear_tablas():
    conn = get_db()
    cursor = conn.cursor()

    # TABLA USUARIOS
    cursor.execute("""
    # TABLA USUARIOS (Añadimos 'activo' y 'fecha_pago' que faltaban)
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

    # TABLA VIAJES (Aseguramos que tenga nombre_conductor)
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

            # 🔥 VALIDACIÓN NUEVA (AQUÍ EXACTO)
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
# ----------------------------------------------------------------

@app.route("/registro", methods=["GET", "POST"])
def registro():
    if request.method == "POST":
        nombre = request.form["nombre"].strip()
        telefono = request.form["telefono"].strip()
        password = request.form["password"].strip()
        tipo = request.form["tipo"].strip()

        conn = get_db()
        conn.execute("INSERT INTO usuarios (nombre, telefono, password, tipo) VALUES (?, ?, ?, ?)", 
                     (nombre, telefono, password, tipo))
        conn.commit()
        conn.close()
        return redirect("/")
    return render_template("registro.html")

# ---------------------- VISTAS PRINCIPALES ----------------------

@app.route("/cliente")
def cliente():
    if session.get("tipo") != "cliente":
        return redirect("/")

    cliente_id = session.get("user_id")
    conn = get_db()

    # 🔥 SOLO viajes realmente activos
    viaje = conn.execute("""
        SELECT id, estado FROM viajes 
        WHERE cliente_id = ? 
        AND estado IN ('pendiente','aceptado','en_camino','recogido')
        ORDER BY id DESC LIMIT 1
    """, (cliente_id,)).fetchone()

    conn.close()

    viaje_id = viaje["id"] if viaje else None
    estado = viaje["estado"] if viaje else None

    return render_template("cliente.html", viaje_id=viaje_id, estado=estado)
# -----------------------------------------------------------------
from datetime import datetime, timedelta
@app.route("/conductor")
def conductor():
    if not session.get("user_id") or session.get("tipo") != "conductor":
        return redirect("/")

    conn = get_db()

    user = conn.execute(
        "SELECT * FROM usuarios WHERE id=?",
        (session["user_id"],)
    ).fetchone()

    # VALIDAR VENCIMIENTO AUTOMÁTICO (Mantengo tu lógica intacta)
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

    # 🔥 MODIFICACIÓN: Traemos todos los datos del viaje activo para el mapa
    viaje = conn.execute("""
        SELECT id, lat, lng, lat_destino, lng_destino, origen, destino 
        FROM viajes 
        WHERE conductor_id = ? AND estado IN ('aceptado', 'en_camino', 'recogido')
        ORDER BY id DESC LIMIT 1
    """, (session["user_id"],)).fetchone()

    conn.close()

    if viaje:
        # Enviamos el objeto viaje completo al HTML
        return render_template("conductor.html", viaje=viaje, viaje_id=viaje['id'])

    return redirect("/viajes_disponibles")


# --------------- viaje disponible --------------------------------
@app.route("/viajes_disponibles")
def viajes_disponibles():
    if session.get("tipo") != "conductor":
        return redirect("/")
    return render_template("viajes.html")

# ---------------------- LÓGICA DE VIAJES ----------------------
from flask import Flask, render_template, request, redirect, session
from datetime import datetime
import sqlite3

@app.route("/pedir_viaje", methods=["POST"])
def pedir_viaje():
    cliente_id = session.get("user_id")
    if not cliente_id:
        return redirect("/")

    conn = get_db()
    
    # 🔥 VALIDAR SI YA TIENE VIAJE ACTIVO
    viaje_activo = conn.execute("""
        SELECT id FROM viajes 
        WHERE cliente_id = ? AND estado != 'finalizado'
    """, (cliente_id,)).fetchone()

    if viaje_activo:
        conn.close()
        return redirect("/cliente?error=viaje_en_curso")

    # 🔥 CREAR NUEVO VIAJE
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

# ---------------cancelar viaje ------------------------------------
@app.route("/cancelar_viaje/<int:id>")
def cancelar_viaje(id):
    if not session.get("user_id"):  # 🔥 CORREGIDO
        return redirect("/")        # 🔥 CORREGIDO

    conn = get_db()

    viaje = conn.execute(
        "SELECT * FROM viajes WHERE id=?",
        (id,)
    ).fetchone()

    if viaje and viaje["estado"] == "pendiente":
        conn.execute(
            "UPDATE viajes SET estado='cancelado' WHERE id=?",
            (id,)
        )
        conn.commit()

    conn.close()

    return redirect("/cliente?cancelado=1")

# ------------------ aceptar viaje ---------------------------------
@app.route("/aceptar_viaje/<int:viaje_id>")
def aceptar_viaje(viaje_id):
    if not session.get("user_id") or session.get("tipo") != "conductor":
        return redirect("/")

    id_conductor = session.get("user_id")
    nombre_conductor = session.get("nombre")

    conn = get_db()
    conn.execute("""
        UPDATE viajes 
        SET conductor_id = ?, nombre_conductor = ?, estado = 'aceptado' 
        WHERE id = ?
    """, (id_conductor, nombre_conductor, viaje_id))
    conn.commit()
    conn.close()
    return redirect("/conductor")
# -------------------------------------------------------------------
@app.route("/estado/<int:viaje_id>/<nuevo_estado>")
def cambiar_estado(viaje_id, nuevo_estado):
    if session.get("tipo") != "conductor":
        return "No autorizado", 403

    # Lista de estados que permitimos
    estados_validos = ["aceptado", "en_camino", "recogido", "finalizado"]
    if nuevo_estado not in estados_validos:
        return "Estado inválido", 400

    conn = get_db()
    # Actualizamos el viaje asegurándonos de que sea el viaje de ESTE conductor
    conn.execute("""
        UPDATE viajes 
        SET estado = ? 
        WHERE id = ? AND conductor_id = ?
    """, (nuevo_estado, viaje_id, session["user_id"]))
    
    conn.commit()
    conn.close()
    return "OK", 200
# ---------------------- APIS Y UBICACIÓN ----------------------
@app.route("/api_viajes")
def api_viajes():
    conn = get_db()
    viajes = conn.execute("""
        SELECT id, estado, origen, destino, lat, lng, lat_destino, lng_destino 
        FROM viajes 
        WHERE estado='pendiente'
    """).fetchall()
    conn.close()

    return jsonify({"viajes": [dict(v) for v in viajes]})


# -----------------------------------------------------------------
@app.route("/api_estado_viaje/<int:id>")
def api_estado_viaje(id):
    conn = get_db()
    # Traemos el estado y el nombre del conductor de la base de datos
    v = conn.execute("SELECT estado, nombre_conductor FROM viajes WHERE id = ?", (id,)).fetchone()
    conn.close()
    
    if v:
        return jsonify({
            "estado": v["estado"],
            "conductor": v["nombre_conductor"] if v["nombre_conductor"] else "Asignando..."
        })
    return jsonify({"estado": "no_encontrado"}), 404
# ---------------------------------------------------------------------
@app.route("/actualizar_ubicacion", methods=["POST"])
def actualizar_ubicacion():
    if "user_id" not in session: return "No autorizado", 401
    lat, lng = request.form.get("lat"), request.form.get("lng")
    conn = get_db()
    conn.execute("UPDATE usuarios SET lat=?, lng=? WHERE id=?", (lat, lng, session["user_id"]))
    conn.commit()
    conn.close()
    return "OK"
# ---------------------------------------------------------------
@app.route("/ubicacion_conductor/<int:viaje_id>")
def ubicacion_conductor(viaje_id):
    conn = get_db()
    viaje = conn.execute("SELECT conductor_id FROM viajes WHERE id=?", (viaje_id,)).fetchone()
    if not viaje or not viaje["conductor_id"]:
        conn.close()
        return jsonify({"lat": None, "lng": None})
    
    cond = conn.execute("SELECT nombre, lat, lng FROM usuarios WHERE id=?", (viaje["conductor_id"],)).fetchone()
    conn.close()
    return jsonify(dict(cond)) if cond else jsonify({"lat": None, "lng": None})
# -------------------------------------------------------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")
# -------------------------------------------------------------------
@app.route("/verificar_viajes")
def verificar_viajes():
    conn = get_db()

    viaje = conn.execute("""
        SELECT id FROM viajes 
        WHERE estado='pendiente'
        LIMIT 1
    """).fetchone()

    conn.close()

    return {"nuevo_viaje": bool(viaje)}

# ------------------ ruta admin  ------------------------------------

from datetime import datetime, timedelta

@app.route("/admin")
def admin():
    # 🔐 PROTECCIÓN
    if not session.get("admin"):
        return redirect("/admin_login")

    conn = get_db()

    conductores = conn.execute("""
        SELECT * FROM usuarios WHERE tipo='conductor'
    """).fetchall()

    lista = []

    for c in conductores:
        dias_restantes = "Sin pago"
        prioridad = 2  # valor por defecto (activos)

        if c["fecha_pago"]:
            fecha_pago = datetime.strptime(c["fecha_pago"], "%Y-%m-%d")
            vencimiento = fecha_pago + timedelta(days=7)
            dias = (vencimiento - datetime.now()).days

            if dias < 0:
                dias_restantes = "Vencido"
                prioridad = 0  # 🔴 más importante
            else:
                dias_restantes = f"{dias} días"
                prioridad = 2  # 🟢 normal
        else:
            prioridad = 1  # ⚪ sin pago

        c_dict = dict(c)
        c_dict["dias_restantes"] = dias_restantes
        c_dict["prioridad"] = prioridad

        lista.append(c_dict)

    conn.close()

    # 🔥 ORDENAR
    lista.sort(key=lambda x: x["prioridad"])

    return render_template("admin.html", conductores=lista)

# ---------------------  ruta toggle? conductor ---------------------
@app.route("/toggle_conductor/<int:id>")
def toggle_conductor(id):
    conn = get_db()

    user = conn.execute(
        "SELECT activo FROM usuarios WHERE id=?",
        (id,)
    ).fetchone()

    nuevo_estado = 0 if user["activo"] == 1 else 1

    conn.execute(
        "UPDATE usuarios SET activo=? WHERE id=?",
        (nuevo_estado, id)
    )

    conn.commit()
    conn.close()

    return redirect("/admin")
# --------------------------ruta pagar conductor ----------------
from datetime import datetime

@app.route("/pagar_conductor/<int:id>")
def pagar_conductor(id):
    conn = get_db()

    fecha = datetime.now().strftime("%Y-%m-%d")

    conn.execute("""
        UPDATE usuarios 
        SET activo=1, fecha_pago=? 
        WHERE id=?
    """, (fecha, id))

    conn.commit()
    conn.close()

    return redirect("/admin")
# ------------  admin login ------------------------------------
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
# -----------------------------------------------------------
@app.route("/admin_logout")
def admin_logout():
    session.clear()  # borra TODO (usuario + admin)
    return redirect("/admin_login")


# ---------- quitar despues temporal solo crea la tabla ---------

conn = get_db()

conn.execute("""
CREATE TABLE IF NOT EXISTS admin (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    password TEXT
)
""")

conn.commit()
conn.close()

# ----------------- quitar despues de ejjecutar -----------------

conn = get_db()

password_hash = generate_password_hash("admin1")

conn.execute("DELETE FROM admin")  # limpiar si ya había
conn.execute("INSERT INTO admin (password) VALUES (?)", (password_hash,))

conn.commit()
conn.close()

if __name__ == "__main__":
    # Esto solo se ejecuta en tu computadora (Local)
    with app.app_context():
        crear_tablas() 
    app.run(debug=False) # IMPORTANTE: debug en False para internet