"""Modification de watchlist.yaml depuis le logiciel, en gardant les commentaires."""
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.scalarstring import DoubleQuotedScalarString as Q

from ..config import MODES, ErreurConfig, charger_watchlist
from ..outils import RACINE

CHAMPS = ("nom", "requete", "inclure", "exclure", "prix_max", "prix_max_hs", "mode",
          "prix_revente_ref", "cout_pieces", "actif")


def _yaml() -> YAML:
    y = YAML()
    y.preserve_quotes = True
    y.indent(mapping=2, sequence=4, offset=2)
    y.width = 4096
    return y


def _chemin(chemin=None) -> Path:
    return Path(chemin or RACINE / "watchlist.yaml")


def lire(chemin=None):
    with open(_chemin(chemin), encoding="utf-8") as f:
        return _yaml().load(f) or CommentedMap()


def ecrire(data, chemin=None):
    chemin = _chemin(chemin)
    tmp = chemin.with_suffix(".yaml.tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        _yaml().dump(data, f)
    try:
        charger_watchlist(tmp)  # on vérifie avant de remplacer le vrai fichier
    except ErreurConfig:
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(chemin)


def _liste_flow(valeurs) -> CommentedSeq:
    s = CommentedSeq([Q(str(v).strip()) for v in valeurs if str(v).strip()])
    s.fa.set_flow_style()
    return s


def _nombre(v):
    if v is None or v == "":
        return None
    f = float(v)
    return int(f) if f == int(f) else f


def _nettoyer(entree: dict) -> dict:
    nom = str(entree.get("nom") or "").strip()
    if not nom:
        raise ErreurConfig("Donne un nom à la recherche.")
    mode = entree.get("mode") or "les_deux"
    if mode not in MODES:
        raise ErreurConfig(f"Mode inconnu : {mode}")
    if _nombre(entree.get("prix_max")) is None:
        raise ErreurConfig("Le prix maximum est obligatoire.")
    return {
        "nom": nom,
        "requete": str(entree.get("requete") or "").strip(),
        "inclure": _liste_flow(entree.get("inclure") or []),
        "exclure": _liste_flow(entree.get("exclure") or []),
        "prix_max": _nombre(entree.get("prix_max")),
        "prix_max_hs": _nombre(entree.get("prix_max_hs")),
        "mode": mode,
        "prix_revente_ref": _nombre(entree.get("prix_revente_ref")),
        "cout_pieces": _nombre(entree.get("cout_pieces")),
        "actif": bool(entree.get("actif", True)),
    }


def _trouver(data, nom: str):
    for i, r in enumerate(data.get("recherches") or []):
        if str(r.get("nom", "")).strip().lower() == nom.strip().lower():
            return i, r
    return None, None


def enregistrer_recherche(entree: dict, ancien_nom: str | None = None, chemin=None):
    data = lire(chemin)
    valeurs = _nettoyer(entree)
    recherches = data.setdefault("recherches", CommentedSeq())
    i, existante = _trouver(data, ancien_nom or valeurs["nom"])
    if ancien_nom and existante is None:
        raise ErreurConfig(f"Recherche « {ancien_nom} » introuvable.")
    if not ancien_nom and existante is not None:
        raise ErreurConfig(f"Une recherche s'appelle déjà « {valeurs['nom']} ».")
    if existante is None:
        existante = CommentedMap()
        recherches.append(existante)
    for cle in CHAMPS:
        v = valeurs[cle]
        if v is None and cle in ("prix_max_hs", "prix_revente_ref", "cout_pieces"):
            existante.pop(cle, None)
        elif cle in existante and cle in ("inclure", "exclure") and list(existante[cle]) == list(v):
            continue  # on garde la mise en forme d'origine
        else:
            existante[cle] = v
    ecrire(data, chemin)


def modifier_champs(nom: str, champs: dict, chemin=None):
    data = lire(chemin)
    _, r = _trouver(data, nom)
    if r is None:
        raise ErreurConfig(f"Recherche « {nom} » introuvable.")
    for cle, v in champs.items():
        if cle not in CHAMPS or cle == "nom":
            continue
        r[cle] = bool(v) if cle == "actif" else _nombre(v)
    ecrire(data, chemin)


def supprimer_recherche(nom: str, chemin=None):
    data = lire(chemin)
    i, _ = _trouver(data, nom)
    if i is None:
        raise ErreurConfig(f"Recherche « {nom} » introuvable.")
    del data["recherches"][i]
    ecrire(data, chemin)


def enregistrer_exclusions(mots: list, chemin=None):
    data = lire(chemin)
    propres = [str(m).strip() for m in mots if str(m).strip()]
    ancienne = data.get("exclusions_globales")
    if isinstance(ancienne, CommentedSeq):
        ancienne.clear()
        ancienne.extend(propres)
    else:
        data["exclusions_globales"] = CommentedSeq(propres)
    ecrire(data, chemin)
