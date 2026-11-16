"""Mémoire de l'outil : fichiers JSON dans le dossier data/ (commités dans le repo).

- vues.json     : annonces déjà vues (dédoublonnage)
- prix.json     : historique des prix par recherche
- alertes.json  : annonces envoyées sur Telegram (30 derniers jours)
- etat.json     : recherches initialisées, santé des sources
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .modeles import Annonce

log = logging.getLogger("veille")

GARDER_VUES_JOURS = 365
GARDER_ALERTES_JOURS = 30
PRIX_MAX_PAR_RECHERCHE = 500


def maintenant() -> datetime:
    return datetime.now(timezone.utc)


class Stockage:
    def __init__(self, dossier: Path):
        self.dossier = Path(dossier)
        self.dossier.mkdir(parents=True, exist_ok=True)
        self.vues = self._lire("vues.json", {})
        self.prix = self._lire("prix.json", {})
        self.alertes = self._lire("alertes.json", [])
        self.etat = self._lire("etat.json", {})
        self.etat.setdefault("initialisees", [])
        self.etat.setdefault("sante", {})

    # ---------- fichiers ----------
    def _lire(self, nom, defaut):
        chemin = self.dossier / nom
        if not chemin.exists():
            return defaut
        try:
            return json.loads(chemin.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            # On s'arrête plutôt que de repartir de zéro (sinon : avalanche d'alertes).
            raise RuntimeError(f"Le fichier {chemin} est corrompu ({e}). Restaure-le depuis l'historique GitHub.")

    def _ecrire(self, nom, data):
        chemin = self.dossier / nom
        tmp = chemin.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(chemin)

    def sauvegarder(self):
        limite = (maintenant() - timedelta(days=GARDER_VUES_JOURS)).date().isoformat()
        self.vues = {k: v for k, v in self.vues.items() if v.get("d", "") >= limite}
        limite_a = (maintenant() - timedelta(days=GARDER_ALERTES_JOURS)).isoformat()
        self.alertes = [a for a in self.alertes if a.get("date_alerte", "") >= limite_a]
        self._ecrire("vues.json", self.vues)
        self._ecrire("prix.json", self.prix)
        self._ecrire("alertes.json", self.alertes)
        self._ecrire("etat.json", self.etat)

    # ---------- dédoublonnage ----------
    def vue_pour(self, uid: str, recherche: str) -> bool:
        return recherche in self.vues.get(uid, {}).get("r", [])

    def marquer_vue(self, uid: str, recherche: str):
        v = self.vues.setdefault(uid, {"d": maintenant().date().isoformat(), "r": [], "a": 0})
        if recherche not in v["r"]:
            v["r"].append(recherche)

    def deja_alertee(self, uid: str) -> bool:
        return bool(self.vues.get(uid, {}).get("a"))

    def marquer_alertee(self, annonce: Annonce, envoyee: bool = True):
        self.vues.setdefault(annonce.uid, {"d": maintenant().date().isoformat(), "r": [], "a": 0})["a"] = 1
        if envoyee:
            self.alertes.append({
                "date_alerte": maintenant().isoformat(timespec="seconds"),
                "uid": annonce.uid, "source": annonce.source, "recherche": annonce.recherche,
                "titre": annonce.titre, "prix_total": annonce.prix_total, "url": annonce.url,
                "photo": annonce.photo, "etat": annonce.etat, "analyse": annonce.analyse,
            })

    # ---------- historique des prix ----------
    def historique(self, recherche: str) -> list:
        return self.prix.get(recherche, [])

    def ajouter_prix(self, recherche: str, annonce: Annonce):
        liste = self.prix.setdefault(recherche, [])
        liste.append({
            "d": maintenant().isoformat(timespec="minutes"),
            "p": annonce.prix_total, "e": annonce.etat, "s": annonce.source,
        })
        del liste[:-PRIX_MAX_PAR_RECHERCHE]

    # ---------- première exécution d'une recherche ----------
    def est_initialisee(self, cle: str) -> bool:
        return cle in self.etat["initialisees"]

    def marquer_initialisee(self, cle: str):
        if cle not in self.etat["initialisees"]:
            self.etat["initialisees"].append(cle)

    # ---------- santé des sources ----------
    def enregistrer_echec(self, source: str, message: str) -> int:
        s = self.etat["sante"].setdefault(source, {"echecs": 0, "alerte": False})
        s["echecs"] += 1
        s["derniere_erreur"] = message[:300]
        s["date"] = maintenant().isoformat(timespec="minutes")
        return s["echecs"]

    def en_pause(self, source: str, seuil: int, heures: float) -> bool:
        """Source en panne depuis peu : on attend avant de réessayer (politesse + quota)."""
        s = self.etat["sante"].get(source)
        if not s or s.get("echecs", 0) < seuil or not s.get("date"):
            return False
        return maintenant() - datetime.fromisoformat(s["date"]) < timedelta(hours=heures)

    def marquer_alerte_panne(self, source: str):
        self.etat["sante"][source]["alerte"] = True

    def enregistrer_succes(self, source: str) -> bool:
        """Renvoie True si la source était signalée en panne (pour annoncer son retour)."""
        s = self.etat["sante"].get(source)
        etait_en_panne = bool(s and s.get("alerte"))
        self.etat["sante"][source] = {"echecs": 0, "alerte": False,
                                      "dernier_succes": maintenant().isoformat(timespec="minutes")}
        return etait_en_panne
