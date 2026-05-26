import imaplib
import email
import time
import json
import requests
import os
from dotenv import load_dotenv

load_dotenv()

GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_PASSWORD = os.getenv("GMAIL_PASSWORD")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
CALLMEBOT_API_KEY = os.getenv("CALLMEBOT_API_KEY")
TU_NUMERO_WHATSAPP = os.getenv("TU_NUMERO_WHATSAPP")
TU_DIRECCION = os.getenv("TU_DIRECCION")


def get_mensaje(pago, envio, resumen_pedido):
    saludo = f"¡Hola! 🛍️ Recibimos tu pedido en misso.ar, ¡gracias por tu compra!\n\n📦 *Resumen de tu pedido:*\n{resumen_pedido}\n\n"

    pago = pago.lower().strip()
    envio = envio.lower().strip()

    if pago == "transferencia" and envio == "retiro en domicilio":
        return saludo + f"Para confirmarlo necesitamos verificar el pago. ¿Podrías enviarnos el comprobante de transferencia? Una vez confirmado coordinamos el retiro en nuestro domicilio en {TU_DIRECCION}. ¿En qué horarios te quedaría cómodo pasar?"

    elif pago == "transferencia" and envio == "correo argentino":
        return saludo + "Para confirmarlo necesitamos verificar el pago. ¿Podrías enviarnos el comprobante de transferencia? Una vez confirmado procedemos a despachar tu producto y te enviamos el código de seguimiento por este medio."

    elif pago == "efectivo" and envio == "retiro en domicilio":
        return saludo + f"Tu pedido está listo. Podés pasar a retirarlo en nuestro domicilio en {TU_DIRECCION}. ¿En qué horarios te quedaría cómodo pasar?"

    elif pago == "mercado pago" and envio == "retiro en domicilio":
        return saludo + f"¡Recibimos tu pago correctamente! Podemos coordinar el retiro en nuestro domicilio en {TU_DIRECCION}. ¿En qué horarios te quedaría cómodo pasar?"

    elif pago == "mercado pago" and envio == "correo argentino":
        return saludo + "¡Recibimos tu pago correctamente! Vamos a proceder a despachar tu producto y te enviamos el código de seguimiento por este medio."

    elif envio == "cadete":
        return saludo + "Para coordinar la entrega necesitamos que nos indiques tu dirección completa para cotizarte el envío por cadete."

    else:
        return saludo + f"Nos comunicaremos a la brevedad para coordinar los detalles de tu pedido. (Pago: {pago} | Envío: {envio})"


def extraer_datos_con_gemini(cuerpo_mail):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent?key={GEMINI_API_KEY}"

    prompt = f"""
Analizá este mail de pedido y extraé los siguientes datos en formato JSON exacto:
{{
  "numero_pedido": "...",
  "cliente": "...",
  "telefono": "...",
  "productos": "lista de productos con color, cantidad y precio en una sola línea",
  "total": "...",
  "metodo_pago": "uno de: transferencia | efectivo | mercado pago",
  "metodo_envio": "uno de: correo argentino | retiro en domicilio | cadete"
}}

Si algún dato no está, poné null.
Respondé SOLO el JSON, sin texto extra ni backticks.

MAIL:
{cuerpo_mail}
"""

    body = {"contents": [{"parts": [{"text": prompt}]}]}
    response = requests.post(url, json=body)
    result = response.json()

    text = result["candidates"][0]["content"]["parts"][0]["text"]
    text = text.strip().replace("```json", "").replace("```", "").strip()

    return json.loads(text)


def enviar_whatsapp(mensaje):
    url = "https://api.callmebot.com/whatsapp.php"
    params = {
        "phone": TU_NUMERO_WHATSAPP,
        "text": mensaje,
        "apikey": CALLMEBOT_API_KEY
    }

    response = requests.get(url, params=params)

    if response.status_code == 200:
        print("✅ WhatsApp enviado correctamente")
    else:
        print(f"❌ Error enviando WhatsApp: {response.text}")


def leer_mails_nuevos():
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(GMAIL_USER, GMAIL_PASSWORD)
    mail.select("inbox")

    _, mensajes = mail.search(None, '(UNSEEN SUBJECT "Nuevo pedido")')
    ids = mensajes[0].split()
    print(f"📬 Mails nuevos encontrados: {len(ids)}")

    for mail_id in ids:
        _, msg_data = mail.fetch(mail_id, "(RFC822)")
        msg = email.message_from_bytes(msg_data[0][1])

        cuerpo = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    cuerpo = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                    break
        else:
            cuerpo = msg.get_payload(decode=True).decode("utf-8", errors="ignore")

        print(f"\n📧 Procesando pedido...\n{cuerpo[:200]}...")

        try:
            datos = extraer_datos_con_gemini(cuerpo)
            print(f"✅ Datos extraídos: {datos}")

            resumen = f"{datos.get('productos', 'Ver detalle en mail')}\n💰 Total: ${datos.get('total', '?')}"
            pago = datos.get("metodo_pago") or ""
            envio = datos.get("metodo_envio") or ""
            mensaje_cliente = get_mensaje(pago, envio, resumen)

            mensaje_para_vos = f"""🔔 *NUEVO PEDIDO #{datos.get('numero_pedido', '?')}*

👤 Cliente: {datos.get('cliente', '?')}
📱 Tel: {datos.get('telefono') or 'No encontrado'}
💳 Pago: {pago}
🚚 Envío: {envio}

✉️ *Mensaje sugerido para enviar al cliente:*
──────────────────
{mensaje_cliente}
──────────────────"""

            enviar_whatsapp(mensaje_para_vos)

        except Exception as e:
            print(f"❌ Error procesando mail: {e}")

    mail.logout()


if __name__ == "__main__":
    print("🤖 Bot Misso iniciado. Revisando mails cada 2 minutos...")
    while True:
        try:
            leer_mails_nuevos()
        except Exception as e:
            print(f"❌ Error general: {e}")
        time.sleep(120)