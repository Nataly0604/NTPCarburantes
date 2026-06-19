import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from datetime import datetime, timedelta
from dotenv import load_dotenv
from models import db, Empresa, Tanque, Cliente, Ingreso, Venta

# Cargar variables de entorno desde .env
load_dotenv()

app = Flask(__name__)

# Usar Supabase (PostgreSQL) si la variable DATABASE_URL está definida, sino SQLite local
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///carburantes.db')
# Render a veces envía postgres:// en vez de postgresql://, esto lo corrige
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'ntpcarburantes_secret_key_12345')

# Inicializar Base de Datos
db.init_app(app)

with app.app_context():
    db.create_all()
    # Semilla para Empresa por defecto
    if not Empresa.query.first():
        empresa_default = Empresa(
            nombre="NTPCarburantes Petrol",
            nit="7629340-1",
            direccion="Av. Circunvalación Nro. 450",
            ciudad="Santa Cruz",
            telefono="+591 3 3445566",
            factor_holgura=10.0,      # 10% de margen adicional
            cupo_base_nuevo=100.0     # 100 Litros iniciales para clientes nuevos
        )
        db.session.add(empresa_default)
        db.session.commit()


def calcular_cupo_cliente(cliente, empresa):
    """
    Calcula el cupo de compra restante para un cliente basado en la regla de negocio.
    Retorna: (limite_semanal, litros_consumidos_esta_semana, es_nuevo, mensaje)
    """
    # Encontrar la fecha límite de hace 28 días (4 semanas)
    hace_28_dias = datetime.now() - timedelta(days=28)
    
    # Encontrar todas las ventas del cliente en los últimos 28 días
    ventas_28_dias = Venta.query.filter(
        Venta.cliente_id == cliente.id,
        Venta.fecha >= hace_28_dias
    ).all()
    
    # Encontrar el inicio de la semana actual para restar el consumo de esta semana
    # Consideramos una semana móvil de los últimos 7 días para el consumo actual del cupo
    hace_7_dias = datetime.now() - timedelta(days=7)
    ventas_esta_semana = Venta.query.filter(
        Venta.cliente_id == cliente.id,
        Venta.fecha >= hace_7_dias
    ).all()
    
    litros_consumidos_esta_semana = sum(v.litros for v in ventas_esta_semana)

    # Buscar la venta más antigua de la historia del cliente para verificar si es "nuevo"
    primer_venta = Venta.query.filter(Venta.cliente_id == cliente.id).order_by(Venta.fecha.asc()).first()
    
    # Es cliente nuevo si no tiene ventas o si su primera venta fue hace menos de 7 días
    if not primer_venta or (datetime.now() - primer_venta.fecha).days < 7:
        limite_semanal = empresa.cupo_base_nuevo
        es_nuevo = True
        mensaje = "Cliente nuevo (sin historial suficiente). Se aplica el cupo base inicial."
    else:
        # Calcular promedio semanal de los últimos 28 días
        total_litros_28 = sum(v.litros for v in ventas_28_dias)
        promedio_semanal = total_litros_28 / 4.0
        
        # Límite semanal = promedio semanal + holgura
        limite_semanal = promedio_semanal + (promedio_semanal * empresa.factor_holgura / 100.0)
        es_nuevo = False
        mensaje = f"Historial evaluado (últimos 28 días). Promedio semanal: {promedio_semanal:.2f}L."

    return limite_semanal, litros_consumidos_esta_semana, es_nuevo, mensaje


# --- RUTAS DE LA APLICACIÓN ---

@app.route('/')
def index():
    # Estadísticas para el dashboard
    tanques = Tanque.query.all()
    total_clientes = Cliente.query.count()
    total_ingresos = Ingreso.query.count()
    total_ventas = Venta.query.count()
    
    # Ventas recientes
    ventas_recientes = Venta.query.order_by(Venta.fecha.desc()).limit(5).all()
    
    # Alertas de stock bajo
    alertas_tanques = [t for t in tanques if t.alerta_stock_bajo]
    
    empresa = Empresa.query.first()

    return render_template(
        'index.html',
        tanques=tanques,
        total_clientes=total_clientes,
        total_ingresos=total_ingresos,
        total_ventas=total_ventas,
        ventas_recientes=ventas_recientes,
        alertas_tanques=alertas_tanques,
        empresa=empresa,
        datetime_now=datetime.now()
    )


# --- CRUD EMPRESA ---
@app.route('/empresa', methods=['GET', 'POST'])
def empresa():
    empresa_data = Empresa.query.first()
    if request.method == 'POST':
        if not empresa_data:
            empresa_data = Empresa()
            db.session.add(empresa_data)
            
        empresa_data.nombre = request.form.get('nombre')
        empresa_data.nit = request.form.get('nit')
        empresa_data.direccion = request.form.get('direccion')
        empresa_data.ciudad = request.form.get('ciudad')
        empresa_data.telefono = request.form.get('telefono')
        empresa_data.factor_holgura = float(request.form.get('factor_holgura', 10.0))
        empresa_data.cupo_base_nuevo = float(request.form.get('cupo_base_nuevo', 100.0))
        
        db.session.commit()
        flash('Configuración de la empresa guardada exitosamente.', 'success')
        return redirect(url_for('empresa'))
        
    return render_template('empresa.html', empresa=empresa_data)


# --- CRUD TANQUES ---
@app.route('/tanques', methods=['GET', 'POST'])
def tanques():
    if request.method == 'POST':
        identificador = request.form.get('identificador')
        tipo_carburante = request.form.get('tipo_carburante')
        capacidad_maxima = float(request.form.get('capacidad_maxima', 0))
        stock_minimo = float(request.form.get('stock_minimo', 0))
        
        # Validar si ya existe
        tanque_existente = Tanque.query.filter_by(identificador=identificador).first()
        if tanque_existente:
            flash(f'El tanque con identificador {identificador} ya existe.', 'danger')
        else:
            nuevo_tanque = Tanque(
                identificador=identificador,
                tipo_carburante=tipo_carburante,
                capacidad_maxima=capacidad_maxima,
                stock_minimo=stock_minimo
            )
            db.session.add(nuevo_tanque)
            db.session.commit()
            flash('Tanque registrado exitosamente.', 'success')
        return redirect(url_for('tanques'))
        
    lista_tanques = Tanque.query.all()
    return render_template('tanques.html', tanques=lista_tanques)


@app.route('/tanques/editar/<int:id>', methods=['POST'])
def editar_tanque(id):
    tanque = Tanque.query.get_or_404(id)
    tanque.identificador = request.form.get('identificador')
    tanque.tipo_carburante = request.form.get('tipo_carburante')
    tanque.capacidad_maxima = float(request.form.get('capacidad_maxima', 0))
    tanque.stock_minimo = float(request.form.get('stock_minimo', 0))
    
    db.session.commit()
    flash('Tanque actualizado exitosamente.', 'success')
    return redirect(url_for('tanques'))


@app.route('/tanques/eliminar/<int:id>', methods=['POST'])
def eliminar_tanque(id):
    tanque = Tanque.query.get_or_404(id)
    db.session.delete(tanque)
    db.session.commit()
    flash('Tanque eliminado exitosamente.', 'success')
    return redirect(url_for('tanques'))


# --- CRUD CLIENTES ---
@app.route('/clientes', methods=['GET', 'POST'])
def clientes():
    if request.method == 'POST':
        ci_nit = request.form.get('ci_nit')
        nombre = request.form.get('nombre')
        placa = request.form.get('placa').upper()
        tipo_cliente = request.form.get('tipo_cliente')
        estado = request.form.get('estado', 'Activo')
        
        # Validar si ya existe placa o ci_nit
        cliente_placa = Cliente.query.filter_by(placa=placa).first()
        cliente_ci = Cliente.query.filter_by(ci_nit=ci_nit).first()
        
        if cliente_placa:
            flash(f'Ya existe un cliente registrado con la placa {placa}.', 'danger')
        elif cliente_ci:
            flash(f'Ya existe un cliente registrado con el CI/NIT {ci_nit}.', 'danger')
        else:
            nuevo_cliente = Cliente(
                ci_nit=ci_nit,
                nombre=nombre,
                placa=placa,
                tipo_cliente=tipo_cliente,
                estado=estado
            )
            db.session.add(nuevo_cliente)
            db.session.commit()
            flash('Cliente registrado exitosamente.', 'success')
        return redirect(url_for('clientes'))
        
    lista_clientes = Cliente.query.all()
    return render_template('clientes.html', clientes=lista_clientes)


@app.route('/clientes/editar/<int:id>', methods=['POST'])
def editar_cliente(id):
    cliente = Cliente.query.get_or_404(id)
    cliente.ci_nit = request.form.get('ci_nit')
    cliente.nombre = request.form.get('nombre')
    cliente.placa = request.form.get('placa').upper()
    cliente.tipo_cliente = request.form.get('tipo_cliente')
    cliente.estado = request.form.get('estado')
    
    db.session.commit()
    flash('Cliente actualizado exitosamente.', 'success')
    return redirect(url_for('clientes'))


@app.route('/clientes/eliminar/<int:id>', methods=['POST'])
def eliminar_cliente(id):
    cliente = Cliente.query.get_or_404(id)
    db.session.delete(cliente)
    db.session.commit()
    flash('Cliente eliminado exitosamente.', 'success')
    return redirect(url_for('clientes'))


# --- INGRESO DE CARBURANTE ---
@app.route('/ingresos', methods=['GET', 'POST'])
def ingresos():
    if request.method == 'POST':
        tanque_id = int(request.form.get('tanque_id'))
        litros = float(request.form.get('litros', 0))
        factura = request.form.get('factura')
        fecha_str = request.form.get('fecha')
        
        tanque = Tanque.query.get(tanque_id)
        if not tanque:
            flash('El tanque seleccionado no existe.', 'danger')
        elif litros <= 0:
            flash('La cantidad de litros ingresada debe ser mayor que cero.', 'danger')
        elif tanque.stock_actual + litros > tanque.capacidad_maxima:
            flash(f'Error: El ingreso excede la capacidad máxima del tanque ({tanque.capacidad_maxima}L). Stock actual: {tanque.stock_actual:.2f}L.', 'danger')
        else:
            fecha = datetime.strptime(fecha_str, '%Y-%m-%dT%H:%M') if fecha_str else datetime.now()
            nuevo_ingreso = Ingreso(
                tanque_id=tanque_id,
                litros=litros,
                factura=factura,
                fecha=fecha
            )
            db.session.add(nuevo_ingreso)
            db.session.commit()
            flash(f'Se ingresaron {litros:.2f}L al tanque {tanque.identificador} con éxito.', 'success')
        return redirect(url_for('ingresos'))
        
    lista_ingresos = Ingreso.query.order_by(Ingreso.fecha.desc()).all()
    tanques_disponibles = Tanque.query.all()
    return render_template('ingresos.html', ingresos=lista_ingresos, tanques=tanques_disponibles)


# --- VENTAS CONTROLADAS ---
@app.route('/ventas', methods=['GET', 'POST'])
def ventas():
    empresa = Empresa.query.first()
    
    if request.method == 'POST':
        identificacion = request.form.get('identificacion').strip().upper()
        tanque_id = int(request.form.get('tanque_id'))
        litros = float(request.form.get('litros', 0))
        fecha_str = request.form.get('fecha')
        fecha = datetime.strptime(fecha_str, '%Y-%m-%dT%H:%M') if fecha_str else datetime.now()
        
        # Buscar el cliente por Placa o por CI/NIT
        cliente = Cliente.query.filter((Cliente.placa == identificacion) | (Cliente.ci_nit == identificacion)).first()
        
        # Registrar cliente automáticamente si no existe
        if not cliente:
            nombre_auto = request.form.get('cliente_nombre_auto', '').strip()
            ci_nit_auto = request.form.get('cliente_ci_nit_auto', '').strip()
            
            if not nombre_auto or not ci_nit_auto:
                flash('El cliente no está registrado. Ingrese el nombre y CI/NIT para registrarlo automáticamente.', 'warning')
                return redirect(url_for('ventas'))
            
            # Comprobar duplicados
            if Cliente.query.filter_by(ci_nit=ci_nit_auto).first():
                flash(f'Ya existe un cliente con el CI/NIT {ci_nit_auto}.', 'danger')
                return redirect(url_for('ventas'))
            
            cliente = Cliente(
                ci_nit=ci_nit_auto,
                nombre=nombre_auto,
                placa=identificacion if '-' in identificacion or len(identificacion) < 10 else ci_nit_auto,  # adivinar placa
                tipo_cliente='Particular',
                estado='Activo'
            )
            # Asegurar placa única
            if not identificacion or Cliente.query.filter_by(placa=cliente.placa).first():
                cliente.placa = f"TEMP-{datetime.now().strftime('%M%S')}"
            
            db.session.add(cliente)
            db.session.commit()
            flash(f'Cliente {cliente.nombre} registrado automáticamente.', 'info')

        tanque = Tanque.query.get(tanque_id)
        
        # Validaciones de la venta
        if cliente.estado == 'Suspendido':
            flash(f'Venta bloqueada: El cliente {cliente.nombre} se encuentra SUSPENDIDO.', 'danger')
        elif not tanque:
            flash('El tanque seleccionado no existe.', 'danger')
        elif litros <= 0:
            flash('La cantidad de litros a vender debe ser mayor que cero.', 'danger')
        elif tanque.stock_actual < litros:
            flash(f'Stock insuficiente en el tanque {tanque.identificador}. Stock disponible: {tanque.stock_actual:.2f}L.', 'danger')
        else:
            # Validar regla de negocio (cupos)
            limite_semanal, litros_consumidos, _, _ = calcular_cupo_cliente(cliente, empresa)
            cupo_disponible = max(0.0, limite_semanal - litros_consumidos)
            
            if litros > cupo_disponible:
                flash(f'Venta excede el límite permitido. Cupo disponible actual: {cupo_disponible:.2f}L (Límite: {limite_semanal:.2f}L - Consumido: {litros_consumidos:.2f}L). La venta fue bloqueada.', 'danger')
            else:
                nueva_venta = Venta(
                    cliente_id=cliente.id,
                    tanque_id=tanque_id,
                    litros=litros,
                    fecha=fecha
                )
                db.session.add(nueva_venta)
                db.session.commit()
                flash(f'Venta registrada con éxito: {litros:.2f}L de {tanque.tipo_carburante} entregados al vehículo placa {cliente.placa}.', 'success')
                
        return redirect(url_for('ventas'))

    lista_ventas = Venta.query.order_by(Venta.fecha.desc()).all()
    tanques_disponibles = Tanque.query.all()
    return render_template('ventas.html', ventas=lista_ventas, tanques=tanques_disponibles)


# --- API DE VERIFICACIÓN DE CLIENTES EN TIEMPO REAL ---
@app.route('/api/verificar_cliente')
def api_verificar_cliente():
    identificacion = request.args.get('identificacion', '').strip().upper()
    if not identificacion:
        return jsonify({'error': 'Falta el parámetro de identificación'}), 400
        
    empresa = Empresa.query.first()
    cliente = Cliente.query.filter((Cliente.placa == identificacion) | (Cliente.ci_nit == identificacion)).first()
    
    if not cliente:
        return jsonify({
            'existe': False,
            'mensaje': 'Cliente no registrado. Se creará automáticamente al procesar la venta.',
            'cupo_maximo': empresa.cupo_base_nuevo,
            'consumido': 0.0,
            'disponible': empresa.cupo_base_nuevo
        })
        
    if cliente.estado == 'Suspendido':
        return jsonify({
            'existe': True,
            'suspendido': True,
            'nombre': cliente.nombre,
            'estado': cliente.estado,
            'mensaje': 'CLIENTE SUSPENDIDO. Venta bloqueada administrativamente.',
            'cupo_maximo': 0.0,
            'consumido': 0.0,
            'disponible': 0.0
        })
        
    limite_semanal, litros_consumidos, es_nuevo, mensaje_detalles = calcular_cupo_cliente(cliente, empresa)
    cupo_disponible = max(0.0, limite_semanal - litros_consumidos)
    
    return jsonify({
        'existe': True,
        'suspendido': False,
        'nombre': cliente.nombre,
        'placa': cliente.placa,
        'ci_nit': cliente.ci_nit,
        'estado': cliente.estado,
        'es_nuevo': es_nuevo,
        'cupo_maximo': round(limite_semanal, 2),
        'consumido': round(litros_consumidos, 2),
        'disponible': round(cupo_disponible, 2),
        'mensaje': mensaje_detalles
    })


if __name__ == '__main__':
    app.run(debug=True)
