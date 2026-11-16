"""Leboncoin via les alertes e-mail (fonctionne depuis le cloud).

Principe : sur Leboncoin, tu enregistres tes recherches avec l'alerte e-mail activée.
Les e-mails arrivent dans une boîte Gmail ; l'outil les lit (sans les modifier),
extrait les annonces et les passe dans les mêmes filtres que les autres sites.

Une seule lecture de la boîte par exécution : les annonces trouvées sont ensuite
comparées à chaque recherche de la watchlist (mots-clés, prix, état).
"""
import email
import html
import imaplib
import logging
import os
import re
import socket
from datetime import date, timedelta
from email.message import Message
from urllib.parse import unquote

from ..modeles import Annonce
from .base import ErreurSource, Source

log = logging.getLogger("veille")

MOIS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
RE_LIEN = re.compile(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S | re.I)
RE_ID = re.compile(r"leboncoin\.fr/(?:ad/)?[a-z_]+/(\d{8,12})", re.I)
RE_PRIX = re.compile(r"(\d{1,3}(?:[   .]\d{3})*(?:,\d{2})?)\s?€")
RE_IMG = re.compile(r'<img\b[^>]*src="([^"]+)"', re.I)
TEXTES_BOUTONS = ("voir l'annonce", "voir", "voir plus", "voir toutes", "gérer", "se désabonner",
                  "désinscrire", "leboncoin", "paramètres", "aide")


def _texte(fragment: str) -> str:
    sans_balises = re.sub(r"<[^>]+>", " ", fragment)
    return re.sub(r"\s+", " ", html.unescape(sans_balises)).strip()


def _prix(texte: str) -> float | None:
    m = RE_PRIX.search(texte)
    if not m:
        return None
    brut = re.sub(r"[   .]", "", m.group(1)).replace(",", ".")
    try:
        return float(brut)
    except ValueError:
        return None


def _id_annonce(url: str) -> str | None:
    cible = url
    for _ in range(3):  # les liens de suivi contiennent l'adresse encodée
        m = RE_ID.search(cible)
        if m:
            return m.group(1)
        cible = unquote(cible)
    return None


def extraire_annonces(contenu_html: str) -> list[Annonce]:
    """Extrait les annonces d'un e-mail d'alerte Leboncoin (HTML)."""
    blocs: dict[str, dict] = {}
    for m in RE_LIEN.finditer(contenu_html):
        url, interieur = html.unescape(m.group(1)), m.group(2)
        ident = _id_annonce(url)
        if not ident:
            continue
        b = blocs.setdefault(ident, {"textes": [], "photo": None, "fin": m.end()})
        b["fin"] = max(b["fin"], m.end())
        texte = _texte(interieur)
        if texte:
            b["textes"].append(texte)
        img = RE_IMG.search(interieur)
        if img and not b["photo"]:
            b["photo"] = html.unescape(img.group(1))
        alt = re.search(r'alt="([^"]+)"', interieur)
        if alt:
            b["textes"].append(html.unescape(alt.group(1)))

    annonces = []
    for ident, b in blocs.items():
        titres = [t for t in b["textes"] if not RE_PRIX.fullmatch(t.strip())
                  and t.lower().strip(" ›>") not in TEXTES_BOUTONS and len(t) > 3]
        titre = max(titres, key=len, default="")
        titre = RE_PRIX.sub("", titre).strip(" -–·|")
        prix = next((p for p in (_prix(t) for t in b["textes"]) if p is not None), None)
        if prix is None:  # prix affiché juste après le lien
            prix = _prix(_texte(contenu_html[b["fin"]:b["fin"] + 800]))
        if not titre or prix is None:
            continue
        annonces.append(Annonce(
            source="leboncoin", id_source=ident, titre=titre, prix=prix,
            url=f"https://www.leboncoin.fr/ad/consoles/{ident}", photo=b["photo"],
        ))
    return annonces


def _html_du_message(msg: Message) -> str:
    for partie in msg.walk():
        if partie.get_content_type() == "text/html":
            charset = partie.get_content_charset() or "utf-8"
            return partie.get_payload(decode=True).decode(charset, errors="replace")
    return ""


class LeboncoinEmailSource(Source):
    nom = "leboncoin_email"
    libelle = "Leboncoin (e-mails)"
    delai = 0

    def __init__(self, cfg, session=None):
        super().__init__(cfg, session)
        conf = cfg.get("leboncoin_email", {}) or {}
        self.adresse = os.environ.get("GMAIL_ADRESSE", "").strip()
        self.mot_de_passe = os.environ.get("GMAIL_MOT_DE_PASSE_APPLI", "").replace(" ", "").strip()
        self.dossier = conf.get("dossier", "INBOX")
        self.jours = int(conf.get("jours", 3))
        self._cache: list[Annonce] | None = None

    def prete(self):
        if not (self.adresse and self.mot_de_passe):
            return False, "GMAIL_ADRESSE / GMAIL_MOT_DE_PASSE_APPLI non configurés"
        return True, ""

    def lire_boite(self) -> tuple[int, list[Annonce]]:
        """Renvoie (nombre d'e-mails Leboncoin lus, annonces extraites)."""
        depuis = date.today() - timedelta(days=self.jours)
        critere = f'(FROM "leboncoin" SINCE {depuis.day:02d}-{MOIS[depuis.month - 1]}-{depuis.year})'
        try:
            boite = imaplib.IMAP4_SSL("imap.gmail.com", 993, timeout=30)
        except (OSError, socket.timeout) as e:
            raise ErreurSource(f"connexion à Gmail impossible : {e}")
        try:
            try:
                boite.login(self.adresse, self.mot_de_passe)
            except imaplib.IMAP4.error:
                raise ErreurSource("Gmail refuse la connexion : vérifie l'adresse et le mot de passe d'application")
            statut, _ = boite.select(f'"{self.dossier}"', readonly=True)  # lecture seule : rien n'est modifié
            if statut != "OK":
                raise ErreurSource(f"dossier Gmail « {self.dossier} » introuvable")
            _, donnees = boite.search(None, critere)
            numeros = donnees[0].split()[-60:]
            annonces, vus = [], set()
            for num in numeros:
                _, brut = boite.fetch(num, "(BODY.PEEK[])")
                if not brut or not isinstance(brut[0], tuple):
                    continue
                msg = email.message_from_bytes(brut[0][1])
                for a in extraire_annonces(_html_du_message(msg)):
                    if a.id_source not in vus:
                        vus.add(a.id_source)
                        annonces.append(a)
            return len(numeros), annonces
        finally:
            try:
                boite.logout()
            except Exception:
                pass

    def chercher(self, rech):
        if self._cache is None:
            nb, self._cache = self.lire_boite()
            log.info("[%s] %d e-mail(s) Leboncoin lus, %d annonce(s) extraite(s).", self.nom, nb, len(self._cache))
        return [Annonce(**a.__dict__) for a in self._cache]
