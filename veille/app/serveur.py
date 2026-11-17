"""Le logiciel « Veille consoles » : un petit serveur local + une interface web.

L'interface s'ouvre dans sa propre fenêtre (Edge ou Chrome en « mode application »).
Rien n'est accessible depuis l'extérieur, sauf si tu actives l'accès téléphone
(même Wi-Fi uniquement, protégé par une clé secrète).
"""
import contextlib
import io
import json
import logging
import mimetypes
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import webbrowser
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

from .. import synchro
from ..affichage import sans_couleur
from ..config import ErreurConfig, Recherche, charger_config, charger_watchlist
from ..outils import RACINE, ecrire_env
from ..prix import conseils, medianes_par_jour, statistiques
from . import watchlist_edit

log = logging.getLogger("veille")

STATIQUE = Path(__file__).parent / "static"
DOSSIER_LOCAL = RACINE / ".local-data"
PORT = 8765
PORT_TELEPHONE = 8766
DELAI_SANS_FENETRE = 150  # secondes sans signe de vie (fenêtre réduite : le navigateur ralentit les pings)


# ───────────────────────── état du logiciel ─────────────────────────

class Etat:
    def __init__(self):
        self.jeton = secrets.token_urlsafe(24)
        self.dernier_ping = time.time()
        self.tache: dict | None = None
        self.verrou = threading.Lock()
        self.telegram_jeton_attente = ""
        self.synchro_demarrage = "en_cours"
        self.serveur_tel: ThreadingHTTPServer | None = None
        self.arret = threading.Event()


ETAT = Etat()


def _actif(cle: str) -> bool:
    return bool(os.environ.get(cle, "").strip())


def capturer(fn, *args, **kwargs):
    """Lance une fonction qui écrit dans le terminal et récupère son texte."""
    tampon = io.StringIO()
    with contextlib.redirect_stdout(tampon):
        resultat = fn(*args, **kwargs)
    lignes = [sans_couleur(l).strip() for l in tampon.getvalue().splitlines()]
    return resultat, [l for l in lignes if l]


def _lire_json(chemin: Path, defaut):
    try:
        return json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return defaut


def annonce_dict(a) -> dict:
    return {"uid": a.uid, "source": a.source, "recherche": a.recherche, "titre": a.titre,
            "prix_total": a.prix_total, "prix": a.prix, "port": a.port, "port_estime": a.port_estime,
            "url": a.url, "photo": a.photo, "etat": a.etat, "indice_etat": a.indice_etat,
            "analyse": a.analyse, "localisation": a.localisation, "enchere": a.enchere}


# ───────────────────────── tâches longues (veille, démo) ─────────────────────────

class CaptureLogs(logging.Handler):
    def __init__(self, tache):
        super().__init__(logging.INFO)
        self.tache = tache

    def emit(self, r):
        self.tache["logs"].append({"niveau": r.levelname.lower(), "texte": sans_couleur(r.getMessage()),
                                   "heure": time.strftime("%H:%M:%S")})


def lancer_tache(type_: str, fonction):
    with ETAT.verrou:
        if ETAT.tache and ETAT.tache["en_cours"]:
            raise ErreurConfig("Une veille est déjà en cours, patiente quelques secondes.")
        tache = {"id": uuid.uuid4().hex[:8], "type": type_, "en_cours": True, "logs": [], "alertes": [],
                 "messages": [], "bilan": None, "erreur": None, "debut": time.time()}
        ETAT.tache = tache

    def corps():
        gestion = CaptureLogs(tache)
        logging.getLogger("veille").addHandler(gestion)
        try:
            tache["bilan"] = fonction(tache)
        except Exception as e:  # on affiche l'erreur dans le logiciel
            log.exception("Erreur pendant la tâche")
            tache["erreur"] = str(e)
        finally:
            logging.getLogger("veille").removeHandler(gestion)
            tache["en_cours"] = False
            tache["duree"] = round(time.time() - tache["debut"], 1)

    threading.Thread(target=corps, daemon=True).start()
    return tache


def _telegram_collecte(tache):
    from ..telegram import Telegram

    class TelegramCollecte(Telegram):
        def annonce(self, annonce):
            tache["alertes"].append(annonce_dict(annonce))
            return True

        def texte(self, message_html):
            import html
            import re
            tache["messages"].append(html.unescape(re.sub(r"<[^>]+>", "", message_html)))
            return True

    return TelegramCollecte(simulation=True)


def tache_veille(tache):
    from ..main import executer
    return executer(simulation=True, dossier_data=DOSSIER_LOCAL, telegram=_telegram_collecte(tache))


def tache_demo(tache):
    from ..main import executer
    from ..sources.demo import DemoSource
    cfg = charger_config()
    recherches, _ = charger_watchlist()
    choix = [r for r in recherches if r.actif][:2]
    dossier = Path(tempfile.mkdtemp(prefix="veille-demo-"))
    tg = _telegram_collecte(tache)
    executer(dossier_data=dossier, sources=[DemoSource(cfg, tour=1)], telegram=tg, recherches=choix)
    tache["messages"].clear()  # le résumé de démarrage n'intéresse pas ici
    bilan = executer(dossier_data=dossier, sources=[DemoSource(cfg, tour=2)], telegram=tg, recherches=choix)
    shutil.rmtree(dossier, ignore_errors=True)
    return bilan


# ───────────────────────── données pour l'interface ─────────────────────────

def nom_depot() -> str:
    depot = synchro.adresse_github()
    return depot.rstrip("/").removesuffix(".git").split("github.com/")[-1] if depot else ""


def date_donnees_robot() -> str | None:
    if not synchro.adresse_github():
        return None
    r = synchro.git("log", "-1", "--format=%cI", "--", "data")
    return r.stdout.strip() or None


def api_resume(_):
    cfg = charger_config()
    try:
        recherches, _ = charger_watchlist()
        watchlist = {"actives": sum(r.actif for r in recherches), "total": len(recherches), "erreur": None}
    except ErreurConfig as e:
        watchlist = {"actives": 0, "total": 0, "erreur": str(e)}
    from ..sources import LIBELLES
    etat = _lire_json(RACINE / "data" / "etat.json", {})
    sante = etat.get("sante", {})
    sources = []
    for nom, actif in (cfg.get("sources") or {}).items():
        s = sante.get(nom, {})
        sources.append({"nom": nom, "libelle": LIBELLES.get(nom, nom), "actif": bool(actif),
                        "echecs": s.get("echecs", 0), "dernier_succes": s.get("dernier_succes"),
                        "message": s.get("dernier_message") or s.get("message")})
    alertes = _lire_json(RACINE / "data" / "alertes.json", [])
    alertes = sorted(alertes, key=lambda a: a.get("date_alerte", ""), reverse=True)[:60]
    depot = nom_depot()
    return {
        "comptes": {"telegram": _actif("TELEGRAM_TOKEN") and _actif("TELEGRAM_CHAT_ID"),
                    "ebay": _actif("EBAY_CLIENT_ID") and _actif("EBAY_CLIENT_SECRET"),
                    "gmail": _actif("GMAIL_ADRESSE") and _actif("GMAIL_MOT_DE_PASSE_APPLI"),
                    "gmail_adresse": os.environ.get("GMAIL_ADRESSE", "")},
        "github": {"depot": depot, "git": synchro.git_installe(),
                   "modifs": synchro.modifications_locales() if depot else [],
                   "synchro_demarrage": ETAT.synchro_demarrage},
        "watchlist": watchlist,
        "sources": sources,
        "alertes": alertes,
        "nb_vues": len(_lire_json(RACINE / "data" / "vues.json", {})),
        "maj_robot": date_donnees_robot(),
        "seuils": {k: cfg[k] for k in ("seuil_bonne_affaire_pct", "seuil_marge_eur", "seuil_marge_pct")},
        "telephone": url_telephone(),
        "windows": os.name == "nt",
    }


def api_prix(_):
    cfg = charger_config()
    recherches, _ = charger_watchlist()
    historique = _lire_json(RACINE / "data" / "prix.json", {})
    sortie = []
    for r in recherches:
        points = historique.get(r.nom, [])
        stats = statistiques(points)
        sortie.append({
            "nom": r.nom, "actif": r.actif, "mode": r.mode,
            "actuel": {"prix_max": r.prix_max, "prix_max_hs": r.prix_max_hs,
                       "prix_revente_ref": r.prix_revente_ref, "cout_pieces": r.cout_pieces},
            "stats": stats,
            "conseils": conseils(stats, r, cfg) if stats and stats["n"] >= cfg["echantillon_min"] else None,
            "points": [{"p": p["p"], "e": p.get("e", "inconnu"), "s": p.get("s", ""), "d": p.get("d", "")}
                       for p in points],
            "par_jour": medianes_par_jour(points),
        })
    return {"recherches": sortie, "echantillon_min": cfg["echantillon_min"]}


def api_prix_appliquer(corps):
    noms = corps.get("noms") or []
    donnees = {r["nom"]: r for r in api_prix(None)["recherches"]}
    faits = []
    for nom in noms:
        c = (donnees.get(nom) or {}).get("conseils")
        if c:
            watchlist_edit.modifier_champs(nom, {k: c[k] for k in ("prix_max", "prix_max_hs", "prix_revente_ref")
                                                 if c[k] is not None})
            faits.append(nom)
    return {"ok": True, "faits": faits}


def api_watchlist(_):
    recherches, exclusions = charger_watchlist()
    return {"recherches": [r.__dict__ for r in recherches], "exclusions": exclusions}


def api_watchlist_recherche(corps):
    watchlist_edit.enregistrer_recherche(corps.get("recherche") or {}, corps.get("ancien_nom"))
    return {"ok": True}


def api_watchlist_champs(corps):
    watchlist_edit.modifier_champs(corps["nom"], corps.get("champs") or {})
    return {"ok": True}


def api_watchlist_supprimer(corps):
    watchlist_edit.supprimer_recherche(corps["nom"])
    return {"ok": True}


def api_watchlist_exclusions(corps):
    watchlist_edit.enregistrer_exclusions(corps.get("mots") or [])
    return {"ok": True}


def api_sources(_):
    from ..sources import SOURCES
    cfg = charger_config()
    sortie = []
    for nom, cls in SOURCES.items():
        pret, raison = cls(cfg).prete()
        sortie.append({"nom": nom, "libelle": cls.libelle, "prete": pret, "raison": raison})
    return {"sources": sortie}


def api_tester(corps):
    from ..analyse import detecter_etat
    from ..sources import SOURCES
    nom = corps.get("source")
    if nom not in SOURCES:
        raise ErreurConfig("Choisis un site.")
    source = SOURCES[nom](charger_config())
    pret, raison = source.prete()
    if not pret:
        raise ErreurConfig(f"{source.libelle} n'est pas encore configuré ({raison}). Va dans « Comptes ».")
    requete = (corps.get("requete") or "").strip() or "psp 3000"
    annonces = source.chercher(Recherche(nom="test", requete=requete))
    sortie = []
    for a in annonces[:40]:
        a.etat, a.indice_etat = detecter_etat(a)
        sortie.append(annonce_dict(a))
    return {"annonces": sortie, "total": len(annonces)}


def api_lancer(corps):
    type_ = corps.get("type", "veille")
    tache = lancer_tache(type_, tache_demo if type_ == "demo" else tache_veille)
    return {"id": tache["id"]}


def api_tache(_):
    t = ETAT.tache
    if not t:
        return {"tache": None}
    return {"tache": {k: v for k, v in t.items()}}


# ───────────────────────── comptes ─────────────────────────

def _api_telegram(jeton: str, methode: str, **params) -> dict:
    try:
        return requests.get(f"https://api.telegram.org/bot{jeton}/{methode}", params=params, timeout=20).json()
    except (requests.RequestException, ValueError):
        return {"ok": False, "description": "impossible de joindre Telegram (connexion internet ?)"}


def api_telegram_jeton(corps):
    jeton = (corps.get("jeton") or "").strip()
    if not jeton:
        raise ErreurConfig("Colle le jeton donné par BotFather.")
    moi = _api_telegram(jeton, "getMe")
    if not moi.get("ok"):
        raise ErreurConfig(f"Telegram refuse ce jeton : {moi.get('description')}. Vérifie le copier-coller.")
    ETAT.telegram_jeton_attente = jeton
    return {"bot": moi["result"]["username"]}


def api_telegram_verifier(_):
    jeton = ETAT.telegram_jeton_attente
    if not jeton:
        raise ErreurConfig("Recommence à l'étape 1.")
    maj = _api_telegram(jeton, "getUpdates")
    chats = [(m.get("message") or {}).get("chat") for m in maj.get("result", [])]
    chats = [ch for ch in chats if ch and ch.get("type") == "private"]
    if not chats:
        raise ErreurConfig("Je ne vois pas encore ton message. Envoie « bonjour » à ton bot puis réessaie.")
    chat = chats[-1]
    ecrire_env({"TELEGRAM_TOKEN": jeton, "TELEGRAM_CHAT_ID": str(chat["id"])})
    ETAT.telegram_jeton_attente = ""
    test = _api_telegram(jeton, "sendMessage", chat_id=chat["id"],
                         text="👋 Bonjour ! Ton bot de veille consoles rétro est bien connecté. 🎮")
    return {"prenom": chat.get("first_name", ""), "test": bool(test.get("ok"))}


def api_telegram_test(_):
    if not (_actif("TELEGRAM_TOKEN") and _actif("TELEGRAM_CHAT_ID")):
        raise ErreurConfig("Telegram n'est pas encore configuré.")
    r = _api_telegram(os.environ["TELEGRAM_TOKEN"], "sendMessage", chat_id=os.environ["TELEGRAM_CHAT_ID"],
                      text="🎮 Message de test envoyé depuis le logiciel Veille consoles.")
    if not r.get("ok"):
        raise ErreurConfig(f"Envoi refusé : {r.get('description')}")
    return {"ok": True}


def api_ebay(corps):
    from ..sources.base import ErreurSource
    from ..sources.ebay import EbaySource
    client_id = (corps.get("client_id") or "").strip()
    secret = (corps.get("secret") or "").strip()
    if not client_id or not secret:
        if _actif("EBAY_CLIENT_ID") and _actif("EBAY_CLIENT_SECRET") and not client_id and not secret:
            client_id, secret = os.environ["EBAY_CLIENT_ID"], os.environ["EBAY_CLIENT_SECRET"]
        else:
            raise ErreurConfig("Remplis les deux champs (App ID et Cert ID).")
    anciens = {k: os.environ.get(k, "") for k in ("EBAY_CLIENT_ID", "EBAY_CLIENT_SECRET")}
    os.environ.update({"EBAY_CLIENT_ID": client_id, "EBAY_CLIENT_SECRET": secret})
    try:
        EbaySource(charger_config()).jeton()
        valide, message = True, ""
    except ErreurSource as e:
        valide, message = False, str(e)
    if valide or corps.get("forcer"):
        ecrire_env({"EBAY_CLIENT_ID": client_id, "EBAY_CLIENT_SECRET": secret})
    else:
        os.environ.update(anciens)
    return {"valide": valide, "message": message, "enregistre": valide or bool(corps.get("forcer"))}


def api_gmail(corps):
    from ..sources.base import ErreurSource
    from ..sources.email_leboncoin import LeboncoinEmailSource
    adresse = (corps.get("adresse") or os.environ.get("GMAIL_ADRESSE", "")).strip()
    code = (corps.get("code") or "").replace(" ", "").strip() or os.environ.get("GMAIL_MOT_DE_PASSE_APPLI", "")
    if not adresse or not code:
        raise ErreurConfig("Remplis l'adresse Gmail et le code de 16 lettres.")
    anciens = {k: os.environ.get(k, "") for k in ("GMAIL_ADRESSE", "GMAIL_MOT_DE_PASSE_APPLI")}
    os.environ.update({"GMAIL_ADRESSE": adresse, "GMAIL_MOT_DE_PASSE_APPLI": code})
    try:
        nb, annonces = LeboncoinEmailSource(charger_config()).lire_boite()
    except ErreurSource as e:
        os.environ.update(anciens)
        raise ErreurConfig(str(e))
    ecrire_env({"GMAIL_ADRESSE": adresse, "GMAIL_MOT_DE_PASSE_APPLI": code})
    return {"emails": nb, "annonces": [{"titre": a.titre, "prix": a.prix, "url": a.url} for a in annonces[:10]]}


# ───────────────────────── GitHub ─────────────────────────

def api_github_synchroniser(corps):
    if not synchro.adresse_github():
        raise ErreurConfig("Le projet n'est pas encore relié à GitHub.")
    if not synchro._identite_ok():
        raise ErreurConfig("Indique d'abord ton pseudo GitHub (Comptes → GitHub).")
    ok1, lignes = capturer(synchro.recuperer)
    if not ok1:
        return {"ok": False, "lignes": lignes}
    ok2, lignes2 = capturer(synchro.envoyer, (corps.get("message") or "").strip() or "Modifications depuis le logiciel")
    return {"ok": bool(ok2), "lignes": lignes + lignes2}


def api_github_identite(corps):
    pseudo = (corps.get("pseudo") or "").strip()
    if not pseudo:
        raise ErreurConfig("Indique ton pseudo GitHub.")
    email = (corps.get("email") or "").strip() or f"{pseudo}@users.noreply.github.com"
    synchro.git("config", "user.name", pseudo)
    synchro.git("config", "user.email", email)
    return {"ok": True}


def api_github_relier(corps):
    import re
    adresse = (corps.get("adresse") or "").strip()
    if not synchro.git_installe():
        raise ErreurConfig("Git n'est pas installé : https://git-scm.com/download/win (options par défaut).")
    if not re.match(r"^https://github\.com/[\w.-]+/[\w.-]+?(\.git)?/?$", adresse):
        raise ErreurConfig("Ça ne ressemble pas à une adresse de repo GitHub (https://github.com/pseudo/nom.git).")
    if corps.get("pseudo"):
        api_github_identite(corps)
    if not (RACINE / ".git").exists():
        synchro.git("init", "-b", "main")
    if synchro.adresse_github():
        synchro.git("remote", "set-url", "origin", adresse)
    else:
        synchro.git("remote", "add", "origin", adresse)
    synchro.git("add", "-A")
    if synchro.git("diff", "--cached", "--quiet").returncode != 0:
        synchro.git("commit", "-q", "-m", "Version initiale de la veille consoles")
    r = synchro.git("push", "-u", "origin", "main", timeout=600)
    if r.returncode != 0:
        raise ErreurConfig("L'envoi a échoué. Vérifie que le repo est vide et que tu es connecté au bon compte.")
    return {"ok": True}


def synchro_au_demarrage():
    try:
        if synchro.adresse_github():
            ok, _ = capturer(synchro.recuperer, silencieux=True)
            ETAT.synchro_demarrage = "ok" if ok else "echec"
        else:
            ETAT.synchro_demarrage = "non_relie"
    except Exception:
        ETAT.synchro_demarrage = "echec"


# ───────────────────────── accès téléphone ─────────────────────────

def ip_locale() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def url_telephone() -> dict:
    if not ETAT.serveur_tel:
        return {"actif": False}
    url = f"http://{ip_locale()}:{PORT_TELEPHONE}/?cle={ETAT.jeton}"
    import segno
    qr = segno.make(url, error="m").svg_inline(scale=5, dark="#e8e8ef", light=None, border=2)
    return {"actif": True, "url": url, "qr": qr}


def api_telephone(corps):
    if corps.get("actif") and not ETAT.serveur_tel:
        try:
            srv = ThreadingHTTPServer(("0.0.0.0", PORT_TELEPHONE), Gestionnaire)
        except OSError as e:
            raise ErreurConfig(f"Impossible d'ouvrir l'accès téléphone : {e}")
        srv.daemon_threads = True
        ETAT.serveur_tel = srv
        threading.Thread(target=srv.serve_forever, daemon=True).start()
    elif not corps.get("actif") and ETAT.serveur_tel:
        srv, ETAT.serveur_tel = ETAT.serveur_tel, None
        threading.Thread(target=srv.shutdown, daemon=True).start()
    return url_telephone()


def api_raccourci(_):
    from ..interface import creer_raccourci
    ok, lignes = capturer(creer_raccourci)
    if not ok:
        raise ErreurConfig(" ".join(lignes) or "Impossible de créer le raccourci.")
    return {"ok": True}


def api_quitter(_):
    ETAT.arret.set()
    return {"ok": True}


ROUTES_GET = {
    "/api/resume": api_resume, "/api/prix": api_prix, "/api/watchlist": api_watchlist,
    "/api/sources": api_sources, "/api/tache": api_tache,
}
ROUTES_POST = {
    "/api/prix/appliquer": api_prix_appliquer,
    "/api/watchlist/recherche": api_watchlist_recherche, "/api/watchlist/champs": api_watchlist_champs,
    "/api/watchlist/supprimer": api_watchlist_supprimer, "/api/watchlist/exclusions": api_watchlist_exclusions,
    "/api/tester": api_tester, "/api/lancer": api_lancer,
    "/api/comptes/telegram/jeton": api_telegram_jeton, "/api/comptes/telegram/verifier": api_telegram_verifier,
    "/api/comptes/telegram/test": api_telegram_test,
    "/api/comptes/ebay": api_ebay, "/api/comptes/gmail": api_gmail,
    "/api/github/synchroniser": api_github_synchroniser, "/api/github/identite": api_github_identite,
    "/api/github/relier": api_github_relier,
    "/api/telephone": api_telephone, "/api/raccourci": api_raccourci, "/api/quitter": api_quitter,
}


# ───────────────────────── serveur HTTP ─────────────────────────

class Gestionnaire(BaseHTTPRequestHandler):
    server_version = "VeilleConsoles"

    def log_message(self, *args):
        pass

    def _local(self) -> bool:
        return self.server.server_address[1] == PORT_LOCAL[0]

    def _hote_ok(self) -> bool:
        hote = (self.headers.get("Host") or "").rsplit(":", 1)[0]
        if self._local():
            return hote in ("127.0.0.1", "localhost")
        return True  # accès téléphone : protégé par la clé

    def _cle_ok(self) -> bool:
        if self._local():
            return True
        cookie = SimpleCookie(self.headers.get("Cookie") or "")
        return "veille" in cookie and secrets.compare_digest(cookie["veille"].value, ETAT.jeton)

    def _envoyer(self, code: int, corps: bytes, type_: str, entetes: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", type_)
        self.send_header("Content-Length", str(len(corps)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in (entetes or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(corps)

    def _json(self, code: int, donnees):
        self._envoyer(code, json.dumps(donnees, ensure_ascii=False, default=str).encode("utf-8"),
                      "application/json; charset=utf-8")

    def do_GET(self):
        if not self._hote_ok():
            return self._json(403, {"erreur": "accès refusé"})
        url = urlparse(self.path)
        if url.path in ("/", "/index.html"):
            entetes = {}
            cle = parse_qs(url.query).get("cle", [""])[0]
            if not self._local() and cle and secrets.compare_digest(cle, ETAT.jeton):
                entetes["Set-Cookie"] = f"veille={ETAT.jeton}; HttpOnly; SameSite=Strict; Max-Age=31536000; Path=/"
            elif not self._cle_ok():
                return self._envoyer(403, "Accès refusé : scanne le QR code affiché sur ton PC.".encode(),
                                     "text/plain; charset=utf-8")
            page = (STATIQUE / "index.html").read_text(encoding="utf-8").replace("{{JETON}}", ETAT.jeton)
            return self._envoyer(200, page.encode("utf-8"), "text/html; charset=utf-8", entetes)
        if url.path.startswith("/static/"):
            chemin = (STATIQUE / url.path.removeprefix("/static/")).resolve()
            if STATIQUE.resolve() in chemin.parents and chemin.is_file():
                type_ = mimetypes.guess_type(chemin.name)[0] or "application/octet-stream"
                if type_.startswith("text/") or type_ == "application/javascript":
                    type_ += "; charset=utf-8"
                return self._envoyer(200, chemin.read_bytes(), type_)
            return self._json(404, {"erreur": "introuvable"})
        if url.path == "/favicon.ico":
            return self._envoyer(200, (RACINE / "assets" / "veille.ico").read_bytes(), "image/x-icon")
        if url.path == "/api/ping":
            if self._local():
                ETAT.dernier_ping = time.time()
            return self._json(200, {"app": "veille-consoles"})
        self._api(ROUTES_GET, {})

    def do_POST(self):
        if not self._hote_ok():
            return self._json(403, {"erreur": "accès refusé"})
        try:
            taille = int(self.headers.get("Content-Length") or 0)
            corps = json.loads(self.rfile.read(min(taille, 1_000_000)) or b"{}")
        except ValueError:
            return self._json(400, {"erreur": "requête illisible"})
        self._api(ROUTES_POST, corps if isinstance(corps, dict) else {})

    def _api(self, routes, corps):
        chemin = urlparse(self.path).path
        fonction = routes.get(chemin)
        if not fonction:
            return self._json(404, {"erreur": "introuvable"})
        # Un site web malveillant ne peut pas ajouter cet en-tête : protège contre les requêtes forcées.
        if not secrets.compare_digest(self.headers.get("X-Veille-Jeton", ""), ETAT.jeton) or not self._cle_ok():
            return self._json(403, {"erreur": "accès refusé"})
        if chemin in ("/api/telephone", "/api/quitter", "/api/raccourci") and not self._local():
            return self._json(403, {"erreur": "à faire depuis le PC"})
        try:
            self._json(200, fonction(corps))
        except ErreurConfig as e:
            self._json(400, {"erreur": str(e)})
        except requests.RequestException as e:
            self._json(502, {"erreur": f"Problème de connexion : {e}"})
        except Exception as e:
            log.exception("Erreur dans %s", chemin)
            self._json(500, {"erreur": f"Erreur inattendue : {e}"})


PORT_LOCAL = [PORT]


# ───────────────────────── fenêtre ─────────────────────────

def _navigateurs_windows() -> list[str]:
    bases = [os.environ.get(k, "") for k in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA")]
    relatifs = [r"Microsoft\Edge\Application\msedge.exe", r"Google\Chrome\Application\chrome.exe"]
    return [str(Path(b) / r) for r in relatifs for b in bases if b and (Path(b) / r).exists()]


def _navigateurs_unix() -> list[str]:
    noms = ["microsoft-edge", "google-chrome", "chromium", "chromium-browser"]
    mac = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
           "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"]
    return [p for p in (shutil.which(n) for n in noms) if p] + [m for m in mac if Path(m).exists()]


def ouvrir_fenetre(url: str):
    candidats = _navigateurs_windows() if os.name == "nt" else _navigateurs_unix()
    profil = DOSSIER_LOCAL / "fenetre"
    profil.mkdir(parents=True, exist_ok=True)
    for exe in candidats:
        try:
            subprocess.Popen([exe, f"--app={url}", "--window-size=1320,860", f"--user-data-dir={profil}",
                              "--no-first-run", "--no-default-browser-check"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except OSError:
            continue
    webbrowser.open(url)


def deja_lance(port: int) -> bool:
    try:
        r = requests.get(f"http://127.0.0.1:{port}/api/ping", timeout=1.5)
        return r.json().get("app") == "veille-consoles"
    except (requests.RequestException, ValueError):
        return False


def _rediriger_sorties():
    """Sans console (pythonw), on écrit les messages dans un fichier."""
    DOSSIER_LOCAL.mkdir(parents=True, exist_ok=True)
    if sys.stdout is None or sys.stderr is None or not sys.stdout.isatty():
        journal = open(DOSSIER_LOCAL / "logiciel.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = journal
        for h in logging.getLogger().handlers:
            if isinstance(h, logging.StreamHandler):
                h.setStream(journal)


def lancer(ouvrir: bool = True, port: int = PORT):
    _rediriger_sorties()
    if deja_lance(port):
        if ouvrir:
            ouvrir_fenetre(f"http://127.0.0.1:{port}/")
        return
    try:
        serveur = ThreadingHTTPServer(("127.0.0.1", port), Gestionnaire)
    except OSError:
        serveur = ThreadingHTTPServer(("127.0.0.1", 0), Gestionnaire)
    serveur.daemon_threads = True
    PORT_LOCAL[0] = serveur.server_address[1]
    url = f"http://127.0.0.1:{PORT_LOCAL[0]}/"
    print(f"Logiciel prêt : {url}")
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    threading.Thread(target=synchro_au_demarrage, daemon=True).start()
    if ouvrir:
        ouvrir_fenetre(url)
    ETAT.dernier_ping = time.time() + 30  # laisse le temps à la fenêtre de s'ouvrir
    try:
        while not ETAT.arret.wait(5):
            fenetre_fermee = time.time() - ETAT.dernier_ping > DELAI_SANS_FENETRE
            if ouvrir and fenetre_fermee and not ETAT.serveur_tel:
                break
    except KeyboardInterrupt:
        pass
    serveur.shutdown()
    if ETAT.serveur_tel:
        ETAT.serveur_tel.shutdown()
