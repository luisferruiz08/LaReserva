# lareserva.py - Asistente La Reserva Bar
import os
import sys
import asyncio
import subprocess
import importlib

# ==========================================
# Dependencias locales (Se instalan solas)
# ==========================================
CARPETA_PROYECTO = os.path.dirname(os.path.abspath(__file__))
CARPETA_LIBS = os.path.join(CARPETA_PROYECTO, "libs")
os.makedirs(CARPETA_LIBS, exist_ok=True)

if CARPETA_LIBS not in sys.path:
    sys.path.insert(0, CARPETA_LIBS)

def verificar_libreria(paquete, modulo):
    try:
        importlib.import_module(modulo)
        print(f"✅ {paquete}: disponible")
    except ImportError:
        print(f"⚠️ {paquete}: no está instalado. Instalando...")
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", 
            "--target", CARPETA_LIBS, "--upgrade", paquete
        ])
        importlib.invalidate_caches()
        print(f"✅ {paquete}: instalado correctamente")

verificar_libreria("python-dotenv", "dotenv")
verificar_libreria("openai", "openai")
verificar_libreria("python-telegram-bot", "telegram")

from dotenv import load_dotenv
from openai import OpenAI
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters
)

# ==========================================
# Base de productos
# ==========================================
try:
    from productos import PRODUCTOS
    print("✅ Base de productos cargada correctamente")
    print(f"ℹ️ Total de servicios/productos: {len(PRODUCTOS)}")
except Exception as error_productos:
    print("❌ Base de productos NO cargada")
    print(f"⚠️ Error: {error_productos}")
    PRODUCTOS = []

# ==========================================
# Credenciales
# ==========================================
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHATGPT_API_KEY = os.getenv("CHATGPT_API_KEY")

if not TELEGRAM_TOKEN:
    print("❌ No se encontró TELEGRAM_TOKEN en .env")
    sys.exit()

if not CHATGPT_API_KEY:
    print("❌ No se encontró CHATGPT_API_KEY en .env")
    sys.exit()

# ==========================================
# OpenAI (ChatGPT)
# ==========================================
cliente_openai = OpenAI(api_key=CHATGPT_API_KEY)
MODELO_PRINCIPAL = "gpt-4o-mini" # Puedes usar también "gpt-3.5-turbo" o "gpt-4o"

# ==========================================
# Estado por usuario
# ==========================================
memoria_usuarios = {}
producto_activo = {}

def buscar_producto(codigo):
    for producto in PRODUCTOS:
        if producto["codigo"].upper() == codigo.upper():
            return producto
    return None

def construir_contexto_productos():
    if not PRODUCTOS:
        return "Actualmente no existen productos cargados."
    
    texto = "CATÁLOGO OFICIAL DE LA RESERVA BAR:\n\n"
    for producto in PRODUCTOS:
        precio_str = f"${producto['precio']:,.0f}".replace(",", ".") if producto['precio'] > 0 else "Consultar / Precio no aplica"
        texto += (
            f"Código: {producto['codigo']}\n"
            f"Nombre: {producto['nombre']}\n"
            f"Descripción: {producto['descripcion']}\n"
            f"Precio: {precio_str} COP\n\n"
        )
    return texto

CONTEXTO_PRODUCTOS = construir_contexto_productos()

def consultar_chatgpt(mensaje, usuario_id):
    previous_id = memoria_usuarios.get(usuario_id)
    codigo_activo = producto_activo.get(usuario_id)
    informacion_producto = ""

    if codigo_activo:
        producto = buscar_producto(codigo_activo)
        if producto:
            precio_str = f"${producto['precio']:,.0f}".replace(",", ".") if producto['precio'] > 0 else "Consultar / Precio no aplica"
            informacion_producto = f"""
            PRODUCTO/SERVICIO ACTIVO EN ESTA CONVERSACIÓN:
            Código: {producto['codigo']}
            Nombre: {producto['nombre']}
            Descripción: {producto['descripcion']}
            Precio: {precio_str}
            
            El cliente llegó desde la Landing consultando esto. 
            Mantén esto como contexto principal hasta que el cliente pregunte por otra cosa.
            """

    prompt_sistema = f"""
    Eres el asistente virtual de 'La Reserva', un bar premium y elegante en Popayán.
    
    REGLAS:
    1. Responde únicamente con base en el catálogo oficial proporcionado.
    2. No inventes productos, características ni precios.
    3. Si un producto no existe, indícalo claramente.
    4. Responde en español, de forma cordial, elegante y breve.
    5. Todavía no realices pagos ni confirmes pedidos o reservas definitivamente en el sistema. Si el cliente quiere reservar, indícale que has tomado sus datos y que el equipo de La Reserva se comunicará para confirmar.
    6. Si existe un PRODUCTO/SERVICIO ACTIVO, úsalo como contexto principal.
    
    {CONTEXTO_PRODUCTOS}
    
    {informacion_producto}
    """

    try:
        respuesta = cliente_openai.chat.completions.create(
            model=MODELO_PRINCIPAL,
            messages=[
                {"role": "system", "content": prompt_sistema},
                {"role": "user", "content": mensaje}
            ]
        )
        return respuesta.choices[0].message.content
    except Exception as error_principal:
        print("⚠️ Modelo principal tuvo un inconveniente")
        print(error_principal)
        return "En este momento tengo dificultades para comunicarme con el sistema. Por favor, intenta nuevamente en unos minutos."

async def iniciar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    usuario_id = update.effective_user.id
    nombre = update.effective_user.first_name or "Invitado"

    print("\n==============================================")
    print("🔗 PRUEBA DE DEEP LINK")
    print("Mensaje completo:", update.message.text)
    print("Argumentos recibidos:", context.args)
    print("==============================================")

    # Reinicio lógico de la sesión
    memoria_usuarios.pop(usuario_id, None)
    producto_activo.pop(usuario_id, None)

    # Si llega desde la Landing Page con un código (ej. /start BAR-001)
    if context.args:
        codigo = context.args[0].strip().upper()
        producto = buscar_producto(codigo)
        
        print(f"📥 Referencia recibida desde Landing: {codigo}")
        
        if producto:
            producto_activo[usuario_id] = codigo
            precio_str = f"${producto['precio']:,.0f}".replace(",", ".") if producto['precio'] > 0 else "N/A"
            print(f"🍸 Producto/Servicio identificado: {producto['nombre']}")
            
            mensaje = (
                "--------------------------------------------------\n"
                "🍸 NUEVA CONSULTA\n"
                "--------------------------------------------------\n\n"
                f"Hola {nombre} 👋\n\n"
                f"Llegaste desde nuestra página consultando:\n\n"
                f"🔹 {producto['nombre']} ({producto['codigo']})\n"
                f"📝 {producto['descripcion']}\n"
            )
            
            if producto['precio'] > 0:
                mensaje += f"💰 Precio: {precio_str} COP\n\n"
            else:
                mensaje += "\n"
                
            mensaje += "¿En qué te puedo ayudar con esto?"
            
            await update.message.reply_text(mensaje)
            return

        await update.message.reply_text(f"⚠️ No encontré la referencia {codigo} en nuestro catálogo.")
        return

    # Si abre el bot normalmente sin código
    await update.message.reply_text(
        f"🍸 Hola {nombre}. Soy el asistente virtual de La Reserva Bar.\n\n"
        "Puedo ayudarte con nuestra carta de cócteles, eventos y reservas de mesa."
    )

async def recibir_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    usuario_id = update.effective_user.id
    nombre = update.effective_user.first_name or "Usuario"
    mensaje = update.message.text

    print("\n--------------------------------------------------")
    print(f"👤 Usuario: {nombre}")
    print(f"💬 Mensaje: {mensaje}")
    print(f"🎯 Activo: {producto_activo.get(usuario_id, 'ninguno')}")
    print(f"🤖 Consultando IA...")

    respuesta = await asyncio.to_thread(
        consultar_chatgpt,
        mensaje,
        usuario_id
    )

    await update.message.reply_text(respuesta)
    print("✅ Respuesta enviada a Telegram")

def main():
    print("\n==============================================")
    print("🍸 ASISTENTE LA RESERVA BAR - INICIADO")
    print("==============================================")
    print(f"📦 Productos cargados: {len(PRODUCTOS)}")
    print("🔗 Deep Link desde Landing: ACTIVO")
    print("⏳ Esperando mensajes desde Telegram...\n")

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", iniciar))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_mensaje))
    
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()