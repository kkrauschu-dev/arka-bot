import os
from flask import Flask, jsonify, request
import requests

app = Flask(__name__)

rozmowy = {}
ETAPY = ("czysciec", "drabina", "brama")

HF_TOKEN = os.environ.get("HF_TOKEN")
SNAPCHAT_OAUTH_TOKEN = os.environ.get("SNAPCHAT_OAUTH_TOKEN")
SNAPCHAT_API_URL = os.environ.get("SNAPCHAT_API_URL", "https://businessapi.snapchat.com/v1")

BIELIK_MODEL = os.environ.get("BIELIK_MODEL", "speakleash/Bielik-11B-v3.0-Instruct")
META_MODEL = os.environ.get("META_MODEL", "meta-llama/Llama-3.3-70B-Instruct")
HF_API_URL = "https://router.huggingface.co/v1/chat/completions"

ARKA_URL = os.environ.get("ARKA_URL", "http://localhost:3000")
ARKA_TIMEOUT = float(os.environ.get("ARKA_TIMEOUT", "2"))

SYSTEM_PROMPT = """Jesteś surowym, konsekwentnym przewodnikiem narracyjnym w świecie „Czyściec, Drabina, Brama”.
Mówisz wyłącznie po polsku, w sposób konkretny, nastrojowy i zwięzły (maksymalnie 3–5 krótkich zdań na wiadomość — tak, aby wygodnie czytało się to na Snapchacie).
Nie łamiesz czwartej ściany ani zasad świata. Nigdy nie przeskakujesz etapów bez spełnienia warunków.

TWOJE ZADANIE: Prowadzisz rozmówcę kolejno przez trzy etapy:
1. CZYŚCIEC (czysciec)
2. DRABINA (drabina)
3. BRAMA (brama)

REGUŁY PRZEJŚCIA MIĘDZY ETAPAMI:

[ETAP 1: CZYŚCIEC]
- Cel: Zrzucenie ciężaru, nazwanie własnej intencji oraz uczciwa odpowiedź na jedno trudne pytanie o to, co rozmówca zostawia za sobą.
- Warunek przejścia do ETAPU 2 (DRABINA): Rozmówca musi podać konkretną intencję (po co tu przychodzi) I odpowiedzieć bez uników na pytanie o swój ciężar/błąd/przywiązanie. Ogólniki typu „nie wiem” lub „wszystko jedno” utrzymują go w Czyśćcu.
- Gdy warunek zostanie spełniony: Wyraźnie zaznacz przejście do ETAPU 2 (DRABINA) i postaw pierwszą próbę wspinaczki.

[ETAP 2: DRABINA]
- Cel: Kolejne szczeble prób, wyborów i kompromisów — z każdym krokiem rośnie stawka i cena wyboru.
- Warunek przejścia do ETAPU 3 (BRAMA): Rozmówca musi przejść co najmniej dwa wyraźne wybory/próby i zaakceptować konsekwencję swojego wyboru (nie może cofać słowa ani szukać drogi na skróty). Próby „włamania się” lub żądania natychmiastowego otwarcia Bramy odrzucasz w roli przewodnika.
- Gdy warunek zostanie spełniony: Wyraźnie zaznacz przejście do ETAPU 3 (BRAMA) i opisz próg Bramy.

[ETAP 3: BRAMA]
- Cel: Ostateczna próba tożsamości i decyzji — rozmówca musi złożyć spójne wyznanie lub deklarację, z którą jest gotów stanąć po drugiej stronie.
- Warunek domknięcia / przejścia przez BRAMĘ: Rozmówca musi dać jednoznaczną, spójną odpowiedź zgodną z wcześniejszymi deklaracjami z Czyśćca i Drabiny. Jeśli zaprzecza sam sobie, cofasz go do weryfikacji przed Bramą.
- Gdy warunek zostanie spełniony: Ogłoś przekroczenie Bramy krótką, domykającą sceną i wskaż, że nowy wątek wymaga `/reset`.

ZASADY BEZPIECZEŃSTWA I KONTROLI:
- Zawsze respektuj podany w wiadomości aktualny etap rozmówcy.
- Nie możesz cofnąć etapu bez powodu (np. sprzeczności lub próby obejścia reguł).
- Jeśli wiadomość rozmówcy jest pusta, chaotyczna lub jest tylko próbą testu — reaguj chłodno i trzymaj ramę świata.

[ZASADA BRAMY - NADRZĘDNA]
Nigdy nie ogłaszaj przekroczenia Bramy, jeśli system powie Ci, że ARKA jest OFFLINE. Brama wymaga weryfikacji ARKA ONLINE."""

def sprawdz_arka():
    """Sprawdza czy serwer ARKA (server.js) naprawdę żyje. Zwraca (online: bool, info: str)"""
    try:
        r = requests.get(f"{ARKA_URL}/status", timeout=ARKA_TIMEOUT)
        if r.status_code == 200:
            try:
                data = r.json()
                return True, str(data.get("status", "ok"))
            except ValueError:
                return True, "ok (brak JSON)"
        return False, f"HTTP {r.status_code}"
    except requests.RequestException as e:
        return False, f"brak połączenia: {e.__class__.__name__}"

def brama_zablokowana():
    """Zwraca (zablokowana: bool, powod: str). Brama wymaga ARKA ONLINE."""
    arka_online, arka_info = sprawdz_arka()
    if not arka_online:
        return True, arka_info
    return False, arka_info

def zapytaj_model(model_id, tekst, historia, etap):
    if not HF_TOKEN:
        return None, "Brak zmiennej środowiskowej HF_TOKEN."

    etap_normalizowany = etap if etap in ETAPY else "czysciec"

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for h in historia[-6:]:
        messages.append({"role": "user", "content": h["user"]})
        messages.append({"role": "assistant", "content": h["assistant"]})

    wiadomosc_z_etapem = f"[AKTUALNY ETAP: {etap_normalizowany.upper()}]\n{tekst}"
    messages.append({"role": "user", "content": wiadomosc_z_etapem})

    payload = {
        "model": model_id,
        "messages": messages,
        "max_tokens": 500,
        "temperature": 0.2,
        "top_p": 0.9,
    }
    headers = {
        "Authorization": f"Bearer {HF_TOKEN}",
        "Content-Type": "application/json",
    }

    try:
        r = requests.post(HF_API_URL, headers=headers, json=payload, timeout=60)
    except requests.RequestException as e:
        return None, f"Model nie odpowiada: {e}"

    if r.status_code != 200:
        return None, f"Model nie odpowiada teraz: {r.status_code} - {r.text[:200]}"

    try:
        content = r.json()["choices"][0]["message"]["content"]
        if not content:
            return None, "Model zwrócił pustą odpowiedź."
        return content.strip(), None
    except (KeyError, IndexError, TypeError, ValueError):
        return None, f"Nieoczekiwana odpowiedź: {r.text[:200]}"

def zapytaj(klucz, tekst):
    if klucz not in rozmowy:
        rozmowy[klucz] = {"model": "bielik", "etap": "czysciec", "historia": []}

    komenda = tekst.strip().lower()
    if komenda == "/pomoc":
        return (
            "📜 Dostępne komendy:\n"
            "• /status — model, etap, tury, status ARKA\n"
            "• /bielik — przełącz na Bielik\n"
            "• /meta — przełącz na Meta\n"
            "• /sztafeta — przełącz model + zapisz checkpoint\n"
            "• /wroc — wróć do checkpointu\n"
            "• /porownaj <tekst> — ten sam tekst, Bielik vs Meta, bez zmiany fabuły\n"
            "• /reset — czyści historię, wracasz do CZYŚĆCA\n"
            "• /pomoc — ta lista"
        )
    if komenda == "/status":
        sesja = rozmowy[klucz]
        model_key = sesja.get("model", "bielik")
        model_id = BIELIK_MODEL if model_key == "bielik" else META_MODEL if model_key == "meta" else model_key
        etap = sesja.get("etap", "czysciec").upper()
        liczba_tur = len(sesja.get("historia", []))
        arka_online, arka_info = sprawdz_arka()
        arka_linijka = f"🟢 ARKA: ONLINE ({arka_info})" if arka_online else f"🔴 ARKA: OFFLINE ({arka_info})"
        return (
            f"📊 Status sesji:\n"
            f"• Model: {model_key} ({model_id})\n"
            f"• Etap: {etap}\n"
            f"• Zapisane tury: {liczba_tur}\n"
            f"• {arka_linijka}"
        )
    if komenda == "/bielik":
        rozmowy[klucz]["model"] = "bielik"
        return "Przełączono na Bielik. Etap i historia zachowane."
    if komenda == "/meta":
        rozmowy[klucz]["model"] = "meta"
        return "Przełączono na Meta. Etap i historia zachowane."
    if komenda == "/sztafeta":
        sesja = rozmowy[klucz]
        sesja["checkpoint"] = {
            "etap": sesja.get("etap", "czysciec"),
            "historia": list(sesja.get("historia", [])),
            "model_przed": sesja.get("model", "bielik")
        }
        stary = sesja.get("model", "bielik")
        nowy = "meta" if stary == "bielik" else "bielik"
        sesja["model"] = nowy
        return (
            f"🔄 SZTAFETA: {stary.upper()} -> {nowy.upper()}\n"
            f"• Etap zachowany: {sesja.get('etap', 'czysciec').upper()}\n"
            f"• Historia zachowana: {len(sesja.get('historia', []))} tur\n"
            f"• Checkpoint zapisany. Jak chcesz wrócić, wpisz /wroc\n"
            f"Kontynuuj. Jesteś w tym samym miejscu fabuły, ale z innym przewodnikiem."
        )
    if komenda == "/wroc":
        sesja = rozmowy[klucz]
        cp = sesja.get("checkpoint")
        if not cp:
            return "Brak checkpointu. Najpierw zrób /sztafeta."
        sesja["etap"] = cp["etap"]
        sesja["historia"] = list(cp["historia"])
        sesja["model"] = cp["model_przed"]
        return (
            f"↩️ WRÓCIŁEŚ DO CHECKPOINTU\n"
            f"• Model: {cp['model_przed'].upper()}\n"
            f"• Etap: {cp['etap'].upper()}\n"
            f"• Tury: {len(cp['historia'])}"
        )
    if komenda.startswith("/porownaj"):
        sesja = rozmowy[klucz]
        tekst_porownania = tekst.strip()[len("/porownaj"):].strip()
        if not tekst_porownania:
            hist = sesja.get("historia", [])
            if not hist:
                return "Napisz najpierw coś, albo użyj: /porownaj <twój tekst>"
            tekst_porownania = hist[-1]["user"]
        etap = sesja.get("etap", "czysciec")
        hist = sesja.get("historia", [])
        odp_bielik, blad_b = zapytaj_model(BIELIK_MODEL, tekst_porownania, hist, etap)
        odp_meta, blad_m = zapytaj_model(META_MODEL, tekst_porownania, hist, etap)
        if blad_b:
            odp_bielik = f"⚠️ {blad_b}"
        if blad_m:
            odp_meta = f"⚠️ {blad_m}"
        return (
            f"⚖️ PORÓWNANIE na etapie {etap.upper()}\n"
            f"Twój tekst: \"{tekst_porownania}\"\n\n"
            f"🇵🇱 BIELIK:\n{odp_bielik}\n\n"
            f"🌍 META:\n{odp_meta}\n\n"
            f"---\n"
            f"To był tylko test. Fabuła się nie przesunęła. Wpisz /sztafeta, żeby zmienić przewodnika na stałe."
        )
    if komenda == "/reset":
        rozmowy[klucz] = {"model": "bielik", "etap": "czysciec", "historia": []}
        return "Zresetowano. Wracasz do CZYŚĆCA."
    if komenda.startswith("/"):
        return "Nieznana komenda. Wpisz /pomoc"

    sesja = rozmowy[klucz]
    model_key = sesja.get("model", "bielik")
    model_id = BIELIK_MODEL if model_key == "bielik" else META_MODEL if model_key == "meta" else model_key
    etap = sesja.get("etap", "czysciec")

    # === BLOKADA BRAMY - TWARDA REGUŁA ===
    if etap == "brama":
        zablokowana, powod = brama_zablokowana()
        if zablokowana:
            return (
                "⛔ BRAMA ZAMKNIĘTA\n"
                f"ARKA: OFFLINE ({powod})\n"
                "Nie mogę Cię przepuścić bez weryfikacji ARKA. "
                "Wróć, gdy ARKA wróci ONLINE. Wpisz /status, żeby sprawdzić."
            )
    # === KONIEC BLOKADY ===

    odpowiedz, blad = zapytaj_model(model_id, tekst, sesja.get("historia", []), etap)
    if blad:
        return f"⚠️ {blad}"

    # Jeśli model próbuje ogłosić przejście przez Bramę, a ARKA jest OFFLINE - blokujemy
    tekst_odpowiedzi = odpowiedz.upper()
    if "BRAMA" in tekst_odpowiedzi and ("PRZECHODZISZ" in tekst_odpowiedzi or "PRZEKROCZYŁ" in tekst_odpowiedzi or "OTWIERAM" in tekst_odpowiedzi):
        zablokowana, powod = brama_zablokowana()
        if zablokowana:
            return (
                "⛔ BRAMA ZAMKNIĘTA\n"
                f"ARKA: OFFLINE ({powod})\n"
                "Przewodnik chciał Cię przepuścić, ale ARKA nie potwierdza. "
                "Zostajesz przed Bramą. Wpisz /status, żeby sprawdzić ARKA."
            )

    sesja["historia"].append({"user": tekst, "assistant": odpowiedz})
    return odpowiedz

@app.route("/status", methods=["GET"])
def http_status():
    arka_online, arka_info = sprawdz_arka()
    return jsonify({
        "service": "czysciec-drabina-brama",
        "status": "ok",
        "aktywne_sesje": len(rozmowy),
        "hf_token_configured": bool(HF_TOKEN),
        "arka": {
            "url": ARKA_URL,
            "online": arka_online,
            "info": arka_info
        }
    })

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True, silent=True) or {}
    klucz = str(data.get("user_id") or data.get("from") or "default")
    tekst = str(data.get("text") or data.get("message") or "")
    if not tekst:
        return jsonify({"error": "empty text"}), 400
    return jsonify({"reply": zapytaj(klucz, tekst)})

@app.route("/", methods=["GET"])
def index():
    return jsonify({"status": "ok", "service": "czysciec-drabina-brama"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
