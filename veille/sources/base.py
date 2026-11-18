"""Modèle commun à toutes les sources.

Pour ajouter un site : créer un fichier dans ce dossier avec une classe qui
hérite de Source et implémente chercher(), puis l'inscrire dans __init__.py.
"""
import requests

from ..config import Recherche
from ..modeles import Annonce
from ..outils import USER_AGENT


class ErreurSource(Exception):
    """Erreur « propre » d'une source (message lisible dans les logs)."""


class SourceBloquee(ErreurSource):
    """Le site refuse l'accès (protection anti-robot) : on n'insiste pas."""


class Source:
    nom = "base"
    libelle = "Base"
    delai = 1.0  # secondes de pause entre deux recherches (politesse)

    def __init__(self, cfg: dict, session: requests.Session | None = None):
        self.cfg = cfg
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", USER_AGENT)

    def prete(self) -> tuple[bool, str]:
        """La source peut-elle tourner (clés présentes...) ? -> (oui/non, raison)"""
        return True, ""

    def chercher(self, rech: Recherche) -> list[Annonce]:
        raise NotImplementedError

    def completer(self, annonce: Annonce) -> bool:
        """Va lire la page de l'annonce pour récupérer sa description.

        Renvoie True si une description a été trouvée. Par défaut : rien à faire.
        Une erreur ici ne doit jamais faire échouer la source.
        """
        return False
