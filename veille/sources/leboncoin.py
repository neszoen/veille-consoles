"""Leboncoin, lecture directe de la page de recherche.

✅ Fonctionne depuis une connexion « maison » (ton PC).
❌ Généralement bloqué depuis GitHub Actions (protection DataDome) : dans ce cas,
   utilise plutôt la source « leboncoin_email » (alertes e-mail lues dans Gmail).
"""
import json
import re

from ..config import Recherche
from ..modeles import Annonce
from ..outils import normaliser
from .base import ErreurSource
from .web import SourceWeb

CATEGORIE_CONSOLES = 43  # catégorie « Consoles » (évite jeux et accessoires)
RE_DONNEES =re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


class LeboncoinSource(SourceWeb):
    nom = "leboncoin"
    libelle = "Leboncoin"

    def chercher(self, rech: Recherche) -> list[Annonce]:
        page = self.telecharger("https://www.leboncoin.fr/recherche",
                                {"text": rech.requete, "category": CATEGORIE_CONSOLES,
                                 "sort": "time", "order": "desc"})
        m = RE_DONNEES.search(page)
        if not m:
            raise ErreurSource("la page Leboncoin a changé (données introuvables)")
        try:
            donnees = json.loads(m.group(1))
            annonces = donnees["props"]["pageProps"].get("searchData", {}).get("ads") or []
        except (ValueError, KeyError, AttributeError):
            raise ErreurSource("la page Leboncoin a changé (données illisibles)")
        return [a for a in (self.convertir(x) for x in annonces) if a]

    @staticmethod
    def convertir(ad: dict) -> Annonce | None:
        if ad.get("ad_type") not in (None, "offer"):  # "demand" = quelqu'un qui cherche
            return None
        prix = ad.get("price") or []
        if not prix:
            return None
        frais = [f["price"] / 100 for f in ad.get("shipping_fees") or [] if f.get("price") is not None]
        attributs = {x.get("key"): x.get("value_label") or x.get("value") for x in ad.get("attributes") or []}
        etat = attributs.get("condition") or ""
        images = ad.get("images") or {}
        photo = (images.get("urls_large") or images.get("urls") or [None])[0] or images.get("thumb_url")
        lieu = ad.get("location") or {}
        return Annonce(
            source="leboncoin",
            id_source=str(ad["list_id"]),
            titre=ad.get("subject", ""),
            prix=float(prix[0]),
            url=ad.get("url") or f"https://www.leboncoin.fr/ad/x/{ad['list_id']}",
            port=min(frais) if frais else None,
            photo=photo,
            description=ad.get("body") or "",
            etat_site=etat,
            hs_site=True if "piece" in normaliser(etat) else None,
            localisation=f"{lieu.get('zipcode', '')} {lieu.get('city', '')}".strip(),
            date=ad.get("first_publication_date", ""),
        )
