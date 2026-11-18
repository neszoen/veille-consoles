"""Filtrage, détection de l'état, score bon plan et marge de revente."""
from statistics import median

from .config import Recherche
from .modeles import Annonce
from .outils import contient, normaliser

# Mots qui indiquent une console HS / pour pièces (cherchés en début de mot :
# « defectueu » trouve « défectueux » et « défectueuse »).
MOTS_HS = [
    "hs", "h s", "pour piece", "pour pieces", "pieces detachees",
    "ne s allume", "s allume pas", "s allume plus",
    "ne fonctionne", "fonctionne pas", "fonctionne plus", "non fonctionnel",
    "ne marche", "marche pas", "marche plus", "en panne", "defectueu", "defaillant",
    "a reparer", "pour reparation", "pour bricoleur", "bricoleur",
    "ecran casse", "ecran fissure", "ecran fele", "ecran noir", "ecran hs",
    "ne charge", "charge pas", "ne lit", "lit pas", "ne demarre", "demarre pas",
]
# Mots étrangers (annonces espagnoles, italiennes, allemandes, anglaises, néerlandaises,
# portugaises, polonaises sur Vinted), cherchés en mots entiers pour éviter « Rotterdam ».
# Chaque mot est associé à sa traduction, affichée dans l'alerte.
TRADUCTIONS_HS = {
    # espagnol
    "rota": "cassée", "roto": "cassé", "averiada": "en panne", "averiado": "en panne",
    "no funciona": "ne fonctionne pas", "no enciende": "ne s'allume pas", "para piezas": "pour pièces",
    "para reparar": "à réparer", "pantalla rota": "écran cassé",
    # italien
    "rotto": "cassé", "rotta": "cassée", "guasta": "en panne", "guasto": "en panne",
    "non funziona": "ne fonctionne pas", "non funzionante": "ne fonctionne pas", "non si accende": "ne s'allume pas",
    "per pezzi": "pour pièces", "per ricambi": "pour pièces", "da riparare": "à réparer", "schermo rotto": "écran cassé",
    # allemand
    "defekt": "défectueuse", "kaputt": "cassée", "bastler": "pour bricoleur", "fur teile": "pour pièces",
    "funktioniert nicht": "ne fonctionne pas", "geht nicht an": "ne s'allume pas", "als ersatzteil": "pour pièces",
    # anglais
    "broken": "cassée", "for parts": "pour pièces", "not working": "ne fonctionne pas", "faulty": "défectueuse",
    "spares or repair": "pour pièces", "doesn t turn on": "ne s'allume pas", "won t turn on": "ne s'allume pas",
    "cracked screen": "écran fissuré",
    # néerlandais
    "kapot": "cassée", "defect": "défectueuse", "werkt niet": "ne fonctionne pas", "voor onderdelen": "pour pièces",
    # portugais
    "avariada": "en panne", "nao funciona": "ne fonctionne pas", "para pecas": "pour pièces", "nao liga": "ne s'allume pas",
    # polonais
    "uszkodzona": "endommagée", "uszkodzony": "endommagé", "nie dziala": "ne fonctionne pas", "na czesci": "pour pièces",
}
MOTS_HS_EXACTS = list(TRADUCTIONS_HS)
TRADUCTIONS_NON_TESTE = {
    "non testata": "non testée", "non testato": "non testé", "non provata": "non testée",
    "sin probar": "non testée", "no probada": "non testée", "no probado": "non testé",
    "nicht getestet": "non testée", "ungetestet": "non testée", "untested": "non testée", "not tested": "non testée",
    "niet getest": "non testée", "nao testada": "non testée", "nie testowana": "non testée",
}
TRADUCTIONS_OK = {
    "testata": "testée", "testato": "testé", "funzionante": "fonctionne", "funziona": "fonctionne",
    "perfettamente funzionante": "fonctionne parfaitement",
    "funciona": "fonctionne", "probada": "testée", "funciona perfectamente": "fonctionne parfaitement",
    "getestet": "testée", "funktioniert": "fonctionne", "voll funktionsfahig": "entièrement fonctionnelle",
    "working": "fonctionne", "tested": "testée", "fully working": "fonctionne parfaitement", "works": "fonctionne",
    "werkt": "fonctionne", "getest": "testée", "werkt perfect": "fonctionne parfaitement",
    "testada": "testée", "sprawna": "fonctionne", "dziala": "fonctionne", "przetestowana": "testée",
}
MOTS_OK_EXACTS = list(TRADUCTIONS_OK)
# Mots qui indiquent que le vendeur n'a pas vérifié (souvent risqué).
MOTS_NON_TESTE = [
    "non teste", "pas teste", "sans test", "non verifie", "pas verifie",
    "pas pu tester", "pas pu etre teste", "impossible de tester", "pas de chargeur pour tester",
]
# Mots qui indiquent une console qui marche.
MOTS_OK = [
    "fonctionne", "fonctionnel", "teste", "en etat de marche", "marche parfaitement",
    "marche tres bien", "marche bien", "parfait etat", "tres bon etat", "comme neuf",
    "bon etat de fonctionnement",
]

LIBELLES_ETAT = {
    "hs": "🔧 HS / pour pièces",
    "non_teste": "❓ non testée",
    "fonctionnel": "✅ fonctionnelle",
    "inconnu": "➖ non précisé",
}


def _chercher_etat(texte: str, annonce: Annonce | None = None) -> tuple[str, str] | None:
    """Cherche un indice d'état dans un texte normalisé. Renvoie (etat, mot trouvé) ou None."""
    for mot in MOTS_HS:
        if contient(texte, mot, prefixe=True):
            return "hs", mot
    for mot in MOTS_HS_EXACTS:
        if contient(texte, mot):
            return "hs", f"{mot} = {TRADUCTIONS_HS[mot]}"
    if annonce is not None and annonce.hs_site is True:
        return "hs", f"classée « {annonce.etat_site or 'pour pièces'} » par le site"
    for mot in MOTS_NON_TESTE:
        if contient(texte, mot, prefixe=True):
            return "non_teste", mot
    for mot in TRADUCTIONS_NON_TESTE:
        if contient(texte, mot):
            return "non_teste", f"{mot} = {TRADUCTIONS_NON_TESTE[mot]}"
    for mot in MOTS_OK:
        if contient(texte, mot, prefixe=True):
            return "fonctionnel", mot
    for mot in MOTS_OK_EXACTS:
        if contient(texte, mot):
            return "fonctionnel", f"{mot} = {TRADUCTIONS_OK[mot]}"
    return None


def detecter_etat(annonce: Annonce) -> tuple[str, str]:
    """Renvoie (etat, indice) à partir du titre, de la description et du site.

    Le titre ET la description sont lus ; un signe de panne l'emporte toujours
    (« testée, mais écran cassé » → HS). Les mots étrangers sont traduits dans l'indice.
    """
    titre = normaliser(annonce.titre)
    description = normaliser(annonce.description)
    dans_titre = _chercher_etat(titre, annonce)
    dans_desc = _chercher_etat(description) if description else None
    if dans_desc:
        dans_desc = (dans_desc[0], f"{dans_desc[1]}, lu dans la description")
    for etat in ("hs", "non_teste", "fonctionnel"):
        for trouve in (dans_titre, dans_desc):
            if trouve and trouve[0] == etat:
                return trouve
    if annonce.hs_site is False:
        return "fonctionnel", f"classée « {annonce.etat_site} » par le site"
    return "inconnu", ""


# Accessoires, pièces et jeux, en français et dans les langues fréquentes sur Vinted.
MOTS_ACCESSOIRES = set("""
chargeur cable cordon alimentation adaptateur transformateur batterie housse etui coque sacoche
pochette protection protege film verre stylet stylets skin sticker stickers autocollant carte memoire
memory ecran joystick stick bouton boutons nappe charniere vis tournevis boitier boite notice jeu jeux
support dock grip manette camera ecouteurs casque umd cartouche cartouches piece pieces
cargador funda carcasa protector bateria juego juegos caja soporte pantalla tapa mando repuesto
cavo caricabatterie caricatore alimentatore custodia cover batteria gioco giochi scatola pellicola
vetro lente schermo ricambio ricambi guscio scocca
ladekabel ladegerat netzteil hulle tasche akku spiel spiele schutzfolie displayschutz ersatz glas
charger case battery game games screen shell housing replacement lens controller
""".split())
PRIX_PLANCHER = 0.20
PREPOSITIONS = {"pour", "for", "para", "per", "fur", "compatible", "compatibile", "kompatibel"}


def est_accessoire(titre_normalise: str, rech: Recherche) -> bool:
    """« Chargeur pour PSP » = accessoire ; « PSP 3000 + chargeur » = console."""
    mots = titre_normalise.split()
    if not mots:
        return False
    if mots[0] in MOTS_ACCESSOIRES or (len(mots) > 1 and mots[0] in ("lot", "new", "neuf", "original", "officiel")
                                       and mots[1] in MOTS_ACCESSOIRES):
        return True
    for i, mot in enumerate(mots):
        if mot in MOTS_ACCESSOIRES:
            # accessoire suivi de près par « pour … <console> »
            for j in range(i + 1, min(i + 5, len(mots))):
                if mots[j] in PREPOSITIONS:
                    reste = " ".join(mots[j + 1:])
                    groupes = [o for g in rech.inclure for o in g.split("|") if o.strip()] or [rech.requete]
                    if any(contient(reste, o) for o in groupes):
                        return True
    return False


def correspond(annonce: Annonce, rech: Recherche, exclusions_globales: list) -> tuple[bool, str]:
    """Le titre contient-il les bons mots-clés, et aucun mot exclu ?"""
    titre = normaliser(annonce.titre)
    if est_accessoire(titre, rech):
        return False, "accessoire, pièce ou jeu"
    for groupe in rech.inclure:
        options = [o for o in groupe.split("|") if o.strip()]
        if options and not any(contient(titre, o) for o in options):
            return False, f"mot-clé absent : {groupe}"
    for mot in list(exclusions_globales) + list(rech.exclure):
        if contient(titre, mot):
            return False, f"mot exclu : {mot}"
    return True, ""


def passe_filtres(annonce: Annonce, rech: Recherche) -> tuple[bool, str]:
    """Prix maximum et état compatibles avec le mode de la recherche ?"""
    if rech.mode == "perso" and annonce.etat in ("hs", "non_teste"):
        return False, f"mode perso : état {annonce.etat}"
    limite = rech.prix_max
    if annonce.etat in ("hs", "non_teste") and rech.prix_max_hs:
        limite = rech.prix_max_hs
    if annonce.prix_total > limite:
        return False, f"trop cher : {annonce.prix_total} > {limite}"
    # Une console « en état » à moins de 20 % de sa valeur, c'est presque toujours
    # un accessoire, un jeu ou une arnaque. (Ne s'applique pas aux consoles HS.)
    revente = annonce.analyse.get("revente")
    if annonce.etat != "hs" and revente and annonce.prix_total < revente * PRIX_PLANCHER:
        return False, f"prix anormalement bas ({annonce.prix_total} €) : accessoire ou jeu ?"
    return True, ""


def analyser(annonce: Annonce, rech: Recherche, historique: list, cfg: dict) -> dict:
    """Calcule score bon plan et marge. Résultat aussi rangé dans annonce.analyse."""
    total = annonce.prix_total
    a = {
        "montrer_score": rech.mode in ("perso", "les_deux") and annonce.etat != "hs",
        "montrer_marge": rech.mode in ("revente", "les_deux"),
    }

    # Score bon plan : écart avec la médiane des consoles non HS déjà vues.
    prix_ok = [h["p"] for h in historique if h.get("e") != "hs"]
    a["nb_historique"] = len(prix_ok)
    mediane = median(prix_ok) if len(prix_ok) >= cfg["echantillon_min"] else None
    if mediane:
        a["mediane"] = round(mediane, 2)
        a["ecart_pct"] = round((mediane - total) / mediane * 100)

    # Marge : revente - achat - pièces - port de revente - frais de plateforme.
    revente = rech.prix_revente_ref or mediane
    if revente:
        pieces = (rech.cout_pieces or 0) if annonce.etat == "hs" else 0
        frais = revente * cfg["frais_plateforme_pct"] / 100
        port = cfg["frais_port_revente"]
        marge = revente - total - pieces - port - frais
        a.update({
            "revente": round(revente, 2),
            "revente_origine": "watchlist" if rech.prix_revente_ref else "historique",
            "pieces": pieces,
            "frais": round(frais, 2),
            "port_revente": port,
            "marge_eur": round(marge),
            "marge_pct": round(marge / total * 100) if total > 0 else None,
        })

    feu = False
    if a["montrer_score"] and a.get("ecart_pct", -999) >= cfg["seuil_bonne_affaire_pct"]:
        feu = True
    if (a["montrer_marge"] and a.get("marge_eur", -999) >= cfg["seuil_marge_eur"]
            and (a.get("marge_pct") or 0) >= cfg["seuil_marge_pct"]):
        feu = True
    a["feu"] = feu
    annonce.analyse = a
    return a


def interet(annonce: Annonce) -> float:
    """Sert à classer les annonces de la meilleure à la moins bonne."""
    a = annonce.analyse
    valeurs = []
    if a.get("montrer_marge") and a.get("marge_pct") is not None:
        valeurs.append(a["marge_pct"])
    if a.get("montrer_score") and a.get("ecart_pct") is not None:
        valeurs.append(a["ecart_pct"])
    return max(valeurs) if valeurs else -1000
