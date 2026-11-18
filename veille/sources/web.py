"""Base des sources « site web » (lecture des pages comme un navigateur, poliment)."""
import html
import json
import logging
import re
import time

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


class SourceWeb(Source):
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
