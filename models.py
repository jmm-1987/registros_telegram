from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, time
import pytz
from flask import request

db = SQLAlchemy()

def get_madrid_time():
    """Obtener la hora actual en Madrid"""
    utc_now = datetime.now(pytz.UTC)
    return utc_now.astimezone(pytz.timezone('Europe/Madrid'))

def utc_to_madrid(utc_dt):
    """Convertir hora UTC a hora de Madrid"""
    if utc_dt.tzinfo is None:
        utc_dt = pytz.UTC.localize(utc_dt)
    return utc_dt.astimezone(pytz.timezone('Europe/Madrid'))

def madrid_to_utc(madrid_dt):
    """Convertir hora de Madrid a UTC"""
    if madrid_dt.tzinfo is None:
        madrid_dt = pytz.timezone('Europe/Madrid').localize(madrid_dt)
    return madrid_dt.astimezone(pytz.UTC)

class Usuario(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    nombre = db.Column(db.String(100), nullable=True, default='Usuario')
    password_hash = db.Column(db.String(128))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Empleado(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    apellidos = db.Column(db.String(100), nullable=False)
    dni = db.Column(db.String(9), unique=True, nullable=False)
    seg_social = db.Column(db.String(12), unique=True, nullable=False)
    telefono = db.Column(db.String(20), unique=True, nullable=False)
    telegram_id = db.Column(db.String(50), unique=True)
    hora_entrada = db.Column(db.Time, nullable=True, default=None)
    hora_salida = db.Column(db.Time, nullable=True, default=None)
    hora_entrada2 = db.Column(db.Time, nullable=True, default=None)
    hora_salida2 = db.Column(db.Time, nullable=True, default=None)
    sabados = db.Column(db.Boolean, default=False)
    activo = db.Column(db.Boolean, default=True)
    registros = db.relationship('Registro', backref='empleado', lazy=True)

    def tiene_jornada_abierta(self):
        """Verifica si el empleado tiene una jornada abierta"""
        if not self.registros:
            return False
        
        # Ordenar registros por fecha descendente
        registros_ordenados = sorted(self.registros, key=lambda x: x.fecha, reverse=True)
        ultimo_registro = registros_ordenados[0]
        
        # Si el último registro es una entrada, la jornada está abierta
        return ultimo_registro.tipo == 'entrada'

    def se_paso_hora_salida(self):
        """Verifica si el empleado se ha pasado de su hora de salida"""
        if not self.tiene_jornada_abierta():
            return False
        
        hora_actual = get_madrid_time().time()
        registros_ordenados = sorted(self.registros, key=lambda x: x.fecha, reverse=True)
        ultima_entrada = registros_ordenados[0].fecha_madrid.time()
        
        # Determinar qué turno está activo
        if ultima_entrada < self.hora_entrada:
            # Turno de mañana
            return self.hora_salida is not None and hora_actual > self.hora_salida
        else:
            # Turno de tarde
            return self.hora_salida2 is not None and hora_actual > self.hora_salida2

class Registro(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    empleado_id = db.Column(db.Integer, db.ForeignKey('empleado.id'), nullable=False)
    fecha = db.Column(db.DateTime, nullable=False)
    tipo = db.Column(db.String(10), nullable=False)  # 'entrada' o 'salida'

    def __init__(self, empleado_id, tipo):
        self.empleado_id = empleado_id
        self.tipo = tipo
        # Obtener la hora actual en Madrid y guardarla
        madrid_time = get_madrid_time()
        # Guardar la fecha/hora en UTC en la base de datos
        self.fecha = madrid_time.astimezone(pytz.UTC)

    @property
    def fecha_madrid(self):
        """Obtener la fecha en hora de Madrid"""
        return utc_to_madrid(self.fecha)

def parse_time_field(value):
    return datetime.strptime(value, '%H:%M').time() if value else None

def process_employee_times(form_data):
    """Procesa los campos de tiempo del formulario de empleado"""
    turno_partido = 'turno_partido' in form_data
    
    hora_entrada = parse_time_field(form_data.get('hora_entrada'))
    hora_salida = parse_time_field(form_data.get('hora_salida'))
    
    if turno_partido:
        hora_entrada2 = parse_time_field(form_data.get('hora_entrada2'))
        hora_salida2 = parse_time_field(form_data.get('hora_salida2'))
    else:
        hora_entrada2 = None
        hora_salida2 = None
    
    return {
        'hora_entrada': hora_entrada,
        'hora_salida': hora_salida,
        'hora_entrada2': hora_entrada2,
        'hora_salida2': hora_salida2
    } 