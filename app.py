from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from datetime import datetime, timedelta
import os
import pytz
import threading
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import asyncio
import logging
from models import db, Usuario, Empleado, Registro, get_madrid_time, utc_to_madrid, madrid_to_utc
import schedule
import time

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuración de zona horaria
madrid_tz = pytz.timezone('Europe/Madrid')

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///registro.db')
if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# CREA LAS TABLAS SI NO EXISTEN (esto se ejecuta siempre, también en Render)
with app.app_context():
    db.create_all()
    # (opcional) crea usuario root si no existe
    if not Usuario.query.filter_by(username='root').first():
        admin = Usuario(username='root')
        admin.set_password('root')
        db.session.add(admin)
        db.session.commit()

login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Variable global para el bot
telegram_bot = None

@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))

# Rutas
@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        username = request.form['username']
        nombre = request.form['nombre']
        password = request.form['password']
        
        if Usuario.query.filter_by(username=username).first():
            flash('El nombre de usuario ya existe', 'danger')
            return redirect(url_for('registro'))
        
        user = Usuario(username=username, nombre=nombre)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        flash('Usuario registrado correctamente', 'success')
        return redirect(url_for('login'))
    
    return render_template('registro_usuario.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = Usuario.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('index'))
        flash('Usuario o contraseña incorrectos', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return render_template('dashboard.html')

@app.route('/base')
@login_required
def base():
    return render_template('base.html')

@app.route('/empleados')
@login_required
def empleados():
    empleados = Empleado.query.all()
    return render_template('empleados.html', empleados=empleados)

@app.route('/empleado/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo_empleado():
    if request.method == 'POST':
        nombre = request.form['nombre']
        apellidos = request.form['apellidos']
        dni = request.form['dni']
        seg_social = request.form['seg_social']
        telefono = request.form['telefono']
        hora_entrada = datetime.strptime(request.form['hora_entrada'], '%H:%M').time()
        hora_salida = datetime.strptime(request.form['hora_salida'], '%H:%M').time()
        hora_entrada2 = datetime.strptime(request.form['hora_entrada2'], '%H:%M').time()
        hora_salida2 = datetime.strptime(request.form['hora_salida2'], '%H:%M').time()
        sabados = 'sabados' in request.form
        activo = 'activo' in request.form
        
        empleado = Empleado(
            nombre=nombre,
            apellidos=apellidos,
            dni=dni,
            seg_social=seg_social,
            telefono=telefono,
            hora_entrada=hora_entrada,
            hora_salida=hora_salida,
            hora_entrada2=hora_entrada2,
            hora_salida2=hora_salida2,
            sabados=sabados,
            activo=activo
        )
        db.session.add(empleado)
        db.session.commit()
        
        flash('Empleado registrado correctamente', 'success')
        return redirect(url_for('empleados'))
    
    return render_template('nuevo_empleado.html')

@app.route('/empleado/editar/<int:empleado_id>', methods=['GET', 'POST'])
@login_required
def editar_empleado(empleado_id):
    empleado = Empleado.query.get_or_404(empleado_id)
    
    if request.method == 'POST':
        empleado.nombre = request.form['nombre']
        empleado.apellidos = request.form['apellidos']
        empleado.dni = request.form['dni']
        empleado.seg_social = request.form['seg_social']
        empleado.telefono = request.form['telefono']
        empleado.hora_entrada = datetime.strptime(request.form['hora_entrada'], '%H:%M').time()
        empleado.hora_salida = datetime.strptime(request.form['hora_salida'], '%H:%M').time()
        empleado.hora_entrada2 = datetime.strptime(request.form['hora_entrada2'], '%H:%M').time()
        empleado.hora_salida2 = datetime.strptime(request.form['hora_salida2'], '%H:%M').time()
        empleado.sabados = 'sabados' in request.form
        empleado.activo = 'activo' in request.form
        
        db.session.commit()
        flash('Empleado actualizado correctamente', 'success')
        return redirect(url_for('empleados'))
    
    return render_template('editar_empleado.html', empleado=empleado)

@app.route('/registros/<int:empleado_id>')
@login_required
def registros_empleado(empleado_id):
    empleado = Empleado.query.get_or_404(empleado_id)
    registros = Registro.query.filter_by(empleado_id=empleado_id).order_by(Registro.fecha.desc()).all()
    return render_template('registros.html', empleado=empleado, registros=registros)

@app.route('/consulta_registros', methods=['GET', 'POST'])
@login_required
def consulta_registros():
    empleados = Empleado.query.order_by(Empleado.apellidos).all()
    
    # Valores por defecto
    fecha_inicio = request.args.get('fecha_inicio', get_madrid_time().strftime('%Y-%m-%d'))
    fecha_fin = request.args.get('fecha_fin', get_madrid_time().strftime('%Y-%m-%d'))
    empleado_id = request.args.get('empleado_id', 'todos')
    
    # Construir la consulta base
    query = Registro.query.join(Empleado)
    
    # Convertir las fechas a datetime con zona horaria de Madrid
    inicio = madrid_tz.localize(datetime.strptime(fecha_inicio + ' 00:00:00', '%Y-%m-%d %H:%M:%S'))
    fin = madrid_tz.localize(datetime.strptime(fecha_fin + ' 23:59:59', '%Y-%m-%d %H:%M:%S'))
    
    # Convertir a UTC para la consulta
    inicio_utc = inicio.astimezone(pytz.UTC)
    fin_utc = fin.astimezone(pytz.UTC)
    
    # Aplicar filtros
    query = query.filter(Registro.fecha.between(inicio_utc, fin_utc))
    
    if empleado_id != 'todos':
        query = query.filter(Registro.empleado_id == empleado_id)
    
    # Obtener todos los registros
    registros = query.order_by(Registro.fecha.desc(), Empleado.apellidos).all()
    
    # Agrupar registros por fecha y empleado
    registros_agrupados = {}
    for registro in registros:
        fecha = registro.fecha_madrid.strftime('%Y-%m-%d')
        empleado_id = registro.empleado_id
        key = (fecha, empleado_id)
        
        if key not in registros_agrupados:
            registros_agrupados[key] = {
                'fecha': registro.fecha_madrid,
                'empleado': registro.empleado,
                'entrada': None,
                'salida': None
            }
        
        if registro.tipo == 'entrada':
            registros_agrupados[key]['entrada'] = registro.fecha_madrid
        else:
            registros_agrupados[key]['salida'] = registro.fecha_madrid
    
    # Convertir a lista y ordenar
    registros_agrupados = list(registros_agrupados.values())
    registros_agrupados.sort(key=lambda x: (x['fecha'], x['empleado'].apellidos), reverse=True)
    
    return render_template('consulta_registros.html',
                         empleados=empleados,
                         registros=registros_agrupados,
                         fecha_inicio=fecha_inicio,
                         fecha_fin=fecha_fin,
                         empleado_id=empleado_id)

@app.route('/panel_control')
@login_required
def panel_control():
    empleados = Empleado.query.all()
    return render_template('panel_control.html', empleados=empleados)

# Funciones del bot
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Usuario {update.effective_user.id} envió /start")
    await update.message.reply_text(
        'Bienvenido al sistema de control de horarios. '
        'Para registrarte, envía tu número de teléfono en el formato: /registro 123456789'
    )

async def registro_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        telefono = context.args[0]
        logger.info(f"Usuario {update.effective_user.id} intenta registrarse con teléfono {telefono}")
        with app.app_context():
            empleado = Empleado.query.filter_by(telefono=telefono).first()
            
            if empleado:
                empleado.telegram_id = str(update.effective_user.id)
                db.session.commit()
                logger.info(f"Registro exitoso para {empleado.nombre} {empleado.apellidos}")
                await update.message.reply_text(
                    f'¡Registro completado! {empleado.nombre} {empleado.apellidos}. '
                    'Ahora puedes usar /entrada y /salida para registrar tus horarios.'
                )
            else:
                logger.warning(f"No se encontró empleado con teléfono {telefono}")
                await update.message.reply_text(
                    'No se encontró ningún empleado con ese número de teléfono. '
                    'Contacta con tu administrador.'
                )
    except IndexError:
        logger.warning("Comando /registro sin argumentos")
        await update.message.reply_text('Por favor, envía tu número de teléfono después del comando /registro')

async def entrada_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)
    with app.app_context():
        empleado = Empleado.query.filter_by(telegram_id=telegram_id).first()
        
        if empleado:
            registro = Registro(empleado_id=empleado.id, tipo='entrada')
            db.session.add(registro)
            db.session.commit()
            hora_madrid = registro.fecha_madrid
            await update.message.reply_text(f'Registro de entrada realizado a las {hora_madrid.strftime("%H:%M")}')
        else:
            await update.message.reply_text('No estás registrado. Usa /registro para registrarte.')

async def salida_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)
    with app.app_context():
        empleado = Empleado.query.filter_by(telegram_id=telegram_id).first()
        
        if empleado:
            registro = Registro(empleado_id=empleado.id, tipo='salida')
            db.session.add(registro)
            db.session.commit()
            hora_madrid = registro.fecha_madrid
            await update.message.reply_text(f'Registro de salida realizado a las {hora_madrid.strftime("%H:%M")}')
        else:
            await update.message.reply_text('No estás registrado. Usa /registro para registrarte.')

async def send_notification(telegram_id: str, message: str, command: str):
    """Envía una notificación al usuario de Telegram con botones inline"""
    if telegram_bot and telegram_id:
        try:
            # Crear botón inline
            keyboard = [[InlineKeyboardButton("Fichar", callback_data=command)]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await telegram_bot.bot.send_message(
                chat_id=telegram_id,
                text=message,
                reply_markup=reply_markup
            )
            logger.info(f"Notificación enviada a {telegram_id}")
        except Exception as e:
            logger.error(f"Error al enviar notificación a {telegram_id}: {str(e)}")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja las pulsaciones de los botones inline"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "entrada":
        await entrada_bot(update, context)
    elif query.data == "salida":
        await salida_bot(update, context)

def check_schedules():
    """Verifica los horarios de los empleados y envía notificaciones"""
    logger.info("Verificando horarios de empleados...")
    current_time = get_madrid_time()
    current_weekday = current_time.weekday()
    
    with app.app_context():
        empleados = Empleado.query.filter_by(activo=True).all()
        
        for empleado in empleados:
            # Verificar si es sábado y el empleado no trabaja los sábados
            if current_weekday == 5 and not empleado.sabados:
                continue
                
            # Obtener el último registro del día
            inicio_dia = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
            fin_dia = current_time.replace(hour=23, minute=59, second=59, microsecond=999999)
            
            ultimo_registro = Registro.query.filter(
                Registro.empleado_id == empleado.id,
                Registro.fecha.between(madrid_to_utc(inicio_dia), madrid_to_utc(fin_dia))
            ).order_by(Registro.fecha.desc()).first()
            
            # Verificar hora de entrada
            if not ultimo_registro or ultimo_registro.tipo == 'salida':
                hora_entrada = empleado.hora_entrada
                if current_time.hour == hora_entrada.hour and current_time.minute >= hora_entrada.minute - 5:
                    message = f"Recordatorio: Tu hora de entrada es a las {hora_entrada.strftime('%H:%M')}. No olvides fichar."
                    asyncio.run(send_notification(empleado.telegram_id, message, "entrada"))
            
            # Verificar hora de salida
            if ultimo_registro and ultimo_registro.tipo == 'entrada':
                hora_salida = empleado.hora_salida
                if current_time.hour == hora_salida.hour and current_time.minute >= hora_salida.minute - 5:
                    message = f"Recordatorio: Tu hora de salida es a las {hora_salida.strftime('%H:%M')}. No olvides fichar."
                    asyncio.run(send_notification(empleado.telegram_id, message, "salida"))

async def setup_bot():
    """Configura y inicia el bot de Telegram"""
    global telegram_bot
    
    token = os.environ.get('TELEGRAM_TOKEN')
    if not token:
        logger.error("No se encontró el token de Telegram")
        return

    try:
        logger.info("Iniciando configuración del bot...")
        # Crear la aplicación
        application = Application.builder().token(token).build()
        
        # Registrar handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("registro", registro_bot))
        application.add_handler(CommandHandler("entrada", entrada_bot))
        application.add_handler(CommandHandler("salida", salida_bot))
        application.add_handler(CallbackQueryHandler(button_callback))
        
        # Inicializar el bot
        telegram_bot = application
        logger.info("Bot configurado correctamente")
        
        # Iniciar el bot
        logger.info("Iniciando el bot...")
        await application.initialize()
        await application.start()
        
        # Configurar webhook o polling según el entorno
        webhook_url = os.environ.get('WEBHOOK_URL')
        if webhook_url:
            logger.info(f"Configurando webhook en: {webhook_url}")
            await application.bot.set_webhook(url=webhook_url)
            logger.info("Webhook configurado correctamente")
        else:
            logger.info("No se encontró WEBHOOK_URL, usando polling para desarrollo local")
            await application.updater.start_polling(allowed_updates=Update.ALL_TYPES, poll_interval=30)
            logger.info("Polling iniciado correctamente con intervalo de 30 segundos")
            
            # Mantener el bot en ejecución
            while True:
                await asyncio.sleep(1)
            
    except Exception as e:
        logger.error(f"Error al iniciar el bot: {str(e)}")
        if telegram_bot:
            try:
                await telegram_bot.stop()
                await telegram_bot.shutdown()
            except Exception as stop_error:
                logger.error(f"Error al detener el bot: {str(stop_error)}")

def run_bot():
    """Ejecuta el bot en un thread separado"""
    try:
        logger.info("Creando nuevo event loop para el bot")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        logger.info("Ejecutando setup_bot en el loop")
        loop.run_until_complete(setup_bot())
    except Exception as e:
        logger.error(f"Error en run_bot: {str(e)}")
    finally:
        try:
            if not loop.is_closed():
                loop.close()
        except Exception as e:
            logger.error(f"Error al cerrar el loop: {str(e)}")

# Ruta para el webhook de Telegram
@app.route('/webhook', methods=['POST'])
def webhook():
    if telegram_bot:
        update = Update.de_json(request.get_json(), telegram_bot.bot)
        asyncio.run(telegram_bot.process_update(update))
    return 'ok', 200

def run_scheduler():
    """Ejecuta el scheduler en un thread separado"""
    schedule.every(5).minutes.do(check_schedules)
    
    while True:
        schedule.run_pending()
        time.sleep(1)

# Iniciar el bot en un thread separado
logger.info("Iniciando thread del bot")
bot_thread = threading.Thread(target=run_bot, daemon=True)
bot_thread.start()
logger.info("Thread del bot iniciado")

# Iniciar el scheduler en un thread separado
logger.info("Iniciando thread del scheduler")
scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
scheduler_thread.start()
logger.info("Thread del scheduler iniciado")

if __name__ == '__main__':
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    logger = logging.getLogger(__name__)

    # Ejecutar la aplicación Flask
    logger.info("Iniciando aplicación Flask")
    app.run(debug=True, use_reloader=False) 