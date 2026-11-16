"""Registre des sources. Chaque source est indépendante : si l'une casse, les autres continuent."""
from .base import ErreurSource, Source
from .ebay import EbaySource
from .email_leboncoin import LeboncoinEmailSource
from .label_emmaus import LabelEmmausSource
from .leboncoin import LeboncoinSource
from .vinted import VintedSource

SOURCES = {cls.nom: cls for cls in (EbaySource, VintedSource, LeboncoinEmailSource,
                                    LabelEmmausSource, LeboncoinSource)}

LIBELLES = {cls.nom: cls.libelle for cls in SOURCES.values()} | {"demo": "Démo"}


def construire_sources(cfg: dict) -> list[Source]:
    actives = cfg.get("sources", {}) or {}
    return [cls(cfg) for nom, cls in SOURCES.items() if actives.get(nom)]


__all__ = ["ErreurSource", "Source", "SOURCES", "LIBELLES", "construire_sources"]
