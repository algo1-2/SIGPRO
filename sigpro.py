#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SIGPRO - Sistema Interno de Gestión y Seguimiento de Proyectos
Versión prototipo funcional en Python + SQLite.

Objetivo:
- Registrar proyectos, responsables, personal, pagos, actualizaciones y trazabilidad.
- Funcionar localmente, sin conexión a internet.
- Mantener historial de acciones del sistema.

Credenciales iniciales:
- Usuario: admin      Contraseña: admin123      Rol: admin
- Usuario: supervisor Contraseña: supervisor123 Rol: supervisor
- Usuario: consulta   Contraseña: consulta123   Rol: consulta

Recomendación: cambia estas claves si lo usas para una demo real.
"""

from __future__ import annotations

import csv
import getpass
import hashlib
import os
import sqlite3
import sys
from datetime import datetime, date
from pathlib import Path
from typing import Optional, Iterable

DB_PATH = Path(__file__).with_name("sigpro.db")
EXPORT_DIR = Path(__file__).with_name("exportaciones")

STATUS_VALIDOS = ["Pendiente", "En proceso", "Detenido", "Observado", "Finalizado", "En revisión"]
ROLES_USUARIO = ["admin", "supervisor", "consulta"]


# -----------------------------------------------------------------------------
# Utilidades generales
# -----------------------------------------------------------------------------

def limpiar_pantalla() -> None:
    # Evita mensajes molestos cuando el programa se prueba con entrada redirigida.
    if sys.stdout.isatty():
        os.system("cls" if os.name == "nt" else "clear")


def ahora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def hoy() -> str:
    return date.today().isoformat()


def pausar() -> None:
    input("\nPresiona ENTER para continuar...")


def input_no_vacio(mensaje: str) -> str:
    while True:
        valor = input(mensaje).strip()
        if valor:
            return valor
        print("Este campo no puede quedar vacío.")


def input_opcional(mensaje: str, valor_actual: Optional[str] = None) -> Optional[str]:
    if valor_actual is not None:
        valor = input(f"{mensaje} [{valor_actual}]: ").strip()
        return valor if valor else valor_actual
    valor = input(mensaje).strip()
    return valor if valor else None


def input_float(mensaje: str, defecto: Optional[float] = None) -> float:
    while True:
        raw = input(mensaje).strip()
        if not raw and defecto is not None:
            return defecto
        try:
            return float(raw.replace(",", "."))
        except ValueError:
            print("Ingresa un número válido. Ejemplo: 1500000")


def elegir_opcion(titulo: str, opciones: list[str], permitir_vacio: bool = False, valor_actual: Optional[str] = None) -> Optional[str]:
    print(f"\n{titulo}")
    for i, opcion in enumerate(opciones, start=1):
        print(f"{i}. {opcion}")
    while True:
        extra = "" if not permitir_vacio else " o ENTER para mantener/saltar"
        raw = input(f"Elige una opción{extra}: ").strip()
        if permitir_vacio and raw == "":
            return valor_actual
        if raw.isdigit() and 1 <= int(raw) <= len(opciones):
            return opciones[int(raw) - 1]
        print("Opción inválida.")


def formatear_dinero(valor: Optional[float]) -> str:
    if valor is None:
        return "$0"
    return "$" + f"{valor:,.0f}".replace(",", ".")


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def conectar() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ejecutar(conn: sqlite3.Connection, sql: str, params: Iterable = ()) -> sqlite3.Cursor:
    cur = conn.execute(sql, tuple(params))
    conn.commit()
    return cur


# -----------------------------------------------------------------------------
# Base de datos
# -----------------------------------------------------------------------------

def inicializar_db() -> None:
    with conectar() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                rol TEXT NOT NULL CHECK (rol IN ('admin','supervisor','consulta')),
                activo INTEGER NOT NULL DEFAULT 1,
                creado_en TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS personas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                cargo TEXT,
                departamento TEXT,
                email TEXT,
                telefono TEXT,
                activo INTEGER NOT NULL DEFAULT 1,
                creado_en TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS proyectos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo TEXT UNIQUE NOT NULL,
                nombre TEXT NOT NULL,
                descripcion TEXT,
                entidad TEXT,
                departamento TEXT,
                estado TEXT NOT NULL,
                prioridad TEXT DEFAULT 'Media',
                fecha_inicio TEXT,
                fecha_estimada_termino TEXT,
                presupuesto_asignado REAL DEFAULT 0,
                presupuesto_usado REAL DEFAULT 0,
                responsable_id INTEGER,
                supervisor_id INTEGER,
                empresa_externa TEXT,
                observaciones TEXT,
                creado_en TEXT NOT NULL,
                actualizado_en TEXT NOT NULL,
                FOREIGN KEY (responsable_id) REFERENCES personas(id) ON DELETE SET NULL,
                FOREIGN KEY (supervisor_id) REFERENCES personas(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS proyecto_personas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proyecto_id INTEGER NOT NULL,
                persona_id INTEGER NOT NULL,
                rol_en_proyecto TEXT NOT NULL,
                observaciones TEXT,
                creado_en TEXT NOT NULL,
                UNIQUE (proyecto_id, persona_id, rol_en_proyecto),
                FOREIGN KEY (proyecto_id) REFERENCES proyectos(id) ON DELETE CASCADE,
                FOREIGN KEY (persona_id) REFERENCES personas(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS actualizaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proyecto_id INTEGER NOT NULL,
                tipo TEXT NOT NULL,
                descripcion TEXT NOT NULL,
                fecha_compromiso TEXT,
                registrado_por INTEGER NOT NULL,
                creado_en TEXT NOT NULL,
                FOREIGN KEY (proyecto_id) REFERENCES proyectos(id) ON DELETE CASCADE,
                FOREIGN KEY (registrado_por) REFERENCES usuarios(id) ON DELETE RESTRICT
            );

            CREATE TABLE IF NOT EXISTS pagos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proyecto_id INTEGER NOT NULL,
                monto REAL NOT NULL,
                concepto TEXT NOT NULL,
                fecha_pago TEXT NOT NULL,
                estado TEXT NOT NULL DEFAULT 'Registrado',
                registrado_por INTEGER NOT NULL,
                creado_en TEXT NOT NULL,
                FOREIGN KEY (proyecto_id) REFERENCES proyectos(id) ON DELETE CASCADE,
                FOREIGN KEY (registrado_por) REFERENCES usuarios(id) ON DELETE RESTRICT
            );

            CREATE TABLE IF NOT EXISTS bitacora (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER,
                accion TEXT NOT NULL,
                tabla_afectada TEXT,
                registro_id INTEGER,
                detalle TEXT,
                creado_en TEXT NOT NULL,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL
            );
            """
        )
        conn.commit()
        crear_usuarios_base(conn)


def crear_usuarios_base(conn: sqlite3.Connection) -> None:
    usuarios = [
        ("admin", "admin123", "admin"),
        ("supervisor", "supervisor123", "supervisor"),
        ("consulta", "consulta123", "consulta"),
    ]
    for username, password, rol in usuarios:
        conn.execute(
            """
            INSERT OR IGNORE INTO usuarios (username, password_hash, rol, activo, creado_en)
            VALUES (?, ?, ?, 1, ?)
            """,
            (username, hash_password(password), rol, ahora()),
        )
    conn.commit()


def registrar_bitacora(conn: sqlite3.Connection, usuario_id: Optional[int], accion: str, tabla: Optional[str] = None,
                       registro_id: Optional[int] = None, detalle: Optional[str] = None) -> None:
    conn.execute(
        """
        INSERT INTO bitacora (usuario_id, accion, tabla_afectada, registro_id, detalle, creado_en)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (usuario_id, accion, tabla, registro_id, detalle, ahora()),
    )
    conn.commit()


# -----------------------------------------------------------------------------
# Seguridad básica y permisos
# -----------------------------------------------------------------------------

def login() -> Optional[sqlite3.Row]:
    limpiar_pantalla()
    print("SIGPRO - Sistema Interno de Gestión y Seguimiento de Proyectos")
    print("Inicio de sesión\n")

    username = input("Usuario: ").strip()
    password = getpass.getpass("Contraseña: ")

    with conectar() as conn:
        usuario = conn.execute(
            "SELECT * FROM usuarios WHERE username = ? AND activo = 1",
            (username,),
        ).fetchone()
        if usuario and usuario["password_hash"] == hash_password(password):
            registrar_bitacora(conn, usuario["id"], "Inicio de sesión", "usuarios", usuario["id"], f"Usuario {username}")
            return usuario

    print("\nCredenciales incorrectas o usuario inactivo.")
    pausar()
    return None


def puede_escribir(usuario: sqlite3.Row) -> bool:
    return usuario["rol"] in ("admin", "supervisor")


def requiere_escritura(usuario: sqlite3.Row) -> bool:
    if puede_escribir(usuario):
        return True
    print("\nAcceso denegado: tu rol es de consulta. Solo puedes revisar información.")
    pausar()
    return False


def requiere_admin(usuario: sqlite3.Row) -> bool:
    if usuario["rol"] == "admin":
        return True
    print("\nAcceso denegado: esta acción requiere rol admin.")
    pausar()
    return False


# -----------------------------------------------------------------------------
# Consultas auxiliares
# -----------------------------------------------------------------------------

def obtener_personas(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, nombre, cargo, departamento FROM personas WHERE activo = 1 ORDER BY nombre"
    ).fetchall()


def seleccionar_persona(conn: sqlite3.Connection, titulo: str, permitir_sin_asignar: bool = True) -> Optional[int]:
    personas = obtener_personas(conn)
    if not personas:
        print("No hay personas registradas todavía.")
        return None

    print(f"\n{titulo}")
    if permitir_sin_asignar:
        print("0. Sin asignar")
    for p in personas:
        print(f"{p['id']}. {p['nombre']} | {p['cargo'] or 'Sin cargo'} | {p['departamento'] or 'Sin departamento'}")
    while True:
        raw = input("ID de persona: ").strip()
        if permitir_sin_asignar and raw == "0":
            return None
        if raw.isdigit():
            persona_id = int(raw)
            if any(p["id"] == persona_id for p in personas):
                return persona_id
        print("ID inválido.")


def seleccionar_proyecto(conn: sqlite3.Connection) -> Optional[sqlite3.Row]:
    proyectos = conn.execute(
        "SELECT id, codigo, nombre, estado FROM proyectos ORDER BY actualizado_en DESC"
    ).fetchall()
    if not proyectos:
        print("No hay proyectos registrados.")
        return None

    print("\nProyectos disponibles")
    for p in proyectos:
        print(f"{p['id']}. [{p['codigo']}] {p['nombre']} - {p['estado']}")

    while True:
        raw = input("ID del proyecto: ").strip()
        if raw.isdigit():
            proyecto_id = int(raw)
            proyecto = conn.execute("SELECT * FROM proyectos WHERE id = ?", (proyecto_id,)).fetchone()
            if proyecto:
                return proyecto
        print("ID inválido.")


# -----------------------------------------------------------------------------
# Módulo personas
# -----------------------------------------------------------------------------

def registrar_persona(usuario: sqlite3.Row) -> None:
    if not requiere_escritura(usuario):
        return
    limpiar_pantalla()
    print("Registrar persona\n")
    nombre = input_no_vacio("Nombre completo: ")
    cargo = input("Cargo: ").strip() or None
    departamento = input("Departamento/Área: ").strip() or None
    email = input("Email: ").strip() or None
    telefono = input("Teléfono: ").strip() or None

    with conectar() as conn:
        cur = ejecutar(
            conn,
            """
            INSERT INTO personas (nombre, cargo, departamento, email, telefono, activo, creado_en)
            VALUES (?, ?, ?, ?, ?, 1, ?)
            """,
            (nombre, cargo, departamento, email, telefono, ahora()),
        )
        registrar_bitacora(conn, usuario["id"], "Registró persona", "personas", cur.lastrowid, nombre)
    print("\nPersona registrada correctamente.")
    pausar()


def listar_personas() -> None:
    limpiar_pantalla()
    print("Personas registradas\n")
    with conectar() as conn:
        personas = conn.execute(
            "SELECT * FROM personas WHERE activo = 1 ORDER BY nombre"
        ).fetchall()
    if not personas:
        print("No hay personas registradas.")
    else:
        for p in personas:
            print(f"ID: {p['id']} | {p['nombre']}")
            print(f"Cargo: {p['cargo'] or '-'} | Departamento: {p['departamento'] or '-'}")
            print(f"Email: {p['email'] or '-'} | Teléfono: {p['telefono'] or '-'}")
            print("-" * 70)
    pausar()


# -----------------------------------------------------------------------------
# Módulo proyectos
# -----------------------------------------------------------------------------

def crear_proyecto(usuario: sqlite3.Row) -> None:
    if not requiere_escritura(usuario):
        return
    limpiar_pantalla()
    print("Crear proyecto\n")
    codigo = input_no_vacio("Código del proyecto: ").upper()
    nombre = input_no_vacio("Nombre del proyecto: ")
    descripcion = input("Descripción: ").strip() or None
    entidad = input("Entidad/Municipio/Empresa: ").strip() or None
    departamento = input("Departamento responsable: ").strip() or None
    estado = elegir_opcion("Estado inicial", STATUS_VALIDOS) or "Pendiente"
    prioridad = elegir_opcion("Prioridad", ["Baja", "Media", "Alta", "Crítica"]) or "Media"
    fecha_inicio = input(f"Fecha de inicio [{hoy()}]: ").strip() or hoy()
    fecha_estimada = input("Fecha estimada de término [YYYY-MM-DD]: ").strip() or None
    presupuesto = input_float("Presupuesto asignado: ", 0)
    empresa_externa = input("Empresa externa involucrada: ").strip() or None
    observaciones = input("Observaciones iniciales: ").strip() or None

    with conectar() as conn:
        responsable_id = seleccionar_persona(conn, "Responsable principal", permitir_sin_asignar=True)
        supervisor_id = seleccionar_persona(conn, "Supervisor", permitir_sin_asignar=True)
        try:
            cur = ejecutar(
                conn,
                """
                INSERT INTO proyectos (
                    codigo, nombre, descripcion, entidad, departamento, estado, prioridad,
                    fecha_inicio, fecha_estimada_termino, presupuesto_asignado, presupuesto_usado,
                    responsable_id, supervisor_id, empresa_externa, observaciones, creado_en, actualizado_en
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?)
                """,
                (
                    codigo, nombre, descripcion, entidad, departamento, estado, prioridad,
                    fecha_inicio, fecha_estimada, presupuesto, responsable_id, supervisor_id,
                    empresa_externa, observaciones, ahora(), ahora(),
                ),
            )
            proyecto_id = cur.lastrowid
            registrar_bitacora(conn, usuario["id"], "Creó proyecto", "proyectos", proyecto_id, f"{codigo} - {nombre}")
            conn.execute(
                """
                INSERT INTO actualizaciones (proyecto_id, tipo, descripcion, registrado_por, creado_en)
                VALUES (?, 'Creación', ?, ?, ?)
                """,
                (proyecto_id, f"Proyecto creado con estado inicial: {estado}", usuario["id"], ahora()),
            )
            conn.commit()
            print("\nProyecto creado correctamente.")
        except sqlite3.IntegrityError:
            print("\nError: ya existe un proyecto con ese código.")
    pausar()


def listar_proyectos() -> None:
    limpiar_pantalla()
    print("Listado de proyectos\n")
    print("Filtros opcionales. Deja vacío para no filtrar.")
    filtro_estado = input("Estado: ").strip()
    filtro_departamento = input("Departamento: ").strip()
    filtro_texto = input("Buscar por código/nombre/entidad: ").strip()

    sql = """
        SELECT p.*, r.nombre AS responsable, s.nombre AS supervisor
        FROM proyectos p
        LEFT JOIN personas r ON p.responsable_id = r.id
        LEFT JOIN personas s ON p.supervisor_id = s.id
        WHERE 1 = 1
    """
    params: list = []
    if filtro_estado:
        sql += " AND p.estado LIKE ?"
        params.append(f"%{filtro_estado}%")
    if filtro_departamento:
        sql += " AND p.departamento LIKE ?"
        params.append(f"%{filtro_departamento}%")
    if filtro_texto:
        sql += " AND (p.codigo LIKE ? OR p.nombre LIKE ? OR p.entidad LIKE ?)"
        params.extend([f"%{filtro_texto}%"] * 3)
    sql += " ORDER BY p.actualizado_en DESC"

    with conectar() as conn:
        proyectos = conn.execute(sql, params).fetchall()

    limpiar_pantalla()
    print("Proyectos encontrados\n")
    if not proyectos:
        print("No hay proyectos con esos filtros.")
    for p in proyectos:
        saldo = (p["presupuesto_asignado"] or 0) - (p["presupuesto_usado"] or 0)
        print(f"ID: {p['id']} | [{p['codigo']}] {p['nombre']}")
        print(f"Estado: {p['estado']} | Prioridad: {p['prioridad']} | Departamento: {p['departamento'] or '-'}")
        print(f"Responsable: {p['responsable'] or '-'} | Supervisor: {p['supervisor'] or '-'}")
        print(f"Presupuesto: {formatear_dinero(p['presupuesto_asignado'])} | Usado: {formatear_dinero(p['presupuesto_usado'])} | Saldo: {formatear_dinero(saldo)}")
        print(f"Actualizado: {p['actualizado_en']}")
        print("-" * 90)
    pausar()


def ver_ficha_proyecto() -> None:
    limpiar_pantalla()
    print("Ficha digital del proyecto\n")
    with conectar() as conn:
        proyecto = seleccionar_proyecto(conn)
        if not proyecto:
            pausar()
            return
        ficha = conn.execute(
            """
            SELECT p.*, r.nombre AS responsable, s.nombre AS supervisor
            FROM proyectos p
            LEFT JOIN personas r ON p.responsable_id = r.id
            LEFT JOIN personas s ON p.supervisor_id = s.id
            WHERE p.id = ?
            """,
            (proyecto["id"],),
        ).fetchone()
        personas = conn.execute(
            """
            SELECT pp.rol_en_proyecto, pe.nombre, pe.cargo, pe.departamento, pp.observaciones
            FROM proyecto_personas pp
            JOIN personas pe ON pe.id = pp.persona_id
            WHERE pp.proyecto_id = ?
            ORDER BY pp.rol_en_proyecto, pe.nombre
            """,
            (proyecto["id"],),
        ).fetchall()
        pagos = conn.execute(
            "SELECT * FROM pagos WHERE proyecto_id = ? ORDER BY fecha_pago DESC, id DESC",
            (proyecto["id"],),
        ).fetchall()
        actualizaciones = conn.execute(
            """
            SELECT a.*, u.username
            FROM actualizaciones a
            JOIN usuarios u ON u.id = a.registrado_por
            WHERE a.proyecto_id = ?
            ORDER BY a.creado_en DESC
            LIMIT 10
            """,
            (proyecto["id"],),
        ).fetchall()

    limpiar_pantalla()
    saldo = (ficha["presupuesto_asignado"] or 0) - (ficha["presupuesto_usado"] or 0)
    print(f"FICHA DIGITAL - [{ficha['codigo']}] {ficha['nombre']}")
    print("=" * 90)
    print(f"Estado: {ficha['estado']} | Prioridad: {ficha['prioridad']}")
    print(f"Entidad: {ficha['entidad'] or '-'} | Departamento: {ficha['departamento'] or '-'}")
    print(f"Responsable: {ficha['responsable'] or '-'} | Supervisor: {ficha['supervisor'] or '-'}")
    print(f"Empresa externa: {ficha['empresa_externa'] or '-'}")
    print(f"Fechas: inicio {ficha['fecha_inicio'] or '-'} | término estimado {ficha['fecha_estimada_termino'] or '-'}")
    print(f"Presupuesto asignado: {formatear_dinero(ficha['presupuesto_asignado'])}")
    print(f"Presupuesto usado:     {formatear_dinero(ficha['presupuesto_usado'])}")
    print(f"Saldo estimado:        {formatear_dinero(saldo)}")
    print(f"Descripción: {ficha['descripcion'] or '-'}")
    print(f"Observaciones: {ficha['observaciones'] or '-'}")
    print(f"Creado: {ficha['creado_en']} | Actualizado: {ficha['actualizado_en']}")

    print("\nPERSONAL / PARTES INVOLUCRADAS")
    print("-" * 90)
    if not personas:
        print("Sin personal adicional asignado.")
    for p in personas:
        print(f"{p['rol_en_proyecto']}: {p['nombre']} | {p['cargo'] or '-'} | {p['departamento'] or '-'} | Obs: {p['observaciones'] or '-'}")

    print("\nPAGOS REGISTRADOS")
    print("-" * 90)
    if not pagos:
        print("Sin pagos registrados.")
    for pago in pagos:
        print(f"{pago['fecha_pago']} | {formatear_dinero(pago['monto'])} | {pago['concepto']} | {pago['estado']}")

    print("\nÚLTIMAS ACTUALIZACIONES")
    print("-" * 90)
    if not actualizaciones:
        print("Sin actualizaciones registradas.")
    for a in actualizaciones:
        print(f"{a['creado_en']} | {a['tipo']} | por {a['username']}")
        print(f"  {a['descripcion']}")
    pausar()


def actualizar_estado_proyecto(usuario: sqlite3.Row) -> None:
    if not requiere_escritura(usuario):
        return
    limpiar_pantalla()
    print("Actualizar estado del proyecto\n")
    with conectar() as conn:
        proyecto = seleccionar_proyecto(conn)
        if not proyecto:
            pausar()
            return
        print(f"\nEstado actual: {proyecto['estado']}")
        nuevo_estado = elegir_opcion("Nuevo estado", STATUS_VALIDOS)
        descripcion = input_no_vacio("Descripción de la actualización: ")
        fecha_compromiso = input("Nueva fecha compromiso [opcional YYYY-MM-DD]: ").strip() or None

        ejecutar(
            conn,
            "UPDATE proyectos SET estado = ?, fecha_estimada_termino = COALESCE(?, fecha_estimada_termino), actualizado_en = ? WHERE id = ?",
            (nuevo_estado, fecha_compromiso, ahora(), proyecto["id"]),
        )
        conn.execute(
            """
            INSERT INTO actualizaciones (proyecto_id, tipo, descripcion, fecha_compromiso, registrado_por, creado_en)
            VALUES (?, 'Estado', ?, ?, ?, ?)
            """,
            (proyecto["id"], f"Estado cambiado de {proyecto['estado']} a {nuevo_estado}. {descripcion}", fecha_compromiso, usuario["id"], ahora()),
        )
        conn.commit()
        registrar_bitacora(conn, usuario["id"], "Actualizó estado", "proyectos", proyecto["id"], f"{proyecto['estado']} -> {nuevo_estado}")
    print("\nEstado actualizado correctamente.")
    pausar()


def editar_datos_proyecto(usuario: sqlite3.Row) -> None:
    if not requiere_escritura(usuario):
        return
    limpiar_pantalla()
    print("Editar datos generales de proyecto\n")
    with conectar() as conn:
        proyecto = seleccionar_proyecto(conn)
        if not proyecto:
            pausar()
            return

        nombre = input_opcional("Nombre", proyecto["nombre"])
        descripcion = input_opcional("Descripción", proyecto["descripcion"] or "")
        entidad = input_opcional("Entidad/Municipio/Empresa", proyecto["entidad"] or "")
        departamento = input_opcional("Departamento", proyecto["departamento"] or "")
        prioridad = elegir_opcion("Prioridad", ["Baja", "Media", "Alta", "Crítica"], permitir_vacio=True, valor_actual=proyecto["prioridad"])
        fecha_inicio = input_opcional("Fecha inicio", proyecto["fecha_inicio"] or "")
        fecha_estimada = input_opcional("Fecha estimada término", proyecto["fecha_estimada_termino"] or "")
        presupuesto_asignado = input_float(f"Presupuesto asignado [{proyecto['presupuesto_asignado'] or 0}]: ", proyecto["presupuesto_asignado"] or 0)
        empresa_externa = input_opcional("Empresa externa", proyecto["empresa_externa"] or "")
        observaciones = input_opcional("Observaciones", proyecto["observaciones"] or "")
        responsable_id = seleccionar_persona(conn, "Responsable principal", permitir_sin_asignar=True)
        supervisor_id = seleccionar_persona(conn, "Supervisor", permitir_sin_asignar=True)

        ejecutar(
            conn,
            """
            UPDATE proyectos
            SET nombre = ?, descripcion = ?, entidad = ?, departamento = ?, prioridad = ?,
                fecha_inicio = ?, fecha_estimada_termino = ?, presupuesto_asignado = ?,
                responsable_id = ?, supervisor_id = ?, empresa_externa = ?, observaciones = ?, actualizado_en = ?
            WHERE id = ?
            """,
            (
                nombre, descripcion, entidad, departamento, prioridad, fecha_inicio, fecha_estimada,
                presupuesto_asignado, responsable_id, supervisor_id, empresa_externa, observaciones, ahora(), proyecto["id"],
            ),
        )
        conn.execute(
            """
            INSERT INTO actualizaciones (proyecto_id, tipo, descripcion, registrado_por, creado_en)
            VALUES (?, 'Datos', ?, ?, ?)
            """,
            (proyecto["id"], "Datos generales del proyecto actualizados.", usuario["id"], ahora()),
        )
        conn.commit()
        registrar_bitacora(conn, usuario["id"], "Editó datos generales", "proyectos", proyecto["id"], proyecto["codigo"])
    print("\nDatos actualizados correctamente.")
    pausar()


def asignar_persona_a_proyecto(usuario: sqlite3.Row) -> None:
    if not requiere_escritura(usuario):
        return
    limpiar_pantalla()
    print("Asignar persona a proyecto\n")
    with conectar() as conn:
        proyecto = seleccionar_proyecto(conn)
        if not proyecto:
            pausar()
            return
        persona_id = seleccionar_persona(conn, "Persona a asignar", permitir_sin_asignar=False)
        if not persona_id:
            pausar()
            return
        rol = input_no_vacio("Rol dentro del proyecto: ")
        observaciones = input("Observaciones: ").strip() or None
        try:
            cur = ejecutar(
                conn,
                """
                INSERT INTO proyecto_personas (proyecto_id, persona_id, rol_en_proyecto, observaciones, creado_en)
                VALUES (?, ?, ?, ?, ?)
                """,
                (proyecto["id"], persona_id, rol, observaciones, ahora()),
            )
            ejecutar(conn, "UPDATE proyectos SET actualizado_en = ? WHERE id = ?", (ahora(), proyecto["id"]))
            registrar_bitacora(conn, usuario["id"], "Asignó persona a proyecto", "proyecto_personas", cur.lastrowid, f"Proyecto {proyecto['codigo']} | Rol {rol}")
            print("\nPersona asignada correctamente.")
        except sqlite3.IntegrityError:
            print("\nEsa persona ya está asignada con el mismo rol en este proyecto.")
    pausar()


def registrar_actualizacion(usuario: sqlite3.Row) -> None:
    if not requiere_escritura(usuario):
        return
    limpiar_pantalla()
    print("Registrar actualización / observación\n")
    with conectar() as conn:
        proyecto = seleccionar_proyecto(conn)
        if not proyecto:
            pausar()
            return
        tipo = elegir_opcion("Tipo de actualización", ["Avance", "Retraso", "Observación", "Riesgo", "Documento", "Reunión", "Otro"]) or "Otro"
        descripcion = input_no_vacio("Descripción: ")
        fecha_compromiso = input("Fecha compromiso [opcional YYYY-MM-DD]: ").strip() or None
        cur = ejecutar(
            conn,
            """
            INSERT INTO actualizaciones (proyecto_id, tipo, descripcion, fecha_compromiso, registrado_por, creado_en)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (proyecto["id"], tipo, descripcion, fecha_compromiso, usuario["id"], ahora()),
        )
        ejecutar(conn, "UPDATE proyectos SET actualizado_en = ? WHERE id = ?", (ahora(), proyecto["id"]))
        registrar_bitacora(conn, usuario["id"], "Registró actualización", "actualizaciones", cur.lastrowid, f"{tipo} | Proyecto {proyecto['codigo']}")
    print("\nActualización registrada correctamente.")
    pausar()


def registrar_pago(usuario: sqlite3.Row) -> None:
    if not requiere_escritura(usuario):
        return
    limpiar_pantalla()
    print("Registrar pago / movimiento\n")
    with conectar() as conn:
        proyecto = seleccionar_proyecto(conn)
        if not proyecto:
            pausar()
            return
        monto = input_float("Monto: ")
        concepto = input_no_vacio("Concepto: ")
        fecha_pago = input(f"Fecha de pago [{hoy()}]: ").strip() or hoy()
        estado = elegir_opcion("Estado del pago", ["Registrado", "Pendiente", "Pagado", "Observado", "Anulado"]) or "Registrado"
        cur = ejecutar(
            conn,
            """
            INSERT INTO pagos (proyecto_id, monto, concepto, fecha_pago, estado, registrado_por, creado_en)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (proyecto["id"], monto, concepto, fecha_pago, estado, usuario["id"], ahora()),
        )
        presupuesto_usado = (proyecto["presupuesto_usado"] or 0) + monto if estado in ("Registrado", "Pagado") else (proyecto["presupuesto_usado"] or 0)
        ejecutar(
            conn,
            "UPDATE proyectos SET presupuesto_usado = ?, actualizado_en = ? WHERE id = ?",
            (presupuesto_usado, ahora(), proyecto["id"]),
        )
        conn.execute(
            """
            INSERT INTO actualizaciones (proyecto_id, tipo, descripcion, registrado_por, creado_en)
            VALUES (?, 'Pago', ?, ?, ?)
            """,
            (proyecto["id"], f"Pago/movimiento registrado: {concepto} por {formatear_dinero(monto)}. Estado: {estado}", usuario["id"], ahora()),
        )
        conn.commit()
        registrar_bitacora(conn, usuario["id"], "Registró pago", "pagos", cur.lastrowid, f"Proyecto {proyecto['codigo']} | {formatear_dinero(monto)}")
    print("\nPago/movimiento registrado correctamente.")
    pausar()


# -----------------------------------------------------------------------------
# Bitácora y reportes
# -----------------------------------------------------------------------------

def ver_bitacora() -> None:
    limpiar_pantalla()
    print("Bitácora de acciones del sistema\n")
    limite = input("Cantidad de registros a mostrar [50]: ").strip()
    limite_int = int(limite) if limite.isdigit() else 50
    with conectar() as conn:
        filas = conn.execute(
            """
            SELECT b.*, u.username
            FROM bitacora b
            LEFT JOIN usuarios u ON u.id = b.usuario_id
            ORDER BY b.creado_en DESC
            LIMIT ?
            """,
            (limite_int,),
        ).fetchall()
    if not filas:
        print("Sin acciones registradas.")
    for f in filas:
        print(f"{f['creado_en']} | Usuario: {f['username'] or '-'} | {f['accion']}")
        print(f"Tabla: {f['tabla_afectada'] or '-'} | Registro: {f['registro_id'] or '-'} | Detalle: {f['detalle'] or '-'}")
        print("-" * 90)
    pausar()


def exportar_proyectos_csv(usuario: sqlite3.Row) -> None:
    limpiar_pantalla()
    EXPORT_DIR.mkdir(exist_ok=True)
    archivo = EXPORT_DIR / f"reporte_proyectos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    with conectar() as conn:
        filas = conn.execute(
            """
            SELECT p.codigo, p.nombre, p.entidad, p.departamento, p.estado, p.prioridad,
                   p.fecha_inicio, p.fecha_estimada_termino, p.presupuesto_asignado, p.presupuesto_usado,
                   r.nombre AS responsable, s.nombre AS supervisor, p.empresa_externa, p.actualizado_en
            FROM proyectos p
            LEFT JOIN personas r ON p.responsable_id = r.id
            LEFT JOIN personas s ON p.supervisor_id = s.id
            ORDER BY p.actualizado_en DESC
            """
        ).fetchall()
        with open(archivo, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow([
                "codigo", "nombre", "entidad", "departamento", "estado", "prioridad",
                "fecha_inicio", "fecha_estimada_termino", "presupuesto_asignado", "presupuesto_usado",
                "responsable", "supervisor", "empresa_externa", "actualizado_en",
            ])
            for row in filas:
                writer.writerow([row[k] for k in row.keys()])
        registrar_bitacora(conn, usuario["id"], "Exportó reporte CSV", "proyectos", None, str(archivo))
    print(f"Reporte generado: {archivo}")
    pausar()


def generar_datos_demo(usuario: sqlite3.Row) -> None:
    if not requiere_admin(usuario):
        return
    limpiar_pantalla()
    print("Generar datos de demostración")
    confirmar = input("Esto agregará personas, proyectos y registros demo. ¿Continuar? [s/N]: ").strip().lower()
    if confirmar != "s":
        return

    with conectar() as conn:
        personas_demo = [
            ("María Torres", "Encargada de Obras", "Obras Municipales", "maria.torres@demo.local", "+56 9 1111 1111"),
            ("Luis Fuentes", "Supervisor Técnico", "Inspección", "luis.fuentes@demo.local", "+56 9 2222 2222"),
            ("Camila Reyes", "Analista de Finanzas", "Finanzas", "camila.reyes@demo.local", "+56 9 3333 3333"),
            ("Jorge Vidal", "Coordinador Externo", "Empresa Externa", "jorge.vidal@externa.local", "+56 9 4444 4444"),
        ]
        ids = []
        for p in personas_demo:
            cur = conn.execute(
                """
                INSERT INTO personas (nombre, cargo, departamento, email, telefono, activo, creado_en)
                VALUES (?, ?, ?, ?, ?, 1, ?)
                """,
                (*p, ahora()),
            )
            ids.append(cur.lastrowid)
        conn.commit()

        cur = conn.execute(
            """
            INSERT INTO proyectos (
                codigo, nombre, descripcion, entidad, departamento, estado, prioridad,
                fecha_inicio, fecha_estimada_termino, presupuesto_asignado, presupuesto_usado,
                responsable_id, supervisor_id, empresa_externa, observaciones, creado_en, actualizado_en
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "OBRA-001", "Mejoramiento de sede comunitaria",
                "Proyecto demo para trazabilidad de obra, responsables, pagos y retrasos.",
                "Municipalidad Demo", "Obras Municipales", "En proceso", "Alta",
                hoy(), "2026-08-30", 25000000, 3500000, ids[0], ids[1],
                "Constructora Demo SpA", "Primer registro demo del sistema SIGPRO.", ahora(), ahora(),
            ),
        )
        proyecto_id = cur.lastrowid
        conn.execute(
            "INSERT INTO proyecto_personas (proyecto_id, persona_id, rol_en_proyecto, observaciones, creado_en) VALUES (?, ?, ?, ?, ?)",
            (proyecto_id, ids[2], "Finanzas", "Revisión de pagos y saldos", ahora()),
        )
        conn.execute(
            "INSERT INTO proyecto_personas (proyecto_id, persona_id, rol_en_proyecto, observaciones, creado_en) VALUES (?, ?, ?, ?, ?)",
            (proyecto_id, ids[3], "Contratista externo", "Ejecución en terreno", ahora()),
        )
        conn.execute(
            "INSERT INTO actualizaciones (proyecto_id, tipo, descripcion, fecha_compromiso, registrado_por, creado_en) VALUES (?, ?, ?, ?, ?, ?)",
            (proyecto_id, "Avance", "Se registró avance inicial de planificación y asignación de responsables.", "2026-07-15", usuario["id"], ahora()),
        )
        conn.execute(
            "INSERT INTO actualizaciones (proyecto_id, tipo, descripcion, fecha_compromiso, registrado_por, creado_en) VALUES (?, ?, ?, ?, ?, ?)",
            (proyecto_id, "Retraso", "Retraso informado por espera de material. Queda registro del responsable y fecha compromiso.", "2026-07-22", usuario["id"], ahora()),
        )
        conn.execute(
            "INSERT INTO pagos (proyecto_id, monto, concepto, fecha_pago, estado, registrado_por, creado_en) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (proyecto_id, 3500000, "Primer pago a empresa externa", hoy(), "Pagado", usuario["id"], ahora()),
        )
        conn.commit()
        registrar_bitacora(conn, usuario["id"], "Generó datos demo", "proyectos", proyecto_id, "Demo SIGPRO")
    print("\nDatos demo generados correctamente.")
    pausar()


# -----------------------------------------------------------------------------
# Menús
# -----------------------------------------------------------------------------

def menu_principal(usuario: sqlite3.Row) -> None:
    while True:
        limpiar_pantalla()
        print("SIGPRO - Sistema Interno de Gestión y Seguimiento de Proyectos")
        print(f"Usuario: {usuario['username']} | Rol: {usuario['rol']}")
        print("=" * 80)
        print("1. Registrar persona")
        print("2. Listar personas")
        print("3. Crear proyecto")
        print("4. Listar / filtrar proyectos")
        print("5. Ver ficha digital de proyecto")
        print("6. Actualizar estado de proyecto")
        print("7. Editar datos generales de proyecto")
        print("8. Asignar persona a proyecto")
        print("9. Registrar actualización / observación")
        print("10. Registrar pago / movimiento")
        print("11. Ver bitácora de acciones")
        print("12. Exportar proyectos a CSV")
        print("13. Generar datos demo")
        print("0. Salir")
        opcion = input("\nSelecciona una opción: ").strip()

        if opcion == "1":
            registrar_persona(usuario)
        elif opcion == "2":
            listar_personas()
        elif opcion == "3":
            crear_proyecto(usuario)
        elif opcion == "4":
            listar_proyectos()
        elif opcion == "5":
            ver_ficha_proyecto()
        elif opcion == "6":
            actualizar_estado_proyecto(usuario)
        elif opcion == "7":
            editar_datos_proyecto(usuario)
        elif opcion == "8":
            asignar_persona_a_proyecto(usuario)
        elif opcion == "9":
            registrar_actualizacion(usuario)
        elif opcion == "10":
            registrar_pago(usuario)
        elif opcion == "11":
            ver_bitacora()
        elif opcion == "12":
            exportar_proyectos_csv(usuario)
        elif opcion == "13":
            generar_datos_demo(usuario)
        elif opcion == "0":
            with conectar() as conn:
                registrar_bitacora(conn, usuario["id"], "Cierre de sesión", "usuarios", usuario["id"], usuario["username"])
            print("Cerrando SIGPRO...")
            break
        else:
            print("Opción inválida.")
            pausar()


def main() -> None:
    try:
        inicializar_db()
        usuario = None
        for _ in range(3):
            usuario = login()
            if usuario:
                break
        if not usuario:
            print("Demasiados intentos fallidos. Saliendo.")
            sys.exit(1)
        menu_principal(usuario)
    except KeyboardInterrupt:
        print("\nInterrupción manual. Saliendo.")
    except sqlite3.Error as e:
        print(f"\nError de base de datos: {e}")
        print("Revisa permisos de escritura en la carpeta del programa.")
        sys.exit(1)


if __name__ == "__main__":
    main()
