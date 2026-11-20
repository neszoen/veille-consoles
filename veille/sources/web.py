"""Base des sources « site web » (lecture des pages comme un navigateur, poliment)."""
import html
import json
import logging
import re
import time
from urllib.parse import urlparse

import requests

from .base import ErreurSource, Source, SourceBloquee

# Les sites renvoient une page vide ou bloquée aux « robots » qui ne se présentent
# pas comme un navigateur : on utilise donc l'identité d'un navigateur courant.
UA_NAVIGATEUR = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                 "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

SIGNES_BLOCAGE = ("captcha-delivery.com", "geo.captcha-delivery", "cf-chl-", "Just a moment...",
                  "Access denied", "Pardon Our Interruption")


log = logging.getLogger("veille")

RE_JSON_LD = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S)
RE_META = re.compile(r'<meta[^>]+(?:property|name)="(?:og:description|description|twitter:description)"[^>]*>', re.I)


def extraire_description(page: str) -> str:
    """Description d'une page d'annonce : données structurées (JSON-LD), sinon balises meta."""
    for bloc in RE_JSON_LD.findall(page):
        try:
            donnees = json.loads(bloc.strip())
        except ValueError:
            continue
        for d in donnees if isinstance(donnees, list) else [donnees]:
            if isinstance(d, dict) and isinstance(d.get("description"), str) and len(d["description"]) > 10:
                return html.unescape(d["description"]).strip()
    textes = []
    for balise in RE_META.findall(page):
        contenu = re.search(r'content="([^"]*)"', balise)
        if contenu:
            textes.append(html.unescape(contenu.group(1)).strip())
    return max(textes, key=len, default="")


INDISPONIBLE = ("soldout", "outofstock", "discontinued")


def _produits_json_ld(page: str):
    for bloc in RE_JSON_LD.findall(page):
        try:
            donnees = json.loads(bloc.strip())
        except ValueError:
            continue
        for d in donnees if isinstance(donnees, list) else [donnees]:
            if isinstance(d, dict) and "Product" in str(d.get("@type", "")):
                yield d


def page_dit_vendue(page: str, marqueurs=()) -> bool:
    """Vrai si la page indique que l'annonce n'est plus en vente.

    On se fie d'abord aux données structurées du produit principal (« availability »),
    puis à quelques phrases propres au site.
    """
    for produit in _produits_json_ld(page):
        offres = produit.get("offers") or {}
        for offre in offres if isinstance(offres, list) else [offres]:
            dispo = str((offre or {}).get("availability", "")).lower()
            if any(m in dispo for m in INDISPONIBLE):
                return True
    texte = html.unescape(page).lower()
    return any(m.lower() in texte for m in marqueurs)


class SourceWeb(Source):
    marqueurs_vendu: tuple = ()  # textes propres au site qui signalent une annonce vendue
    delai = 3.0  # 3 à 4 s entre deux pages d'un même site (quelques pages par demi-heure)

    def __init__(self, cfg, session=None):
        super().__init__(cfg, session)
        self.session.headers.update({
            "User-Agent": UA_NAVIGATEUR,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.5",
        })

    def telecharger(self, url: str, params: dict | None = None) -> str:
        for essai in range(2):
            try:
                r = self.session.get(url, params=params, timeout=30)
            except requests.RequestException as e:
                raise ErreurSource(f"connexion à {self.libelle} impossible : {type(e).__name__}")
            debut = r.text[:6000]
            if r.status_code in (401, 403) or (len(r.text) < 20000 and any(s in debut for s in SIGNES_BLOCAGE)):
                raise SourceBloquee(f"{self.libelle} bloque l'accès (protection anti-robot, code {r.status_code})")
            if r.status_code == 429:
                if essai == 0:
                    time.sleep(30)
                    continue
                raise ErreurSource(f"{self.libelle} demande de ralentir (code 429)")
            if r.status_code != 200:
                raise ErreurSource(f"réponse inattendue de {self.libelle} (code {r.status_code})")
            return r.text
        raise ErreurSource(f"{self.libelle} ne répond pas correctement")

    def completer(self, annonce) -> bool:
        if not annonce.url.startswith("http"):
            return False
        time.sleep(self.delai * 0.6)
        try:
            page = self.telecharger(annonce.url)
        except SourceBloquee as e:
            self.descriptions_restantes = 0  # le site refuse les pages d'annonce : on n'insiste pas
            log.info("[%s] pages d'annonce bloquées, descriptions ignorées pour ce passage (%s)", self.nom, e)
            return False
        except ErreurSource as e:
            log.debug("[%s] description illisible (%s) : %s", self.nom, e, annonce.url)
            return False
        description = extraire_description(page)
        # La balise meta reprend parfois juste le titre : sans intérêt.
        if len(description) <= len(annonce.titre) + 5:
            return False
        annonce.description = description[:3000]
        return True

    def verifier(self, alerte: dict) -> str | None:
        url = alerte.get("url", "")
        if not url.startswith("http"):
            return None
        time.sleep(self.delai * 0.6)
        try:
            r = self.session.get(url, timeout=25, allow_redirects=True)
        except requests.RequestException:
            return None
        if r.status_code in (404, 410):
            return "retiree"
        debut = r.text[:6000]
        if r.status_code in (401, 403) or (len(r.text) < 20000 and any(s in debut for s in SIGNES_BLOCAGE)):
            raise SourceBloquee(f"{self.libelle} bloque l'accès (code {r.status_code})")
        if r.status_code != 200:
            return None
        if page_dit_vendue(r.text, self.marqueurs_vendu):
            return "vendue"
        # Annonce supprimée : le site renvoie souvent vers le catalogue ou l'accueil.
        if r.history:
            ident = str(alerte.get("uid", "")).split(":", 1)[-1]
            depart, arrivee = urlparse(url).path.rstrip("/"), urlparse(r.url).path.rstrip("/")
            if arrivee != depart and not (ident and ident in arrivee):
                return "retiree"
        return "disponible"
