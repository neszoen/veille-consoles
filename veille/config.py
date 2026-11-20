"""Lecture de watchlist.yaml et config.yaml."""
import copy
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .outils import RACINE

MODES = ("perso", "revente", "les_deux")


class ErreurConfig(Exception):
    pass


@dataclass
class Recherche:
    nom: str
    requete: str
    inclure: list = field(default_factory=list)
    exclure: list = field(default_factory=list)
    prix_max: float = 0
    prix_max_hs: float | None = None
    mode: str = "les_deux"
    prix_revente_ref: float | None = None
    cout_pieces: float | None = None
    actif: bool = True


def _liste(valeur) -> list:
    if valeur is None:
        return []
    if isinstance(valeur, (str, int, float)):
        return [str(valeur)]
    return [str(x) for x in valeur]


def _nombre(valeur, champ, nom):
    if valeur is None or valeur == "":
        return None
    try:
        return float(valeur)
    except (TypeError, ValueError):
        raise ErreurConfig(f"watchlist.yaml, recherche « {nom} » : « {champ} » doit être un nombre (lu : {valeur!r}).")


def lire_yaml(chemin: Path) -> dict:
    try:
        with open(chemin, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise ErreurConfig(f"{chemin.name} est mal formé (vérifie les espaces et les tirets) : {e}")


def charger_watchlist(chemin: Path | None = None):
    chemin = Path(chemin or RACINE / "watchlist.yaml")
    data = lire_yaml(chemin)
    exclusions = _liste(data.get("exclusions_globales"))
    recherches, noms = [], set()
    for i, r in enumerate(data.get("recherches") or [], 1):
        if not isinstance(r, dict):
            raise ErreurConfig(f"watchlist.yaml : la recherche n°{i} est mal écrite.")
        nom = str(r.get("nom") or "").strip()
        if not nom:
            raise ErreurConfig(f"watchlist.yaml : la recherche n°{i} n'a pas de « nom ».")
        if nom.lower() in noms:
            raise ErreurConfig(f"watchlist.yaml : deux recherches s'appellent « {nom} ».")
        noms.add(nom.lower())
        mode = str(r.get("mode") or "les_deux").strip()
        if mode not in MODES:
            raise ErreurConfig(f"watchlist.yaml, « {nom} » : mode « {mode} » inconnu (choix : perso, revente, les_deux).")
        prix_max = _nombre(r.get("prix_max"), "prix_max", nom)
        if prix_max is None:
            raise ErreurConfig(f"watchlist.yaml, « {nom} » : « prix_max » est obligatoire.")
        inclure = _liste(r.get("inclure"))
        requete = str(r.get("requete") or "").strip() or " ".join(g.split("|")[0].strip() for g in inclure)
        if not requete:
            raise ErreurConfig(f"watchlist.yaml, « {nom} » : il faut une « requete » ou des mots à « inclure ».")
        recherches.append(Recherche(
            nom=nom,
            requete=requete,
            inclure=inclure,
            exclure=_liste(r.get("exclure")),
            prix_max=prix_max,
            prix_max_hs=_nombre(r.get("prix_max_hs"), "prix_max_hs", nom),
            mode=mode,
            prix_revente_ref=_nombre(r.get("prix_revente_ref"), "prix_revente_ref", nom),
            cout_pieces=_nombre(r.get("cout_pieces"), "cout_pieces", nom),
            actif=bool(r.get("actif", True)),
        ))
    return recherches, exclusions


DEFAUTS = {
    "frais_plateforme_pct": 10,
    "frais_port_revente": 6,
    "frais_port_defaut": 8,
    "code_postal": "75001",
    "seuil_bonne_affaire_pct": 25,
    "seuil_marge_eur": 30,
    "seuil_marge_pct": 50,
    "echantillon_min": 5,
    "alertes_max_par_execution": 15,
    "descriptions_max_par_source": 20,
    "verifier_vendues_max_par_source": 15,
    "verifier_vendues_jours": 30,
    "verifier_vendues_intervalle_h": 2,
    "echecs_avant_alerte": 3,
    "sources": {"ebay": True, "vinted": True, "leboncoin": False, "leboncoin_email": True,
                "label_emmaus": True},
    "leboncoin_email": {"dossier": "INBOX", "jours": 3},
    "pause_source_en_panne_h": 3,
    "vinted": {"port_estime": 4},
    "ebay": {"pays_vendeur": "FR", "inclure_encheres": True, "resultats_par_recherche": 50},
}


def charger_config(chemin: Path | None = None) -> dict:
    chemin = Path(chemin or RACINE / "config.yaml")
    cfg = copy.deepcopy(DEFAUTS)
    if chemin.exists():
        for cle, valeur in lire_yaml(chemin).items():
            if isinstance(valeur, dict) and isinstance(cfg.get(cle), dict):
                cfg[cle].update(valeur)
            else:
                cfg[cle] = valeur
    return cfg
