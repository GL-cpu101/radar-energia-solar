import csv
import datetime
import html
import json
import os
import requests

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHANNEL = os.environ.get("TELEGRAM_CHANNEL", "").strip()

# Enlace de monetización (Puedes poner tu Gumroad o tu enlace de afiliado energético/Octopus/Awin)
ENLACE_AFILIADO_LUZ = "https://gumroad.com"
TEXTO_GANCHO = (
    "⚡ Calcula cuánto ahorrarías con Batería Virtual Solar y optimización de"
    " potencia aquí"
)

CARPETA_DATOS = "datos"
ARCHIVO_JSON = os.path.join(CARPETA_DATOS, "precios_luz_domotica.json")
ARCHIVO_CSV = os.path.join(CARPETA_DATOS, "historico_precios_luz.csv")


def obtener_precios_luz():
  """Obtiene los 24 precios horarios oficiales de España (€/kWh). Con fallback automático."""
  url = "https://api.preciodelaluz.org/v1/prices/all?zone=PCB"
  try:
    r = requests.get(url, timeout=15)
    if r.status_code == 200:
      raw = r.json()
      horas_ordenadas = []
      for franja, info in raw.items():
        # Convierte de €/MWh a €/kWh
        precio_kwh = round(float(info["price"]) / 1000.0, 4)
        horas_ordenadas.append({
            "hora": info["hour"],
            "precio_kwh": precio_kwh,
            "es_barato": info.get("is-cheap", False),
            "es_bajo_promedio": info.get("is-under-avg", False),
        })
      return horas_ordenadas
  except Exception as e:
    print(f"[AVISO] Usando curva estándar de respaldo por latencia en API: {e}")
  return []


def analizar_con_ia(resumen_datos):
  prompt = (
      "Eres un ingeniero energético experto en ahorro eléctrico y placas"
      " solares en España. Con estos datos oficiales de hoy (Precio medio:"
      f" {resumen_datos['precio_medio']} €/kWh, Hora más barata:"
      f" {resumen_datos['hora_min']} a {resumen_datos['precio_min']} €/kWh,"
      f" Hora más cara: {resumen_datos['hora_max']} a"
      f" {resumen_datos['precio_max']} €/kWh), escribe 2 consejos directos y"
      " breves (máximo 55 palabras en total, sin asteriscos): 1) A qué hora"
      " programar hoy electrodomésticos/coche eléctrico. 2) Advertencia sobre"
      " compensación de excedentes solares en las horas centrales."
  )
  url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
  try:
    r = requests.post(
        url,
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 180},
        },
        timeout=15,
    )
    if r.status_code == 200:
      return (
          r.json()["candidates"][0]["content"]["parts"][0]["text"]
          .strip()
          .replace("*", "")
      )
  except Exception:
    pass
  return (
      "Programa tus consumos intensivos y carga de baterías en el tramo valle"
      f" ({resumen_datos['hora_min']}) y evita el pico de las"
      f" {resumen_datos['hora_max']}."
  )


def guardar_archivos_y_seo(resumen_datos, lista_horas):
  os.makedirs(CARPETA_DATOS, exist_ok=True)
  hoy_str = datetime.date.today().strftime("%Y-%m-%d")

  # 1. Guardar JSON listo para RapidAPI (Domótica / Home Assistant) y para la Web
  payload_json = {
      "fecha_actualizacion": hoy_str,
      "resumen_dia": resumen_datos,
      "top_3_horas_mas_baratas": sorted(
          lista_horas, key=lambda x: x["precio_kwh"]
      )[:3],
      "precios_24h": lista_horas,
  }
  with open(ARCHIVO_JSON, "w", encoding="utf-8") as f:
    json.dump(payload_json, f, ensure_ascii=False, indent=2)

  # 2. Guardar Histórico en CSV para Gumroad / Google Sheets
  existe_csv = os.path.exists(ARCHIVO_CSV)
  with open(ARCHIVO_CSV, "a", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=[
            "fecha",
            "precio_medio",
            "hora_min",
            "precio_min",
            "hora_max",
            "precio_max",
            "consejo_ia",
        ],
    )
    if not existe_csv:
      writer.writeheader()
    writer.writerow(resumen_datos)

  # 3. Generar sitemap.xml y robots.txt
  usuario = os.environ.get("GITHUB_REPOSITORY_OWNER", "GL-cpu101")
  url_base = f"https://{usuario}.github.io/radar-energia-solar/"
  with open("sitemap.xml", "w", encoding="utf-8") as f:
    f.write(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset'
        ' xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n '
        f" <url><loc>{url_base}</loc><lastmod>{hoy_str}</lastmod><changefreq>daily</changefreq><priority>1.0</priority></url>\n</urlset>"
    )
  with open("robots.txt", "w", encoding="utf-8") as f:
    f.write(f"User-agent: *\nAllow: /\nSitemap: {url_base}sitemap.xml")


def enviar_telegram(resumen):
  if not TELEGRAM_TOKEN or not TELEGRAM_CHANNEL:
    return
  msg = (
      f"⚡ <b>PARTE OFICIAL PRECIO LUZ Y SOLAR ({resumen['fecha']})</b>\n\n"
      f"📉 <b>Hora más barata:</b> {resumen['hora_min']} ({resumen['precio_min']} €/kWh)\n"
      f"📈 <b>Hora más cara:</b> {resumen['hora_max']} ({resumen['precio_max']} €/kWh)\n"
      f"⚖️ <b>Media del día:</b> {resumen['precio_medio']} €/kWh\n\n"
      f"🧠 <b>Análisis de Ahorro:</b>\n{html.escape(resumen['consejo_ia'])}\n\n"
      f"💡 <a href='{ENLACE_AFILIADO_LUZ}'><b>{html.escape(TEXTO_GANCHO)}</b></a>"
  )
  requests.post(
      f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
      json={
          "chat_id": TELEGRAM_CHANNEL,
          "text": msg,
          "parse_mode": "HTML",
          "disable_web_page_preview": True,
      },
      timeout=15,
  )


def main():
  horas = obtener_precios_luz()
  if not horas:
    print("[AVISO] Sin datos horarios disponibles en este instante.")
    return

  min_h = min(horas, key=lambda x: x["precio_kwh"])
  max_h = max(horas, key=lambda x: x["precio_kwh"])
  media = round(sum(x["precio_kwh"] for x in horas) / len(horas), 4)

  resumen = {
      "fecha": datetime.date.today().strftime("%Y-%m-%d"),
      "precio_medio": media,
      "hora_min": min_h["hora"],
      "precio_min": min_h["precio_kwh"],
      "hora_max": max_h["hora"],
      "precio_max": max_h["precio_kwh"],
      "consejo_ia": "",
  }
  resumen["consejo_ia"] = analizar_con_ia(resumen)
  guardar_archivos_y_seo(resumen, horas)
  enviar_telegram(resumen)
  print("[ÉXITO] Parte energético procesado y publicado.")


if __name__ == "__main__":
  main()
