"""Repère les annonces déjà alertées qui ont été vendues ou retirées.

À chaque passage, le robot revérifie quelques alertes récentes (les moins
récemment vérifiées d'abord). Une annonce vendue est marquée dans
data/alertes.json (« vendue ») et le site ne l'affiche plus.
"""
import logging
from datetime import datetime, timedelta

from .sources.base import SourceBloquee
from .stockage import maintenant

log = logging.getLogger("veille")


def _date(texte: str) -> datetime | None:
    try:
        return datetime.fromisoformat(texte)
    except (TypeError, ValueError):
        return None


def a_verifier(alertes: list, source: str, cfg: dict) -> list:
    """Alertes de cette source à revérifier, les plus anciennement vérifiées d'abord."""
    jours = int(cfg.get("verifier_vendues_jours", 30))
    intervalle = timedelta(hours=float(cfg.get("verifier_vendues_intervalle_h", 2)))
    maintenant_ = maintenant()
    candidates = []
    for a in alertes:
        if a.get("source") != source or a.get("vendue"):
            continue
        cree = _date(a.get("date_alerte", ""))
        if not cree or maintenant_ - cree > timedelta(days=jours):
            continue
        derniere = _date(a.get("verifiee", ""))
        if derniere and maintenant_ - derniere < intervalle:
            continue
        candidates.append(a)
    candidates.sort(key=lambda a: a.get("verifiee", ""))
    return candidates[: int(cfg.get("verifier_vendues_max_par_source", 15))]


def verifier_alertes(store, sources: list, cfg: dict, bilan: dict):
    """Revérifie les alertes récentes et marque celles qui sont vendues ou retirées."""
    for src in sources:
        for alerte in a_verifier(store.alertes, src.nom, cfg):
            try:
                statut = src.verifier(alerte)
            except SourceBloquee as e:
                log.info("[%s] vérification des annonces vendues interrompue : %s", src.nom, e)
                break
            except Exception as e:  # une vérification ratée ne doit rien casser
                log.debug("[%s] vérification impossible (%s) : %s", src.nom, e, alerte.get("url"))
                continue
            if statut is None:
                continue
            alerte["verifiee"] = maintenant().isoformat(timespec="seconds")
            if statut in ("vendue", "retiree"):
                alerte["vendue"] = alerte["verifiee"]
                alerte["motif_vendue"] = statut
                bilan["vendues"] = bilan.get("vendues", 0) + 1
                log.info("[%s] %s : %s", src.nom, "vendue" if statut == "vendue" else "retirée",
                         alerte.get("titre", "")[:60])
