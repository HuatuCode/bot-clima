import os
import telebot
import sqlite3
import requests
import schedule
import time
import threading
from google import genai
from dotenv import load_dotenv
import datetime
import locale

# Configurar para que la fecha salga en español (depende de tu sistema) y carga de las variables del archivo .env
try:
    locale.setlocale(locale.LC_TIME, 'es_ES.UTF-8') 
except locale.Error:
    pass

load_dotenv()

bot = telebot.TeleBot(os.getenv("TELEGRAM_TOKEN"))
OPENWEATHER_KEY = os.getenv("WEATHER_TOKEN")
cliente_gemini = genai.Client(api_key=os.getenv("GEMINI_TOKEN"))

# --- 1. MEMORIA ---
conn = sqlite3.connect("usuarios.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS usuarios (chat_id INTEGER PRIMARY KEY, ciudad TEXT)")
conn.commit()

def guardar_usuario(chat_id, ciudad):
    cursor.execute("INSERT OR REPLACE INTO usuarios (chat_id, ciudad) VALUES (?, ?)", (chat_id, ciudad))
    conn.commit()

def obtener_usuarios():
    cursor.execute("SELECT chat_id, ciudad FROM usuarios")
    return cursor.fetchall()

# --- 2. HERRAMIENTA (TOOL) ---
def obtener_clima(ciudad):
    url = f"http://api.openweathermap.org/data/2.5/weather?q={ciudad}&appid={OPENWEATHER_KEY}&units=metric&lang=es"
    data = requests.get(url).json()
    temp = data["main"]["temp"]
    desc = data["weather"][0]["description"]
    return f"{temp}°C, {desc}"

# --- 3. CEREBRO (LLM) ---
def interpretar_ubicacion(mensaje):
    # El LLM actúa como filtro de datos
    prompt = f"""
    El usuario quiere registrar su ciudad. Su mensaje es: "{mensaje}"
    Si la ciudad es clara, responde EXACTAMENTE con el formato: "CIUDAD: Nombre, Código de País" (ejemplo: CIUDAD: Lima, PE).
    Si el mensaje es ambiguo o falta la ciudad, pregúntale amablemente a qué ciudad se refiere.
    """
    respuesta = cliente_gemini.models.generate_content(model='gemini-3.5-flash-lite', contents=prompt) 
    return respuesta.text

def generar_mensaje_buenos_dias(ciudad, clima):
    # Obtiene la fecha actual, ej: "miércoles 4 de noviembre"
    fecha_actual = datetime.datetime.now().strftime("%A %d de %B")
    
    prompt = f"Eres un asistente matutino. Redacta un mensaje de buenos días para alguien en {ciudad}. El clima hoy es: {clima}. Sé breve y motivador detallando cómo va a variar el clima a lo largo del día. Hoy es {fecha_actual}, menciónalo explícitamente en el saludo."
    
    respuesta = cliente_gemini.models.generate_content(model='gemini-3.5-flash-lite', contents=prompt)
    return respuesta.text

# --- 4. INTERFAZ Y AUTONOMÍA ---
@bot.message_handler(commands=['start'])
def bienvenida(message):
    bot.reply_to(message, "¡Hola! Para darte los buenos días, ¿dónde te encuentras hoy?")

@bot.message_handler(func=lambda m: True)
def procesar_mensaje(message):
    analisis = interpretar_ubicacion(message.text) # Evaluamos el mensaje con IA
    
    if analisis.startswith("CIUDAD:"):
        ciudad_limpia = analisis.replace("CIUDAD:", "").strip()
        guardar_usuario(message.chat.id, ciudad_limpia)
        bot.reply_to(message, f"¡Anotado! He guardado tu ubicación como: {ciudad_limpia}. Te escribiré pronto.")
    else:
        # Si el LLM tiene dudas, te hará la pregunta de vuelta (ej. "¿A qué Lima te refieres?")
        bot.reply_to(message, analisis)

def enviar_reporte_diario():
    try:
        usuarios = obtener_usuarios()
        for chat_id, ciudad in usuarios:
            clima = obtener_clima(ciudad)
            mensaje = generar_mensaje_buenos_dias(ciudad, clima)
            bot.send_message(chat_id, mensaje)
    except Exception as e:
        print(f"Error enviando reporte: {e}")

# Autonomía
schedule.every(10).seconds.do(enviar_reporte_diario)


def hilo_autonomia():
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    threading.Thread(target=hilo_autonomia, daemon=True).start()
    bot.polling(none_stop=True)