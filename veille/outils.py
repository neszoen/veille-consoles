"""Petites fonctions utilitaires partagées."""
import os
import re
import unicodedata
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent

USER_AGENT = "VeilleConsolesRetro/1.0 (outil personnel; usage non commercial)"


def normaliser(texte) -> str:
    """Minuscules, sans accents, ponctuation remplacée par des espaces.

    « Écran CASSÉ ! » -> « ecran casse »
    """
    if not texte:
        return ""
    t = unicodedata.normalize("NFKD", str(texte).lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return t.strip()


def contient(texte_normalise: str, mot: str, prefixe: bool = False) -> bool:
    """Le mot (ou l'expression) apparaît-il dans le texte, en mots entiers ?

    prefixe=True accepte la suite du dernier mot : « teste » trouve « testee ».
    """
    m = normaliser(mot)
    if not m:
        return False
    fin = "" if prefixe else r"\b"
    return re.search(r"\b" + re.escape(m) + fin, texte_normalise) is not None


def euros(valeur) -> str:
    """12.5 -> '12,50 €' ; 12.0 -> '12 €'"""
    if valeur is None:
        return "?"
    if abs(valeur - round(valeur)) < 0.005:
        return f"{round(valeur)} €"
    return f"{valeur:.2f} €".replace(".", ",")


def ecrire_env(valeurs: dict, chemin: Path | None = None) -> None:
    """Met à jour (ou crée) le fichier .env en gardant les autres lignes."""
    chemin = chemin or RACINE / ".env"
    lignes = chemin.read_text(encoding="utf-8").splitlines() if chemin.exists() else []
    restantes = dict(valeurs)
    for i, ligne in enumerate(lignes):
        cle = ligne.split("=", 1)[0].strip()
        if "=" in ligne and not ligne.lstrip().startswith("#") and cle in restantes:
            lignes[i] = f"{cle}={restantes.pop(cle)}"
    lignes += [f"{cle}={v}" for cle, v in restantes.items()]
    chemin.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    os.environ.update({k: str(v) for k, v in valeurs.items()})


def charger_env(chemin: Path | None = None) -> None:
    """Lit le fichier .env (utilisé seulement sur ton PC, jamais commité)."""
    chemin = chemin or RACINE / ".env"
    if not chemin.exists():
        return
    for ligne in chemin.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#") or "=" not in ligne:
            continue
        cle, valeur = ligne.split("=", 1)
        os.environ.setdefault(cle.strip(), valeur.strip().strip('"').strip("'"))
