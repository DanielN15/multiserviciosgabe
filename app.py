from flask import Flask, request, jsonify, render_template
import uuid
import smtplib
from email.mime.text import MIMEText
import sqlite3
import random
import os
import json
import random


from werkzeug.utils import secure_filename
app = Flask(__name__, template_folder="templates", static_folder="static")

def get_db():
    conn = sqlite3.connect("database.db", timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn

def generar_numero_orden(conn):
    row = conn.execute("""
        SELECT orden
        FROM ordenes
        WHERE orden LIKE 'OT-%'
        ORDER BY CAST(REPLACE(orden,'OT-','') AS INTEGER) DESC
        LIMIT 1
    """).fetchone()

    if row:
        ultimo = int(row["orden"].replace("OT-", ""))
        nuevo = ultimo + 1
    else:
        nuevo = 1

    return f"OT-{str(nuevo).zfill(4)}"

def generar_usuario_cliente(conn):
    while True:
        usuario = str(random.randint(100000, 999999))
        existe = conn.execute(
            "SELECT usuario FROM usuarios WHERE usuario=?",
            (usuario,)
        ).fetchone()

        if not existe:
            return usuario
def limpiar_monto(valor):
    valor = str(valor or "0")
    valor = valor.replace("$", "")
    valor = valor.replace(",", "")
    valor = valor.strip()

    try:
        return float(valor)
    except:
        return 0
@app.route("/")
@app.route("/index.html")
def index():
    return render_template("index.html")

@app.route("/recuperar.html")
def recuperar_page():
    return render_template("recuperar.html")

@app.route("/login.html")
def login_page():
    return render_template("login.html")
    
@app.route("/consultar.html")
def consultar_page():
    return render_template("consultar.html")
    
@app.route("/inventario.html")
def inventario_page():
    return render_template("inventario.html")	
@app.route("/corte-x.html")
def cortex_page():
    return render_template("corte-x.html")	
@app.route("/corte-z.html")
def cortez_page():
    return render_template("corte-z.html")	
@app.route("/reporte-corte-z.html")
def reporte_cortez_page():
    return render_template("reporte-corte-z.html")
@app.route("/compras.html")
def compras_page():
    return render_template("compras.html")
@app.route("/proveedores.html")
def proveedores_page():
    return render_template("proveedores.html")
@app.route("/servicios.html")
def servicios_page():
    return render_template("servicios.html")
@app.route("/usuarios.html")
def usuarios_page():
    return render_template("usuarios.html")
@app.route("/ubicaciones.html")
def ubicaciones_page():
    return render_template("ubicaciones.html")

@app.route("/panel.html")
def panel_page():
    return render_template("panel.html")

@app.route("/cliente.html")
def cliente_page():
    return render_template("cliente.html")
@app.route("/pos.html")
def pos_page():
    return render_template("pos.html")
@app.route("/orden.html")
def orden_page():
    return render_template("orden.html")





def asegurar_tabla_cortes(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cortes_z(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_cierre TEXT,
            usuario TEXT,
            sucursal TEXT,
            tickets INTEGER DEFAULT 0,
            efectivo REAL DEFAULT 0,
            tarjeta REAL DEFAULT 0,
            transferencia REAL DEFAULT 0,
            total REAL DEFAULT 0
        )
    """)

def obtener_desde_corte(conn, sucursal):
    asegurar_tabla_cortes(conn)
    if (sucursal or "").upper() == "TODAS":
        row = conn.execute("""
            SELECT COALESCE(MAX(fecha_cierre), datetime('now','localtime','start of day')) AS desde
            FROM cortes_z
        """).fetchone()
    else:
        row = conn.execute("""
            SELECT COALESCE(MAX(fecha_cierre), datetime('now','localtime','start of day')) AS desde
            FROM cortes_z
            WHERE upper(trim(sucursal)) = upper(trim(?))
        """, (sucursal,)).fetchone()
    return row["desde"]

def generar_resumen_corte(conn, sucursal):
    sucursal = (sucursal or "TODAS").strip()
    desde = obtener_desde_corte(conn, sucursal)

    condiciones = ["datetime(p.fecha) > datetime(?)"]
    params = [desde]

    if sucursal.upper() != "TODAS":
        condiciones.append("upper(trim(p.sucursal)) = upper(trim(?))")
        params.append(sucursal)

    where = "WHERE " + " AND ".join(condiciones)

    resumen = conn.execute(f"""
        SELECT
            COUNT(*) AS tickets,
            COALESCE(SUM(p.total),0) AS total,
            COALESCE(SUM(CASE WHEN lower(p.metodo_pago) LIKE '%efectivo%' THEN p.total ELSE 0 END),0) AS efectivo,
            COALESCE(SUM(CASE WHEN lower(p.metodo_pago) LIKE '%tarjeta%' THEN p.total ELSE 0 END),0) AS tarjeta,
            COALESCE(SUM(CASE WHEN lower(p.metodo_pago) LIKE '%transfer%' THEN p.total ELSE 0 END),0) AS transferencia
        FROM pagos p
        {where}
    """, params).fetchone()

    ventas = conn.execute(f"""
        SELECT
            p.id,
            p.orden,
            p.fecha,
            p.cliente,
            p.total,
            p.metodo_pago,
            p.recibido,
            p.cambio,
            p.usuario,
            p.sucursal
        FROM pagos p
        {where}
        ORDER BY p.fecha DESC
    """, params).fetchall()

    return {
        "result": "ok",
        "desde": desde,
        "sucursal": sucursal,
        "tickets": int(resumen["tickets"] or 0),
        "productos": int(resumen["tickets"] or 0),
        "cancelados": 0,
        "fondo_inicial": 0,
        "retiros_gastos": 0,
        "descuentos": 0,
        "efectivo": float(resumen["efectivo"] or 0),
        "tarjeta": float(resumen["tarjeta"] or 0),
        "transferencia": float(resumen["transferencia"] or 0),
        "total": float(resumen["total"] or 0),
        "ventas": [dict(row) for row in ventas]
    }

def listar_reportes_corte_z(conn, sucursal="TODAS", folio="", fecha_inicio="", fecha_fin="", usuario=""):
    asegurar_tabla_cortes(conn)

    sucursal = (sucursal or "TODAS").strip()
    folio = (folio or "").strip().upper().replace(" ", "")
    fecha_inicio = (fecha_inicio or "").strip()
    fecha_fin = (fecha_fin or "").strip()
    usuario = (usuario or "").strip()

    condiciones = []
    params = []

    if sucursal.upper() != "TODAS":
        condiciones.append("upper(trim(sucursal)) = upper(trim(?))")
        params.append(sucursal)

    if folio:
        folio_num = folio.replace("CZ-", "").lstrip("0") or "0"
        condiciones.append("""
            (
                CAST(id AS TEXT) = ?
                OR upper(printf('CZ-%04d', id)) = upper(?)
                OR upper(printf('CZ-%04d', id)) LIKE upper(?)
            )
        """)
        params.extend([folio_num, folio, f"%{folio}%"])

    if fecha_inicio:
        condiciones.append("datetime(fecha_cierre) >= datetime(?)")
        params.append(fecha_inicio + " 00:00:00")

    if fecha_fin:
        condiciones.append("datetime(fecha_cierre) <= datetime(?)")
        params.append(fecha_fin + " 23:59:59")

    if usuario:
        condiciones.append("upper(usuario) LIKE upper(?)")
        params.append(f"%{usuario}%")

    where = "WHERE " + " AND ".join(condiciones) if condiciones else ""

    filas = conn.execute(f"""
        SELECT
            id,
            printf('CZ-%04d', id) AS folio,
            fecha_cierre,
            usuario,
            sucursal,
            tickets,
            efectivo,
            tarjeta,
            transferencia,
            total
        FROM cortes_z
        {where}
        ORDER BY datetime(fecha_cierre) DESC, id DESC
    """, params).fetchall()

    resumen = conn.execute(f"""
        SELECT
            COUNT(*) AS cortes,
            COALESCE(SUM(tickets),0) AS tickets,
            COALESCE(SUM(efectivo),0) AS efectivo,
            COALESCE(SUM(tarjeta),0) AS tarjeta,
            COALESCE(SUM(transferencia),0) AS transferencia,
            COALESCE(SUM(total),0) AS total
        FROM cortes_z
        {where}
    """, params).fetchone()

    return {
        "result": "ok",
        "cortes": int(resumen["cortes"] or 0),
        "tickets": int(resumen["tickets"] or 0),
        "efectivo": float(resumen["efectivo"] or 0),
        "tarjeta": float(resumen["tarjeta"] or 0),
        "transferencia": float(resumen["transferencia"] or 0),
        "total": float(resumen["total"] or 0),
        "reportes": [dict(row) for row in filas]
    }


def filtro_sucursal(columna="ubicaciones"):
    sucursal = (
        request.args.get("sucursal")
        or request.form.get("sucursal")
        or "TODAS"
    )

    sucursal = (sucursal or "").strip()

    if not sucursal or sucursal.upper() == "TODAS":
        return "", ()

    return f" WHERE upper({columna}) = upper(?) ", (sucursal,)
@app.route("/api/login", methods=["POST"])
def login():
    usuario = request.form.get("usuario")
    password = request.form.get("password")

    conn = get_db()
    user = conn.execute("""
        SELECT *
        FROM usuarios
        WHERE usuario = ?
        AND password = ?
     """, (usuario, password)).fetchone()
    conn.close()

    if user:
        sucursal = request.form.get("sucursal", "")
        rol = user["rol"] or ""
        ubicaciones = user["ubicaciones"] or ""

    if rol.lower() == "admin" and user["usuario"].lower() != "admin":
        if not sucursal:
            return jsonify({
                "status": "requiere_sucursal",
                "mensaje": "Selecciona una sucursal"
            })

    if user["usuario"].lower() == "admin":
        sucursal = "TODAS"

    return jsonify({
        "status": "ok",
        "usuario": user["usuario"],
        "nombre": user["nombre"],
        "rol": user["rol"],
        "email": user["email"],
        "telefono": user["telefono"],
        "password": user["password"],
        "ubicaciones": ubicaciones,
        "sucursalActiva": sucursal
    })

    return jsonify({"status": "error"})
@app.route("/api/verificarUsuario")

def verificar_usuario():
    usuario = request.args.get("usuario", "").strip()

    conn = get_db()
    user = conn.execute("""
        SELECT usuario, rol, ubicaciones
        FROM usuarios
        WHERE usuario=?
        LIMIT 1
    """, (usuario,)).fetchone()
    conn.close()

    if not user:
        return jsonify({"existe": False})

    return jsonify({
        "existe": True,
        "usuario": user["usuario"],
        "rol": user["rol"],
        "ubicaciones": user["ubicaciones"] or ""
    })
@app.route("/api")
def api_get():
    tipo = request.args.get("tipo")

    conn = get_db()

    if tipo == "corteX":
        sucursal = (request.args.get("sucursal") or "TODAS").strip()
        data = generar_resumen_corte(conn, sucursal)
        conn.close()
        return jsonify(data)

    if tipo == "corteZ":
        sucursal = (request.args.get("sucursal") or "TODAS").strip()
        data = generar_resumen_corte(conn, sucursal)
        conn.close()
        return jsonify(data)

    if tipo == "reporteCortesZ":
        data = listar_reportes_corte_z(
            conn,
            sucursal=request.args.get("sucursal") or "TODAS",
            folio=request.args.get("folio") or "",
            fecha_inicio=request.args.get("fecha_inicio") or "",
            fecha_fin=request.args.get("fecha_fin") or "",
            usuario=request.args.get("usuario") or ""
        )
        conn.close()
        return jsonify(data)

    if tipo == "historialTicketsPos":
        texto = (request.args.get("texto") or "").strip()
        fecha_inicio = (request.args.get("fecha_inicio") or "").strip()
        fecha_fin = (request.args.get("fecha_fin") or "").strip()
        sucursal = (request.args.get("sucursal") or "TODAS").strip()

        condiciones = []
        params = []

        if sucursal.upper() != "TODAS":
            condiciones.append("upper(trim(p.sucursal)) = upper(trim(?))")
            params.append(sucursal)

        if texto:
            condiciones.append("""
                (
                    upper(p.orden) LIKE upper(?)
                    OR upper(p.cliente) LIKE upper(?)
                    OR upper(o.cliente) LIKE upper(?)
                    OR upper(o.telefono) LIKE upper(?)
                    OR upper(o.vehiculo) LIKE upper(?)
                    OR upper(o.placa) LIKE upper(?)
                    OR upper(p.metodo_pago) LIKE upper(?)
                )
            """)
            buscar = "%" + texto + "%"
            params.extend([buscar, buscar, buscar, buscar, buscar, buscar, buscar])

        if fecha_inicio:
            condiciones.append("date(p.fecha) >= date(?)")
            params.append(fecha_inicio)

        if fecha_fin:
            condiciones.append("date(p.fecha) <= date(?)")
            params.append(fecha_fin)

        where = ""

        if condiciones:
            where = "WHERE " + " AND ".join(condiciones)

        data = conn.execute(f"""
            SELECT
                p.id,
                p.orden,
                p.fecha,
                p.cliente,
                p.total,
                p.metodo_pago,
                p.recibido,
                p.cambio,
                p.usuario,
                p.sucursal,
                o.telefono,
                o.vehiculo,
                o.placa,
                o.trabajo
            FROM pagos p
            LEFT JOIN ordenes o ON o.orden = p.orden
            {where}
            ORDER BY p.fecha DESC
            LIMIT 100
        """, params).fetchall()

        conn.close()
        return jsonify([dict(row) for row in data])

    if tipo == "ordenesCobrar":
        sucursal = (request.args.get("sucursal") or "TODAS").strip()

        if sucursal.upper() == "TODAS":
            data = conn.execute("""
                SELECT *
                FROM ordenes
                WHERE estado='Terminada'
                ORDER BY fecha DESC
            """).fetchall()
        else:
            data = conn.execute("""
                SELECT *
                FROM ordenes
                WHERE estado='Terminada'
                AND upper(trim(ubicaciones)) = upper(trim(?))
                ORDER BY fecha DESC
            """, (sucursal,)).fetchall()

        conn.close()
        return jsonify([dict(row) for row in data])
    if tipo == "detalleOrdenCobro":
        orden = (request.args.get("orden") or "").strip()

        data = conn.execute("""
            SELECT 
                o.*,
                u.email AS email_cliente,
                u.direccion AS direccion_cliente
            FROM ordenes o
            LEFT JOIN usuarios u ON u.usuario = o.usuario
            WHERE o.orden=?
            LIMIT 1
        """, (orden,)).fetchone()

        conn.close()

        if not data:
            return jsonify({
                "result": "error",
                "mensaje": "No se encontró la orden"
            })

        return jsonify(dict(data))
    if tipo == "usuariosAdmin":
        usuario_actual = (request.args.get("usuario_actual") or "").strip().lower()

        if usuario_actual != "admin":
            conn.close()
            return jsonify({
                "result": "error",
                "mensaje": "No autorizado"
            })

        data = conn.execute("""
            SELECT usuario,
                   password,
                   nombre,
                   rol,
                   email,
                   direccion,
                   telefono,
                   ubicaciones
            FROM usuarios
            ORDER BY nombre ASC
        """).fetchall()

        conn.close()
        return jsonify([dict(row) for row in data])

    if tipo == "servicios":
        data = conn.execute("""
            SELECT id,
                   categoria,
                   descripcion,
                   costo_menudeo,
                   costo_mayoreo,
                   notas,
                   estado
            FROM servicios
            ORDER BY categoria ASC, descripcion ASC
        """).fetchall()

        conn.close()
        return jsonify([dict(row) for row in data])

    if tipo == "categorias":
        data = conn.execute("""
            SELECT DISTINCT categoria
            FROM inventario
            WHERE categoria IS NOT NULL
            AND categoria != ''
            ORDER BY categoria
        """).fetchall()

        conn.close()
        return jsonify([row["categoria"] for row in data])
    
    if tipo == "clientes":
        data = conn.execute("""
            SELECT usuario,nombre,rol,email,direccion,telefono
            FROM usuarios
            WHERE lower(rol)='cliente'
        """).fetchall()

        conn.close()
        return jsonify([dict(row) for row in data])

    if tipo == "vehiculos":
        data = conn.execute("SELECT * FROM vehiculos").fetchall()
        conn.close()
        return jsonify([dict(row) for row in data])

    if tipo == "proveedores":
        data = conn.execute("SELECT nombre FROM proveedores ORDER BY nombre").fetchall()
        conn.close()
        return jsonify([row["nombre"] for row in data])
    if tipo == "proveedoresAdmin":
        data = conn.execute("""
        SELECT id, nombre, direccion, telefono
        FROM proveedores
        ORDER BY id ASC
    """).fetchall()

        conn.close()
        return jsonify([dict(row) for row in data])
    if tipo == "ubicacionesAdmin":
        data = conn.execute("""
            SELECT id, nombre, direccion, telefono, estado
            FROM ubicaciones
            ORDER BY id ASC
        """).fetchall()
        conn.close()
        return jsonify([dict(row) for row in data])

    if tipo == "ubicaciones":
        data = conn.execute("SELECT nombre FROM ubicaciones ORDER BY nombre").fetchall()
        conn.close()
        return jsonify([row["nombre"] for row in data])

    if tipo == "buscarInventario":
        campo = request.args.get("campo")
        texto = (request.args.get("texto") or "").strip()
        sucursal = (request.args.get("sucursal") or "TODAS").strip()

        campos_validos = {
            "codigo": "codigo",
            "producto": "producto",
            "proveedor": "proveedor",
            "ubicacion": "ubicacion"
        }

        columna = campos_validos.get(campo, "codigo")

        if sucursal.upper() == "TODAS":
            data = conn.execute(f"""
                SELECT *
                FROM inventario
                WHERE upper(trim({columna})) LIKE upper(trim(?))
                ORDER BY producto
            """, (f"%{texto}%",)).fetchall()
        else:
            data = conn.execute(f"""
                SELECT *
                FROM inventario
                WHERE upper(trim({columna})) LIKE upper(trim(?))
                AND upper(trim(ubicacion)) = upper(trim(?))
                ORDER BY producto
            """, (f"%{texto}%", sucursal)).fetchall()

        conn.close()
        return jsonify([dict(row) for row in data])

    
    if tipo == "consultas":
        where, params = filtro_sucursal("ubicaciones")

        data = conn.execute(f"""
        SELECT *
        FROM consultas
        {where}
        ORDER BY fecha DESC
        """, params).fetchall()
        conn.close()
        return jsonify([dict(row) for row in data])

    if tipo == "ordenes":
        where, params = filtro_sucursal("ubicaciones")

        data = conn.execute(f"""
        SELECT *
        FROM ordenes
        {where}
        ORDER BY fecha DESC
        """, params).fetchall()
        conn.close()
        return jsonify([dict(row) for row in data])

    if tipo == "inventario":
        where, params = filtro_sucursal("ubicacion")

        data = conn.execute(f"""
        SELECT *
        FROM inventario
        {where}
         """, params).fetchall()
        conn.close()
        return jsonify([dict(row) for row in data])

    if tipo == "cerrar":
        id = request.args.get("id")
        conn.execute("""
            UPDATE consultas
            SET estado='Cerrado',
                fecha_cierre=datetime('now','localtime')
            WHERE id=?
        """, (id,))
        conn.commit()
        conn.close()
        return jsonify({"result": "ok"})

    if tipo == "procesarOrden":
        id = request.args.get("id")

        cursor = conn.execute("""
            UPDATE ordenes
            SET estado='Proceso',
                fecha_proceso=datetime('now','localtime')
            WHERE orden=?
        """, (id,))

        conn.commit()
        conn.close()

        if cursor.rowcount == 0:
            return jsonify({
                "result": "error",
                "mensaje": "No se encontró la orden"
            })

        return jsonify({"result": "ok"})

    if tipo == "cerrarOrden":
        id = request.args.get("id")

        cursor = conn.execute("""
            UPDATE ordenes
            SET estado='Terminada',
                fecha_terminada=datetime('now','localtime')
            WHERE orden=?
        """, (id,))

        conn.commit()
        conn.close()

        if cursor.rowcount == 0:
            return jsonify({
                "result": "error",
                "mensaje": "No se encontró la orden"
            })

        return jsonify({"result": "ok"})
    if tipo == "eliminarOrden":
        id = (request.args.get("id") or "").strip()

        if not id:
            conn.close()
            return jsonify({
                "result": "error",
                "mensaje": "Falta el número de orden"
            })

        cursor = conn.execute("""
            DELETE FROM ordenes
            WHERE orden=?
        """, (id,))

        conn.commit()
        conn.close()

    if tipo == "movimientosInventario":
        sucursal = (request.args.get("sucursal") or "TODAS").strip()

        if not sucursal or sucursal.upper() == "TODAS":
            data = conn.execute("""
                SELECT *
                FROM movimientos
                ORDER BY fecha DESC
            """).fetchall()
        else:
            data = conn.execute("""
                SELECT *
                FROM movimientos
                WHERE upper(trim(sucursal)) = upper(trim(?))
                OR upper(trim(destino)) = upper(trim(?))
                ORDER BY fecha DESC
            """, (sucursal, sucursal)).fetchall()

        conn.close()
        return jsonify([dict(row) for row in data])

        if not sucursal or sucursal.upper() == "TODAS":
            data = conn.execute("""
                SELECT *
                FROM movimientos
                ORDER BY fecha DESC
            """).fetchall()
        else:
            data = conn.execute("""
                SELECT *
                FROM movimientos
                WHERE upper(trim(sucursal)) = upper(trim(?))
                OR upper(trim(destino)) = upper(trim(?))
                ORDER BY fecha DESC
            """, (sucursal, sucursal)).fetchall()

        conn.close()
        return jsonify([dict(row) for row in data])

    if tipo == "siguienteCompra":
        row = conn.execute("""
            SELECT folio
            FROM compras
            ORDER BY id DESC
            LIMIT 1
        """).fetchone()

        if row and row["folio"]:
            try:
                ultimo_numero = int(str(row["folio"]).replace("OC-", ""))
            except:
                ultimo_numero = 0
        else:
            ultimo_numero = 0

        nuevo_folio = "OC-" + str(ultimo_numero + 1).zfill(5)

        conn.close()
        return jsonify({"folio": nuevo_folio})

    if tipo == "compras":
        sucursal = (request.args.get("sucursal") or "TODAS").strip()

        if sucursal.upper() == "TODAS":
            data = conn.execute("""
                SELECT *
                FROM compras
                ORDER BY id DESC
            """).fetchall()
        else:
            data = conn.execute("""
                SELECT *
                FROM compras
                WHERE upper(trim(sucursal)) = upper(trim(?))
                ORDER BY id DESC
            """, (sucursal,)).fetchall()

        conn.close()
        return jsonify([dict(row) for row in data])

    if tipo == "detalleCompra":
        folio = (request.args.get("folio") or "").strip()

        data = conn.execute("""
            SELECT
                codigo,
                producto,
                cantidad,
                costo_unitario,
                subtotal
            FROM compras_detalle
            WHERE folio_compra = ?
            ORDER BY id ASC
        """, (folio,)).fetchall()

        conn.close()
        return jsonify([dict(row) for row in data])

    conn.close()
    return jsonify([])    

@app.route("/api/siguienteOrden")
def siguiente_orden():
    conn = get_db()
    numero = generar_numero_orden(conn)
    conn.close()
    return jsonify({"orden": numero})

@app.route("/api/guardarOrden", methods=["POST"])
def guardar_orden():
    conn = get_db()

    numero = generar_numero_orden(conn)
    usuario_existente = request.form.get("usuarioExistente")
    cliente = request.form.get("cliente") or ""
    telefono_cliente = request.form.get("telefono") or ""
    email_cliente = request.form.get("email") or ""
    direccion_cliente = request.form.get("direccion") or ""
    ubicaciones_cliente = request.form.get("ubicaciones") or request.form.get("sucursal") or ""

    if usuario_existente and usuario_existente != "nuevo":
        usuario_cliente = usuario_existente
        password_cliente = ""

        conn.execute("""
            UPDATE usuarios
            SET telefono=?,
                email=?,
                direccion=?,
                ubicaciones=?
            WHERE usuario=?
        """, (
            telefono_cliente,
            email_cliente,
            direccion_cliente,
            ubicaciones_cliente,
            usuario_cliente
        ))
    else:
        usuario_cliente = generar_usuario_cliente(conn)
        password_cliente = usuario_cliente

        conn.execute("""
            INSERT INTO usuarios(
                usuario,
                password,
                nombre,
                rol,
                email,
                direccion,
                telefono,
                ubicaciones
            )
            VALUES(?,?,?,?,?,?,?,?)
        """, (
            usuario_cliente,
            password_cliente,
            cliente,
            "Cliente",
            email_cliente,
            direccion_cliente,
            telefono_cliente,
            ubicaciones_cliente
        ))

    conn.execute("""
    INSERT INTO ordenes(
        orden,
        fecha,
        cliente,
        usuario,
        telefono,
        vehiculo,
        placa,
        trabajo,
        total,
        ubicaciones,
        estado
    )
    VALUES(
        ?,
        datetime('now','localtime'),
        ?,?,?,?,?,?,?,?,
        'Nueva'
    )
        """, (
             numero,
             cliente,
            usuario_cliente,
    request.form.get("telefono"),
    request.form.get("vehiculo"),
    request.form.get("placa"),
    request.form.get("trabajo"),
    request.form.get("total"),
    request.form.get("sucursal")
        ))

    placa = request.form.get("placa") or ""
    vin = request.form.get("vin") or ""
    odometro = request.form.get("odometro") or ""

    vehiculo_existente = conn.execute("""
        SELECT id, odometro
        FROM vehiculos
        WHERE usuario=?
        AND (
            placa=?
            OR (vin != '' AND vin=?)
        )
        LIMIT 1
    """, (
        usuario_cliente,
        placa,
        vin
    )).fetchone()

    if vehiculo_existente:
        odometro_actual = vehiculo_existente["odometro"] or ""

        if odometro:
            ultimo_odometro = odometro_actual

            if "-" in odometro_actual:
                partes = odometro_actual.split("-")
                ultimo_odometro = partes[-1].strip()

            if ultimo_odometro != odometro:
                nuevo_odometro = ultimo_odometro + " - " + odometro
                conn.execute("""
                    UPDATE vehiculos
                    SET odometro=?
                    WHERE id=?
                """, (
                    nuevo_odometro,
                    vehiculo_existente["id"]
                ))

    else:
        conn.execute("""
            INSERT INTO vehiculos(
                usuario,
                cliente,
                telefono,
                vehiculo,
                placa,
                anio,
                vin,
                odometro,
                color,
                fecha_alta
            )
            VALUES(
                ?,?,?,?,?,?,?,?,?,datetime('now','localtime')
            )
        """, (
            usuario_cliente,
            cliente,
            request.form.get("telefono"),
            request.form.get("vehiculo"),
            request.form.get("placa"),
            request.form.get("anio"),
            request.form.get("vin"),
            request.form.get("odometro"),
            request.form.get("color")
        ))

    conn.commit()
    conn.close()

    return jsonify({
        "result": "ok",
        "orden": numero,
        "usuario": usuario_cliente,
        "password": password_cliente
    })
@app.route("/api", methods=["POST"])
def api_post():
    tipo = request.form.get("tipo")
    conn = get_db()


    if tipo == "realizarCorteZ":
        usuario = (request.form.get("usuario") or "").strip().upper()
        sucursal = (request.form.get("sucursal") or "TODAS").strip().upper()

        try:
            data = generar_resumen_corte(conn, sucursal)
            asegurar_tabla_cortes(conn)

            cur = conn.execute("""
                INSERT INTO cortes_z(
                    fecha_cierre, usuario, sucursal, tickets,
                    efectivo, tarjeta, transferencia, total
                )
                VALUES(datetime('now','localtime'),?,?,?,?,?,?,?)
            """, (
                usuario,
                sucursal,
                data["tickets"],
                data["efectivo"],
                data["tarjeta"],
                data["transferencia"],
                data["total"]
            ))

            folio = f"CZ-{cur.lastrowid:04d}"
            conn.commit()
            conn.close()

            return jsonify({
                "result": "ok",
                "mensaje": "Corte Z realizado correctamente. Folio: " + folio,
                "folio": folio,
                "corte": data
            })

        except Exception as e:
            conn.rollback()
            conn.close()
            return jsonify({
                "result": "error",
                "mensaje": str(e)
            })

    if tipo == "venderProductosPos":
        metodo_pago = (request.form.get("metodo_pago") or "").strip()
        recibido = float(request.form.get("recibido") or 0)
        cambio = float(request.form.get("cambio") or 0)
        descuento = float(request.form.get("descuento") or 0)
        usuario = (request.form.get("usuario") or "").strip().upper()
        sucursal = (request.form.get("sucursal") or "").strip().upper()
        productos_json = request.form.get("productos_pos") or "[]"

        cliente_usuario = (request.form.get("cliente_usuario") or "").strip()
        cliente_nombre = (request.form.get("cliente_nombre") or "").strip().upper()
        cliente_telefono = (request.form.get("cliente_telefono") or "").strip()
        cliente_email = (request.form.get("cliente_email") or "").strip().upper()
        cliente_direccion = (request.form.get("cliente_direccion") or "").strip().upper()

        if not cliente_nombre:
            cliente_nombre = "PÚBLICO EN GENERAL"

        if not metodo_pago:
            conn.close()
            return jsonify({
                "result": "error",
                "mensaje": "Selecciona método de pago"
            })

        try:
            productos_pos = json.loads(productos_json)
        except:
            productos_pos = []

        if not productos_pos:
            conn.close()
            return jsonify({
                "result": "error",
                "mensaje": "Agrega al menos un producto"
            })

        total_productos = 0

        for p in productos_pos:
            cantidad = float(p.get("cantidad") or 0)
            precio = float(p.get("precio") or 0)
            total_productos += cantidad * precio

        total_final = total_productos - descuento

        if total_final < 0:
            total_final = 0

        if metodo_pago.lower() == "efectivo" and recibido < total_final:
            conn.close()
            return jsonify({
                "result": "error",
                "mensaje": "El efectivo recibido es menor al total"
            })

        folio_row = conn.execute("""
            SELECT 'VP-' || strftime('%Y%m%d%H%M%S','now','localtime') AS folio
        """).fetchone()

        folio = folio_row["folio"]

        try:
            # VALIDAR INVENTARIO ANTES DE COBRAR
            for p in productos_pos:
                codigo = str(p.get("codigo") or "").strip().upper()
                cantidad = float(p.get("cantidad") or 0)

                if not codigo or cantidad <= 0:
                    continue

                producto_db = conn.execute("""
                    SELECT *
                    FROM inventario
                    WHERE upper(trim(codigo)) = upper(trim(?))
                    AND upper(trim(ubicacion)) = upper(trim(?))
                    LIMIT 1
                """, (
                    codigo,
                    sucursal
                )).fetchone()

                if not producto_db:
                    conn.rollback()
                    conn.close()
                    return jsonify({
                        "result": "error",
                        "mensaje": "Producto no encontrado en inventario: " + codigo
                    })

                cantidad_actual = float(producto_db["cantidad"] or 0)

                if cantidad_actual < cantidad:
                    conn.rollback()
                    conn.close()
                    return jsonify({
                        "result": "error",
                        "mensaje": "No hay suficiente inventario para: " + str(producto_db["producto"])
                    })

            # DESCONTAR INVENTARIO
            for p in productos_pos:
                codigo = str(p.get("codigo") or "").strip().upper()
                cantidad = float(p.get("cantidad") or 0)

                if not codigo or cantidad <= 0:
                    continue

                producto_db = conn.execute("""
                    SELECT *
                    FROM inventario
                    WHERE upper(trim(codigo)) = upper(trim(?))
                    AND upper(trim(ubicacion)) = upper(trim(?))
                    LIMIT 1
                """, (
                    codigo,
                    sucursal
                )).fetchone()

                nueva_cantidad = float(producto_db["cantidad"] or 0) - cantidad

                conn.execute("""
                    UPDATE inventario
                    SET cantidad=?
                    WHERE id=?
                """, (
                    nueva_cantidad,
                    producto_db["id"]
                ))

                conn.execute("""
                    INSERT INTO movimientos(
                        fecha,
                        codigo,
                        producto,
                        tipo,
                        cantidad,
                        descripcion,
                        usuario,
                        sucursal,
                        destino
                    )
                    VALUES(datetime('now','localtime'),?,?,?,?,?,?,?,?)
                """, (
                    producto_db["codigo"],
                    producto_db["producto"],
                    "Salida",
                    cantidad,
                    "SALIDA POR VENTA POS " + folio,
                    usuario,
                    sucursal,
                    ""
                ))

            # REGISTRAR PAGO UNA SOLA VEZ
            conn.execute("""
                INSERT INTO pagos(
                    orden,
                    fecha,
                    cliente,
                    total,
                    metodo_pago,
                    recibido,
                    cambio,
                    usuario,
                    sucursal
                )
                VALUES(
                    ?,
                    datetime('now','localtime'),
                    ?,?,?,?,?,?,?
                )
            """, (
                folio,
                cliente_nombre,
                total_final,
                metodo_pago,
                recibido,
                cambio,
                usuario,
                sucursal
            ))

            conn.commit()
            conn.close()

            return jsonify({
                "result": "ok",
                "orden": folio,
                "total": total_final,
                "cliente": cliente_nombre,
                "telefono": cliente_telefono,
                "email": cliente_email,
                "direccion": cliente_direccion
            })

        except Exception as e:
            conn.rollback()
            conn.close()
            return jsonify({
                "result": "error",
                "mensaje": str(e)
            })    
    if tipo == "cobrarOrden":
        orden = (request.form.get("orden") or "").strip()
        metodo_pago = (request.form.get("metodo_pago") or "").strip()
        recibido = float(request.form.get("recibido") or 0)
        cambio = float(request.form.get("cambio") or 0)
        descuento = float(request.form.get("descuento") or 0)
        usuario = (request.form.get("usuario") or "").strip().upper()
        sucursal = (request.form.get("sucursal") or "").strip().upper()
        productos_json = request.form.get("productos_pos") or "[]"

        if not orden:
            conn.close()
            return jsonify({
                "result": "error",
                "mensaje": "Falta la orden"
            })

        if not metodo_pago:
            conn.close()
            return jsonify({
                "result": "error",
                "mensaje": "Selecciona método de pago"
            })

        try:
            productos_pos = json.loads(productos_json)
        except:
            productos_pos = []

        orden_db = conn.execute("""
            SELECT *
            FROM ordenes
            WHERE orden=?
            LIMIT 1
        """, (orden,)).fetchone()

        if not orden_db:
            conn.close()
            return jsonify({
                "result": "error",
                "mensaje": "No se encontró la orden"
            })

        if str(orden_db["estado"]).lower() == "pagada":
            conn.close()
            return jsonify({
                "result": "error",
                "mensaje": "Esta orden ya fue pagada"
            })

        if str(orden_db["estado"]).lower() != "terminada":
            conn.close()
            return jsonify({
                "result": "error",
                "mensaje": "Solo se pueden cobrar órdenes terminadas"
            })

        total_raw = str(orden_db["total"] or "0")
        total_raw = total_raw.replace("$", "").replace(",", "").strip()

        try:
            total_orden = float(total_raw or 0)
        except:
            total_orden = 0

        total_productos = 0

        for p in productos_pos:
            cantidad = float(p.get("cantidad") or 0)
            precio = float(p.get("precio") or 0)
            total_productos += cantidad * precio

        total_final = total_orden + total_productos - descuento

        if total_final < 0:
            total_final = 0

        if metodo_pago.lower() == "efectivo" and recibido < total_final:
            conn.close()
            return jsonify({
                "result": "error",
                "mensaje": "El efectivo recibido es menor al total"
            })

        try:
            # VALIDAR INVENTARIO ANTES DE COBRAR
            for p in productos_pos:
                codigo = str(p.get("codigo") or "").strip().upper()
                cantidad = float(p.get("cantidad") or 0)

                if not codigo or cantidad <= 0:
                    continue

                producto_db = conn.execute("""
                    SELECT *
                    FROM inventario
                    WHERE upper(trim(codigo)) = upper(trim(?))
                    AND upper(trim(ubicacion)) = upper(trim(?))
                    LIMIT 1
                """, (
                    codigo,
                    sucursal
                )).fetchone()

                if not producto_db:
                    conn.rollback()
                    conn.close()
                    return jsonify({
                        "result": "error",
                        "mensaje": "Producto no encontrado en inventario: " + codigo
                    })

                cantidad_actual = float(producto_db["cantidad"] or 0)

                if cantidad_actual < cantidad:
                    conn.rollback()
                    conn.close()
                    return jsonify({
                        "result": "error",
                        "mensaje": "No hay suficiente inventario para: " + str(producto_db["producto"])
                    })

            # DESCONTAR INVENTARIO
            for p in productos_pos:
                codigo = str(p.get("codigo") or "").strip().upper()
                cantidad = float(p.get("cantidad") or 0)

                if not codigo or cantidad <= 0:
                    continue

                producto_db = conn.execute("""
                    SELECT *
                    FROM inventario
                    WHERE upper(trim(codigo)) = upper(trim(?))
                    AND upper(trim(ubicacion)) = upper(trim(?))
                    LIMIT 1
                """, (
                    codigo,
                    sucursal
                )).fetchone()

                nueva_cantidad = float(producto_db["cantidad"] or 0) - cantidad

                conn.execute("""
                    UPDATE inventario
                    SET cantidad=?
                    WHERE id=?
                """, (
                    nueva_cantidad,
                    producto_db["id"]
                ))

                conn.execute("""
                    INSERT INTO movimientos(
                        fecha,
                        codigo,
                        producto,
                        tipo,
                        cantidad,
                        descripcion,
                        usuario,
                        sucursal,
                        destino
                    )
                    VALUES(datetime('now','localtime'),?,?,?,?,?,?,?,?)
                """, (
                    producto_db["codigo"],
                    producto_db["producto"],
                    "Salida",
                    cantidad,
                    "SALIDA POR VENTA POS " + orden,
                    usuario,
                    sucursal,
                    ""
                ))

            conn.execute("""
                INSERT INTO pagos(
                    orden,
                    fecha,
                    cliente,
                    total,
                    metodo_pago,
                    recibido,
                    cambio,
                    usuario,
                    sucursal
                )
                VALUES(
                    ?,
                    datetime('now','localtime'),
                    ?,?,?,?,?,?,?
                )
            """, (
                orden,
                orden_db["cliente"],
                total_final,
                metodo_pago,
                recibido,
                cambio,
                usuario,
                sucursal
            ))

            conn.execute("""
                UPDATE ordenes
                SET estado='Pagada',
                    total=?
                WHERE orden=?
            """, (
                total_final,
                orden
            ))

            conn.commit()
            conn.close()

            return jsonify({
                "result": "ok",
                "orden": orden,
                "total": total_final
            })

        except Exception as e:
            conn.rollback()
            conn.close()
            return jsonify({
                "result": "error",
                "mensaje": str(e)
            })
    if tipo == "agregarUsuario":
        usuario_actual = (request.form.get("usuario_actual") or "").strip().lower()

        if usuario_actual != "admin":
            conn.close()
            return jsonify({
                "result": "error",
                "mensaje": "Solo el usuario principal admin puede agregar usuarios"
            })

        usuario = (request.form.get("usuario") or "").strip()
        password = (request.form.get("password") or "").strip()
        nombre = (request.form.get("nombre") or "").strip().upper()
        rol = (request.form.get("rol") or "").strip()
        email = (request.form.get("email") or "").strip().upper()
        direccion = (request.form.get("direccion") or "").strip().upper()
        telefono = (request.form.get("telefono") or "").strip()
        ubicaciones = (request.form.get("ubicaciones") or "").strip()

        if not usuario:
            conn.close()
            return jsonify({"result":"error","mensaje":"Falta el usuario"})

        if not password:
            conn.close()
            return jsonify({"result":"error","mensaje":"Falta la contraseña"})

        if not nombre:
            conn.close()
            return jsonify({"result":"error","mensaje":"Falta el nombre"})

        if rol not in ["Admin", "Cliente"]:
            conn.close()
            return jsonify({"result":"error","mensaje":"Selecciona rol Admin o Cliente"})

        existe = conn.execute("""
            SELECT usuario
            FROM usuarios
            WHERE usuario=?
            LIMIT 1
        """, (usuario,)).fetchone()

        if existe:
            conn.close()
            return jsonify({
                "result":"error",
                "mensaje":"Ese usuario ya existe"
            })

        conn.execute("""
            INSERT INTO usuarios(
                usuario,
                password,
                nombre,
                rol,
                email,
                direccion,
                telefono,
                ubicaciones
            )
            VALUES(?,?,?,?,?,?,?,?)
        """, (
            usuario,
            password,
            nombre,
            rol,
            email,
            direccion,
            telefono,
            ubicaciones
        ))

        conn.commit()
        conn.close()

        return jsonify({"result":"ok"})
    
    if tipo == "modificarUsuario":
        usuario_actual = (request.form.get("usuario_actual") or "").strip().lower()

        if usuario_actual != "admin":
            conn.close()
            return jsonify({
                "result": "error",
                "mensaje": "Solo el usuario principal admin puede modificar usuarios"
            })

        usuario = (request.form.get("usuario") or "").strip()
        password = (request.form.get("password") or "").strip()
        nombre = (request.form.get("nombre") or "").strip().upper()
        rol = (request.form.get("rol") or "").strip()
        email = (request.form.get("email") or "").strip().upper()
        direccion = (request.form.get("direccion") or "").strip().upper()
        telefono = (request.form.get("telefono") or "").strip()
        ubicaciones = (request.form.get("ubicaciones") or "").strip()

        if not usuario:
            conn.close()
            return jsonify({"result":"error","mensaje":"Falta el usuario"})

        if usuario.lower() == "admin" and rol != "Administrador":
            rol = "Administrador"

        conn.execute("""
            UPDATE usuarios
            SET password=?,
                nombre=?,
                rol=?,
                email=?,
                direccion=?,
                telefono=?,
                ubicaciones=?
            WHERE usuario=?
        """, (
            password,
            nombre,
            rol,
            email,
            direccion,
            telefono,
            ubicaciones,
            usuario
        ))

        conn.commit()
        conn.close()

        return jsonify({"result":"ok"})
    
    if tipo == "eliminarUsuario":
        usuario_actual = (request.form.get("usuario_actual") or "").strip().lower()
        usuario = (request.form.get("usuario") or "").strip()

        if usuario_actual != "admin":
            conn.close()
            return jsonify({
                "result": "error",
                "mensaje": "Solo el usuario principal admin puede eliminar usuarios"
            })

        if not usuario:
            conn.close()
            return jsonify({"result":"error","mensaje":"Falta el usuario"})

        if usuario.lower() == "admin":
            conn.close()
            return jsonify({
                "result":"error",
                "mensaje":"No puedes eliminar el usuario principal admin"
            })

        conn.execute("""
            DELETE FROM usuarios
            WHERE usuario=?
        """, (usuario,))

        conn.commit()
        conn.close()

        return jsonify({"result":"ok"})

    if tipo == "agregarServicio":
        categoria = (request.form.get("categoria") or "").strip().upper()
        descripcion = (request.form.get("descripcion") or "").strip().upper()
        costo_menudeo = request.form.get("costo_menudeo") or 0
        costo_mayoreo = request.form.get("costo_mayoreo") or 0
        notas = (request.form.get("notas") or "").strip().upper()
        estado = (request.form.get("estado") or "Activo").strip()

        if not descripcion:
            conn.close()
            return jsonify({
                "result": "error",
                "mensaje": "La descripción del servicio es obligatoria"
            })

        existe = conn.execute("""
            SELECT id
            FROM servicios
            WHERE upper(trim(descripcion)) = upper(trim(?))
            LIMIT 1
        """, (descripcion,)).fetchone()

        if existe:
            conn.close()
            return jsonify({
                "result": "error",
                "mensaje": "Este servicio ya existe"
            })

        conn.execute("""
            INSERT INTO servicios(
                categoria,
                descripcion,
                costo_menudeo,
                costo_mayoreo,
                notas,
                estado
            )
            VALUES(?,?,?,?,?,?)
        """, (
            categoria,
            descripcion,
            costo_menudeo,
            costo_mayoreo,
            notas,
            estado
        ))

        conn.commit()
        conn.close()

        return jsonify({"result": "ok"})
    if tipo == "modificarServicio":
        id_servicio = request.form.get("id")
        categoria = (request.form.get("categoria") or "").strip().upper()
        descripcion = (request.form.get("descripcion") or "").strip().upper()
        costo_menudeo = request.form.get("costo_menudeo") or 0
        costo_mayoreo = request.form.get("costo_mayoreo") or 0
        notas = (request.form.get("notas") or "").strip().upper()
        estado = (request.form.get("estado") or "Activo").strip()

        if not id_servicio:
            conn.close()
            return jsonify({
                "result": "error",
                "mensaje": "Falta el ID del servicio"
            })

        if not descripcion:
            conn.close()
            return jsonify({
                "result": "error",
                "mensaje": "La descripción del servicio es obligatoria"
            })

        existe = conn.execute("""
            SELECT id
            FROM servicios
            WHERE upper(trim(descripcion)) = upper(trim(?))
            AND id != ?
            LIMIT 1
        """, (
            descripcion,
            id_servicio
        )).fetchone()

        if existe:
            conn.close()
            return jsonify({
                "result": "error",
                "mensaje": "Ya existe otro servicio con esa descripción"
            })

        conn.execute("""
            UPDATE servicios
            SET categoria=?,
                descripcion=?,
                costo_menudeo=?,
                costo_mayoreo=?,
                notas=?,
                estado=?
            WHERE id=?
        """, (
            categoria,
            descripcion,
            costo_menudeo,
            costo_mayoreo,
            notas,
            estado,
            id_servicio
        ))

        conn.commit()
        conn.close()

        return jsonify({"result": "ok"})
    
    if tipo == "eliminarServicio":
        id_servicio = request.form.get("id")

        if not id_servicio:
            conn.close()
            return jsonify({
                "result": "error",
                "mensaje": "Falta el ID del servicio"
            })

        conn.execute("""
            UPDATE servicios
            SET estado='Inactivo'
            WHERE id=?
        """, (id_servicio,))

        conn.commit()
        conn.close()

        return jsonify({"result": "ok"})

    if tipo == "agregarProducto":

        codigo = (request.form.get("codigo") or "").strip().upper()
        producto = (request.form.get("producto") or "").strip().upper()
        categoria = (request.form.get("categoria") or "").strip().upper()
        cantidad = request.form.get("cantidad") or 0
        precio = request.form.get("precio") or 0
        proveedor = (request.form.get("proveedor") or "").strip().upper()
        ubicacion = (request.form.get("ubicacion") or "").strip().upper()
        multi_sucursal = request.form.get("multiSucursal") == "true"

        if not codigo:
            conn.close()
            return jsonify({"result":"error","mensaje":"Falta el código"})

        if not producto:
            conn.close()
            return jsonify({"result":"error","mensaje":"Falta el producto"})

        if not ubicacion and not multi_sucursal:
            conn.close()
            return jsonify({"result":"error","mensaje":"Falta la sucursal"})

        if multi_sucursal:
            ubicaciones = conn.execute("""
                SELECT nombre
                FROM ubicaciones
                ORDER BY nombre
            """).fetchall()

            lista_ubicaciones = [u["nombre"] for u in ubicaciones]
        else:
            lista_ubicaciones = [ubicacion]

        try:
            for ubicacion_item in lista_ubicaciones:

                ubicacion_item = (ubicacion_item or "").strip().upper()

                if not ubicacion_item:
                    continue

                row = conn.execute("""
                    SELECT id
                    FROM inventario
                    WHERE id LIKE 'P-%'
                    ORDER BY CAST(REPLACE(id,'P-','') AS INTEGER) DESC
                    LIMIT 1
                """).fetchone()

                if row:
                    ultimo = int(row["id"].replace("P-", ""))
                    nuevo_id = f"P-{str(ultimo + 1).zfill(4)}"
                else:
                    nuevo_id = "P-0001"

                conn.execute("""
                    INSERT INTO inventario(
                        id,
                        fecha,
                        codigo,
                        producto,
                        categoria,
                        cantidad,
                        precio,
                        proveedor,
                        ubicacion
                    )
                    VALUES(
                        ?,
                        datetime('now','localtime'),
                        ?,?,?,?,?,?,?
                    )
                """, (
                    nuevo_id,
                    codigo,
                    producto,
                    categoria,
                    cantidad,
                    precio,
                    proveedor,
                    ubicacion_item
                ))

            conn.commit()
            conn.close()
            return jsonify({"result":"ok"})

        except Exception as e:
            conn.rollback()
            conn.close()
            return jsonify({"result":"error","mensaje":str(e)})
    if tipo == "modificarProducto":
        id_producto = (request.form.get("id") or "").strip()
        codigo = (request.form.get("codigo") or "").strip().upper()
        producto = (request.form.get("producto") or "").strip().upper()
        categoria = (request.form.get("categoria") or "").strip().upper()
        cantidad = request.form.get("cantidad") or 0
        precio = request.form.get("precio") or 0
        proveedor = (request.form.get("proveedor") or "").strip().upper()
        ubicacion = (request.form.get("ubicacion") or "").strip().upper()

        if not id_producto:
            conn.close()
            return jsonify({"result":"error","mensaje":"Falta el ID del producto"})

        if not codigo:
            conn.close()
            return jsonify({"result":"error","mensaje":"Falta el código"})

        if not producto:
            conn.close()
            return jsonify({"result":"error","mensaje":"Falta el producto"})

        if not ubicacion:
            conn.close()
            return jsonify({"result":"error","mensaje":"Falta la sucursal"})

        try:
            cursor = conn.execute("""
                UPDATE inventario
                SET codigo=?,
                    producto=?,
                    categoria=?,
                    cantidad=?,
                    precio=?,
                    proveedor=?,
                    ubicacion=?
                WHERE id=?
            """, (
                codigo,
                producto,
                categoria,
                cantidad,
                precio,
                proveedor,
                ubicacion,
                id_producto
            ))

            conn.commit()
            conn.close()

            if cursor.rowcount == 0:
                return jsonify({
                    "result":"error",
                    "mensaje":"No se encontró el producto para modificar"
                })

            return jsonify({"result":"ok"})

        except Exception as e:
            conn.rollback()
            conn.close()
            return jsonify({"result":"error","mensaje":str(e)})
    if tipo == "agregarCompra":
        folio = (request.form.get("folio") or "").strip().upper()
        factura = (request.form.get("factura") or "").strip().upper()
        proveedor = (request.form.get("proveedor") or "").strip().upper()
        fecha = (request.form.get("fecha") or "").strip()
        sucursal = (request.form.get("sucursal") or "").strip().upper()
        observaciones = (request.form.get("observaciones") or "").strip().upper()
        subtotal = float(request.form.get("subtotal") or 0)
        iva = float(request.form.get("iva") or 0)
        iva_porcentaje = float(request.form.get("iva_porcentaje") or 16)
        total = float(request.form.get("total") or 0)
        estado = (request.form.get("estado") or "Pendiente").strip()
        creado_por = (request.form.get("creado_por") or "").strip().upper()
        productos_json = request.form.get("productos") or "[]"
        
        if not folio:
            conn.close()
            return jsonify({"result":"error","mensaje":"Falta el folio de compra"})

        if not factura:
            conn.close()
            return jsonify({"result":"error","mensaje":"Falta el número de factura"})

        if not proveedor:
            conn.close()
            return jsonify({"result":"error","mensaje":"Falta el proveedor"})

        if not sucursal:
            conn.close()
            return jsonify({"result":"error","mensaje":"Falta la sucursal"})

        try:
            productos = json.loads(productos_json)
        except:
            productos = []

        if len(productos) == 0:
            conn.close()
            return jsonify({"result":"error","mensaje":"Agrega al menos un producto"})

        existe = conn.execute("""
            SELECT id
            FROM compras
            WHERE upper(trim(factura)) = upper(trim(?))
            AND upper(trim(proveedor)) = upper(trim(?))
        """, (factura, proveedor)).fetchone()

        if existe:
            conn.close()
            return jsonify({
                "result":"error",
                "mensaje":"Ya existe una compra con esa factura y proveedor"
            })

        try:
            conn.execute("""
                INSERT INTO compras(
                    folio,
                    factura,
                    fecha,
                    proveedor,
                    sucursal,
                    observaciones,
                    subtotal,
                    iva,
                    iva_porcentaje,
                    total,
                    estado,
                    creado_por
                )
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                folio,
                factura,
                fecha,
                proveedor,
                sucursal,
                observaciones,
                subtotal,
                iva,
                iva_porcentaje,
                total,
                estado,
                creado_por
            ))

            for p in productos:
                codigo = str(p.get("codigo") or "").strip().upper()
                producto = str(p.get("producto") or "").strip().upper()
                cantidad = float(p.get("cantidad") or 0)
                costo_unitario = float(p.get("costo_unitario") or 0)
                subtotal_producto = float(p.get("subtotal") or 0)

                conn.execute("""
                    INSERT INTO compras_detalle(
                        folio_compra,
                        codigo,
                        producto,
                        cantidad,
                        costo_unitario,
                        subtotal
                    )
                    VALUES(?,?,?,?,?,?)
                """, (
                    folio,
                    codigo,
                    producto,
                    cantidad,
                    costo_unitario,
                    subtotal_producto
                ))

            conn.commit()
            conn.close()
            return jsonify({"result":"ok","folio":folio})

        except Exception as e:
            conn.rollback()
            conn.close()
            return jsonify({"result":"error","mensaje":str(e)})

    if tipo == "modificarCompra":
        folio = (request.form.get("folio") or "").strip().upper()
        factura = (request.form.get("factura") or "").strip().upper()
        proveedor = (request.form.get("proveedor") or "").strip().upper()
        fecha = (request.form.get("fecha") or "").strip()
        sucursal = (request.form.get("sucursal") or "").strip().upper()
        observaciones = (request.form.get("observaciones") or "").strip().upper()
        subtotal = float(request.form.get("subtotal") or 0)
        iva = float(request.form.get("iva") or 0)
        iva_porcentaje = float(request.form.get("iva_porcentaje") or 16)
        total = float(request.form.get("total") or 0)
        estado = (request.form.get("estado") or "Pendiente").strip()
        productos_json = request.form.get("productos") or "[]"

        if not folio:
            conn.close()
            return jsonify({"result":"error","mensaje":"Falta el folio"})

        try:
            productos = json.loads(productos_json)
        except:
            productos = []

        if len(productos) == 0:
            conn.close()
            return jsonify({"result":"error","mensaje":"Agrega al menos un producto"})

        try:
            conn.execute("""
                UPDATE compras
                SET factura=?,
                    fecha=?,
                    proveedor=?,
                    sucursal=?,
                    observaciones=?,
                    subtotal=?,
                    iva=?,
                    iva_porcentaje=?,
                    total=?,
                    estado=?
                WHERE folio=?
            """, (
                factura,
                fecha,
                proveedor,
                sucursal,
                observaciones,
                subtotal,
                iva,
                iva_porcentaje,
                total,
                estado,
                folio
            ))

            conn.execute("""
                DELETE FROM compras_detalle
                WHERE folio_compra=?
            """, (folio,))

            for p in productos:
                codigo = str(p.get("codigo") or "").strip().upper()
                producto = str(p.get("producto") or "").strip().upper()
                cantidad = float(p.get("cantidad") or 0)
                costo_unitario = float(p.get("costo_unitario") or 0)
                subtotal_producto = float(p.get("subtotal") or 0)

                conn.execute("""
                    INSERT INTO compras_detalle(
                        folio_compra,
                        codigo,
                        producto,
                        cantidad,
                        costo_unitario,
                        subtotal
                    )
                    VALUES(?,?,?,?,?,?)
                """, (
                    folio,
                    codigo,
                    producto,
                    cantidad,
                    costo_unitario,
                    subtotal_producto
                ))

            conn.commit()
            conn.close()
            return jsonify({"result":"ok"})

        except Exception as e:
            conn.rollback()
            conn.close()
            return jsonify({"result":"error","mensaje":str(e)})

    if tipo == "eliminarCompra":
        folio = (request.form.get("folio") or "").strip().upper()

        if not folio:
            conn.close()
            return jsonify({"result":"error","mensaje":"Falta el folio"})

        try:
            conn.execute("""
                DELETE FROM compras_detalle
                WHERE folio_compra=?
            """, (folio,))

            conn.execute("""
                DELETE FROM compras
                WHERE folio=?
            """, (folio,))

            conn.commit()
            conn.close()
            return jsonify({"result":"ok"})

        except Exception as e:
            conn.rollback()
            conn.close()
            return jsonify({"result":"error","mensaje":str(e)})
    if tipo == "recibirCompra":
        folio = (request.form.get("folio") or "").strip().upper()
        usuario = (request.form.get("usuario") or "").strip().upper()

        compra = conn.execute("""
            SELECT *
            FROM compras
            WHERE folio=?
        """, (folio,)).fetchone()

        if not compra:
            conn.close()
            return jsonify({
                "result": "error",
                "mensaje": "Compra no encontrada"
            })

        if str(compra["estado"]).lower() == "recibida":
            conn.close()
            return jsonify({
                "result": "error",
                "mensaje": "Esta compra ya fue recibida"
            })

        detalles = conn.execute("""
            SELECT *
            FROM compras_detalle
            WHERE folio_compra=?
        """, (folio,)).fetchall()

        try:
            for d in detalles:
                codigo = str(d["codigo"] or "").strip().upper()
                producto = str(d["producto"] or "").strip().upper()
                cantidad = float(d["cantidad"] or 0)
                costo = float(d["costo_unitario"] or 0)
                sucursal = str(compra["sucursal"] or "").strip().upper()
                proveedor = str(compra["proveedor"] or "").strip().upper()

                existente = conn.execute("""
                    SELECT *
                    FROM inventario
                    WHERE upper(trim(codigo)) = upper(trim(?))
                    AND upper(trim(ubicacion)) = upper(trim(?))
                    LIMIT 1
                """, (codigo, sucursal)).fetchone()

                if existente:
                    nueva_cantidad = float(existente["cantidad"] or 0) + cantidad

                    conn.execute("""
                        UPDATE inventario
                        SET cantidad=?,
                            precio=?,
                            proveedor=?
                        WHERE id=?
                    """, (
                        nueva_cantidad,
                        costo,
                        proveedor,
                        existente["id"]
                    ))
                else:
                    row = conn.execute("""
                        SELECT id
                        FROM inventario
                        WHERE id LIKE 'P-%'
                        ORDER BY CAST(REPLACE(id,'P-','') AS INTEGER) DESC
                        LIMIT 1
                    """).fetchone()

                    if row:
                        ultimo = int(row["id"].replace("P-", ""))
                        nuevo_id = f"P-{str(ultimo + 1).zfill(4)}"
                    else:
                        nuevo_id = "P-0001"

                    conn.execute("""
                        INSERT INTO inventario(
                            id,
                            fecha,
                            codigo,
                            producto,
                            categoria,
                            cantidad,
                            precio,
                            proveedor,
                            ubicacion
                        )
                        VALUES(
                            ?,
                            datetime('now','localtime'),
                            ?,?,?,?,?,?,?
                        )
                    """, (
                        nuevo_id,
                        codigo,
                        producto,
                        "",
                        cantidad,
                        costo,
                        proveedor,
                        sucursal
                    ))

                conn.execute("""
                    INSERT INTO movimientos(
                        fecha,
                        codigo,
                        producto,
                        tipo,
                        cantidad,
                        descripcion,
                        usuario,
                        sucursal,
                        destino
                    )
                    VALUES(datetime('now','localtime'),?,?,?,?,?,?,?,?)
                """, (
                    codigo,
                    producto,
                    "Entrada por compra",
                    cantidad,
                    "COMPRA RECIBIDA " + folio,
                    usuario,
                    sucursal,
                    ""
                ))

            conn.execute("""
                UPDATE compras
                SET estado='Recibida'
                WHERE folio=?
            """, (folio,))

            conn.commit()
            conn.close()

            return jsonify({"result":"ok"})

        except Exception as e:
            conn.rollback()
            conn.close()
            return jsonify({
                "result":"error",
                "mensaje":str(e)
            })    
    if tipo == "eliminarProducto":
          try:
            id_producto = request.form.get("id")

            print("ID A ELIMINAR:", id_producto)

            cursor = conn.execute("""
                DELETE FROM inventario
                WHERE id = ?
            """, (id_producto,))

            conn.commit()
            conn.close()

            if cursor.rowcount == 0:
                return jsonify({
                    "result": "error",
                    "mensaje": "No se encontró el producto"
                })

            return jsonify({"result": "ok"})

          except Exception as e:
             print("ERROR AL ELIMINAR:", e)
             conn.close()
          return jsonify({
                "result": "error",
                "mensaje": str(e)
            })

    if tipo == "movimientoInventario":
        codigo = (request.form.get("codigo") or "").strip()
        cantidad = int(request.form.get("cantidad") or 0)
        tipo_mov = request.form.get("tipoMovimiento")
        sucursal = (request.form.get("sucursal") or "").strip()
        destino = (request.form.get("destino") or "").strip()
        transferencia = request.form.get("transferencia") == "true"

        # Normalizar sucursal origen con el nombre real guardado en ubicaciones
        row_sucursal = conn.execute("""
            SELECT nombre
            FROM ubicaciones
            WHERE upper(trim(nombre)) = upper(trim(?))
            LIMIT 1
        """, (sucursal,)).fetchone()

        if row_sucursal:
            sucursal = row_sucursal["nombre"]

        # Normalizar sucursal destino con el nombre real guardado en ubicaciones
        if destino:
            row_destino = conn.execute("""
                SELECT nombre
                FROM ubicaciones
                WHERE upper(trim(nombre)) = upper(trim(?))
                LIMIT 1
            """, (destino,)).fetchone()

            if row_destino:
                destino = row_destino["nombre"]

        producto_origen = conn.execute("""
            SELECT *
            FROM inventario
            WHERE upper(trim(codigo)) = upper(trim(?))
            AND upper(trim(ubicacion)) = upper(trim(?))
            LIMIT 1
        """, (codigo, sucursal)).fetchone()

        if not producto_origen:
            conn.close()
            return jsonify({
                "result": "error",
                "mensaje": "Producto no encontrado en sucursal origen"
            })

        cantidad_origen = int(producto_origen["cantidad"] or 0)

        if transferencia:

            if not destino:
                conn.close()
                return jsonify({
                    "result": "error",
                    "mensaje": "Selecciona una sucursal destino"
                })

            if sucursal.strip().upper() == destino.strip().upper():
                conn.close()
                return jsonify({
                    "result": "error",
                    "mensaje": "La sucursal destino debe ser diferente a la sucursal origen"
                })

            if cantidad_origen < cantidad:
                conn.close()
                return jsonify({
                    "result": "error",
                    "mensaje": "No hay suficiente inventario en origen"
                })

            # RESTAR EN ORIGEN
            conn.execute("""
                UPDATE inventario
                SET cantidad=?
                WHERE id=?
            """, (
                cantidad_origen - cantidad,
                producto_origen["id"]
            ))

            producto_destino = conn.execute("""
                SELECT *
                FROM inventario
                WHERE upper(trim(codigo)) = upper(trim(?))
                AND upper(trim(ubicacion)) = upper(trim(?))
                LIMIT 1
            """, (codigo, destino)).fetchone()

            if producto_destino:
                cantidad_destino = int(producto_destino["cantidad"] or 0)

                # SUMAR EN DESTINO EXISTENTE
                conn.execute("""
                    UPDATE inventario
                    SET cantidad=?
                    WHERE id=?
                """, (
                    cantidad_destino + cantidad,
                    producto_destino["id"]
                ))

            else:
                # CREAR PRODUCTO EN DESTINO SI NO EXISTE
                row = conn.execute("""
                    SELECT id
                    FROM inventario
                    WHERE id LIKE 'P-%'
                    ORDER BY CAST(REPLACE(id,'P-','') AS INTEGER) DESC
                    LIMIT 1
                """).fetchone()

                if row:
                    ultimo = int(row["id"].replace("P-", ""))
                    nuevo_id = f"P-{str(ultimo + 1).zfill(4)}"
                else:
                    nuevo_id = "P-0001"

                conn.execute("""
                    INSERT INTO inventario(
                        id,
                        fecha,
                        codigo,
                        producto,
                        categoria,
                        cantidad,
                        precio,
                        proveedor,
                        ubicacion
                    )
                    VALUES(
                        ?,
                        datetime('now','localtime'),
                        ?,?,?,?,?,?,?
                    )
                """, (
                    nuevo_id,
                    producto_origen["codigo"],
                    producto_origen["producto"],
                    producto_origen["categoria"],
                    cantidad,
                    producto_origen["precio"],
                    producto_origen["proveedor"],
                    destino
                ))

        else:
            # ENTRADA O SALIDA NORMAL, SOLO EN LA SUCURSAL ORIGEN
            if tipo_mov == "Entrada":
                nueva_cantidad = cantidad_origen + cantidad
            else:
                nueva_cantidad = cantidad_origen - cantidad

            if nueva_cantidad < 0:
                conn.close()
                return jsonify({
                    "result": "error",
                    "mensaje": "No hay suficiente inventario"
                })

            conn.execute("""
                UPDATE inventario
                SET cantidad=?
                WHERE id=?
            """, (
                nueva_cantidad,
                producto_origen["id"]
            ))

            destino = ""

        cursor_movimiento = conn.execute("""
    INSERT INTO movimientos(
        fecha,
        codigo,
        producto,
        tipo,
        cantidad,
        descripcion,
        usuario,
        sucursal,
        destino
    )
    VALUES(datetime('now','localtime'),?,?,?,?,?,?,?,?)
""", (
    codigo,
    producto_origen["producto"],
    tipo_mov,
    cantidad,
    request.form.get("descripcion"),
    request.form.get("usuario"),
    sucursal,
    destino
    ))

        folio_movimiento = cursor_movimiento.lastrowid

        conn.commit()
        conn.close()

        return jsonify({
        "result": "ok",
        "folio": folio_movimiento
        })
    if tipo == "agregarUbicacion":
        nombre = (request.form.get("nombre") or "").strip().upper()
        direccion = (request.form.get("direccion") or "").strip().upper()
        telefono = (request.form.get("telefono") or "").strip()

        if not nombre:
            conn.close()
            return jsonify({"result":"error","mensaje":"El nombre es obligatorio"})

        existe = conn.execute("""
            SELECT id FROM ubicaciones
            WHERE upper(nombre)=upper(?)
            LIMIT 1
        """, (nombre,)).fetchone()

        if existe:
            conn.close()
            return jsonify({"result":"error","mensaje":"La ubicación ya existe"})

        conn.execute("""
            INSERT INTO ubicaciones(nombre,direccion,telefono,estado)
            VALUES(?,?,?,?)
        """, (nombre,direccion,telefono,"Activa"))

        conn.commit()
        conn.close()
        return jsonify({"result":"ok"})

    if tipo == "modificarUbicacion":
        id_ubicacion = request.form.get("id")
        nombre = (request.form.get("nombre") or "").strip().upper()
        direccion = (request.form.get("direccion") or "").strip().upper()
        telefono = (request.form.get("telefono") or "").strip()
        estado = request.form.get("estado") or "Activa"
        if not id_ubicacion or not nombre:
            conn.close()
            return jsonify({"result":"error","mensaje":"ID y nombre son obligatorios"})

        conn.execute("""
            UPDATE ubicaciones
            SET nombre=?, direccion=?, telefono=?, estado=?
            WHERE id=?
        """, (nombre,direccion,telefono,estado,id_ubicacion))

        conn.commit()
        conn.close()
        return jsonify({"result":"ok"})

    if tipo == "eliminarUbicacion":
        id_ubicacion = request.form.get("id")

        if not id_ubicacion:
            conn.close()
            return jsonify({"result":"error","mensaje":"ID obligatorio"})

        conn.execute("DELETE FROM ubicaciones WHERE id=?", (id_ubicacion,))
        conn.commit()
        conn.close()
        return jsonify({"result":"ok"})

    if tipo == "agregarProveedor":
        nombre = (request.form.get("nombre") or "").strip().upper()
        direccion = (request.form.get("direccion") or "").strip().upper()
        telefono = (request.form.get("telefono") or "").strip()

        if not nombre:
            conn.close()
            return jsonify({
                "result": "error",
                "mensaje": "El nombre del proveedor es obligatorio"
            })

        existe = conn.execute("""
            SELECT id
            FROM proveedores
            WHERE upper(trim(nombre)) = upper(trim(?))
            LIMIT 1
        """, (nombre,)).fetchone()

        if existe:
            conn.close()
            return jsonify({
                "result": "error",
                "mensaje": "Este proveedor ya existe"
            })

        conn.execute("""
            INSERT INTO proveedores(nombre, direccion, telefono)
            VALUES(?,?,?)
        """, (
            nombre,
            direccion,
            telefono
        ))

        conn.commit()
        conn.close()

        return jsonify({"result": "ok"})
    if tipo == "modificarProveedor":
        id_proveedor = request.form.get("id")
        nombre = (request.form.get("nombre") or "").strip().upper()
        direccion = (request.form.get("direccion") or "").strip().upper()
        telefono = (request.form.get("telefono") or "").strip()

        if not id_proveedor or not nombre:
            conn.close()
            return jsonify({
                "result": "error",
                "mensaje": "ID y nombre son obligatorios"
            })

        existe = conn.execute("""
            SELECT id
            FROM proveedores
            WHERE upper(trim(nombre)) = upper(trim(?))
            AND id != ?
            LIMIT 1
        """, (
            nombre,
            id_proveedor
        )).fetchone()

        if existe:
            conn.close()
            return jsonify({
                "result": "error",
                "mensaje": "Ya existe otro proveedor con ese nombre"
            })

        conn.execute("""
            UPDATE proveedores
            SET nombre=?,
                direccion=?,
                telefono=?
            WHERE id=?
        """, (
            nombre,
            direccion,
            telefono,
            id_proveedor
        ))

        conn.commit()
        conn.close()

        return jsonify({"result": "ok"})
    if tipo == "eliminarProveedor":
        id_proveedor = request.form.get("id")

        if not id_proveedor:
            conn.close()
            return jsonify({
                "result": "error",
                "mensaje": "Falta el ID del proveedor"
            })

        conn.execute("""
            DELETE FROM proveedores
            WHERE id=?
        """, (id_proveedor,))

        conn.commit()
        conn.close()

        return jsonify({"result": "ok"})
    
    conn.close()
    return jsonify({"result":"error","mensaje":"Tipo no reconocido"})
    
    

@app.route("/api/consultasPendientes", methods=["POST"])
def consultas_pendientes():
    conn = get_db()
    sucursal = request.form.get("sucursal") or "TODAS"

    if sucursal == "TODAS":
        data = conn.execute("""
            SELECT *
            FROM consultas
            WHERE estado='Pendiente'
            ORDER BY fecha DESC
        """).fetchall()
    else:
        data = conn.execute("""
            SELECT *
            FROM consultas
            WHERE estado='Pendiente'
            AND ubicaciones=?
            ORDER BY fecha DESC
        """, (sucursal,)).fetchall()

    conn.close()
    return jsonify([dict(row) for row in data])
@app.route("/api/guardarConsulta", methods=["POST"])
def guardar_consulta():
    conn = get_db()

    consulta_id = "C-" + str(uuid.uuid4())[:8].upper()

    nombre = request.form.get("nombre", "")
    correo = request.form.get("correo", "")
    telefono = request.form.get("telefono", "")
    consulta = request.form.get("consulta", "")
    descripcion = request.form.get("descripcion", "")

    conn.execute("""
        INSERT INTO consultas(
            id, fecha, nombre, correo, telefono,
            consulta, descripcion, estado, fecha_cierre
        )
        VALUES(
            ?, datetime('now','localtime'), ?, ?, ?, ?, ?, 'Pendiente', ''
        )
    """, (
        consulta_id,
        nombre,
        correo,
        telefono,
        consulta,
        descripcion
    ))

    conn.commit()
    conn.close()

    try:
        enviar_correo_consulta(nombre, correo, telefono, consulta, descripcion)
    except Exception as e:
        print("Error enviando correo:", e)

    return jsonify({"result": "ok"})
def enviar_correo_consulta(nombre, correo, telefono, consulta, descripcion):
    remitente = "edainballesteros8@gmail.com"
    password = "mvsh zmne gtpe pkla"
    destinatario = "edainballesteros8@gmail.com"

    cuerpo = f"""
    Nueva consulta desde la página web

    Nombre: {nombre}
    Correo: {correo}
    Teléfono: {telefono}
    Consulta: {consulta}

    Descripción:
    {descripcion}
    """

    msg = MIMEText(cuerpo, "plain", "utf-8")
    msg["Subject"] = "Nueva Consulta - Multiservicios GABE"
    msg["From"] = remitente
    msg["To"] = destinatario

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as servidor:
        servidor.login(remitente, password)
        servidor.send_message(msg)  
@app.route("/api/recuperarPassword", methods=["POST"])
def recuperar_password():
    dato = request.form.get("dato", "").strip()

    conn = get_db()
    user = conn.execute("""
        SELECT usuario, password, nombre, email
        FROM usuarios
        WHERE usuario = ?
        OR email = ?
        LIMIT 1
    """, (dato, dato)).fetchone()
    conn.close()

    if not user:
        return jsonify({"result": "error", "mensaje": "Usuario o correo no encontrado"})

    if not user["email"]:
        return jsonify({"result": "error", "mensaje": "Este usuario no tiene correo registrado"})

    try:
        cuerpo = f"""
Hola {user['nombre']}

Estos son tus datos de acceso:

Usuario: {user['usuario']}
Contraseña: {user['password']}

Multiservicios GABE
"""

        msg = MIMEText(cuerpo, "plain", "utf-8")
        msg["Subject"] = "Recuperación de contraseña - Multiservicios GABE"
        msg["From"] = "edainballesteros8@gmail.com"
        msg["To"] = user["email"]

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as servidor:
            servidor.login("edainballesteros8@gmail.com", "mvsh zmne gtpe pkla")
            servidor.send_message(msg)

        return jsonify({"result": "ok"})

    except Exception as e:
        print("Error recuperar password:", e)
        return jsonify({"result": "error", "mensaje": "No se pudo enviar el correo"})         
@app.route("/api/guardarCita", methods=["POST"])
def guardar_cita():
    conn = get_db()

    conn.execute("""
        INSERT INTO agenda(
            cliente,
            telefono,
            vehiculo,
            fecha,
            hora,
            servicio,
            notas,
            estado,
            ubicaciones
        )
        VALUES(?,?,?,?,?,?,?,?,?)
    """, (
        request.form.get("cliente"),
        request.form.get("telefono"),
        request.form.get("vehiculo"),
        request.form.get("fecha"),
        request.form.get("hora"),
        request.form.get("servicio"),
        request.form.get("notas"),
        "Pendiente",
        request.form.get("ubicaciones")
    ))

    conn.commit()
    conn.close()

    return jsonify({"result":"ok"})

@app.route("/api/agenda")
def agenda():
    sucursal = request.args.get("sucursal") or "TODAS"

    conn = get_db()

    if sucursal == "TODAS":
        data = conn.execute("""
            SELECT *
            FROM agenda
            ORDER BY fecha ASC, hora ASC
        """).fetchall()
    else:
        data = conn.execute("""
            SELECT *
            FROM agenda
            WHERE ubicaciones=?
            ORDER BY fecha ASC, hora ASC
        """, (sucursal,)).fetchall()

    conn.close()
    return jsonify([dict(row) for row in data])

@app.route("/api/obtenerOrden")
def obtener_orden():
    orden = request.args.get("orden")

    conn = get_db()

    fila = conn.execute("""
        SELECT 
            o.*,
            u.rol AS rol_cliente,
            u.email AS email_cliente,
            u.direccion AS direccion_cliente,
            u.telefono AS telefono_usuario,
            v.anio AS anio_vehiculo,
            v.vin AS vin_vehiculo,
            v.odometro AS odometro_vehiculo,
            v.color AS color_vehiculo
        FROM ordenes o
        LEFT JOIN usuarios u 
            ON o.usuario = u.usuario
        LEFT JOIN vehiculos v 
            ON o.usuario = v.usuario
            AND o.placa = v.placa
        WHERE o.orden = ?
        LIMIT 1
    """, (orden,)).fetchone()

    conn.close()

    if not fila:
        return jsonify({"error":"No encontrada"})

    return jsonify(dict(fila))

@app.route("/api/eliminarCita")
def eliminar_cita():
    id = request.args.get("id")
    conn = get_db()
    conn.execute("DELETE FROM agenda WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return jsonify({"result":"ok"})


@app.route("/api/finalizarCita")
def finalizar_cita():
    id = request.args.get("id")
    conn = get_db()
    conn.execute("""
        UPDATE agenda
        SET estado='Finalizada'
        WHERE id=?
    """, (id,))
    conn.commit()
    conn.close()
    return jsonify({"result":"ok"})
@app.route("/api/cambiarLogo", methods=["POST"])
def cambiar_logo():
    if "logo" not in request.files:
        return jsonify({"result":"error","mensaje":"No se recibió archivo"})

    archivo = request.files["logo"]

    if archivo.filename == "":
        return jsonify({"result":"error","mensaje":"Archivo vacío"})

    extension = archivo.filename.rsplit(".",1)[-1].lower()

    if extension not in ["png","jpg","jpeg","webp"]:
        return jsonify({"result":"error","mensaje":"Formato no permitido"})

    ruta = os.path.join("static","img","logo_actual.png")
    from PIL import Image

    ruta = os.path.join("static", "img", "logo_actual.png")

    # Abrir la imagen subida
    imagen = Image.open(archivo)

    # Convertir a RGBA (para conservar transparencias si existen)
    imagen = imagen.convert("RGBA")

    # Redimensionar manteniendo la proporción
    imagen.thumbnail((180, 180), Image.LANCZOS)

        # Guardar optimizada
    imagen.save(ruta, optimize=True)

    return jsonify({
        "result":"ok",
        "logo":"/static/img/logo_actual.png"
    })
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
