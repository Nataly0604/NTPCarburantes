from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Empresa(db.Model):
    __tablename__ = 'empresa'
    
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    nit = db.Column(db.String(50), nullable=False)
    direccion = db.Column(db.String(200), nullable=False)
    ciudad = db.Column(db.String(100), nullable=False)
    telefono = db.Column(db.String(50), nullable=False)
    factor_holgura = db.Column(db.Float, default=10.0, nullable=False)  # Porcentaje (ej. 10.0%)
    cupo_base_nuevo = db.Column(db.Float, default=100.0, nullable=False)  # Litros (ej. 100L)

    def __repr__(self):
        return f"<Empresa {self.nombre}>"


class Tanque(db.Model):
    __tablename__ = 'tanque'
    
    id = db.Column(db.Integer, primary_key=True)
    identificador = db.Column(db.String(50), unique=True, nullable=False)  # ej. T-01
    tipo_carburante = db.Column(db.String(20), nullable=False)  # Gasolina o Diésel
    capacidad_maxima = db.Column(db.Float, nullable=False)  # en litros
    stock_minimo = db.Column(db.Float, nullable=False)  # stock de seguridad
    
    # Relaciones
    ingresos = db.relationship('Ingreso', backref='tanque', lazy=True, cascade="all, delete-orphan")
    ventas = db.relationship('Venta', backref='tanque', lazy=True, cascade="all, delete-orphan")
    
    @property
    def stock_actual(self):
        """Calcula el stock actual en tiempo real a partir de ingresos y ventas."""
        total_ingresos = sum(i.litros for i in self.ingresos)
        total_ventas = sum(v.litros for v in self.ventas)
        return max(0.0, total_ingresos - total_ventas)
    
    @property
    def porcentaje_llenado(self):
        """Devuelve el porcentaje de llenado actual del tanque."""
        if self.capacidad_maxima <= 0:
            return 0.0
        return min(100.0, (self.stock_actual / self.capacidad_maxima) * 100)

    @property
    def alerta_stock_bajo(self):
        """Devuelve True si el stock actual está por debajo del stock mínimo de seguridad."""
        return self.stock_actual < self.stock_minimo

    def __repr__(self):
        return f"<Tanque {self.identificador} ({self.tipo_carburante})>"


class Cliente(db.Model):
    __tablename__ = 'cliente'
    
    id = db.Column(db.Integer, primary_key=True)
    ci_nit = db.Column(db.String(50), unique=True, nullable=False)
    nombre = db.Column(db.String(150), nullable=False)
    placa = db.Column(db.String(20), unique=True, nullable=False)  # Placa del vehículo
    tipo_cliente = db.Column(db.String(50), default='Particular', nullable=False)  # Particular, Transporte Público, Empresa
    estado = db.Column(db.String(20), default='Activo', nullable=False)  # Activo, Suspendido
    
    # Relación
    ventas = db.relationship('Venta', backref='cliente', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Cliente {self.nombre} - Placa: {self.placa}>"


class Ingreso(db.Model):
    __tablename__ = 'ingreso'
    
    id = db.Column(db.Integer, primary_key=True)
    tanque_id = db.Column(db.Integer, db.ForeignKey('tanque.id', ondelete='CASCADE'), nullable=False)
    litros = db.Column(db.Float, nullable=False)
    factura = db.Column(db.String(100), nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.now, nullable=False)

    def __repr__(self):
        return f"<Ingreso Tanque {self.tanque_id}: {self.litros}L>"


class Venta(db.Model):
    __tablename__ = 'venta'
    
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id', ondelete='CASCADE'), nullable=False)
    tanque_id = db.Column(db.Integer, db.ForeignKey('tanque.id', ondelete='CASCADE'), nullable=False)
    litros = db.Column(db.Float, nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.now, nullable=False)

    def __repr__(self):
        return f"<Venta Cliente {self.cliente_id}: {self.litros}L>"
