"""Structure d'une annonce, commune à toutes les sources."""
from dataclasses import dataclass, field


@dataclass
class Annonce:
    source: str                 # "ebay", "rakuten"...
    id_source: str              # identifiant de l'annonce sur le site
    titre: str
    prix: float                 # prix de l'objet seul
    url: str
    port: float | None = None   # None = inconnu
    photo: str | None = None
    description: str = ""
    etat_site: str = ""         # état tel qu'affiché par le site ("Occasion"...)
    hs_site: bool | None = None # True = le site classe l'objet "pour pièces"
                                # False = le site le classe "fonctionnel"
    enchere: bool = False
    localisation: str = ""
    date: str = ""

    # --- rempli par l'analyse ---
    recherche: str = ""
    etat: str = "inconnu"       # hs / non_teste / fonctionnel / inconnu
    indice_etat: str = ""       # le mot qui a permis de deviner l'état
    port_estime: bool = False
    analyse: dict = field(default_factory=dict)

    @property
    def uid(self) -> str:
        return f"{self.source}:{self.id_source}"

    @property
    def prix_total(self) -> float:
        return round(self.prix + (self.port or 0), 2)
