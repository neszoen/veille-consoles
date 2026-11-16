"""Menu interactif : tout ce qu'il faut pour utiliser l'outil sans taper de commande."""
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import requests

from .affichage import (attention, bandeau, c, effacer_ecran, erreur, info, ok, tableau, titre)
from .config import ErreurConfig, Recherche, charger_config, charger_watchlist
from .outils import RACINE, ecrire_env, euros
from .synchro import synchroniser

DOSSIER_LOCAL = RACINE / ".local-data"  # données des essais sur ton PC (jamais envoyées sur GitHub)
LIBELLES_MODE = {"perso": "perso", "revente": "revente", "les_deux": "les deux"}
COULEURS_ETAT = {"hs": ("HS", "magenta"), "non_teste": ("non testée", "bleu"),
                 "fonctionnel": ("fonctionne", "vert"), "inconnu": ("?", "gris")}


# ───────────────────────── petits outils ─────────────────────────

def demander(question: str, defaut: str = "") -> str:
    suffixe = c(f" [{defaut}]", "gris") if defaut else ""
    try:
        reponse = input(f"\n  {c('?', 'rose', 'gras')} {question}{suffixe} : ").strip().lstrip("﻿")
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit(0)
    return reponse or defaut


def oui(question: str, defaut: bool = True) -> bool:
    rep = demander(question + (" (O/n)" if defaut else " (o/N)")).lower()
    return defaut if not rep else rep.startswith("o") or rep.startswith("y")


def pause():
    try:
        input(c("\n  ↩  Appuie sur Entrée pour revenir au menu… ", "gris"))
    except (EOFError, KeyboardInterrupt):
        raise SystemExit(0)


def dans_codespaces() -> bool:
    return os.environ.get("CODESPACES") == "true"


def masquer(valeur: str) -> str:
    return f"{valeur[:4]}…{valeur[-3:]}" if len(valeur) > 10 else "•••"


def telegram_configure() -> bool:
    return bool(os.environ.get("TELEGRAM_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))


def ebay_configure() -> bool:
    return bool(os.environ.get("EBAY_CLIENT_ID") and os.environ.get("EBAY_CLIENT_SECRET"))


def _statut(fait: bool, texte_ok: str, texte_ko: str) -> str:
    return c(f"✔ {texte_ok}", "vert") if fait else c(f"○ {texte_ko}", "jaune")


def panneau():
    titre("Ma configuration")
    print(f"  {'Telegram':<11} {_statut(telegram_configure(), 'connecté', 'à configurer (choix 2)')}")
    print(f"  {'eBay':<11} {_statut(ebay_configure(), 'clés enregistrées', 'à configurer (choix 2)')}")
    print(f"  {'Gmail':<11} {_statut(gmail_configure(), 'connecté (alertes Leboncoin)', 'à configurer (choix 2)')}")
    from .synchro import adresse_github
    depot = adresse_github()
    nom_depot = depot.rstrip("/").removesuffix(".git").split("github.com/")[-1] if depot else ""
    print(f"  {'GitHub':<11} {_statut(bool(depot), f'relié ({nom_depot})', 'pas encore relié (choix 7)')}")
    try:
        recherches, _ = charger_watchlist()
        actives = sum(r.actif for r in recherches)
        print(f"  {'Watchlist':<11} {c(f'✔ {actives} recherche(s) active(s)', 'vert')}"
              f"{c(f', {len(recherches) - actives} en pause', 'gris')}")
    except ErreurConfig as e:
        print(f"  {'Watchlist':<11} {c('✖ erreur : ' + str(e), 'rouge')}")


# ───────────────────────── démonstration ─────────────────────────

def demo():
    from .main import executer
    from .sources.demo import DemoSource
    from .telegram import Telegram

    titre("Démonstration avec de fausses annonces")
    info("Rien n'est envoyé ni enregistré : c'est juste pour voir à quoi ressemblent les alertes.")
    cfg = charger_config()
    recherches, _ = charger_watchlist()
    choix = [r for r in recherches if r.actif][:2]
    dossier = Path(tempfile.mkdtemp(prefix="veille-demo-"))
    tg = Telegram(simulation=True)
    logging.getLogger("veille").setLevel(logging.WARNING)  # on garde l'écran lisible
    try:
        titre("1ʳᵉ exécution : l'outil découvre les annonces déjà en ligne")
        executer(dossier_data=dossier, sources=[DemoSource(cfg, tour=1)], telegram=tg, recherches=choix)
        titre("30 minutes plus tard : de nouvelles annonces arrivent")
        executer(dossier_data=dossier, sources=[DemoSource(cfg, tour=2)], telegram=tg, recherches=choix)
        titre("Encore 30 minutes plus tard : rien de nouveau")
        bilan = executer(dossier_data=dossier, sources=[DemoSource(cfg, tour=2)], telegram=tg, recherches=choix)
        ok(f"Aucune alerte en double ({bilan['alertes']} envoyée) : le dédoublonnage fonctionne.")
    finally:
        logging.getLogger("veille").setLevel(logging.NOTSET)
    print()
    info(f"{c('Jaune', 'jaune')} = 🔥 très bonne affaire · {c('Violet', 'magenta')} = 🔧 HS à réparer · "
         f"{c('Vert', 'vert')} = fonctionne")


# ───────────────────────── Telegram ─────────────────────────

def _api_telegram(jeton: str, methode: str, **params) -> dict:
    try:
        return requests.get(f"https://api.telegram.org/bot{jeton}/{methode}", params=params, timeout=20).json()
    except (requests.RequestException, ValueError):
        return {"ok": False, "description": "impossible de joindre Telegram (connexion internet ?)"}


def configurer_telegram():
    titre("Configurer Telegram")
    if telegram_configure():
        ok(f"Déjà configuré (jeton {masquer(os.environ['TELEGRAM_TOKEN'])}).")
        if not oui("Veux-tu le reconfigurer ?", defaut=False):
            return
    print(f"""
  {c('1.', 'rose', 'gras')} Dans Telegram, cherche {c('@BotFather', 'gras')} (badge bleu ✔) et envoie {c('/newbot', 'gras')}
  {c('2.', 'rose', 'gras')} Donne un nom (ex. {c('Veille Consoles', 'gras')}), puis un identifiant finissant par {c('bot', 'gras')}
  {c('3.', 'rose', 'gras')} BotFather répond avec un jeton du genre {c('7123456789:AAH…', 'gras')}""")

    while True:
        jeton = demander("Colle ici le jeton (Entrée seule pour annuler)")
        if not jeton:
            return
        moi = _api_telegram(jeton, "getMe")
        if moi.get("ok"):
            break
        erreur(f"Telegram refuse ce jeton : {moi.get('description')}. Vérifie le copier-coller.")
    nom_bot = moi["result"]["username"]
    ok(f"Bot trouvé : {c('@' + nom_bot, 'gras')}")

    print(f"\n  {c('4.', 'rose', 'gras')} Ouvre {c(f'https://t.me/{nom_bot}', 'cyan')}, appuie sur "
          f"{c('Démarrer', 'gras')} et envoie-lui « bonjour ».")
    for essai in range(5):
        try:
            input(c("\n  ↩  Quand c'est fait, appuie sur Entrée… ", "gris"))
        except (EOFError, KeyboardInterrupt):
            raise SystemExit(0)
        maj = _api_telegram(jeton, "getUpdates")
        chats = [(m.get("message") or {}).get("chat") for m in maj.get("result", [])]
        chats = [ch for ch in chats if ch and ch.get("type") == "private"]
        if chats:
            chat = chats[-1]
            break
        attention("Je ne vois pas encore ton message. Vérifie que tu l'as bien envoyé à "
                  f"@{nom_bot}, puis réessaie.")
    else:
        erreur("Toujours rien reçu. Réessaie plus tard depuis le menu.")
        return

    ecrire_env({"TELEGRAM_TOKEN": jeton, "TELEGRAM_CHAT_ID": str(chat["id"])})
    ok(f"Conversation trouvée avec {c(chat.get('first_name', ''), 'gras')} (n° {chat['id']}). Enregistré dans .env.")
    test = _api_telegram(jeton, "sendMessage", chat_id=chat["id"],
                         text="👋 Bonjour ! Ton bot de veille consoles rétro est bien connecté. 🎮")
    if test.get("ok"):
        ok("Message de test envoyé : regarde ton téléphone ! 📱")
    else:
        erreur(f"Le message de test n'est pas passé : {test.get('description')}")
    print()
    attention("Garde ce jeton secret : sur GitHub, il ira dans les « Secrets », jamais dans le code.")


# ───────────────────────── eBay ─────────────────────────

def configurer_ebay():
    from .sources.base import ErreurSource
    from .sources.ebay import EbaySource

    titre("Configurer eBay")
    if ebay_configure():
        ok(f"Clés déjà enregistrées (App ID {masquer(os.environ['EBAY_CLIENT_ID'])}).")
        if not oui("Veux-tu les remplacer ?", defaut=False):
            return
    print(f"""
  Sur {c('developer.ebay.com', 'cyan')} → menu à ton nom → {c('Application Keysets', 'gras')} → colonne {c('Production', 'gras')}.
  {c('ℹ', 'cyan')} eBay vérifie parfois les nouveaux comptes avant d'activer les clés : c'est normal, ça peut prendre quelques jours.""")
    client_id = demander("App ID (Client ID)")
    if not client_id:
        return
    secret = demander("Cert ID (Client Secret)")
    if not secret:
        return
    anciens = {k: os.environ.get(k, "") for k in ("EBAY_CLIENT_ID", "EBAY_CLIENT_SECRET")}
    os.environ.update({"EBAY_CLIENT_ID": client_id, "EBAY_CLIENT_SECRET": secret})
    info("Vérification auprès d'eBay…")
    try:
        EbaySource(charger_config()).jeton()
        ok("eBay accepte tes clés ! 🎉")
        valide = True
    except ErreurSource as e:
        erreur(str(e))
        attention("Si ton compte est encore en cours de vérification chez eBay, c'est normal.")
        valide = oui("Enregistrer quand même ces clés ?", defaut=True)
    if valide:
        ecrire_env({"EBAY_CLIENT_ID": client_id, "EBAY_CLIENT_SECRET": secret})
        ok("Clés enregistrées dans .env.")
    else:
        os.environ.update(anciens)


def gmail_configure() -> bool:
    return bool(os.environ.get("GMAIL_ADRESSE") and os.environ.get("GMAIL_MOT_DE_PASSE_APPLI"))


def configurer_gmail():
    from .sources.base import ErreurSource
    from .sources.email_leboncoin import LeboncoinEmailSource

    titre("Leboncoin par e-mail (Gmail)")
    print(f"""
  Leboncoin bloque les robots, mais il envoie lui-même des {c('alertes par e-mail', 'gras')}.
  L'outil lit ces e-mails dans ta boîte Gmail ({c('en lecture seule', 'gras')} : rien n'est supprimé ni marqué lu).

  {c('A.', 'rose', 'gras')} Sur {c('leboncoin.fr', 'cyan')}, connecté à ton compte : cherche par ex. « psp » dans la catégorie
     {c('Consoles', 'gras')}, clique {c('Enregistrer la recherche', 'gras')} et active les {c('alertes e-mail', 'gras')}.
     Fais-le pour chaque console de ta watchlist.
  {c('B.', 'rose', 'gras')} Sur ton compte Google : active la {c('Validation en deux étapes', 'gras')}, puis va sur
     {c('https://myaccount.google.com/apppasswords', 'cyan')}, crée un mot de passe nommé « veille »
     et copie le code de 16 lettres qui s'affiche.
  {c('ℹ', 'cyan')} Ce code donne accès à la boîte mail : il reste sur ton PC (.env) et dans les secrets GitHub.
     Tu pourras le supprimer à tout moment sur la même page Google.""")
    adresse = demander("Adresse Gmail qui reçoit les alertes Leboncoin", os.environ.get("GMAIL_ADRESSE", ""))
    if not adresse:
        return
    code = demander("Code de 16 lettres (mot de passe d'application)").replace(" ", "")
    if not code:
        return
    anciens = {k: os.environ.get(k, "") for k in ("GMAIL_ADRESSE", "GMAIL_MOT_DE_PASSE_APPLI")}
    os.environ.update({"GMAIL_ADRESSE": adresse, "GMAIL_MOT_DE_PASSE_APPLI": code})
    info("Connexion à Gmail…")
    try:
        nb, annonces = LeboncoinEmailSource(charger_config()).lire_boite()
    except ErreurSource as e:
        erreur(str(e))
        os.environ.update(anciens)
        return
    ecrire_env({"GMAIL_ADRESSE": adresse, "GMAIL_MOT_DE_PASSE_APPLI": code})
    ok("Gmail accepte la connexion. Enregistré dans .env.")
    if nb == 0:
        info("Aucun e-mail Leboncoin des 3 derniers jours pour l'instant : normal si tu viens de créer tes alertes.")
    elif not annonces:
        attention(f"{nb} e-mail(s) Leboncoin trouvés, mais je n'ai pas su en lire les annonces.")
        info("Le format a peut-être changé : signale-le pour que la lecture soit ajustée.")
    else:
        ok(f"{nb} e-mail(s) Leboncoin lus, {len(annonces)} annonce(s) extraite(s) :\n")
        tableau(["Prix", "Titre"], [[c(euros(a.prix), "gras"), a.titre[:65]] for a in annonces[:10]])


def configurer_comptes():
    sous_menu = [("1", "📱 Telegram", configurer_telegram), ("2", "🔑 eBay", configurer_ebay),
                 ("3", "📧 Gmail (alertes Leboncoin)", configurer_gmail)]
    titre("Configurer mes comptes")
    print(f"  {'Telegram':<10} {_statut(telegram_configure(), 'connecté', 'à configurer')}")
    print(f"  {'eBay':<10} {_statut(ebay_configure(), 'clés enregistrées', 'à configurer')}")
    print(f"  {'Gmail':<10} {_statut(gmail_configure(), 'connecté', 'à configurer')}\n")
    for cle, libelle, _ in sous_menu:
        print(f"   {c(' ' + cle + ' ', 'gras', 'rose')} {libelle}")
    print(f"   {c(' 0 ', 'gras', 'rose')} ↩  Retour")
    choix = demander("Lequel ?")
    action = next((a for k, _, a in sous_menu if k == choix), None)
    if action:
        effacer_ecran()
        bandeau()
        action()


def tester_source(requete: str | None = None, nom_source: str | None = None):
    from .analyse import detecter_etat
    from .sources import SOURCES

    titre("Tester une recherche sur un site")
    noms = list(SOURCES)
    if not nom_source:
        for i, nom in enumerate(noms, 1):
            print(f"   {c(f' {i} ', 'gras', 'rose')} {SOURCES[nom].libelle}")
        rep = demander("Quel site ?", "1")
        if not rep.isdigit() or not 1 <= int(rep) <= len(noms):
            attention("Choix inconnu.")
            return
        nom_source = noms[int(rep) - 1]
    if nom_source not in SOURCES:
        erreur(f"Source inconnue : {nom_source} (choix : {', '.join(noms)})")
        return
    source = SOURCES[nom_source](charger_config())
    pret, raison = source.prete()
    if not pret:
        attention(f"{source.libelle} n'est pas encore configuré : {raison}.")
        return
    requete = requete or demander("Que veux-tu chercher ?", "psp 3000")
    info(f"Recherche « {requete} » sur {source.libelle}…")
    try:
        annonces = source.chercher(Recherche(nom="test", requete=requete))
    except Exception as e:
        erreur(str(e))
        return
    ok(f"{len(annonces)} annonces trouvées (les plus récentes d'abord) :\n")
    lignes = []
    for a in annonces[:20]:
        etat, _ = detecter_etat(a)
        libelle, couleur = COULEURS_ETAT[etat]
        port = c("?", "gris") if a.port is None else (euros(a.port) + (c("~", "gris") if a.port_estime else ""))
        lignes.append([c(euros(a.prix), "gras"), port, c(libelle, couleur),
                       a.titre[:58] + ("…" if len(a.titre) > 58 else "")])
    tableau(["Prix", "Port", "État", "Titre"], lignes)


# ───────────────────────── veille ─────────────────────────

def lancer_veille():
    from .main import executer

    titre("Lancer une veille maintenant")
    if not ebay_configure():
        attention("eBay n'est pas encore configuré : il sera ignoré, les autres sites tournent.")
    info("Les alertes s'affichent ici ; rien n'est envoyé sur Telegram.")
    info("Une fois sur GitHub, c'est le robot qui enverra les alertes pour de vrai.\n")
    executer(simulation=True, dossier_data=DOSSIER_LOCAL)


# ───────────────────────── watchlist ─────────────────────────

def voir_watchlist():
    titre("Ma watchlist")
    try:
        recherches, exclusions = charger_watchlist()
    except ErreurConfig as e:
        erreur(str(e))
        info("Corrige le fichier avec le choix 6, puis reviens ici.")
        return
    lignes = []
    for r in recherches:
        lignes.append([
            c(r.nom, "gras") if r.actif else c(r.nom, "gris"),
            LIBELLES_MODE[r.mode],
            euros(r.prix_max),
            euros(r.prix_max_hs) if r.prix_max_hs else c("—", "gris"),
            euros(r.prix_revente_ref) if r.prix_revente_ref else c("auto", "gris"),
            euros(r.cout_pieces) if r.cout_pieces else c("—", "gris"),
            c("● active", "vert") if r.actif else c("○ en pause", "gris"),
        ])
    tableau(["Recherche", "Mode", "Max", "Max HS", "Revente", "Pièces", "Statut"], lignes)
    print()
    info(f"Prix maximum toujours port compris · {len(exclusions)} mots exclus partout "
         f"({', '.join(exclusions[:5])}…)")


def modifier_watchlist():
    titre("Modifier ma watchlist")
    chemin = RACINE / "watchlist.yaml"
    if os.name == "nt":
        info("Le fichier s'ouvre dans le Bloc-notes. Modifie, enregistre (Ctrl+S) puis ferme la fenêtre.")
        commande = ["notepad.exe", str(chemin)]
    elif dans_codespaces() and shutil.which("code"):
        info("Le fichier s'ouvre dans un onglet au-dessus. Modifie-le (c'est enregistré tout seul),")
        info("puis ferme son onglet (croix ✕) pour revenir ici.")
        commande = ["code", "--wait", str(chemin)]
    else:
        info("Modifie le fichier, puis Ctrl+O et Entrée pour enregistrer, Ctrl+X pour quitter.")
        commande = [os.environ.get("EDITOR") or "nano", str(chemin)]
    info("Règle d'or : garde les mêmes espaces en début de ligne que les autres recherches.")
    try:
        subprocess.run(commande)
    except FileNotFoundError:
        erreur(f"Aucun éditeur disponible. Ouvre le fichier {chemin.name} à la main, puis reviens ici.")
        pause()
    print()
    try:
        charger_watchlist()
        ok("Fichier valide ✨")
        voir_watchlist()
    except ErreurConfig as e:
        erreur(str(e))
        attention("Le fichier contient une erreur : relance ce choix pour la corriger.")
        return
    from .synchro import adresse_github, envoyer, modifications_locales
    if adresse_github() and "watchlist.yaml" in modifications_locales():
        if oui("Envoyer cette modification sur GitHub maintenant (le robot l'utilisera) ?"):
            envoyer("Watchlist modifiée depuis le menu")


# ───────────────────────── raccourci ─────────────────────────

def creer_raccourci(silencieux: bool = False) -> bool:
    if os.name != "nt":
        info("Pas de raccourci ici : pour rouvrir la veille, tape  ./veille.sh  dans le terminal.")
        return False
    def q(p):  # chemin entre apostrophes pour PowerShell
        return "'" + str(p).replace("'", "''") + "'"
    script = (
        "$b=[Environment]::GetFolderPath('Desktop');"
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $b 'Veille consoles.lnk'));"
        f"$s.TargetPath={q(RACINE / 'Veille.bat')};$s.WorkingDirectory={q(RACINE)};"
        f"$s.IconLocation={q(RACINE / 'assets' / 'veille.ico')};"
        "$s.Description='Veille bons plans consoles rétro';$s.Save()"
    )
    r = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True)
    if r.returncode == 0:
        if not silencieux:
            ok("Raccourci « Veille consoles » créé sur ton Bureau 🎮")
        return True
    erreur(f"Impossible de créer le raccourci : {r.stderr.strip()[:200]}")
    return False


def raccourci():
    titre("Raccourci sur le Bureau")
    creer_raccourci()


# ───────────────────────── menu principal ─────────────────────────

CHOIX = [
    ("1", "▶  Voir une démonstration", demo),
    ("2", "⚙️  Configurer mes comptes (Telegram, eBay, Gmail)", configurer_comptes),
    ("3", "🔍 Tester une recherche sur un site", tester_source),
    ("4", "🚀 Lancer une veille maintenant", lancer_veille),
    ("5", "📋 Voir ma watchlist", voir_watchlist),
    ("6", "✏️  Modifier ma watchlist", modifier_watchlist),
    ("7", "🔄 Synchroniser avec GitHub (autre PC)", synchroniser),
    ("8", "🖥  Créer un raccourci sur le Bureau", raccourci),
    ("0", "🚪 Quitter", None),
]


def menu():
    from .synchro import adresse_github, recuperer
    if adresse_github():
        # À l'ouverture : on récupère ce qui a été fait sur l'autre PC ou par le robot.
        print(c("\n  🔄 Récupération des nouveautés depuis GitHub…", "gris"))
        recuperer(silencieux=True)
    while True:
        effacer_ecran()
        bandeau()
        panneau()
        titre("Que veux-tu faire ?")
        for cle, libelle, _ in CHOIX:
            if cle == "8" and os.name != "nt":
                continue  # raccourci Bureau : Windows uniquement
            print(f"   {c(' ' + cle + ' ', 'gras', 'rose')} {libelle}")
        choix = demander("Ton choix (chiffre puis Entrée)")
        action = next((a for k, _, a in CHOIX if k == choix), "inconnu")
        if action is None:
            print(c("\n  À bientôt, et bonnes affaires ! 👋\n", "rose"))
            return
        effacer_ecran()
        bandeau()
        if action == "inconnu":
            attention(f"« {choix} » n'est pas dans le menu.")
        else:
            try:
                action()
            except (ErreurConfig, requests.RequestException) as e:
                erreur(str(e))
            except Exception as e:  # le menu ne doit jamais se fermer brutalement
                logging.getLogger("veille").exception("Erreur inattendue : %s", e)
        pause()
