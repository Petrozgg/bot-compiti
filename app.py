import os
import re
import csv
import io
import requests
from flask import Flask, request

app = Flask(__name__)

# Questi valori NON si scrivono qui: li metteremo su Render in un passaggio dopo
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
SHEET_CSV_URL = os.environ.get("SHEET_CSV_URL")

AIUTO = (
    "Ciao! Scrivimi una materia (es. matematica) "
    "oppure una data (es. 12/11/2026) e ti dico i compiti."
)


def leggi_compiti():
    r = requests.get(SHEET_CSV_URL, timeout=10)
    r.encoding = "utf-8"
    righe = list(csv.reader(io.StringIO(r.text)))
    compiti = []
    # Ordine colonne: Consegna, Materia, Compito
    for riga in righe[1:]:
        if len(riga) >= 3 and riga[0].strip():
            compiti.append({
                "consegna": riga[0].strip(),
                "materia": riga[1].strip(),
                "compito": riga[2].strip(),
            })
    return compiti


def leggi_data(testo):
    m = re.fullmatch(r"(\d{1,2})[/.\-](\d{1,2})(?:[/.\-](\d{2,4}))?", testo.strip())
    if not m:
        return None
    giorno, mese, anno = m.groups()
    return int(giorno), int(mese), (int(anno) % 100 if anno else None)


def formatta(lista):
    return "\n\n".join(
        f"📚 {c['materia']} (consegna {c['consegna']})\n📝 {c['compito']}"
        for c in lista
    )


def cerca(testo):
    testo = testo.strip().lower()
    compiti = leggi_compiti()

    data = leggi_data(testo)
    if data:
        g, m, a = data
        trovati = []
        for c in compiti:
            d = leggi_data(c["consegna"])
            if d and d[0] == g and d[1] == m and (a is None or d[2] is None or d[2] == a):
                trovati.append(c)
        if not trovati:
            return f"Non ho trovato compiti con consegna il {testo}."
        return formatta(trovati)

    trovati = [c for c in compiti if c["materia"].lower() == testo]
    if trovati:
        return formatta(trovati)

    return AIUTO


def invia(numero, testo):
    url = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
    corpo = {
        "messaging_product": "whatsapp",
        "to": numero,
        "type": "text",
        "text": {"body": testo},
    }
    r = requests.post(url, headers=headers, json=corpo, timeout=10)
    print("Risposta Meta:", r.status_code, r.text)


@app.route("/")
def home():
    return "Bot compiti attivo!"


@app.route("/webhook", methods=["GET"])
def verifica():
    if (request.args.get("hub.mode") == "subscribe"
            and request.args.get("hub.verify_token") == VERIFY_TOKEN):
        return request.args.get("hub.challenge"), 200
    return "Token errato", 403


@app.route("/webhook", methods=["POST"])
def ricevi():
    dati = request.get_json(silent=True) or {}
    try:
        for entry in dati.get("entry", []):
            for change in entry.get("changes", []):
                for msg in change.get("value", {}).get("messages", []):
                    if msg.get("type") == "text":
                        numero = msg["from"]
                        testo = msg["text"]["body"]
                        try:
                            risposta = cerca(testo)
                        except Exception as e:
                            print("Errore nella ricerca:", e)
                            risposta = "Ops, ho avuto un problema a leggere i compiti. Riprova tra poco."
                        invia(numero, risposta)
    except Exception as e:
        print("Errore:", e)
    return "ok", 200
