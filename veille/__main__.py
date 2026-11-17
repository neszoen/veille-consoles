"""Point d'entrée.

  Le plus simple : double-cliquer sur Veille.bat (ouvre le menu).

  python -m veille --menu           menu interactif
  python -m veille                  exécution normale (utilisée par GitHub Actions)
  python -m veille --simulation     exécution sans rien envoyer (données dans .local-data/)
  python -m veille --demo           démonstration avec de fausses annonces
  python -m veille --test-ebay "psp 3000"
  python -m veille --boucle 30      une exécution toutes les 30 min (VPS / Docker)
"""
import argparse
import logging
import sys
import time

from .affichage import configurer_logs, erreur
from .config import ErreurConfig
from .outils import charger_env


def _preparer_console():
    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def main():
    _preparer_console()
    p = argparse.ArgumentParser(prog="python -m veille", description="Veille bons plans consoles rétro")
    p.add_argument("--menu", action="store_true", help="menu interactif")
    p.add_argument("--simulation", action="store_true", help="n'envoie rien sur Telegram")
    p.add_argument("--demo", action="store_true", help="démonstration avec de fausses annonces")
    p.add_argument("--tester", metavar="RECHERCHE", help="affiche les annonces trouvées pour une recherche")
    p.add_argument("--source", default="ebay", help="site à tester avec --tester (ebay, vinted, leboncoin…)")
    p.add_argument("--raccourci", action="store_true", help="crée le raccourci sur le Bureau")
    p.add_argument("--boucle", type=int, metavar="MINUTES", help="tourne en continu (VPS / Docker)")
    p.add_argument("--debug", action="store_true", help="logs détaillés")
    args = p.parse_args()

    configurer_logs(args.debug)
    charger_env()

    from . import interface
    try:
        if args.menu:
            return interface.menu()
        if args.demo:
            return interface.demo()
        if args.tester:
            return interface.tester_source(args.tester, args.source)
        if args.raccourci:
            return interface.creer_raccourci()

        from .main import executer
        dossier = interface.DOSSIER_LOCAL if args.simulation else None
        if args.boucle:
            while True:
                try:
                    executer(simulation=args.simulation, dossier_data=dossier)
                except Exception:
                    logging.getLogger("veille").exception("Exécution en échec")
                time.sleep(args.boucle * 60)
        executer(simulation=args.simulation, dossier_data=dossier)
    except ErreurConfig as e:
        erreur(f"Erreur de configuration : {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
