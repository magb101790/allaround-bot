from http.server import BaseHTTPRequestHandler
import json
import os
import urllib.request
from datetime import datetime
import pytz

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
NOTION_DB_ATTIVITA = os.environ.get("NOTION_DB_ATTIVITA")
NOTION_DB_ABITUDINI = os.environ.get("NOTION_DB_ABITUDINI")
NOTION_DB_LOG = os.environ.get("NOTION_DB_LOG")
NOTION_DB_SETTINGS = os.environ.get("NOTION_DB_SETTINGS")
TIMEZONE = "Europe/Rome"

tz = pytz.timezone(TIMEZONE)

REPLY_KEYBOARD = {
    "keyboard": [
        [{"text": "📋 Oggi"}, {"text": "➕ Aggiungi"}],
        [{"text": "✅ Fatto"}, {"text": "📊 Recap"}],
        [{"text": "🗂 Menu"}]
    ],
    "resize_keyboard": True,
    "persistent": True
}

def notion_request(method, path, data=None):
    url = f"https://api.notion.com/v1{path}"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req) as res:
        return json.loads(res.read())

def telegram_send(text, chat_id=None, reply_markup=None):
    cid = chat_id or TELEGRAM_CHAT_ID
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": cid, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    else:
        payload["reply_markup"] = json.dumps(REPLY_KEYBOARD)
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req)
    except Exception as e:
        print(f"Telegram error: {e}")

def telegram_answer_callback(callback_query_id):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery"
    payload = {"callback_query_id": callback_query_id}
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req)
    except:
        pass

def gemini_ask(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as res:
        result = json.loads(res.read())
        return result["candidates"][0]["content"]["parts"][0]["text"].strip()

def get_settings():
    res = notion_request("POST", f"/databases/{NOTION_DB_SETTINGS}/query", {})
    settings = {}
    for page in res["results"]:
        try:
            key = page["properties"]["Impostazione"]["title"][0]["text"]["content"]
            val_arr = page["properties"]["Valore"]["rich_text"]
            val = val_arr[0]["text"]["content"] if val_arr else ""
            settings[key] = val
        except:
            pass
    return settings

def get_attivita_aperte():
    res = notion_request("POST", f"/databases/{NOTION_DB_ATTIVITA}/query", {
        "filter": {
            "and": [
                {"property": "Stato", "select": {"does_not_equal": "Fatto"}},
                {"property": "Stato", "select": {"does_not_equal": "Saltato"}}
            ]
        }
    })
    items = []
    for page in res["results"]:
        try:
            nome = page["properties"]["Nome"]["title"]
            if not nome:
                continue
            azione = page["properties"]["Azione esterna"]["rich_text"]
            scadenza = page["properties"]["Scadenza"]["date"]
            items.append({
                "id": page["id"],
                "nome": nome[0]["text"]["content"],
                "tipo": (page["properties"]["Tipo"]["select"] or {}).get("name", "Task"),
                "scadenza": scadenza["start"] if scadenza else None,
                "azione": azione[0]["text"]["content"] if azione else None
            })
        except:
            pass
    return items

def get_abitudini_attive():
    res = notion_request("POST", f"/databases/{NOTION_DB_ABITUDINI}/query", {
        "filter": {"property": "Attiva", "checkbox": {"equals": True}}
    })
    items = []
    for page in res["results"]:
        try:
            nome = page["properties"]["Abitudine"]["title"]
            if not nome:
                continue
            orario = page["properties"]["Orario ideale"]["rich_text"]
            azione = page["properties"]["Azione esterna"]["rich_text"]
            items.append({
                "id": page["id"],
                "nome": nome[0]["text"]["content"],
                "orario": orario[0]["text"]["content"] if orario else None,
                "azione": azione[0]["text"]["content"] if azione else None
            })
        except:
            pass
    return items

def segna_fatto(page_id):
    notion_request("PATCH", f"/pages/{page_id}", {
        "properties": {"Stato": {"select": {"name": "Fatto"}}}
    })

def segna_rimandato(page_id):
    notion_request("PATCH", f"/pages/{page_id}", {
        "properties": {"Stato": {"select": {"name": "Rimandato"}}}
    })

def aggiungi_attivita(nome, tipo="Task"):
    notion_request("POST", "/pages", {
        "parent": {"database_id": NOTION_DB_ATTIVITA},
        "properties": {
            "Nome": {"title": [{"text": {"content": nome}}]},
            "Tipo": {"select": {"name": tipo}},
            "Stato": {"select": {"name": "Da fare"}},
            "Priorità": {"select": {"name": "Media"}}
        }
    })

_state = {}

def cmd_start(chat_id):
    telegram_send(
        "👋 Ciao! Sono il tuo bot *AllaRound*.\n\n"
        "Usa i pulsanti qui sotto per navigare 👇",
        chat_id
    )

def cmd_menu(chat_id):
    keyboard = {
        "inline_keyboard": [
            [{"text": "📋 Oggi", "callback_data": "cmd_oggi"},
             {"text": "➕ Aggiungi", "callback_data": "cmd_aggiungi"}],
            [{"text": "✅ Fatto", "callback_data": "cmd_fatto"},
             {"text": "📊 Recap", "callback_data": "cmd_recap"}]
        ]
    }
    telegram_send("🗂 *Menu AllaRound*\nCosa vuoi fare?", chat_id, reply_markup=keyboard)

def cmd_oggi(chat_id):
    attivita = get_attivita_aperte()
    abitudini = get_abitudini_attive()
    msg = "📋 *Attività aperte*\n"
    for a in attivita[:10]:
        scad = f" ⏰ {a['scadenza']}" if a['scadenza'] else ""
        msg += f"• {a['nome']} _{a['tipo']}{scad}_\n"
    if not attivita:
        msg += "Nessuna attività pendente 🎉\n"
    msg += "\n🔁 *Abitudini attive*\n"
    for a in abitudini:
        orario = f" alle {a['orario']}" if a['orario'] else ""
        msg += f"• {a['nome']}{orario}\n"
    if not abitudini:
        msg += "Nessuna abitudine configurata\n"
    telegram_send(msg, chat_id)

def cmd_aggiungi(chat_id):
    keyboard = {
        "inline_keyboard": [
            [{"text": "📌 Task", "callback_data": "tipo_Task"},
             {"text": "🔁 Abitudine", "callback_data": "tipo_Abitudine"}],
            [{"text": "🎯 Obiettivo", "callback_data": "tipo_Obiettivo"},
             {"text": "🔔 Promemoria", "callback_data": "tipo_Promemoria"}]
        ]
    }
    telegram_send("Cosa vuoi aggiungere?", chat_id, reply_markup=keyboard)

def cmd_fatto(chat_id):
    attivita = get_attivita_aperte()
    if not attivita:
        telegram_send("Nessuna attività pendente! 🎉", chat_id)
        return
    keyboard = {"inline_keyboard": [
        [{"text": f"✅ {a['nome']}", "callback_data": f"fatto_{a['id']}"}]
        for a in attivita[:8]
    ]}
    telegram_send("Cosa hai completato?", chat_id, reply_markup=keyboard)

def cmd_recap(chat_id):
    attivita = get_attivita_aperte()
    abitudini = get_abitudini_attive()
    try:
        msg = gemini_ask(f"Scrivi un recap breve (max 5 righe) in italiano. "
                       f"Attività ancora aperte: {len(attivita)}. "
                       f"Abitudini configurate: {len(abitudini)}. "
                       f"Sii incoraggiante. Usa emoji.")
    except:
        msg = f"🌙 Hai ancora {len(attivita)} attività aperte."
    telegram_send(msg, chat_id)

def handle_text(text, chat_id):
    # Gestisci pulsanti della Reply Keyboard
    if text == "📋 Oggi":
        cmd_oggi(chat_id)
    elif text == "➕ Aggiungi":
        cmd_aggiungi(chat_id)
    elif text == "✅ Fatto":
        cmd_fatto(chat_id)
    elif text == "📊 Recap":
        cmd_recap(chat_id)
    elif text == "🗂 Menu":
        cmd_menu(chat_id)
    else:
        # Gestisci stato conversazione (es. aggiunta attività)
        state = _state.get(chat_id)
        if state and state.get("azione") == "aggiungi":
            tipo = state.get("tipo", "Task")
            aggiungi_attivita(text, tipo)
            _state.pop(chat_id, None)
            telegram_send(f"✅ *{text}* aggiunto come {tipo}!", chat_id)
        else:
            telegram_send("Usa i pulsanti qui sotto 👇", chat_id)

def handle_callback(callback_query_id, data, chat_id):
    telegram_answer_callback(callback_query_id)
    if data == "cmd_oggi":
        cmd_oggi(chat_id)
    elif data == "cmd_aggiungi":
        cmd_aggiungi(chat_id)
    elif data == "cmd_fatto":
        cmd_fatto(chat_id)
    elif data == "cmd_recap":
        cmd_recap(chat_id)
    elif data.startswith("tipo_"):
        tipo = data.replace("tipo_", "")
        _state[chat_id] = {"azione": "aggiungi", "tipo": tipo}
        telegram_send(f"Hai scelto *{tipo}*.\n\nScrivimi il nome:", chat_id)
    elif data.startswith("fatto_"):
        page_id = data.replace("fatto_", "")
        segna_fatto(page_id)
        telegram_send("✅ Ottimo! Segnato come fatto!", chat_id)
    elif data.startswith("rimanda_"):
        page_id = data.replace("rimanda_", "")
        segna_rimandato(page_id)
        telegram_send("⏭ Rimandato.", chat_id)

def invia_spotify(settings, chat_id, testo):
    playlist = settings.get("spotify_link", "https://open.spotify.com/section/0JQ5DAqbMKFQ00XGBls6wr")
    keyboard = {"inline_keyboard": [[{"text": "▶️ Apri Spotify", "url": playlist}]]}
    telegram_send(testo, chat_id, reply_markup=keyboard)

def handle_scheduler():
    now = datetime.now(tz)
    ora = now.strftime("%H:%M")
    try:
        settings = get_settings()
    except:
        settings = {}
    chat_id = TELEGRAM_CHAT_ID

    if ora == settings.get("orario_recap_mattutino", "08:00"):
        attivita = get_attivita_aperte()
        abitudini = get_abitudini_attive()
        oggi = now.strftime("%A %d %B %Y")
        try:
            msg = gemini_ask(f"Sei un assistente personale motivante. Oggi è {oggi}. "
                           f"Attività da fare: {', '.join([a['nome'] for a in attivita[:5]]) or 'nessuna'}. "
                           f"Abitudini di oggi: {', '.join([a['nome'] for a in abitudini]) or 'nessuna'}. "
                           f"Scrivi un messaggio mattutino breve (max 5 righe) in italiano con emoji.")
        except:
            msg = f"🌅 Buongiorno! Hai {len(attivita)} attività e {len(abitudini)} abitudini oggi. Forza! 💪"
        telegram_send(msg, chat_id)

    spotify_orari = {k: v for k, v in settings.items() if k.startswith("orario_musica")}
    for chiave, orario_spotify in spotify_orari.items():
        if ora == orario_spotify:
            testo = "🎵 Pausa musicale del pomeriggio! 🎶" if "pomeriggio" in chiave else "🎵 Buongiorno con la musica! 🎶"
            invia_spotify(settings, chat_id, testo)

    if ora == settings.get("orario_lettura", "21:00"):
        telegram_send("📚 Hai letto le tue 25 pagine oggi? Prenditi 30 minuti prima di dormire!", chat_id)

    if ora == settings.get("orario_recap_serale", "22:30"):
        attivita = get_attivita_aperte()
        try:
            msg = gemini_ask(f"Scrivi un recap serale breve (max 5 righe) in italiano. "
                           f"Attività ancora aperte: {len(attivita)}. Sii onesto ma incoraggiante. Usa emoji.")
        except:
            msg = f"🌙 Giornata finita! Hai ancora {len(attivita)} attività aperte."
        telegram_send(msg, chat_id)

    reminder_orari = {k: v for k, v in settings.items() if k.startswith("orario_reminder_")}
    for chiave, orario_reminder in reminder_orari.items():
        if ora == orario_reminder:
            nome = chiave.replace("orario_reminder_", "")
            testo = settings.get(f"testo_reminder_{nome}", f"🔔 Reminder: {nome}")
            telegram_send(testo, chat_id)


class handler(BaseHTTPRequestHandler):

    def do_POST(self):
        try:
            path = self.path
            content_length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_length)

            if "cron=1" in path:
                handle_scheduler()
                self._respond(200, "ok")
                return

            body = json.loads(raw_body) if raw_body else {}

            if "callback_query" in body:
                cq = body["callback_query"]
                handle_callback(cq["id"], cq["data"], str(cq["from"]["id"]))
            elif "message" in body:
                msg = body["message"]
                chat_id = str(msg["chat"]["id"])
                text = msg.get("text", "")
                if text.startswith("/start"):
                    cmd_start(chat_id)
                elif text.startswith("/"):
                    handle_text(text.replace("/", "").split()[0], chat_id)
                else:
                    handle_text(text, chat_id)

            self._respond(200, "ok")

        except Exception as e:
            print(f"Error: {e}")
            self._respond(500, str(e))

    def do_GET(self):
        self._respond(200, "AllaRound Bot is running!")

    def _respond(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, format, *args):
        pass
