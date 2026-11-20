"""Label Emmaüs : boutique en ligne solidaire (Emmaüs, Armée du Salut, ressourceries…).

Peu d'annonces de consoles, mais souvent à petit prix. Fonctionne depuis le cloud.
"""
import html
import json
import re

from ..config import Recherche
from ..modeles import Annonce
from .base import ErreurSource
from .web import SourceWeb

BASE = "https://www.label-emmaus.co"
MARQUEUR = 'class="product-card catalogue-card"'


class LabelEmmausSource(SourceWeb):
    nom = "label_emmaus"
    libelle = "Label Emmaüs"
    marqueurs_vendu = ("ce produit a été vendu", "ce produit n'est plus disponible")

    def chercher(self, rech: Recherche) -> list[Annonce]:
        page = self.telecharger(f"{BASE}/fr/catalogue/", {"q": rech.requete, "tri": "recent"})
        if MARQUEUR not in page:
            if "products-list" in page or "Aucun résultat" in page or "aucun produit" in page.lower():
                return []
            raise ErreurSource("la page Label Emmaüs a changé (produits introuvables)")
        return [a for a in (self.convertir(bloc) for bloc in page.split(MARQUEUR)[1:]) if a]

    @staticmethod
    def convertir(bloc: str) -> Annonce | None:
        ident = re.search(r'data-id="(\d+)"', bloc)
        ga4 = re.search(r'data-ga4-item="([^"]*)"', bloc)
        lien = re.search(r'<a href="([^"]+)"\s+title="([^"]*)"', bloc)
        image = re.search(r'<img[^>]*src="([^"]+)"', bloc)
        if not (ident and ga4 and lien):
            return None
        try:
            prix = float(json.loads(html.unescape(ga4.group(1)))["price"])
        except (ValueError, KeyError):
            return None
        photo = html.unescape(image.group(1)) if image else None
        if photo and photo.startswith("/"):
            photo = BASE + photo
        return Annonce(
            source="label_emmaus",
            id_source=ident.group(1),
            titre=html.unescape(lien.group(2)),
            prix=prix,
            url=BASE + html.unescape(lien.group(1)),
            photo=photo,
        )
