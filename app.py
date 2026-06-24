import os
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
app = Flask(__name__)
app.secret_key = "secreto_muy_seguro_mi_bike_app_macuil"

from functools import wraps
from flask import session, redirect, url_for

def requiere_conductor_activo(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        user_id = session.get("user_id")

        # Si no hay sesión
        if not user_id:
            return redirect(url_for("login"))

        # Si no es conductor
        if not rol("conductor"):
            return redirect(url_for("login"))

        # 🔒 Validar estado
        if not conductor_activo(user_id):
            return "Tu cuenta está bloqueada o inactiva", 403

        return f(*args, **kwargs)
    return wrapper

# ---------------------- DB ----------------------
import sys

def resource_path(relative_path):
    """Obtiene ruta correcta tanto en .py como en .exe"""
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
def rol(r):
    tipo = session.get("tipo")
    if not tipo:
        return False
    return tipo.strip().lower() == r.strip().lower()


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
        lng_destino REAL
    )""")

    conn.commit()
    conn.close()

crear_tablas()

# ---------------------- LOGIN ----------------------
from werkzeug.security import check_password_hash, generate_password_hash
from flask import request, session, redirect, url_for, render_template

@app.route("/", methods=["GET", "POST"])
def login():

    # --- 1. VALIDACIÓN DE SESIÓN ACTIVA ---
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

            # 🚫 VALIDACIÓN DE USUARIO ACTIVO (IMPORTANTE)
            if user["activo"] == 0:
                conn.close()
                error = "Usuario bloqueado o inactivo"
                return render_template("login.html", error=error)

            password_db = user["password"]

            # 🔐 CASO 1: contraseña con hash
            if password_db.startswith("scrypt:") or password_db.startswith("pbkdf2:"):
                if not check_password_hash(password_db, password):
                    conn.close()
                    error = "Teléfono o contraseña incorrectos"
                    return render_template("login.html", error=error)

            # 🟡 CASO 2: contraseña en texto plano
            else:
                if password_db != password:
                    conn.close()
                    error = "Teléfono o contraseña incorrectos"
                    return render_template("login.html", error=error)

                # 🔥 actualizar a hash automáticamente
                hash_nuevo = generate_password_hash(password)
                conn.execute(
                    "UPDATE usuarios SET password=? WHERE id=?",
                    (hash_nuevo, user["id"])
                )
                conn.commit()

            # --- SESIÓN ---
            session.clear()
            session["user_id"] = user["id"]
            session["nombre"] = user["nombre"]
            session["telefono"] = user["telefono"]

            tipo_usuario = str(user["tipo"]).lower().strip()
            session["tipo"] = tipo_usuario

            conn.close()

            # 🚀 REDIRECCIÓN SEGÚN ROL
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
# ---------------------- REGISTRO CLIENTE ----------------------
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

        conn.execute(
            "INSERT INTO usuarios (nombre, telefono, password, tipo) VALUES (?, ?, ?, ?)",
            (nombre, tel, pwd, tipo)
        )

        conn.commit()
        conn.close()
        return redirect(url_for("login"))

    return render_template("registro.html")

# ---------------------- REGISTRO CONDUCTOR ----------------------
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

        conn.execute("""
            INSERT INTO usuarios (nombre, telefono, password, tipo, numero_unidad, color_vehiculo)
            VALUES (?, ?, ?, 'conductor', ?, ?)
        """, (n, t, p, u, c))

        conn.commit()
        conn.close()
        return redirect(url_for("login"))

    return render_template("registro_conductor.html")
@app.route("/conductor")
def conductor():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("tipo") != "conductor":
        return "No autorizado", 403

    user_id = session["user_id"]

    # Validación de pago
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

    # Viaje activo del conductor
    viaje_row = conn.execute("""
        SELECT * FROM viajes
        WHERE conductor_id=?
        AND estado IN ('aceptado','en_camino','recogido','cerca')
        ORDER BY id DESC
        LIMIT 1
    """, (user_id,)).fetchone()

    # Viajes pendientes
    viajes_pendientes_rows = conn.execute("""
        SELECT *
        FROM viajes
        WHERE estado='pendiente'
        ORDER BY id DESC
    """).fetchall()

    # CONTADOR DE VIAJES FINALIZADOS (Corregido con comision_pagada = 0)
    total_viajes = conn.execute("""
        SELECT COUNT(*)
        FROM viajes
        WHERE conductor_id=?
        AND estado='finalizado'
        AND comision_pagada = 0
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
        id_viaje_activo=id_viaje  # <-- Pasamos el ID real al mapa
    )


# ---------------------- CLIENTE ----------------------
@app.route("/cliente")
def cliente():
    if not rol("cliente"):
        return redirect(url_for("login"))

    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    conn = get_db()
    viaje = conn.execute("""
        SELECT id FROM viajes
        WHERE cliente_id=? 
        AND estado NOT IN ('finalizado','cancelado')
        ORDER BY id DESC
        LIMIT 1
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
        SELECT id FROM viajes
        WHERE cliente_id=? AND estado NOT IN ('finalizado','cancelado')
    """, (session["user_id"],)).fetchone()

    if existente:
        conn.close()
        return redirect(url_for("cliente"))

    d = request.form

    # Manejo de errores en conversión numérica
    try:
        lat = float(d.get("lat", 0))
        lng = float(d.get("lng", 0))
        lat_d = float(d.get("lat_destino", 0))
        lng_d = float(d.get("lng_destino", 0))
    except ValueError:
        lat, lng, lat_d, lng_d = 0.0, 0.0, 0.0, 0.0

    conn.execute("""
        INSERT INTO viajes (cliente_id, estado, origen, destino, lat, lng, lat_destino, lng_destino)
        VALUES (?, 'pendiente', ?, ?, ?, ?, ?, ?)
    """, (
        session["user_id"],
        d.get("origen", ""),
        d.get("destino", ""),
        lat, lng, lat_d, lng_d
    ))

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
        
        # --- ESTO ES LO QUE DEBES ASEGURAR QUE ESTÉ ---
        from flask import session
        session.pop('viaje_id', None) # Borra el viaje de la memoria del cliente
        # ----------------------------------------------
        
        conn.close()
        return redirect(url_for("cliente"))
    
    conn.close()
    return redirect(url_for("cliente", error="No se pudo cancelar o ya fue aceptado"))

# ---------------------- CONDUCTOR ----------------------
@app.route("/estado_conductor")
def estado_conductor():
    print("SESSION:", dict(session))

    if session.get("tipo") != "conductor":
        return "Acceso denegado", 403

    conn = get_db()
    viaje = conn.execute("""
        SELECT * FROM viajes
        WHERE conductor_id=?
        AND estado IN ('aceptado','en_camino','recogido')
        ORDER BY id DESC LIMIT 1
    """, (session["user_id"],)).fetchone()
    conn.close()

    return render_template("conductor.html", viaje=dict(viaje) if viaje else None)
@app.route("/estado_conductor_v2")
def estado_conductor_v2():  # <--- CAMBIA ESTE NOMBRE
    print("SESSION:", dict(session))

    if session.get("tipo") != "conductor":
        return "Acceso denegado", 403

    conn = get_db()
    viaje = conn.execute("""
        SELECT * FROM viajes
        WHERE conductor_id=?
        AND estado IN ('aceptado','en_camino','recogido')
        ORDER BY id DESC LIMIT 1
    """, (session["user_id"],)).fetchone()
    conn.close()

    return render_template("conductor.html", viaje=dict(viaje) if viaje else None)
@app.route('/pagar_conductor/<int:id>')
def pagar_conductor(id):
    if not es_admin():
        return redirect(url_for('login'))

    try:
        conn = get_db()
        # Actualizamos la fecha de pago al día de hoy y reseteamos el estado
        fecha_hoy = datetime.now().strftime("%Y-%m-%d")

        conn.execute('''
            UPDATE usuarios
            SET fecha_pago = ?, activo = 1
            WHERE id = ?
        ''', (fecha_hoy, id))

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error en pago: {e}")
        return "Error interno al procesar el pago", 500

    return redirect(url_for('admin'))

@app.route("/viajes_disponibles")
def viajes_disponibles():
    # 1. Validación de rol
    if not rol("conductor"):
        return redirect("/")

    user_id = session.get("user_id")
    
    # 2. 🔒 VALIDACIÓN CRÍTICA: Solo conductores activos pueden ver viajes
    if not conductor_activo(user_id):
        return render_template(
            "viajes.html", 
            viaje_activo=None, 
            viajes=[], 
            mensaje_error="Tu cuenta está inactiva. Realiza tu pago para ver viajes."
        )

    conn = get_db()

    # 3. 🔒 Buscar si tiene viaje activo (ignora cancelados y finalizados)
    viaje_activo_row = conn.execute("""
        SELECT * FROM viajes
        WHERE conductor_id=?
        AND estado IN ('aceptado', 'en_camino', 'recogido', 'cerca')
        ORDER BY id DESC LIMIT 1
    """, (user_id,)).fetchone()

    if viaje_activo_row:
        conn.close()
        return render_template(
            "viajes.html",
            viaje_activo=dict(viaje_activo_row),
            viajes=None
        )

    # 4. ✅ Mostrar SOLO los que están realmente pendientes (limpia cancelados)
    viajes_rows = conn.execute("""
        SELECT * FROM viajes
        WHERE estado = 'pendiente'
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "viajes.html",
        viajes=[dict(v) for v in viajes_rows],
        viaje_activo=None
    )
from flask import jsonify # Asegúrate de tener esto importado arriba
@app.route("/aceptar_viaje/<int:id>", methods=["POST"])
def aceptar_viaje(id):
    try:
        if not rol("conductor"):
            return jsonify({"status": "error", "message": "No autorizado"}), 401

        user_id = session.get("user_id")
        conn = get_db()

        # Verificar si el viaje existe
        viaje = conn.execute("SELECT estado FROM viajes WHERE id = ?", (id,)).fetchone()
        
        if not viaje:
            conn.close()
            return jsonify({"status": "error", "message": "El viaje ya no existe"}), 200 # Usamos 200 para que el JS no brinque al catch

        if viaje["estado"] == "cancelado":
            conn.close()
            return jsonify({"status": "error", "message": "El cliente canceló el viaje"}), 200

        # Intentar el update
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
        print(f"Error: {e}")
        return jsonify({"status": "error", "message": "Error interno del servidor"}), 200

    # -------------------------------------------------------------------

    # 1. Verificar si ya tiene un viaje activo
    activo = conn.execute("""
        SELECT id FROM viajes 
        WHERE conductor_id=? 
        AND estado IN ('aceptado','en_camino','recogido','cerca')
        LIMIT 1
    """, (user_id,)).fetchone()

    if activo:
        conn.close()
        return jsonify({"status": "error", "message": "Ya tienes un viaje en curso"}), 400

    # 2. Intentar aceptar el viaje (Solo si sigue pendiente)
    cursor = conn.execute("""
        UPDATE viajes 
        SET conductor_id=?, estado='aceptado' 
        WHERE id=? AND estado='pendiente'
    """, (user_id, id))
    
    conn.commit()

    if cursor.rowcount == 0:
        conn.close()
        # Si llegamos aquí y no es cancelación, es porque otro conductor ganó
        return jsonify({"status": "error", "message": "El viaje ya fue tomado por otro conductor"}), 400

    conn.close()

    return jsonify({
        "status": "ok",
        "message": "Viaje aceptado"
    })
@app.route("/cambiar_estado_viaje/<int:id>/<nuevo_estado>", methods=["POST"])
def cambiar_estado_viaje(id, nuevo_estado):
    # 1. Verificación de sesión y rol
    if not rol("conductor"):
        return jsonify({"status": "error", "message": "No autorizado"}), 403

    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error", "message": "Sesión expirada"}), 403

    conn = get_db()
    
    # 2. Validar que el viaje existe y pertenece al conductor
    viaje = conn.execute("""
        SELECT estado FROM viajes 
        WHERE id=? AND conductor_id=?
    """, (id, user_id)).fetchone()

    if not viaje:
        conn.close()
        return jsonify({"status": "error", "message": "Viaje no encontrado"}), 404

    # 3. Lógica de transiciones
    # El estado 'pendiente' se maneja en 'aceptar_viaje_ajax'
    # Esta ruta maneja el progreso posterior
    transiciones = {
        "aceptado": "en_camino",
        "en_camino": "recogido",
        "recogido": "finalizado"
    }

    estado_actual = viaje["estado"]

    # Validar si el cambio solicitado es el siguiente paso lógico
    if estado_actual not in transiciones or transiciones[estado_actual] != nuevo_estado:
        conn.close()
        return jsonify({
            "status": "error", 
            "message": f"Transición no permitida de {estado_actual} a {nuevo_estado}"
        }), 400

    # 4. Actualizar
    try:
        conn.execute("UPDATE viajes SET estado=? WHERE id=?", (nuevo_estado, id))
        conn.commit()
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        conn.close()

    return jsonify({"status": "ok", "nuevo_estado": nuevo_estado})

# ---------------------- API ----------------------
@app.route("/api_viajes")
def api_viajes():
    conn = get_db()
    viajes = conn.execute("SELECT * FROM viajes").fetchall()
    conn.close()
    return jsonify({"viajes": [dict(v) for v in viajes]})

@app.route("/api/viaje_cliente")
def api_viaje_cliente():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"viaje": None})

    conn = get_db()
    viaje = conn.execute("""
        SELECT * FROM viajes
        WHERE cliente_id=? AND estado != 'finalizado'
        ORDER BY id DESC LIMIT 1
    """, (user_id,)).fetchone()
    conn.close()

    if viaje:
        return jsonify({"viaje": dict(viaje)})
    else:
        return jsonify({"viaje": None})
@app.route("/aceptar_viaje_ajax/<int:id>", methods=["POST"])
def aceptar_viaje_ajax(id):
    if not rol("conductor"):
        return jsonify({"ok": False})

    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"ok": False})

    conn = get_db()

    # 🔒 Verificar viaje activo
    activo = conn.execute("""
        SELECT id FROM viajes
        WHERE conductor_id=?
        AND estado IN ('aceptado','en_camino','recogido')
        LIMIT 1
    """, (user_id,)).fetchone()

    if activo:
        conn.close()
        return jsonify({
            "ok": False,
            "error": "Ya tienes un viaje activo"
        })

    conn.execute("""
        UPDATE viajes
        SET conductor_id=?, estado='aceptado'
        WHERE id=? AND estado='pendiente'
    """, (user_id, id))

    conn.commit()
    conn.close()

    return jsonify({"ok": True})
@app.route('/toggle_conductor/<int:id>')
def toggle_conductor(id):
    if session.get('tipo') != 'admin':
        return redirect(url_for('login'))

    conn = get_db()

    conductor = conn.execute(
        'SELECT activo FROM usuarios WHERE id = ?', (id,)
    ).fetchone()

    if conductor:
        nuevo_estado = 0 if conductor['activo'] == 1 else 1
        conn.execute(
            'UPDATE usuarios SET activo = ? WHERE id = ?',
            (nuevo_estado, id)
        )
        conn.commit()

    conn.close()
    return redirect(url_for('admin'))

# ---------------------- ADMIN ----------------------
@app.route("/admin")
def admin():
    if session.get("tipo") != "admin":
        return "Acceso denegado", 403

    conn = get_db()

    # =================================================================
    # NUEVO: DETECTOR AUTOMÁTICO PARA QUE NUNCA MÁS DE ERROR DE COLUMNA
    # =================================================================
    try:
        # Intentamos ver si la columna ya existe en la tabla de viajes
        conn.execute("SELECT comision_pagada FROM viajes LIMIT 1")
    except sqlite3.OperationalError:
        # Si da error porque no existe, Python la crea solito aquí mismo
        conn.execute("ALTER TABLE viajes ADD COLUMN comision_pagada INTEGER DEFAULT 0")
        conn.commit()
    # =================================================================

    conductores_db = conn.execute("""
        SELECT * 
        FROM usuarios
        WHERE tipo='conductor'
    """).fetchall()

    lista = []
    hoy = datetime.now()

    for c in conductores_db:
        c = dict(c)

        # -------- CALCULAR DÍAS DE SUSCRIPCIÓN --------
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

        # -------- CONTEO FILTRADO DE VIAJES PENDIENTES --------
        total_viajes = conn.execute("""
            SELECT COUNT(*)
            FROM viajes
            WHERE conductor_id=?
            AND estado='finalizado'
            AND comision_pagada = 0
        """, (c["id"],)).fetchone()[0]

        c["total_viajes"] = total_viajes
        c["comision"] = total_viajes * 3

        lista.append(c)

    conn.commit()
    conn.close()

    return render_template("admin.html", conductores=lista)


# -------- ACCIÓN DE REINICIO DE VIAJES Y RENOVACIÓN --------
@app.route("/admin/procesar_reinicio_conductor/<int:id_conductor>", methods=["POST"])
def procesar_reinicio_conductor(id_conductor):
    if session.get("tipo") != "admin":
        return "Acceso denegado", 403

    hoy_str = datetime.now().strftime("%Y-%m-%d")
    conn = get_db()
    
    try:
        # 1. Archivar viajes actuales para sacarlos del conteo dinámico
        conn.execute("""
            UPDATE viajes 
            SET comision_pagada = 1 
            WHERE conductor_id = ? AND estado = 'finalizado'
        """, (id_conductor,))
        
        # 2. Renovar vigencia de 7 días al conductor
        conn.execute("""
            UPDATE usuarios 
            SET activo = 1, fecha_pago = ? 
            WHERE id = ?
        """, (hoy_str, id_conductor))
        
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Error en el proceso de reinicio: {e}")
    finally:
        conn.close()
        
    return redirect(url_for("admin"))

# -------- NUEVA RUTA PARA EL BOTÓN DE REINICIO INDIVIDUAL --------
# Cambiamos el nombre de la función a reiniciar_contador_conductor para evitar el conflicto
@app.route("/admin/reset_viajes_conductor/<int:conductor_id>", methods=["POST"])
def reiniciar_contador_conductor(conductor_id):
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
        """, (conductor_id,))
        
        # 2. Le renovamos sus 7 días de suscripción poniéndole la fecha de hoy
        conn.execute("""
            UPDATE usuarios 
            SET activo = 1, fecha_pago = ? 
            WHERE id = ?
        """, (hoy_str, conductor_id))
        
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Error al reiniciar viajes: {e}")
    finally:
        conn.close()
        
    return redirect(url_for("admin"))

# ---------------------- RESET ----------------------
# ---------------------- FUNCIONES DE ADMINISTRACIÓN ----------------------

def es_admin():
    """Verifica de forma segura si el usuario actual es administrador."""
    return session.get("tipo") == "admin"
@app.route("/reset_conductores")
def reset_conductores():
    if not es_admin():
        return "Acceso denegado: Se requiere perfil de administrador", 403

    conn = get_db()
    # Borramos solo a los usuarios marcados como conductores
    conn.execute("DELETE FROM usuarios WHERE tipo = 'conductor'")
    conn.commit()
    conn.close()

    # Redirige de vuelta al panel para ver la tabla vacía
    return redirect(url_for('admin'))

@app.route("/reset_clientes")
def reset_clientes():
    if not es_admin():
        return "Acceso denegado: Se requiere perfil de administrador", 403

    conn = get_db()
    # Borramos solo a los usuarios marcados como clientes
    conn.execute("DELETE FROM usuarios WHERE tipo = 'cliente'")
    conn.commit()
    conn.close()

    return redirect(url_for('admin'))

@app.route("/reset_viajes")
def reset_viajes():
    if not es_admin():
        return "Acceso denegado: Se requiere perfil de administrador", 403

    conn = get_db()
    # Borramos la tabla completa de viajes
    conn.execute("DELETE FROM viajes")
    conn.commit()
    conn.close()

    return redirect(url_for('admin'))

# ---------------------- LOGOUT ----------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))
@app.route("/actualizar_ubicacion", methods=["POST"])
def actualizar_ubicacion():
    if "user_id" not in session:
        return "", 403

    lat = request.form.get("lat")
    lng = request.form.get("lng")

    conn = get_db()
    conn.execute(
        "UPDATE usuarios SET lat=?, lng=? WHERE id=?",
        (lat, lng, session["user_id"])
    )
    conn.commit()
    conn.close()

    return "", 200
@app.route("/verificar_viajes")
def verificar_viajes():
    if not rol("conductor"):
        return jsonify({"nuevo_viaje": False})

    ultimo_id = request.args.get("ultimo_id", 0)

    conn = get_db()
    viaje = conn.execute("""
        SELECT id FROM viajes
        WHERE estado='pendiente' AND id > ?
        ORDER BY id DESC LIMIT 1
    """, (ultimo_id,)).fetchone()
    conn.close()

    if viaje:
        return jsonify({"nuevo_viaje": True, "id": viaje["id"]})
    else:
        return jsonify({"nuevo_viaje": False})
@app.route("/verificar_cancelaciones")
def verificar_cancelaciones():
    if not rol("conductor"):
        return jsonify({"cancelado": False})

    ultimo_id = request.args.get("ultimo_id", 0)

    conn = get_db()
    viaje = conn.execute("""
        SELECT id FROM viajes
        WHERE estado='cancelado' AND id > ?
        ORDER BY id DESC LIMIT 1
    """, (ultimo_id,)).fetchone()
    conn.close()

    if viaje:
        return jsonify({"cancelado": True, "id": viaje["id"]})
    else:
        return jsonify({"cancelado": False})
from werkzeug.security import generate_password_hash

@app.route("/admin/cambiar_password", methods=["POST"])
def cambiar_password():
    # 🔒 Verificar que sea admin
    if "user_id" not in session or session.get("tipo") != "admin":
        return redirect(url_for("login"))

    nueva = request.form.get("nueva_password", "").strip()
    confirmar = request.form.get("confirmar_password", "").strip()

    # 🔴 Validaciones
    if not nueva or not confirmar:
        return "Completa todos los campos"

    if nueva != confirmar:
        return "Las contraseñas no coinciden"

    if len(nueva) < 6:
        return "La contraseña debe tener al menos 6 caracteres"

    # 🔐 Generar hash
    hash_nuevo = generate_password_hash(nueva)

    # 💾 Guardar en BD
    conn = get_db()
    conn.execute(
        "UPDATE usuarios SET password=? WHERE id=?",
        (hash_nuevo, session["user_id"])
    )
    conn.commit()
    conn.close()

    return redirect(url_for("admin"))
@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"

    return response
from flask import session, jsonify
@app.route("/api_estado_viaje/<int:viaje_id>")
def api_estado_viaje(viaje_id):
    conn = get_db()
    # Obtenemos los datos del viaje y del usuario (conductor) vinculado
    viaje = conn.execute("""
        SELECT 
            v.estado, 
            u.nombre, 
            u.numero_unidad, 
            u.color_vehiculo, 
            u.lat, 
            u.lng
        FROM viajes v
        LEFT JOIN usuarios u ON v.conductor_id = u.id
        WHERE v.id = ?
    """, (viaje_id,)).fetchone()
    conn.close()

    # Si el viaje no existe
    if not viaje:
        session.pop('viaje_id', None)
        return jsonify({"estado": "no_existe"})

    # Limpiar sesión si el viaje ya terminó
    if viaje["estado"] in ["cancelado", "finalizado"]:
        session.pop('viaje_id', None)

    # RESPUESTA LIMPIA: Nombres directos para que tu JS los lea fácil
    return jsonify({
        "estado": viaje["estado"],
        "nombre": viaje["nombre"] or "Buscando conductor...",
        "unidad": viaje["numero_unidad"] or "---",
        "color": viaje["color_vehiculo"] or "---",
        "lat": viaje["lat"],
        "lng": viaje["lng"]
    })

def conductor_activo(user_id):
    conn = get_db()
    user = conn.execute(
        "SELECT activo FROM usuarios WHERE id=?",
        (user_id,)
    ).fetchone()
    conn.close()
    # Retorna True si existe y está marcado como 1
    return True if (user and user["activo"] == 1) else False

# 1. ESTA ES PARA VER SI HAY VIAJES NUEVOS EN LA LISTA
@app.route("/api/verificar_viajes")
def api_verificar_viajes():
    user_id = session.get("user_id")
    if not conductor_activo(user_id):
        return jsonify({"hay_viajes": False})
    
    conn = get_db()
    viaje = conn.execute("SELECT id FROM viajes WHERE estado='pendiente'").fetchone()
    conn.close()
    return jsonify({"hay_viajes": True if viaje else False})

# 2. ESTA ES PARA VER SI EL VIAJE QUE YA ACEPTE SIGUE VIVO O ME LO CANCELARON
@app.route("/api_verificar_status_viaje/<int:viaje_id>")
def api_verificar_status_viaje(viaje_id):
    conn = get_db()
    viaje = conn.execute("SELECT estado, conductor_id FROM viajes WHERE id = ?", (viaje_id,)).fetchone()
    conn.close()
    
    if not viaje:
        return jsonify({"status": "eliminado"})
    
    return jsonify({
        "estado": viaje["estado"],
        "conductor_id": viaje["conductor_id"]
    })

@app.route("/admin/reset_viajes_conductor/<int:conductor_id>", methods=["POST"])
def reset_viajes_conductor(conductor_id):
    if session.get("tipo") != "admin":
        return "Acceso denegado", 403

    hoy_str = datetime.now().strftime("%Y-%m-%d")
    conn = get_db()
    
    try:
        # 1. Marcamos los viajes finales como pagados
        conn.execute("""
            UPDATE viajes 
            SET comision_pagada = 1 
            WHERE conductor_id = ? AND estado = 'finalizado'
        """, (conductor_id,))
        
        # 2. Renovamos vigencia y activamos de nuevo al conductor
        conn.execute("""
            UPDATE usuarios 
            SET activo = 1, fecha_pago = ? 
            WHERE id = ?
        """, (hoy_str, conductor_id))
        
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Error: {e}")
    finally:
        conn.close()
        
    return redirect(url_for("admin"))


if __name__ == "__main__":
    app.run(debug=True)