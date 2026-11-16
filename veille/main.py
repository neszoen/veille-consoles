"""Une exécution complète : interroger les sources, analyser, alerter, sauvegarder."""
import logging
import random
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .analyse import analyser, correspond, detecter_etat, interet, passe_filtres
from .config import Recherche, charger_config, charger_watchlist
from .modeles import Annonce
from .outils import RACINE, euros
from .sources import LIBELLES, Source, construire_sources
from .sources.base import SourceBloquee
from .stockage import Stockage
from .telegram import Telegram, _e

log = logging.getLogger("veille")


def executer(simulation: bool = False, dossier_data: Path | None = None,
             sources: list[Source] | None = None, telegram: Telegram | None = None,
             recherches: list[Recherche] | None = None) -> dict:
    cfg = charger_config()
    if recherches is None:
        recherches, exclusions = charger_watchlist()
    else:
        _, exclusions = charger_watchlist()
    actives = [r for r in recherches if r.actif]
    store = Stockage(dossier_data or RACINE / "data")
    tg = telegram or Telegram.depuis_env(simulation)
    sources = construire_sources(cfg) if sources is None else sources
    bilan = {"annonces": 0, "nouvelles": 0, "alertes": 0, "sources_ok": 0, "sources_ko": 0}
    a_envoyer: list[Annonce] = []

    log.info("Début : %d recherche(s) active(s), %d source(s).", len(actives), len(sources))
    pretes = []
    for src in sources:
        pret, raison = src.prete()
        if not pret:
            log.warning("Source %s ignorée : %s", src.nom, raison)
        elif store.en_pause(src.nom, int(cfg["echecs_avant_alerte"]), float(cfg["pause_source_en_panne_h"])):
            log.info("Source %s en panne : prochain essai dans quelques heures.", src.nom)
        else:
            pretes.append(src)

    # Chaque site est interrogé en parallèle des autres (mais à son rythme, poliment) :
    # l'exécution reste courte, ce qui économise le quota GitHub.
    with ThreadPoolExecutor(max_workers=max(1, len(pretes))) as pool:
        collectes = list(pool.map(lambda s: collecter(s, actives), pretes))
    for src, (resultats, erreurs) in zip(pretes, collectes):
        for rech, annonces in resultats:
            bilan["annonces"] += len(annonces)
            a_envoyer += traiter(src, rech, annonces, exclusions, cfg, store, tg, bilan)
        if src.nom in bilan.get("demarrage", {}):
            _resume_demarrage(src, bilan["demarrage"].pop(src.nom), tg)
        _suivre_sante(src, len(resultats), erreurs, actives, cfg, store, tg, bilan)

    # Envoi des alertes, les meilleures d'abord.
    a_envoyer.sort(key=interet, reverse=True)
    maxi = int(cfg["alertes_max_par_execution"])
    for annonce in a_envoyer[:maxi]:
        if tg.annonce(annonce):
            store.marquer_alertee(annonce)
            bilan["alertes"] += 1
    reste = a_envoyer[maxi:]
    if reste:
        lignes = [f"➕ <b>{len(reste)} autres annonces</b> passent tes filtres :"]
        lignes += [f'• <a href="{_e(a.url)}">{_e(a.titre[:60])}</a> — {euros(a.prix_total)}' for a in reste[:30]]
        if tg.texte("\n".join(lignes)):
            for a in reste:
                store.marquer_alertee(a)

    store.sauvegarder()
    log.info("Fin : %(annonces)d annonces lues, %(nouvelles)d nouvelles, %(alertes)d alertes envoyées, "
             "sources OK %(sources_ok)d / en échec %(sources_ko)d.", bilan)
    return bilan


def collecter(src: Source, actives: list[Recherche]):
    """Lance toutes les recherches sur une source. Renvoie ([(recherche, annonces)], erreurs)."""
    resultats, erreurs = [], []
    for i, rech in enumerate(actives):
        if i:
            time.sleep(src.delai * random.uniform(1, 1.4))
        try:
            annonces = src.chercher(rech)
        except Exception as e:  # une recherche qui plante n'arrête pas les autres
            log.error("[%s] « %s » : échec — %s", src.nom, rech.nom, e)
            erreurs.append(str(e))
            if isinstance(e, SourceBloquee):
                break  # le site nous bloque : inutile d'insister
            continue
        resultats.append((rech, annonces))
    return resultats, erreurs


def traiter(src: Source, rech: Recherche, annonces: list[Annonce], exclusions: list,
            cfg: dict, store: Stockage, tg: Telegram, bilan: dict) -> list[Annonce]:
    """Analyse les annonces d'une recherche ; renvoie celles à alerter."""
    cle_init = f"{src.nom}|{rech.nom}"
    premiere_fois = not store.est_initialisee(cle_init)
    candidates = []
    for a in annonces:
        a.recherche = rech.nom
        ok, raison = correspond(a, rech, exclusions)
        if not ok:
            log.debug("  ignorée (%s) : %s", raison, a.titre)
            continue
        if store.vue_pour(a.uid, rech.nom):
            continue  # déjà traitée lors d'une exécution précédente
        bilan["nouvelles"] += 1
        a.etat, a.indice_etat = detecter_etat(a)
        if a.port is None:
            a.port, a.port_estime = float(cfg["frais_port_defaut"]), True
        analyser(a, rech, store.historique(rech.nom), cfg)
        store.ajouter_prix(rech.nom, a)
        store.marquer_vue(a.uid, rech.nom)
        ok, raison = passe_filtres(a, rech)
        if ok and not store.deja_alertee(a.uid):
            candidates.append(a)
        else:
            log.debug("  filtrée (%s) : %s", raison or "déjà alertée", a.titre)

    log.info("[%s] « %s » : %d annonces, %d retenues%s", src.nom, rech.nom, len(annonces),
             len(candidates), " (première exécution)" if premiere_fois else "")
    if premiere_fois:
        # Première fois : les annonces déjà en ligne ne déclenchent pas d'alerte
        # (sinon avalanche) ; elles servent à l'historique et au résumé de démarrage.
        store.marquer_initialisee(cle_init)
        for a in candidates:
            store.marquer_alertee(a, envoyee=False)
        bilan.setdefault("demarrage", {}).setdefault(src.nom, {"recherches": 0, "annonces": []})
        bilan["demarrage"][src.nom]["recherches"] += 1
        bilan["demarrage"][src.nom]["annonces"] += candidates
        return []
    return candidates


def _resume_demarrage(src: Source, infos: dict, tg: Telegram):
    """Un seul message par site lors de sa toute première exécution."""
    meilleures = sorted(infos["annonces"], key=interet, reverse=True)[:5]
    lignes = [f"🆕 <b>{LIBELLES.get(src.nom, src.nom)}</b> est maintenant surveillé "
              f"({infos['recherches']} recherche(s)). Les annonces déjà en ligne ont servi à "
              "construire l'historique des prix ; seules les <b>nouvelles</b> annonces seront signalées."]
    if meilleures:
        lignes.append("\nLes plus intéressantes en ce moment :")
        for a in meilleures:
            an = a.analyse
            extra = ""
            if an.get("montrer_marge") and an.get("marge_eur") is not None:
                extra = f" · marge {an['marge_eur']:+d} €"
            elif an.get("ecart_pct") is not None:
                extra = f" · {an['ecart_pct']} % sous la médiane"
            lignes.append(f'• <a href="{_e(a.url)}">{_e(a.titre[:55])}</a> — <b>{euros(a.prix_total)}</b>{extra}')
    tg.texte("\n".join(lignes))


def _suivre_sante(src, reussites, erreurs, actives, cfg, store, tg, bilan):
    if actives and reussites == 0:
        bilan["sources_ko"] += 1
        n = store.enregistrer_echec(src.nom, erreurs[0] if erreurs else "inconnue")
        log.error("Source %s en échec (%d fois de suite).", src.nom, n)
        if n == int(cfg["echecs_avant_alerte"]):
            if tg.texte(f"⚠️ <b>Source {LIBELLES.get(src.nom, src.nom)} en panne</b> "
                        f"({n} échecs de suite).\nDernière erreur : <code>{_e(erreurs[0][:300])}</code>\n"
                        "Les autres sources continuent de tourner."):
                store.marquer_alerte_panne(src.nom)
    else:
        bilan["sources_ok"] += 1
        if store.enregistrer_succes(src.nom):
            tg.texte(f"✅ Source {LIBELLES.get(src.nom, src.nom)} de nouveau opérationnelle.")
