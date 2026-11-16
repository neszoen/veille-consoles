"""Envoi des messages Telegram (ou affichage dans le terminal en simulation)."""
import html
import logging
import os
import re
import time

import requests

from .affichage import c, carte
from .analyse import LIBELLES_ETAT
from .modeles import Annonce
from .outils import euros
from .sources import LIBELLES

log = logging.getLogger("veille")

API = "https://api.telegram.org/bot{jeton}/{methode}"


class ErreurTelegram(Exception):
    pass


class Telegram:
    def __init__(self, jeton: str = "", chat_id: str = "", simulation: bool = False):
        self.jeton = (jeton or "").strip()
        self.chat_id = (chat_id or "").strip()
        self.simulation = simulation or not (self.jeton and self.chat_id)
        if self.simulation and not simulation:
            log.warning("TELEGRAM_TOKEN ou TELEGRAM_CHAT_ID absent : les messages sont "
                        "affichés ici au lieu d'être envoyés.")

    @classmethod
    def depuis_env(cls, simulation: bool = False) -> "Telegram":
        return cls(os.environ.get("TELEGRAM_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", ""), simulation)

    def appel(self, methode: str, **donnees):
        url = API.format(jeton=self.jeton, methode=methode)
        try:
            r = requests.post(url, data=donnees, timeout=30)
            reponse = r.json()
        except (requests.RequestException, ValueError) as e:
            # On retire le jeton du message d'erreur pour ne jamais l'afficher dans les logs.
            raise ErreurTelegram(str(e).replace(self.jeton, "***"))
        time.sleep(1.05)  # Telegram limite à ~1 message par seconde vers une même conversation
        if not reponse.get("ok"):
            raise ErreurTelegram(reponse.get("description", "erreur inconnue"))
        return reponse["result"]

    def texte(self, message_html: str) -> bool:
        if self.simulation:
            _afficher(message_html)
            return True
        try:
            self.appel("sendMessage", chat_id=self.chat_id, text=message_html,
                       parse_mode="HTML", disable_web_page_preview="true")
            return True
        except ErreurTelegram as e:
            log.error("Envoi Telegram impossible : %s", e)
            return False

    def annonce(self, annonce: Annonce) -> bool:
        message = formater_alerte(annonce)
        if self.simulation:
            _afficher(message, annonce.photo, annonce.url, couleur_annonce(annonce))
            return True
        if annonce.photo:
            try:
                self.appel("sendPhoto", chat_id=self.chat_id, photo=annonce.photo,
                           caption=message, parse_mode="HTML")
                return True
            except ErreurTelegram as e:
                log.warning("Photo refusée par Telegram (%s), envoi sans photo.", e)
        return self.texte(message)


def _afficher(message_html: str, photo: str | None = None, url: str | None = None,
              couleur: str = "magenta"):
    """Affiche le message dans le terminal, joliment, au lieu de l'envoyer."""
    texte = html.unescape(re.sub(r"<[^>]+>", "", message_html))
    lignes = [l for l in texte.splitlines() if l.strip()]
    if not lignes:
        return
    if url and lignes[-1].startswith("👉"):
        lignes[-1] = c("👉 " + url, "gris")
    if photo:
        lignes.insert(1, c("🖼  " + photo, "gris"))
    lignes[0] = c(lignes[0], "gras")
    carte(lignes, couleur)


def couleur_annonce(a: Annonce) -> str:
    if a.analyse.get("feu"):
        return "jaune"
    return {"hs": "magenta", "non_teste": "bleu", "fonctionnel": "vert"}.get(a.etat, "cyan")


def _e(texte) -> str:
    return html.escape(str(texte), quote=False)


def formater_alerte(a: Annonce) -> str:
    an = a.analyse
    emojis = ("🔥" if an.get("feu") else "") + ("🔧" if a.etat == "hs" else "") + ("📦" if an.get("lot") else "")
    titre = a.titre if len(a.titre) <= 150 else a.titre[:147] + "…"
    lignes = [f"{emojis} <b>{_e(titre)}</b>".strip(), ""]

    prix = f"💶 <b>{euros(a.prix_total)}</b>"
    if a.port:
        prix += f" ({euros(a.prix)} + {euros(a.port)} de port{' estimé' if a.port_estime else ''})"
    elif a.port == 0:
        prix += " (port gratuit)"
    prix += f" · {LIBELLES.get(a.source, a.source)}"
    if a.enchere:
        prix += " · ⏱ enchère en cours"
    lignes.append(prix)

    etat = f"État : {LIBELLES_ETAT.get(a.etat, a.etat)}"
    if a.indice_etat:
        etat += f" <i>({_e(a.indice_etat)})</i>"
    lignes.append(etat)

    if an.get("montrer_marge"):
        if "marge_eur" in an:
            signe = "+" if an["marge_eur"] >= 0 else ""
            pct = f" ({signe}{an['marge_pct']} %)" if an.get("marge_pct") is not None else ""
            lignes.append(f"💰 Marge estimée : <b>{signe}{an['marge_eur']} €</b>{pct}")
            detail = f"revente {euros(an['revente'])} − achat {euros(a.prix_total)}"
            if an.get("pieces"):
                detail += f" − pièces {euros(an['pieces'])}"
            detail += f" − port {euros(an['port_revente'])} − frais {euros(an['frais'])}"
            lignes.append(f"   <i>{detail}</i>")
        else:
            lignes.append("💰 Marge : prix de revente inconnu (ajoute prix_revente_ref)")

    if an.get("montrer_score"):
        if "ecart_pct" in an:
            e = an["ecart_pct"]
            sens = "sous" if e >= 0 else "au-dessus de"
            lignes.append(f"📊 {abs(e)} % {sens} la médiane ({euros(an['mediane'])})")
        else:
            lignes.append(f"📊 Score : historique en construction ({an.get('nb_historique', 0)} annonces)")

    info = f"🔎 {_e(a.recherche)}"
    if a.localisation:
        info += f" · 📍 {_e(a.localisation)}"
    lignes.append(info)
    lignes.append(f'<a href="{html.escape(a.url)}">👉 Voir l\'annonce</a>')
    return "\n".join(lignes)
