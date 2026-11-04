-- SECCIÓN 1 - BASE DE DATOS (SQLite)
-- Cada tabla corresponde a un módulo del sistema.

DROP TABLE IF EXISTS movimientos_inventario;
DROP TABLE IF EXISTS historial_estados;
DROP TABLE IF EXISTS ordenes;
DROP TABLE IF EXISTS servicio_materiales;
DROP TABLE IF EXISTS materiales;
DROP TABLE IF EXISTS servicios;
DROP TABLE IF EXISTS pacientes;
DROP TABLE IF EXISTS odontologos;
DROP TABLE IF EXISTS usuarios;

CREATE TABLE usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    rol TEXT NOT NULL,           -- Administrador, Técnico, Recepción
    usuario TEXT UNIQUE,         -- usuario de acceso al panel (NULL = sin acceso)
    clave_hash TEXT
);

CREATE TABLE odontologos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    telefono TEXT,
    clinica TEXT,
    usuario TEXT UNIQUE,         -- usuario de acceso al portal de cliente (NULL = sin acceso)
    clave_hash TEXT
);

CREATE TABLE pacientes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    odontologo_id INTEGER REFERENCES odontologos(id)
);

CREATE TABLE servicios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    precio REAL NOT NULL DEFAULT 0,
    dias_estimados INTEGER NOT NULL DEFAULT 5
);

CREATE TABLE materiales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    unidad TEXT NOT NULL DEFAULT 'und',
    stock REAL NOT NULL DEFAULT 0,
    stock_minimo REAL NOT NULL DEFAULT 0,
    costo_unitario REAL NOT NULL DEFAULT 0
);

-- "Receta" de cada servicio: qué materiales y cuánto consume
CREATE TABLE servicio_materiales (
    servicio_id INTEGER NOT NULL REFERENCES servicios(id),
    material_id INTEGER NOT NULL REFERENCES materiales(id),
    cantidad REAL NOT NULL,
    PRIMARY KEY (servicio_id, material_id)
);

CREATE TABLE ordenes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    odontologo_id INTEGER NOT NULL REFERENCES odontologos(id),
    paciente_id INTEGER NOT NULL REFERENCES pacientes(id),
    servicio_id INTEGER NOT NULL REFERENCES servicios(id),
    estado TEXT NOT NULL DEFAULT 'Recibida',
    fecha_ingreso TEXT NOT NULL,
    fecha_entrega_estimada TEXT NOT NULL,
    fecha_entrega_real TEXT,
    observaciones TEXT,
    consumo_registrado INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE historial_estados (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    orden_id INTEGER NOT NULL REFERENCES ordenes(id),
    estado TEXT NOT NULL,
    fecha TEXT NOT NULL
);

CREATE TABLE movimientos_inventario (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id INTEGER NOT NULL REFERENCES materiales(id),
    tipo TEXT NOT NULL,          -- ENTRADA o SALIDA
    cantidad REAL NOT NULL,
    fecha TEXT NOT NULL,
    orden_id INTEGER REFERENCES ordenes(id),
    nota TEXT
);

-- Ajustes del laboratorio (nombre, WhatsApp, URL pública). Se crea aquí
-- también (no solo en asegurar_ajustes()) para que init_db() nunca deje
-- la base de datos sin esta tabla, la usa el context_processor en CADA página.
CREATE TABLE configuracion (
    clave TEXT PRIMARY KEY,
    valor TEXT NOT NULL DEFAULT ''
);
