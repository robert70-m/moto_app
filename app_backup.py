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
        fecha_pago TEXT,
        solicitud_conductor INTEGER DEFAULT 0
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

# ---------------------- LOGIN ----------------------
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
                error = "Cuenta suspendida ❌"
                return render_template("login.html", error=error)

            session["user_id"] = user["id"]
            session["tipo"] = user["tipo"]
            session["nombre"] = user["nombre"]

            return redirect("/cliente" if user["tipo"] == "cliente" else "/conductor")
        else:
            error = "Datos incorrectos ❌"

    return render_template("login.html", error=error)

# ---------------------- REGISTRO CLIENTE ----------------------
@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        conn = get_db()
        conn.execute("""
            INSERT INTO usuarios (nombre, telefono, password, tipo)
            VALUES (?, ?, ?, 'cliente')
        """, (
            request.form['nombre'],
            request.form['telefono'],
            request.form['password']
        ))
        conn.commit()
        conn.close()
        return redirect('/')

    return render_template("registro.html")

# ---------------------- CLIENTE ----------------------
@app.route("/cliente")
def cliente():
    if not session.get("tipo") == "cliente":
        return redirect("/")

    conn = get_db()
    viaje = conn.execute("""
        SELECT id, estado FROM viajes 
        WHERE cliente_id = ? 
        AND estado IN ('pendiente','aceptado','en_camino','recogido','en_curso')
        ORDER BY id DESC LIMIT 1
    """, (session["user_id"],)).fetchone()
    conn.close()

    return render_template("cliente.html",
                           viaje_id=viaje["id"] if viaje else None,
                           estado=viaje["estado"] if viaje else None)

# ---------------------- CONDUCTOR ----------------------
@app.route("/conductor")
def conductor():
    if not session.get("tipo") == "conductor":
        return redirect("/")

    conn = get_db()
    user = conn.execute("SELECT * FROM usuarios WHERE id=?", (session["user_id"],)).fetchone()

    if user["activo"] == 0:
        conn.close()
        return "Cuenta suspendida ❌"

    viaje = conn.execute("""
        SELECT * FROM viajes 
        WHERE conductor_id = ? 
        AND estado IN ('aceptado','en_camino','recogido','en_curso')
        ORDER BY id DESC LIMIT 1
    """, (session["user_id"],)).fetchone()

    conn.close()

    if viaje:
        return render_template("conductor.html", viaje=viaje)

    return redirect("/viajes_disponibles")  # (DEBE existir en tu sistema)

# ---------------------- PEDIR VIAJE ----------------------
@app.route("/pedir_viaje", methods=["POST"])
def pedir_viaje():
    if not session.get("user_id"):
        return redirect("/")

    conn = get_db()

    existe = conn.execute("""
        SELECT id FROM viajes 
        WHERE cliente_id=? AND estado NOT IN ('finalizado','cancelado')
    """, (session["user_id"],)).fetchone()

    if existe:
        conn.close()
        return redirect("/cliente?error=viaje_en_curso")

    conn.execute("""
        INSERT INTO viajes (cliente_id, estado, origen, destino, lat, lng, lat_destino, lng_destino)
        VALUES (?, 'pendiente', ?, ?, ?, ?, ?, ?)
    """, (
        session["user_id"],
        request.form.get("origen"),
        request.form.get("destino"),
        request.form.get("lat"),
        request.form.get("lng"),
        request.form.get("lat_destino"),
        request.form.get("lng_destino")
    ))

    conn.commit()
    conn.close()
    return redirect("/cliente")

# ---------------------- ACEPTAR VIAJE ----------------------
@app.route('/aceptar_viaje/<int:id>')
def aceptar_viaje(id):
    if not session.get("user_id"):
        return redirect("/")

    conn = get_db()

    disponible = conn.execute(
        "SELECT id FROM viajes WHERE id=? AND estado='pendiente'", (id,)
    ).fetchone()

    if disponible:
        conn.execute("""
            UPDATE viajes SET estado='en_curso', conductor_id=? WHERE id=?
        """, (session["user_id"], id))
        conn.commit()

    conn.close()
    return redirect("/conductor")

# ---------------------- API ----------------------
@app.route("/api_viajes")
def api_viajes():
    conn = get_db()

    activo = conn.execute("""
        SELECT * FROM viajes 
        WHERE conductor_id=? 
        AND estado IN ('aceptado','en_camino','recogido','en_curso')
        ORDER BY id DESC LIMIT 1
    """, (session.get("user_id"),)).fetchone()

    pendientes = conn.execute("SELECT * FROM viajes WHERE estado='pendiente'").fetchall()

    conn.close()

    return jsonify({
        "viajes": [dict(v) for v in pendientes],
        "viaje_activo": dict(activo) if activo else None
    })

@app.route("/api_estado_viaje/<int:id>")
def api_estado_viaje(id):
    conn = get_db()

    v = conn.execute("""
        SELECT v.estado, u.nombre 
        FROM viajes v
        LEFT JOIN usuarios u ON v.conductor_id = u.id
        WHERE v.id=?
    """, (id,)).fetchone()

    conn.close()

    if v:
        return jsonify({
            "estado": v["estado"],
            "conductor": v["nombre"] if v["nombre"] else "Asignando..."
        })

    return jsonify({"estado": "no_encontrado"})

# ---------------------- UBICACION ----------------------
@app.route("/actualizar_ubicacion", methods=["POST"])
def actualizar_ubicacion():
    if not session.get("user_id"):
        return "No autorizado", 403

    conn = get_db()
    conn.execute("UPDATE usuarios SET lat=?, lng=? WHERE id=?",
                 (request.form.get("lat"), request.form.get("lng"), session["user_id"]))
    conn.commit()
    conn.close()
    return "OK"

# ---------------------- LOGOUT ----------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ---------------------- ADMIN ----------------------
@app.route("/admin_login", methods=["GET","POST"])
def admin_login():
    if request.method == "POST":
        conn = get_db()
        admin = conn.execute("SELECT * FROM admin LIMIT 1").fetchone()
        conn.close()

        if admin and check_password_hash(admin["password"], request.form["password"]):
            session["admin"] = True
            return redirect("/admin")

    return render_template("admin_login.html")

@app.route("/admin")
def admin():
    if not session.get("admin"):
        return redirect("/admin_login")

    conn = get_db()
    conductores = conn.execute("SELECT * FROM usuarios WHERE tipo='conductor'").fetchall()
    solicitudes = conn.execute("SELECT * FROM usuarios WHERE solicitud_conductor=1").fetchall()
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

# ---------------------- REGISTRO CONDUCTOR (CORREGIDO) ----------------------
@app.route("/registro_conductor", methods=["GET", "POST"])
def registro_conductor():
    if request.method == "POST":
        nombre = request.form["nombre"]
        telefono = request.form["telefono"]
        password = request.form["password"]

        conn = get_db()
        conn.execute("""
            INSERT INTO usuarios (nombre, telefono, password, tipo)
            VALUES (?, ?, ?, 'conductor')
        """, (nombre, telefono, password))
        conn.commit()
        conn.close()

        return redirect("/")

    return render_template("registro_conductor.html")

# ---------------------- RUN ----------------------
if __name__ == "__main__":
    with app.app_context():
        crear_tablas()
    app.run(debug=False)