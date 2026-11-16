"""Mise en forme du terminal : couleurs, cadres, logs lisibles. Aucune dépendance."""
import logging
import os
import re
import sys

if os.name == "nt":
    os.system("")  # active les couleurs dans la console Windows

_STYLES = {
    "gras": "1", "dim": "2", "italique": "3",
    "rouge": "31", "vert": "32", "jaune": "33", "bleu": "34", "magenta": "35", "cyan": "36",
    "gris": "90", "rose": "95", "turquoise": "96",
}


def couleurs_actives() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("GITHUB_ACTIONS"):
        return True
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def c(texte, *styles) -> str:
    """c("Bonjour", "gras", "vert") -> texte coloré (ou brut si pas de couleurs)."""
    if not styles or not couleurs_actives():
        return str(texte)
    codes = ";".join(_STYLES[s] for s in styles if s in _STYLES)
    return f"\033[{codes}m{texte}\033[0m"


def sans_couleur(texte: str) -> str:
    return re.sub(r"\033\[[0-9;]*m", "", texte)


def effacer_ecran():
    if sys.stdout.isatty():
        os.system("cls" if os.name == "nt" else "clear")


def bandeau():
    largeur = 52
    print()
    print(c("  " + "━" * largeur, "magenta"))
    print(c("   🎮  VEILLE CONSOLES RÉTRO", "gras", "rose"))
    print(c("       Bons plans perso · Achat-revente · Réparation", "gris"))
    print(c("  " + "━" * largeur, "magenta"))


def titre(texte: str):
    print()
    print(c(f"  {texte}", "gras", "turquoise"))
    print(c("  " + "─" * (len(texte) + 2), "gris"))


def ok(texte):
    print(f"  {c('✔', 'vert', 'gras')} {texte}")


def attention(texte):
    print(f"  {c('!', 'jaune', 'gras')} {c(texte, 'jaune')}")


def erreur(texte):
    print(f"  {c('✖', 'rouge', 'gras')} {c(texte, 'rouge')}")


def info(texte):
    print(f"  {c('›', 'cyan')} {texte}")


def carte(lignes: list[str], couleur: str = "cyan"):
    """Bloc avec une bordure à gauche (robuste aux emojis)."""
    print()
    print(c("  ╭─", couleur) + (" " + lignes[0] if lignes else ""))
    for ligne in lignes[1:-1]:
        print(c("  │ ", couleur) + ligne)
    if len(lignes) > 1:
        print(c("  ╰─ ", couleur) + lignes[-1])


def tableau(entetes: list[str], lignes: list[list[str]], styles: list | None = None):
    """Tableau simple aligné. Les cellules peuvent contenir des couleurs."""
    largeurs = [len(e) for e in entetes]
    for ligne in lignes:
        for i, cell in enumerate(ligne):
            largeurs[i] = max(largeurs[i], len(sans_couleur(cell)))

    def fmt(cells):
        return "  " + "   ".join(cell + " " * (largeurs[i] - len(sans_couleur(cell))) for i, cell in enumerate(cells))

    print(c(fmt(entetes), "gras"))
    print(c("  " + "   ".join("─" * l for l in largeurs), "gris"))
    for ligne in lignes:
        print(fmt(ligne))


class FormatJoli(logging.Formatter):
    """Logs lisibles : heure en gris, icône colorée selon la gravité."""
    ICONES = {
        logging.DEBUG: ("·", "gris"),
        logging.INFO: ("•", "cyan"),
        logging.WARNING: ("!", "jaune"),
        logging.ERROR: ("✖", "rouge"),
        logging.CRITICAL: ("✖", "rouge"),
    }

    def format(self, r: logging.LogRecord) -> str:
        icone, couleur = self.ICONES.get(r.levelno, ("•", "cyan"))
        message = r.getMessage()
        if r.levelno >= logging.WARNING:
            message = c(message, couleur)
        elif r.levelno == logging.DEBUG:
            message = c(message, "gris")
        texte = f"{c(self.formatTime(r, '%H:%M:%S'), 'gris')} {c(icone, couleur, 'gras')} {message}"
        if r.exc_info:
            texte += "\n" + c(self.formatException(r.exc_info), "rouge")
        return texte


def configurer_logs(debug: bool = False):
    gestionnaire = logging.StreamHandler(sys.stdout)
    gestionnaire.setFormatter(FormatJoli())
    racine = logging.getLogger()
    racine.handlers[:] = [gestionnaire]
    racine.setLevel(logging.DEBUG if debug else logging.INFO)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
