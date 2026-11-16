"""Fausse source pour tester l'outil sans aucune clé API (python -m veille --demo)."""
import random

from ..modeles import Annonce
from .base import Source


class DemoSource(Source):
    nom = "demo"
    libelle = "Démo"
    delai = 0

    def __init__(self, cfg, tour: int = 1):
        super().__init__(cfg)
        self.tour = tour

    def chercher(self, rech):
        ref = rech.prix_revente_ref or rech.prix_max * 1.3
        alea = random.Random(rech.nom)
        base = (" ".join(g.split("|")[0].strip() for g in rech.inclure) or rech.requete).upper()
        if self.tour == 1:
            # Premier passage : des annonces « normales » qui remplissent l'historique.
            return [Annonce("demo", f"{rech.nom}-h{i}", f"{base} occasion bon état",
                            round(ref * alea.uniform(0.8, 1.2)), f"https://exemple.fr/{i}", port=6)
                    for i in range(12)]
        return [
            Annonce("demo", f"{rech.nom}-n1", f"{base} fonctionne parfaitement + chargeur",
                    round(ref * 0.55), "https://exemple.fr/n1", port=5,
                    photo="https://exemple.fr/photo1.jpg", localisation="69003 Lyon"),
            Annonce("demo", f"{rech.nom}-n2", f"{base} HS ne s'allume plus pour pièces",
                    round(ref * 0.15), "https://exemple.fr/n2", port=None),
            Annonce("demo", f"{rech.nom}-n3", f"{base} non testée, vendue en l'état",
                    round(ref * 0.3), "https://exemple.fr/n3", port=7, enchere=True),
            Annonce("demo", f"{rech.nom}-n4", f"Coque seule pour {base}",
                    9, "https://exemple.fr/n4", port=3),
            Annonce("demo", f"{rech.nom}-n5", f"{base} collector en boîte",
                    round(ref * 2), "https://exemple.fr/n5", port=8),
        ]
