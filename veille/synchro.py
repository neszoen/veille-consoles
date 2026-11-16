"""Synchronisation avec GitHub : travailler sur le projet depuis plusieurs PC.

Principe : GitHub garde la version de référence. Chaque PC « récupère » les
nouveautés (code, watchlist, données du robot) puis « envoie » ses propres
modifications. Les secrets (.env) ne sont jamais envoyés.
"""
import re
import shutil
import subprocess

from .affichage import attention, c, erreur, info, ok, titre
from .outils import RACINE

NOMS_LISIBLES = {
    "watchlist.yaml": "ta watchlist",
    "config.yaml": "les réglages",
    "README.md": "le guide",
}


def git(*args, capture=True, timeout=120) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=RACINE, capture_output=capture, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def git_installe() -> bool:
    return shutil.which("git") is not None


def adresse_github() -> str:
    if not git_installe() or not (RACINE / ".git").exists():
        return ""
    r = git("remote", "get-url", "origin")
    return r.stdout.strip() if r.returncode == 0 else ""


def _identite_ok() -> bool:
    return bool(git("config", "user.name").stdout.strip() and git("config", "user.email").stdout.strip())


def _demander(question, defaut=""):
    from .interface import demander
    return demander(question, defaut)


def _configurer_identite():
    info("Git doit savoir qui signe les modifications (c'est visible seulement dans ton repo privé).")
    pseudo = _demander("Ton pseudo GitHub")
    if not pseudo:
        return False
    email_defaut = f"{pseudo}@users.noreply.github.com"
    info(f"Pour rester discret, on peut utiliser l'adresse anonyme de GitHub : {c(email_defaut, 'gras')}")
    email = _demander("Adresse e-mail à utiliser", email_defaut)
    git("config", "user.name", pseudo)
    git("config", "user.email", email)
    ok("Identité enregistrée pour ce projet.")
    return True


def relier_github() -> bool:
    """Première fois : relie ce dossier à un repo GitHub privé et envoie le projet."""
    titre("Relier le projet à GitHub")
    if not git_installe():
        erreur("Git n'est pas installé sur ce PC.")
        info("Installe-le depuis https://git-scm.com/download/win (options par défaut), puis relance.")
        return False
    if not (RACINE / ".git").exists():
        git("init", "-b", "main")
    if not _identite_ok() and not _configurer_identite():
        return False

    print(f"""
  {c('1.', 'rose', 'gras')} Va sur {c('https://github.com/new', 'cyan')}
  {c('2.', 'rose', 'gras')} Repository name : {c('veille-consoles', 'gras')}  ·  coche {c('Private', 'gras')} 🔒
  {c('3.', 'rose', 'gras')} Ne coche RIEN d'autre (ni README, ni .gitignore), puis {c('Create repository', 'gras')}
  {c('4.', 'rose', 'gras')} Copie l'adresse affichée (https://github.com/…/veille-consoles.git)""")
    adresse = _demander("Colle l'adresse du repo")
    if not re.match(r"^https://github\.com/[\w.-]+/[\w.-]+?(\.git)?/?$", adresse):
        erreur("Ça ne ressemble pas à une adresse de repo GitHub (https://github.com/pseudo/nom.git).")
        return False
    if adresse_github():
        git("remote", "set-url", "origin", adresse)
    else:
        git("remote", "add", "origin", adresse)

    git("add", "-A")
    if git("diff", "--cached", "--quiet").returncode != 0:
        git("commit", "-q", "-m", "Version initiale de la veille consoles")
    info("Envoi vers GitHub… Une fenêtre de connexion GitHub peut s'ouvrir : connecte-toi.")
    r = git("push", "-u", "origin", "main", capture=False, timeout=600)
    if r.returncode != 0:
        erreur("L'envoi a échoué. Vérifie que le repo est bien vide et que tu es connecté au bon compte.")
        return False
    ok(f"Projet envoyé sur GitHub 🎉  {c(adresse, 'cyan')}")
    attention("N'oublie pas d'ajouter les secrets sur GitHub (README, étape « secrets »).")
    return True


def recuperer(silencieux: bool = False) -> bool:
    """Récupère les nouveautés de GitHub (code, watchlist, données du robot)."""
    if not adresse_github():
        return False
    avant = git("rev-parse", "HEAD").stdout.strip()
    try:
        r = git("pull", "--rebase", "--autostash", "-q", timeout=60)
    except subprocess.TimeoutExpired:
        if not silencieux:
            attention("GitHub ne répond pas (connexion internet ?). On continue avec la version de ce PC.")
        return False
    if r.returncode != 0:
        git("rebase", "--abort")
        if not silencieux or "conflict" in (r.stdout + r.stderr).lower():
            erreur("Impossible de récupérer les nouveautés : la même chose a été modifiée ici et ailleurs.")
            info("Rien n'est perdu. Demande de l'aide pour fusionner (ou annule tes modifications locales).")
        return False
    apres = git("rev-parse", "HEAD").stdout.strip()
    if avant != apres:
        nb = git("rev-list", "--count", f"{avant}..{apres}").stdout.strip()
        ok(f"{nb} nouveauté(s) récupérée(s) depuis GitHub.")
    elif not silencieux:
        ok("Déjà à jour avec GitHub.")
    return True


def modifications_locales() -> list[str]:
    r = git("status", "--porcelain")
    return [ligne[3:].strip().strip('"') for ligne in r.stdout.splitlines() if ligne.strip()]


def envoyer(message: str | None = None) -> bool:
    fichiers = modifications_locales()
    if not fichiers:
        ok("Rien à envoyer : GitHub a déjà tout.")
        return True
    info("Modifications à envoyer :")
    for f in fichiers:
        print(f"     {c('•', 'rose')} {f} {c('(' + NOMS_LISIBLES[f] + ')', 'gris') if f in NOMS_LISIBLES else ''}")
    message = message or _demander("Décris ta modification en quelques mots", "Modifications depuis le menu")
    git("add", "-A")
    git("commit", "-q", "-m", message)
    r = git("push", "-q", capture=False, timeout=300)
    if r.returncode != 0:
        # Quelqu'un (le robot) a envoyé entre-temps : on récupère puis on réessaie.
        if recuperer(silencieux=True) and git("push", "-q", capture=False, timeout=300).returncode == 0:
            ok("Modifications envoyées sur GitHub ✨")
            return True
        erreur("L'envoi a échoué (connexion internet ?). Tes modifications sont gardées sur ce PC ; réessaie plus tard.")
        return False
    ok("Modifications envoyées sur GitHub ✨")
    return True


def synchroniser():
    titre("Synchroniser avec GitHub")
    if not adresse_github():
        info("Ce dossier n'est pas encore relié à GitHub. On le fait maintenant (une seule fois).")
        relier_github()
        return
    if not _identite_ok() and not _configurer_identite():
        return
    info("1/2 · Récupération des nouveautés…")
    if not recuperer():
        return
    info("2/2 · Envoi de tes modifications…")
    envoyer()
