"""Statistiques des prix relevés et prix conseillés pour la watchlist.

Méthode (choisie le 17/11/2026) :
  prix_revente_ref = médiane des annonces − 10 % (un prix demandé > un prix vendu)
  prix_max         = 70 % de la médiane
  prix_max_hs      = prix qui laisse ≈ « seuil_marge_eur » de marge après pièces,
                     port de revente et frais de plateforme (jamais sous l'actuel)
"""
from statistics import median, quantiles

COEF_REVENTE = 0.90
COEF_MAX = 0.70


def arrondi5(x: float) -> int:
    return int(round(x / 5) * 5)


def statistiques(points: list) -> dict | None:
    prix = sorted(p["p"] for p in points if isinstance(p.get("p"), (int, float)))
    if not prix:
        return None
    q = quantiles(prix, n=4) if len(prix) >= 2 else [prix[0]] * 3
    jours = sorted({p["d"][:10] for p in points if p.get("d")})
    return {"n": len(prix), "min": prix[0], "max": prix[-1], "p25": round(q[0], 2),
            "mediane": round(median(prix), 2), "p75": round(q[2], 2),
            "premier_jour": jours[0] if jours else None, "dernier_jour": jours[-1] if jours else None,
            "nb_jours": len(jours)}


def medianes_par_jour(points: list) -> list:
    par_jour: dict[str, list] = {}
    for p in points:
        if p.get("d"):
            par_jour.setdefault(p["d"][:10], []).append(p["p"])
    return [{"jour": j, "mediane": round(median(v), 2), "n": len(v)} for j, v in sorted(par_jour.items())]


def conseils(stats: dict, rech, cfg: dict) -> dict:
    """Prix conseillés pour une recherche, à partir des statistiques."""
    med = stats["mediane"]
    revente = arrondi5(med * COEF_REVENTE)
    hs_calcule = arrondi5(revente * (1 - cfg["frais_plateforme_pct"] / 100) - cfg["frais_port_revente"]
                          - (rech.cout_pieces or 0) - cfg["seuil_marge_eur"])
    hs = max(hs_calcule, int(rech.prix_max_hs or 0))
    return {"prix_max": arrondi5(med * COEF_MAX), "prix_max_hs": hs or None, "prix_revente_ref": revente,
            "hs_garde": hs_calcule < (rech.prix_max_hs or 0)}
