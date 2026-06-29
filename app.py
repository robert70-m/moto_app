import os
import sys
import sqlite3
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = "secreto_muy_seguro_mi_bike_app_macuil"

# ---------------------- DECORADORES Y SEGURIDAD ----------------------
def requiere_conductor_activo(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        user_id = session.get("user_id")

        if not user_id:
            return redirect(url_for("login"))

        if not rol("conductor"):
            return redirect(url_for("login"))

        if not conductor_activo(user_id):
            return "Tu cuenta está bloqueada o inactiva", 403

        return f(*args, **kwargs)
    return wrapper

def es_admin():
    """Verifica de forma segura si el usuario actual es administrador."""
    return session.get("tipo") == "admin"

def rol(r):
    tipo = session.get("tipo")
    if not tipo:
        return False
    return tipo.strip().lower() == r.strip().lower()

def conductor_activo(user_id):
    conn = get_db()
    user = conn.execute(
        "SELECT activo FROM usuarios WHERE id=?",
        (user_id,)
    ).fetchone()
    conn.close()
    return True if (user and user["activo"] == 1) else False

# ---------------------- BASE DE DATOS (SQLITE) ----------------------
def resource_path(relative_path):
    """Obtiene ruta correcta tanto en .py como en .exe con PyInstaller"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

DB_PATH = resource_path("database.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
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
        numero_unidad TEXT,
        color_vehiculo TEXT,
        lat REAL,
        lng REAL,
        activo INTEGER DEFAULT 1,
        fecha_pago TEXT
    )""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS viajes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cliente_id INTEGER,
        conductor_id INTEGER,
        estado TEXT,
        origen TEXT,
        destino TEXT,
        lat REAL,
        lng REAL,
        lat_destino REAL,
        lng_destino REAL,
        comision_pagada INTEGER DEFAULT 0
    )""")

    conn.commit()
    conn.close()

crear_tablas()

# ---------------------- AUTENTICACIÓN (LOGIN/LOGOUT) ----------------------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "GET" and "user_id" in session:
        tipo_sesion = session.get("tipo", "").lower().strip()
        if tipo_sesion == "admin":
            return redirect(url_for("admin"))
        elif tipo_sesion == "conductor":
            return redirect(url_for("conductor"))
        else:
            return redirect(url_for("cliente"))

    error = None

    if request.method == "POST":
        telefono = request.form.get("telefono", "").strip()
        password = request.form.get("password", "").strip()

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM usuarios WHERE telefono=?",
            (telefono,)
        ).fetchone()

        if user:
            if user["activo"] == 0:
                conn.close()
                error = "Usuario bloqueado o inactivo"
                return render_template("login.html", error=error)

            password_db = user["password"]

            # Caso con Hash
            if password_db.startswith("scrypt:") or password_db.startswith("pbkdf2:"):
                if not check_password_hash(password_db, password):
                    conn.close()
                    error = "Teléfono o contraseña incorrectos"
                    return render_template("login.html", error=error)
            # Caso en Texto Plano (Migración segura)
            else:
                if password_db != password:
                    conn.close()
                    error = "Teléfono o contraseña incorrectos"
                    return render_template("login.html", error=error)

                hash_nuevo = generate_password_hash(password)
                conn.execute(
                    "UPDATE usuarios SET password=? WHERE id=?",
                    (hash_nuevo, user["id"])
                )
                conn.commit()

            session.clear()
            session["user_id"] = user["id"]
            session["nombre"] = user["nombre"]
            session["telefono"] = user["telefono"]
            tipo_usuario = str(user["tipo"]).lower().strip()
            session["tipo"] = tipo_usuario
            conn.close()

            if tipo_usuario == "admin":
                return redirect(url_for("admin"))
            elif tipo_usuario == "conductor":
                return redirect(url_for("conductor"))
            else:
                return redirect(url_for("cliente"))
        else:
            conn.close()
            error = "Teléfono o contraseña incorrectos"

    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ---------------------- REGISTROS ----------------------
@app.route("/registro", methods=["GET", "POST"])
def registro():
    if request.method == "POST":
        nombre = request.form.get("nombre")
        tel = request.form.get("telefono")
        pwd = request.form.get("password")
        tipo = request.form.get("tipo")

        conn = get_db()
        if conn.execute("SELECT id FROM usuarios WHERE telefono=?", (tel,)).fetchone():
            conn.close()
            return "Teléfono ya registrado"

        # Guardado con hash desde el inicio
        hash_pwd = generate_password_hash(pwd)
        conn.execute(
            "INSERT INTO usuarios (nombre, telefono, password, tipo) VALUES (?, ?, ?, ?)",
            (nombre, tel, hash_pwd, tipo)
        )
        conn.commit()
        conn.close()
        return redirect(url_for("login"))

    return render_template("registro.html")

@app.route("/registro_conductor", methods=["GET", "POST"])
def registro_conductor():
    if request.method == "POST":
        n = request.form.get("nombre")
        t = request.form.get("telefono")
        p = request.form.get("password")
        u = request.form.get("numero_unidad")
        c = request.form.get("color_vehiculo")

        conn = get_db()
        if conn.execute("SELECT id FROM usuarios WHERE telefono=?", (t,)).fetchone():
            conn.close()
            return "Teléfono ya registrado"

        hash_p = generate_password_hash(p)
        conn.execute("""
            INSERT INTO usuarios (nombre, telefono, password, tipo, numero_unidad, color_vehiculo)
            VALUES (?, ?, ?, 'conductor', ?, ?)
        """, (n, t, hash_p, u, c))

        conn.commit()
        conn.close()
        return redirect(url_for("login"))

    return render_template("registro_conductor.html")

# ---------------------- PANEL CONDUCTOR ----------------------
@app.route("/conductor")
def conductor():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("tipo") != "conductor":
        return "No autorizado", 403

    user_id = session["user_id"]

    if not conductor_activo(user_id):
        return render_template(
            "conductor.html",
            viaje=None,
            viajes_pendientes=[],
            total_viajes=0,
            id_viaje_activo=0,
            mensaje_error="Tu cuenta está inactiva. Realiza tu pago para ver viajes."
        )

    conn = get_db()
    viaje_row = conn.execute("""
        SELECT * FROM viajes
        WHERE conductor_id=?
        AND estado IN ('aceptado','en_camino','recogido','cerca')
        ORDER BY id DESC LIMIT 1
    """, (user_id,)).fetchone()

    viajes_pendientes_rows = conn.execute("""
        SELECT * FROM viajes WHERE estado='pendiente' ORDER BY id DESC
    """).fetchall()

    total_viajes = conn.execute("""
        SELECT COUNT(*) FROM viajes
        WHERE conductor_id=? AND estado='finalizado' AND comision_pagada = 0
    """, (user_id,)).fetchone()[0]
    conn.close()

    viaje = dict(viaje_row) if viaje_row else None
    id_viaje = viaje["id"] if viaje else 0

    if viaje:
        viaje["lat"] = float(viaje.get("lat") or 0)
        viaje["lng"] = float(viaje.get("lng") or 0)
        viaje["lat_destino"] = float(viaje.get("lat_destino") or 0)
        viaje["lng_destino"] = float(viaje.get("lng_destino") or 0)

    return render_template(
        "conductor.html",
        viaje=viaje,
        viajes_pendientes=viajes_pendientes_rows,
        total_viajes=total_viajes,
        id_viaje_activo=id_viaje
    )

@app.route("/viajes_disponibles")
def viajes_disponibles():
    if not rol("conductor"):
        return redirect("/")

    user_id = session.get("user_id")
    if not conductor_activo(user_id):
        return render_template(
            "viajes.html", 
            viaje_activo=None, 
            viajes=[], 
            mensaje_error="Tu cuenta está inactiva. Realiza tu pago para ver viajes."
        )

    conn = get_db()
    viaje_activo_row = conn.execute("""
        SELECT * FROM viajes
        WHERE conductor_id=? AND estado IN ('aceptado', 'en_camino', 'recogido', 'cerca')
        ORDER BY id DESC LIMIT 1
    """, (user_id,)).fetchone()

    if viaje_activo_row:
        conn.close()
        return render_template(
            "viajes.html",
            viaje_activo=dict(viaje_activo_row),
            viajes=None
        )

    viajes_rows = conn.execute("""
        SELECT * FROM viajes WHERE estado = 'pendiente' ORDER BY id DESC
    """).fetchall()
    conn.close()

    return render_template(
        "viajes.html",
        viajes=[dict(v) for v in viajes_rows],
        viaje_activo=None
    )

# ---------------------- FLUJO Y PROGRESO DE VIAJES ----------------------
@app.route("/aceptar_viaje/<int:id>", methods=["POST"])
def aceptar_viaje(id):
    try:
        if not rol("conductor"):
            return jsonify({"status": "error", "message": "No autorizado"}), 401

        user_id = session.get("user_id")
        conn = get_db()

        viaje = conn.execute("SELECT estado FROM viajes WHERE id = ?", (id,)).fetchone()
        if not viaje:
            conn.close()
            return jsonify({"status": "error", "message": "El viaje ya no existe"}), 200

        if viaje["estado"] == "cancelado":
            conn.close()
            return jsonify({"status": "error", "message": "El cliente canceló el viaje"}), 200

        cursor = conn.execute("""
            UPDATE viajes 
            SET conductor_id=?, estado='aceptado' 
            WHERE id=? AND estado='pendiente'
        """, (user_id, id))
        conn.commit()
        conn.close()

        if cursor.rowcount == 0:
            return jsonify({"status": "error", "message": "Ya lo tomó otro conductor"}), 200

        return jsonify({"status": "ok", "message": "Viaje aceptado"})
    except Exception as e:
        return jsonify({"status": "error", "message": "Error interno del servidor"}), 200

@app.route("/aceptar_viaje_ajax/<int:id>", methods=["POST"])
def aceptar_viaje_ajax(id):
    if not rol("conductor"):
        return jsonify({"ok": False})

    user_id = session.get("user_id")
    conn = get_db()

    activo = conn.execute("""
        SELECT id FROM viajes WHERE conductor_id=? AND estado IN ('aceptado','en_camino','recogido') LIMIT 1
    """, (user_id,)).fetchone()

    if activo:
        conn.close()
        return jsonify({"ok": False, "error": "Ya tienes un viaje activo"})

    conn.execute("""
        UPDATE viajes SET conductor_id=?, estado='aceptado' WHERE id=? AND estado='pendiente'
    """, (user_id, id))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/cambiar_estado_viaje/<int:id>/<nuevo_estado>", methods=["POST"])
def cambiar_estado_viaje(id, nuevo_estado):
    if not rol("conductor"):
        return jsonify({"status": "error", "message": "No autorizado"}), 403

    user_id = session.get("user_id")
    conn = get_db()
    viaje = conn.execute("SELECT estado FROM viajes WHERE id=? AND conductor_id=?", (id, user_id)).fetchone()

    if not viaje:
        conn.close()
        return jsonify({"status": "error", "message": "Viaje no encontrado"}), 404

    transiciones = {
        "aceptado": "en_camino",
        "en_camino": "recogido",
        "recogido": "finalizado"
    }
    estado_actual = viaje["estado"]

    if estado_actual not in transiciones or transiciones[estado_actual] != nuevo_estado:
        conn.close()
        return jsonify({"status": "error", "message": f"Transición no permitida"}), 400

    try:
        conn.execute("UPDATE viajes SET estado=? WHERE id=?", (nuevo_estado, id))
        conn.commit()
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        conn.close()

    return jsonify({"status": "ok", "nuevo_estado": nuevo_estado})

@app.route("/finalizar_viaje/<int:viaje_id>")
def finalizar_viaje(viaje_id):
    if not rol("conductor"):
        return redirect(url_for("login"))
    
    conn = get_db()
    conn.execute("UPDATE viajes SET estado='finalizado' WHERE id=? AND conductor_id=?", (viaje_id, session.get("user_id")))
    conn.commit()
    conn.close()
    return redirect(url_for("conductor"))

# ---------------------- OPERACIONES DEL CLIENTE ----------------------
@app.route("/cliente")
def cliente():
    if not rol("cliente"):
        return redirect(url_for("login"))

    user_id = session.get("user_id")
    conn = get_db()
    viaje = conn.execute("""
        SELECT id FROM viajes WHERE cliente_id=? AND estado NOT IN ('finalizado','cancelado') ORDER BY id DESC LIMIT 1
    """, (user_id,)).fetchone()
    conn.close()

    viaje_id = viaje["id"] if viaje else None
    return render_template("cliente.html", viaje_id=viaje_id)

@app.route("/pedir_viaje", methods=["POST"])
def pedir_viaje():
    if not rol("cliente"):
        return redirect(url_for("login"))

    conn = get_db()
    existente = conn.execute("""
        SELECT id FROM viajes WHERE cliente_id=? AND estado NOT IN ('finalizado','cancelado')
    """, (session["user_id"],)).fetchone()

    if existente:
        conn.close()
        return redirect(url_for("cliente"))

    d = request.form
    try:
        lat, lng = float(d.get("lat", 0)), float(d.get("lng", 0))
        lat_d, lng_d = float(d.get("lat_destino", 0)), float(d.get("lng_destino", 0))
    except ValueError:
        lat, lng, lat_d, lng_d = 0.0, 0.0, 0.0, 0.0

    conn.execute("""
        INSERT INTO viajes (cliente_id, estado, origen, destino, lat, lng, lat_destino, lng_destino)
        VALUES (?, 'pendiente', ?, ?, ?, ?, ?, ?)
    """, (session["user_id"], d.get("origen", ""), d.get("destino", ""), lat, lng, lat_d, lng_d))
    conn.commit()
    conn.close()
    return redirect(url_for("cliente"))

@app.route("/cancelar_viaje/<int:viaje_id>", methods=['GET', 'POST'])
def cancelar_viaje(viaje_id):
    conn = get_db()
    viaje = conn.execute("SELECT estado FROM viajes WHERE id=?", (viaje_id,)).fetchone()
    
    if viaje and viaje['estado'] == 'pendiente':
        conn.execute("UPDATE viajes SET estado='cancelado' WHERE id=?", (viaje_id,))
        conn.commit()
        session.pop('viaje_id', None)
        conn.close()
        return redirect(url_for("cliente"))
    
    conn.close()
    return redirect(url_for("cliente", error="No se pudo cancelar o ya fue aceptado"))

# ---------------------- PANEL DE ADMINISTRACIÓN ----------------------
@app.route("/admin")
def admin():
    if session.get("tipo") != "admin":
        return "Acceso denegado", 403

    conn = get_db()
    try:
        conn.execute("SELECT comision_pagada FROM viajes LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE viajes ADD COLUMN comision_pagada INTEGER DEFAULT 0")
        conn.commit()

    conductores_db = conn.execute("SELECT * FROM usuarios WHERE tipo='conductor'").fetchall()
    lista = []
    hoy = datetime.now()

    for c in conductores_db:
        c = dict(c)
        if c["fecha_pago"]:
            fecha_pago = datetime.strptime(c["fecha_pago"], "%Y-%m-%d")
            dias = 7 - (hoy - fecha_pago).days

            if dias <= 0:
                c["dias_restantes"] = "Vencido"
                c["activo"] = 0
                conn.execute("UPDATE usuarios SET activo=0 WHERE id=?", (c["id"],))
            else:
                c["dias_restantes"] = dias
        else:
            c["dias_restantes"] = "Sin pago"
            c["activo"] = 0

        total_viajes = conn.execute("""
            SELECT COUNT(*) FROM viajes WHERE conductor_id=? AND estado='finalizado' AND comision_pagada = 0
        """, (c["id"],)).fetchone()[0]

        c["total_viajes"] = total_viajes
        c["comision"] = total_viajes * 3
        lista.append(c)

    conn.commit()
    conn.close()
    return render_template("admin.html", conductores=lista)

# Cambiamos la URL para que use "procesar_reinicio_conductor" igual que la función y tu HTML:
@app.route("/admin/procesar_reinicio_conductor/<int:id_conductor>", methods=["POST"])
def procesar_reinicio_conductor(id_conductor):
    if session.get("tipo") != "admin":
        return "Acceso denegado", 403

    hoy_str = datetime.now().strftime("%Y-%m-%d")
    conn = get_db()

    try:
        # 1. Marcamos todos sus viajes finalizados actuales como pagados
        conn.execute("""
            UPDATE viajes 
            SET comision_pagada = 1 
            WHERE conductor_id = ? AND estado = 'finalizado'
        """, (id_conductor,))

        # 2. Le renovamos sus 7 días de suscripción poniéndole la fecha de hoy
        conn.execute("""
            UPDATE usuarios 
            SET activo = 1, fecha_pago = ? 
            WHERE id = ?
        """, (hoy_str, id_conductor))

        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Error al reiniciar viajes: {e}")
    finally:
        conn.close()

    return redirect(url_for("admin"))

@app.route('/pagar_conductor/<int:id>')
def pagar_conductor(id):
    if not es_admin():
        return redirect(url_for('login'))
    conn = get_db()
    fecha_hoy = datetime.now().strftime("%Y-%m-%d")
    conn.execute("UPDATE usuarios SET fecha_pago = ?, activo = 1 WHERE id = ?", (fecha_hoy, id))
    conn.commit()
    conn.close()
    return redirect(url_for('admin'))

@app.route("/toggle_conductor/<int:id>")
def toggle_conductor(id):
    if session.get('tipo') != 'admin':
        return redirect(url_for('login'))
    conn = get_db()
    conductor = conn.execute('SELECT activo FROM usuarios WHERE id = ?', (id,)).fetchone()
    if conductor:
        nuevo_estado = 0 if conductor['activo'] == 1 else 1
        conn.execute('UPDATE usuarios SET activo = ? WHERE id = ?', (nuevo_estado, id))
        conn.commit()
    conn.close()
    return redirect(url_for('admin'))

# ---------------------- MÓDULOS RESET DE SEGURIDAD ----------------------
@app.route("/reset_conductores")
def reset_conductores():
    if not es_admin(): return "Acceso denegado", 403
    conn = get_db()
    conn.execute("DELETE FROM usuarios WHERE tipo = 'conductor'")
    conn.commit(); conn.close()
    return redirect(url_for('admin'))

@app.route("/reset_clientes")
def reset_clientes():
    if not es_admin(): return "Acceso denegado", 403
    conn = get_db()
    conn.execute("DELETE FROM usuarios WHERE tipo = 'cliente'")
    conn.commit(); conn.close()
    return redirect(url_for('admin'))

@app.route("/reset_viajes")
def reset_viajes():
    if not es_admin(): return "Acceso denegado", 403
    conn = get_db()
    conn.execute("DELETE FROM viajes")
    conn.commit(); conn.close()
    return redirect(url_for('admin'))

@app.route("/admin/cambiar_password", methods=["POST"])
def cambiar_password():
    if "user_id" not in session or session.get("tipo") != "admin":
        return redirect(url_for("login"))
    nueva = request.form.get("nueva_password", "").strip()
    confirmar = request.form.get("confirmar_password", "").strip()

    if nueva != confirmar or len(nueva) < 6:
        return "Error en validación de contraseña"

    hash_nuevo = generate_password_hash(nueva)
    conn = get_db()
    conn.execute("UPDATE usuarios SET password=? WHERE id=?", (hash_nuevo, session["user_id"]))
    conn.commit(); conn.close()
    return redirect(url_for("admin"))

# ---------------------- APIS DE CONSULTA TELEMÉTRICA ----------------------
@app.route("/api_viajes")
def api_viajes():
    conn = get_db()
    viajes = conn.execute("SELECT * FROM viajes").fetchall()
    conn.close()
    return jsonify({"viajes": [dict(v) for v in viajes]})

@app.route("/actualizar_ubicacion", methods=["POST"])
def actualizar_ubicacion():
    if "user_id" not in session: return "", 403
    conn = get_db()
    conn.execute("UPDATE usuarios SET lat=?, lng=? WHERE id=?", (request.form.get("lat"), request.form.get("lng"), session["user_id"]))
    conn.commit(); conn.close()
    return "", 200

@app.route("/api/viaje_cliente")
def api_viaje_cliente():
    user_id = session.get("user_id")
    if not user_id: return jsonify({"viaje": None})
    conn = get_db()
    viaje = conn.execute("SELECT * FROM viajes WHERE cliente_id=? AND estado != 'finalizado' ORDER BY id DESC LIMIT 1", (user_id,)).fetchone()
    conn.close()
    return jsonify({"viaje": dict(viaje) if viaje else None})

@app.route("/api_estado_viaje/<int:viaje_id>")
def api_estado_viaje(viaje_id):
    conn = get_db()
    viaje = conn.execute("""
        SELECT v.estado, u.nombre, u.numero_unidad, u.color_vehiculo, u.lat, u.lng
        FROM viajes v LEFT JOIN usuarios u ON v.conductor_id = u.id WHERE v.id = ?
    """, (viaje_id,)).fetchone()
    conn.close()

    if not viaje:
        session.pop('viaje_id', None)
        return jsonify({"estado": "no_existe"})

    if viaje["estado"] in ["cancelado", "finalizado"]:
        session.pop('viaje_id', None)

    return jsonify({
        "estado": viaje["estado"],
        "nombre": viaje["nombre"] or "Buscando conductor...",
        "unidad": viaje["numero_unidad"] or "---",
        "color": viaje["color_vehiculo"] or "---",
        "lat": viaje["lat"],
        "lng": viaje["lng"]
    })

@app.route("/api/verificar_viajes")
def api_verificar_viajes():
    if not conductor_activo(session.get("user_id")): return jsonify({"hay_viajes": False})
    conn = get_db()
    viaje = conn.execute("SELECT id FROM viajes WHERE estado='pendiente'").fetchone()
    conn.close()
    return jsonify({"hay_viajes": True if viaje else False})

@app.route("/api_verificar_status_viaje/<int:viaje_id>")
def api_verificar_status_viaje(viaje_id):
    conn = get_db()
    viaje = conn.execute("SELECT estado, conductor_id FROM viajes WHERE id = ?", (viaje_id,)).fetchone()
    conn.close()
    return jsonify({"status": "eliminado"} if not viaje else {"estado": viaje["estado"], "conductor_id": viaje["conductor_id"]})

@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return response

if __name__ == "__main__":
    app.run(debug=True)