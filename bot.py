import imaplib
import email
import time
import json
import re
import requests
import os
from dotenv import load_dotenv

load_dotenv()

GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_PASSWORD = os.getenv("GMAIL_PASSWORD")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
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


def extraer_datos_con_groq(cuerpo_mail):
    url = "https://api.groq.com/openai/v1/chat/completions"

    prompt = f"""
Analizá este mail de pedido y extraé los siguientes datos en formato JSON exacto:
{{
  "cliente": "nombre del cliente",
  "telefono": "numero de telefono",
  "metodo_pago": "uno de: transferencia | efectivo | mercado pago",
  "metodo_envio": "uno de: correo argentino | retiro en domicilio | cadete"
}}

Si algún dato no está, poné null.
Respondé SOLO el JSON, sin texto extra ni backticks.

MAIL:
{cuerpo_mail}
"""

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    body = {
        "model": "llama-3.1-8b-instant",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0
    }

    response = requests.post(url, headers=headers, json=body)
    result = response.json()

    text = result["choices"][0]["message"]["content"]
    text = text.strip().replace("```json", "").replace("```", "").strip()

    return json.loads(text)


def extraer_productos_y_total(cuerpo_mail):
    productos = []
    for linea in cuerpo_mail.split("\n"):
        linea = linea.strip()
        if linea.startswith("-"):
            productos.append(linea)

    match_total = re.search(r'Total:\s*\$?([\d.,]+)', cuerpo_mail)
    total = f"${match_total.group(1)}" if match_total else "?"

    return "\n".join(productos) if productos else "Ver detalle en mail", total


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

        asunto = msg.get("Subject", "")
        match = re.search(r'#(\d+)', asunto)
        numero_pedido = match.group(1) if match else "?"

        cuerpo = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    cuerpo = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                    break
        else:
            cuerpo = msg.get_payload(decode=True).decode("utf-8", errors="ignore")

        print(f"\n📧 Procesando pedido #{numero_pedido}...\n{cuerpo[:200]}...")

        try:
            datos = extraer_datos_con_groq(cuerpo)
            productos, total = extraer_productos_y_total(cuerpo)

            print(f"✅ Datos extraídos: {datos}")

            resumen = f"{productos}\n💰 Total: {total}"
            pago = datos.get("metodo_pago") or ""
            envio = datos.get("metodo_envio") or ""
            mensaje_cliente = get_mensaje(pago, envio, resumen)

            mensaje_para_vos = f"""🔔 *NUEVO PEDIDO #{numero_pedido}*

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