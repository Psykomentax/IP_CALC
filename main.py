import random
import ipaddress
import secrets
from dataclasses import dataclass

from fastapi import FastAPI, Request, Cookie
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# --- Stockage session en mémoire (OK pour un seul serveur/worker).
# Pour plusieurs workers ou redémarrages: Redis.
SESSIONS = {}  # sid -> dict(score_total, total_possible, current_quiz)

@dataclass
class QuizState:
    base_ip: ipaddress.IPv4Address
    network: ipaddress.IPv4Network
    questions: list  # [(label, answer_str), ...]


# --- Logique réseau (reprend ton code, sans Tkinter) ---
def generer_ip():
    while True:
        classe = random.choice(["A", "B", "C"])
        if classe == "A":
            first = random.randint(1, 126)
            base = 8
            octets = [first, random.randint(0, 255), random.randint(0, 255), random.randint(1, 254)]
        elif classe == "B":
            first = random.randint(128, 191)
            base = 16
            octets = [first, random.randint(0, 255), random.randint(0, 255), random.randint(1, 254)]
        else:
            first = random.randint(192, 223)
            base = 24
            octets = [first, random.randint(0, 255), random.randint(0, 255), random.randint(1, 254)]

        addr = ipaddress.IPv4Address("{}.{}.{}.{}".format(*octets))
        prefix = random.randint(base, 30)
        network = ipaddress.IPv4Network((addr, prefix), strict=False)

        if addr == network.network_address or addr == network.broadcast_address:
            continue
        if network.num_addresses < 4:
            continue
        return addr, network


def nombre_sous_reseaux(ip_network: ipaddress.IPv4Network):
    first_octet = int(str(ip_network.network_address).split('.')[0])
    if first_octet < 128:
        base = 8
    elif first_octet < 192:
        base = 16
    else:
        base = 24
    return 2 ** (ip_network.prefixlen - base) if ip_network.prefixlen > base else 1


def generer_questions(base_ip: ipaddress.IPv4Address, net: ipaddress.IPv4Network):
    reseau = net.network_address
    broadcast = net.broadcast_address
    nb_adresses = net.num_addresses
    nb_exploitables = max(0, nb_adresses - 2)
    sous_reseaux_possibles = nombre_sous_reseaux(net)

    return [
        ("Adresse réseau du sous-réseau", str(reseau)),
        ("Adresse de broadcast du sous-réseau", str(broadcast)),
        ("Nombre de sous-réseaux possibles", str(sous_reseaux_possibles)),
        ("Nombre d'IP exploitables dans le sous-réseau", str(nb_exploitables)),
    ]


def generer_explicatif(base_ip: ipaddress.IPv4Address, net: ipaddress.IPv4Network):
    reseau = net.network_address
    broadcast = net.broadcast_address
    prefix = net.prefixlen
    nb_adresses = net.num_addresses
    nb_exploitables = max(0, nb_adresses - 2)
    sous_reseaux_possibles = nombre_sous_reseaux(net)
    first_octet = int(str(net.network_address).split('.')[0])

    if first_octet < 128:
        base = 8
        classe = "A"
    elif first_octet < 192:
        base = 16
        classe = "B"
    else:
        base = 24
        classe = "C"

    bits_empruntes = prefix - base if prefix > base else 0

    return f"""--- Correction détaillée ---
Adresse IP analysée : {base_ip}/{prefix}
Réseau calculé      : {net.network_address}/{prefix}
Classe d'origine    : Classe {classe} (masque par défaut /{base})

1. Adresse réseau :
   L’adresse réseau correspond à l’adresse la plus basse du sous-réseau.
   → Résultat : {reseau}

2. Adresse de broadcast :
   L’adresse de broadcast correspond à la plus haute adresse du sous-réseau.
   → Résultat : {broadcast}

3. Nombre de sous-réseaux possibles :
   Si le masque est plus grand que celui par défaut de la classe, on a 2^(bits empruntés).
   → Bits empruntés : {bits_empruntes}
   → Résultat : {sous_reseaux_possibles} sous-réseau(x)

4. Nombre d’adresses IP exploitables :
   Total d’adresses : {nb_adresses}
   On retire 2 (adresse réseau + broadcast) → {nb_exploitables}
"""


def get_or_create_session(sid: str | None):
    if sid and sid in SESSIONS:
        return sid, SESSIONS[sid]

    sid = secrets.token_urlsafe(24)
    SESSIONS[sid] = {
        "score_total": 0.0,
        "total_possible": 0,
        "current_quiz": None,
    }
    return sid, SESSIONS[sid]


def new_quiz_for(session: dict) -> QuizState:
    base_ip, net = generer_ip()
    questions = generer_questions(base_ip, net)
    quiz = QuizState(base_ip=base_ip, network=net, questions=questions)
    session["current_quiz"] = quiz
    return quiz


@app.get("/", response_class=HTMLResponse)
def index(request: Request, sid: str | None = Cookie(default=None)):
    sid, session = get_or_create_session(sid)
    resp = templates.TemplateResponse("index.html", {"request": request})
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp


@app.post("/api/new")
def api_new(sid: str | None = Cookie(default=None)):
    sid, session = get_or_create_session(sid)
    quiz = new_quiz_for(session)

    payload = {
        "ip": f"{quiz.base_ip}/{quiz.network.prefixlen}",
        "questions": [q[0] for q in quiz.questions],
        "score_total": session["score_total"],
        "total_possible": session["total_possible"],
    }
    resp = JSONResponse(payload)
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp

@app.post("/api/reset")
def api_reset(sid: str | None = Cookie(default=None)):
    sid, session = get_or_create_session(sid)

    session["score_total"] = 0.0
    session["total_possible"] = 0
    session["current_quiz"] = None  # optionnel, mais propre

    payload = {
        "score_total": session["score_total"],
        "total_possible": session["total_possible"],
    }
    resp = JSONResponse(payload)
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp

@app.post("/api/check")
async def api_check(request: Request, sid: str | None = Cookie(default=None)):
    sid, session = get_or_create_session(sid)
    quiz: QuizState | None = session.get("current_quiz")

    if quiz is None:
        return JSONResponse({"error": "Aucun quiz en cours. Clique sur Nouvelle IP."}, status_code=400)

    data = await request.json()
    answers = data.get("answers", [])
    if not isinstance(answers, list) or len(answers) != 4:
        return JSONResponse({"error": "Format de réponses invalide."}, status_code=400)

    points = 0.0
    results = []
    texte_correction = f"Résultats pour {quiz.base_ip}/{quiz.network.prefixlen}\n\n"

    for i, (question, expected) in enumerate(quiz.questions):
        user_rep = str(answers[i]).strip()
        correct = False

        if "adresse" in question.lower():
            try:
                correct = ipaddress.ip_address(user_rep) == ipaddress.ip_address(expected)
            except ValueError:
                correct = False
        else:
            try:
                correct = int(user_rep) == int(expected)
            except Exception:
                correct = (user_rep == expected)

        if correct:
            points += 0.25
            texte_correction += f"{question} : ✔ Bonne réponse ({expected})\n"
        else:
            texte_correction += f"{question} : ✖ Mauvaise réponse ({user_rep}) — Réponse correcte : {expected}\n"

        results.append({
            "question": question,
            "expected": expected,
            "given": user_rep,
            "correct": correct,
        })

    session["score_total"] += points
    session["total_possible"] += 1

    explanation = generer_explicatif(quiz.base_ip, quiz.network)
    resp_payload = {
        "points": round(points, 2),
        "results": results,
        "score_total": round(session["score_total"], 2),
        "total_possible": session["total_possible"],
        "correction_text": texte_correction,
        "explanation": explanation,
    }
    resp = JSONResponse(resp_payload)
    resp.set_cookie("sid", sid, httponly=True, samesite="lax")
    return resp

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
