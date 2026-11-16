"""Vinted, lecture de la page de résultats (annonces les plus récentes d'abord).

Le prix retenu inclut la « protection acheteurs » obligatoire. Le port n'est pas
affiché dans les résultats : on utilise une estimation (config.yaml → vinted.port_estime).
"""
import html
import re

from ..config import Recherche
from ..modeles import Annonce
from .base import ErreurSource
from .web import SourceWeb

CATEGORIE_CONSOLES = 3025  # « Jeux vidéo et consoles › Consoles » (évite jeux et accessoires)
RE_IMAGE =re.compile(r'<img\b[^>]*data-testid="product-item-id-(\d+)--image--img"[^>]*>')
RE_ALT = re.compile(
    r"^(?P<titre>.*?)(?:, Marque\s?: (?P<marque>.*?))?(?:, Taille\s?: .*?)?(?:, État\s?: (?P<etat>.*?))?"
    r", (?P<prix>[\d\s.,]+)\s?€(?:, (?P<total>[\d\s.,]+)\s?€)?.*$")


def _nombre(texte: str | None) -> float | None:
    if not texte:
        return None
    t = texte.replace(" ", "").replace(" ", "")
    if "," in t and "." in t:
        t = t.replace(",", "")
    return float(t.replace(",", "."))


class VintedSource(SourceWeb):
    nom = "vinted"
    libelle = "Vinted"

    def chercher(self, rech: Recherche) -> list[Annonce]:
        page = self.telecharger("https://www.vinted.fr/catalog",
                                {"search_text": rech.requete, "order": "newest_first",
                                 "catalog[]": CATEGORIE_CONSOLES})
        balises = RE_IMAGE.finditer(page)
        resultats, vus = [], set()
        for m in balises:
            ident = m.group(1)
            if ident in vus:
                continue
            vus.add(ident)
            annonce = self.convertir(ident, m.group(0))
            if annonce:
                resultats.append(annonce)
        if not resultats and "product-item-id" not in page and "catalog" in page:
            # Page sans aucune vignette : soit 0 résultat, soit la structure a changé.
            if "feed-grid" not in page:
                raise ErreurSource("la page Vinted a changé (annonces introuvables)")
        return resultats

    def convertir(self, ident: str, balise: str) -> Annonce | None:
        alt = re.search(r'alt="([^"]*)"', balise)
        src = re.search(r'src="([^"]*)"', balise)
        if not alt:
            return None
        m = RE_ALT.match(html.unescape(alt.group(1)))
        if not m:
            return None
        try:
            prix = _nombre(m.group("total")) or _nombre(m.group("prix"))
        except ValueError:
            return None
        return Annonce(
            source="vinted",
            id_source=ident,
            titre=m.group("titre").strip(),
            prix=prix,
            url=f"https://www.vinted.fr/items/{ident}",
            port=float(self.cfg.get("vinted", {}).get("port_estime", 4)),
            port_estime=True,
            photo=html.unescape(src.group(1)) if src else None,
            etat_site=m.group("etat") or "",
        )
