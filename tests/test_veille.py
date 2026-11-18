"""Tests automatiques : python -m unittest discover tests"""
import tempfile
import unittest

from veille.analyse import analyser, correspond, detecter_etat, passe_filtres
from veille.config import DEFAUTS, Recherche
from veille.main import executer
from veille.modeles import Annonce
from veille.outils import contient, normaliser
from veille.sources.base import ErreurSource, Source
from veille.sources.ebay import EbaySource
from veille.telegram import Telegram, formater_alerte

CFG = dict(DEFAUTS)


def annonce(titre, prix=30, port=5, **kw):
    return Annonce("test", kw.pop("id", titre), titre, prix, "https://x.fr", port=port, **kw)


PSP = Recherche(nom="PSP 3000", requete="psp 3000", inclure=["psp", "3000 | 3004"],
                prix_max=60, prix_max_hs=30, mode="les_deux", prix_revente_ref=80, cout_pieces=15)


class TestTexte(unittest.TestCase):
    def test_normaliser(self):
        self.assertEqual(normaliser("Écran CASSÉ, ne s'allume pas !"), "ecran casse ne s allume pas")

    def test_mots_entiers(self):
        self.assertTrue(contient("console tres recherchee", "recherchee"))
        self.assertFalse(contient("console tres recherchee", "recherche"))
        self.assertTrue(contient("console testee", "teste", prefixe=True))


class TestEtat(unittest.TestCase):
    def cas(self, titre, attendu, **kw):
        self.assertEqual(detecter_etat(annonce(titre, **kw))[0], attendu, titre)

    def test_etats(self):
        self.cas("PSP 3004 HS", "hs")
        self.cas("PSP 3000 ne s'allume plus", "hs")
        self.cas("PSP 3000 écran fissuré", "hs")
        self.cas("PSP 3000 ne fonctionne pas", "hs")
        self.cas("PSP 3000 non testée", "non_teste")
        self.cas("PSP 3000 testée et fonctionnelle", "fonctionnel")
        self.cas("PSP 3000 noire", "inconnu")
        self.cas("PSP 3000 noire", "hs", hs_site=True, etat_site="Pour pièces")
        self.cas("PSP 3000 noire", "fonctionnel", hs_site=False, etat_site="Occasion")


class TestFiltres(unittest.TestCase):
    def test_mots_cles(self):
        self.assertTrue(correspond(annonce("Sony PSP-3004 noire"), PSP, [])[0])
        self.assertFalse(correspond(annonce("Sony PSP 1004"), PSP, [])[0])
        self.assertFalse(correspond(annonce("Coque seule PSP 3000"), PSP, ["coque seule"])[0])

    def test_accessoires(self):
        for titre in ["Chargeur usb pour PlayStation psp 1000 2000 3000 neuf",
                      "Cavo USB di alimentazione per Sony PSP 1000/2000/3000/E1000",
                      "Funda + protector pantalla PSP 2000 3000",
                      "Housse de protection pour PSP 3000"]:
            self.assertFalse(correspond(annonce(titre), PSP, [])[0], titre)
        for titre in ["PSP 3000 + chargeur + 3 jeux", "Sony PSP 3004 noire avec housse",
                      "Console PSP 3000 rouge", "Lot PSP 3000 et jeux"]:
            self.assertTrue(correspond(annonce(titre), PSP, [])[0], titre)

    def test_prix_et_mode(self):
        a = annonce("PSP 3000", prix=50, port=5)
        a.etat = "fonctionnel"
        self.assertTrue(passe_filtres(a, PSP)[0])
        a.etat = "hs"
        self.assertFalse(passe_filtres(a, PSP)[0])  # 55 € > prix_max_hs 30 €
        perso = Recherche(nom="p", requete="p", prix_max=100, mode="perso")
        self.assertFalse(passe_filtres(a, perso)[0])


class TestCalculs(unittest.TestCase):
    def test_marge_hs(self):
        a = annonce("PSP 3000 HS", prix=15, port=5)
        a.etat = "hs"
        an = analyser(a, PSP, [], CFG)
        # 80 - 20 - 15 pièces - 6 port - 8 frais = 31
        self.assertEqual(an["marge_eur"], 31)
        self.assertEqual(an["marge_pct"], 155)
        self.assertTrue(an["feu"])

    def test_score_mediane(self):
        hist = [{"p": p, "e": "fonctionnel"} for p in (70, 75, 80, 85, 90)] + [{"p": 10, "e": "hs"}]
        a = annonce("PSP 3000", prix=55, port=5)
        a.etat = "fonctionnel"
        an = analyser(a, PSP, hist, CFG)
        self.assertEqual(an["mediane"], 80)
        self.assertEqual(an["ecart_pct"], 25)

    def test_pas_assez_historique(self):
        a = annonce("PSP 3000", prix=55)
        an = analyser(a, Recherche(nom="x", requete="x", prix_max=60), [{"p": 80, "e": "ok"}], CFG)
        self.assertNotIn("mediane", an)
        self.assertIn("historique en construction", formater_alerte(a))


class FausseSource(Source):
    nom = "fausse"
    delai = 0

    def __init__(self, annonces=None, erreur=False):
        super().__init__(CFG)
        self.annonces, self.erreur = annonces or [], erreur

    def chercher(self, rech):
        if self.erreur:
            raise ErreurSource("site indisponible")
        return [Annonce(**a.__dict__) for a in self.annonces]


class Memoire(Telegram):
    def __init__(self):
        super().__init__(simulation=True)
        self.messages = []

    def texte(self, m):
        self.messages.append(m)
        return True

    def annonce(self, a):
        self.messages.append(formater_alerte(a))
        return True


class TestExecution(unittest.TestCase):
    def test_dedoublonnage_et_panne(self):
        dossier = tempfile.mkdtemp()
        anciennes = [annonce(f"PSP 3000 {i}", prix=70, id=f"a{i}") for i in range(6)]
        tg = Memoire()
        executer(dossier_data=dossier, sources=[FausseSource(anciennes)], telegram=tg, recherches=[PSP])
        self.assertEqual(len(tg.messages), 1)  # résumé de première exécution seulement

        nouvelle = annonce("PSP 3000 testée", prix=40, id="n1")
        tg = Memoire()
        bilan = executer(dossier_data=dossier, sources=[FausseSource(anciennes + [nouvelle])],
                         telegram=tg, recherches=[PSP])
        self.assertEqual(bilan["alertes"], 1)
        self.assertIn("PSP 3000 testée", tg.messages[0])

        tg = Memoire()
        bilan = executer(dossier_data=dossier, sources=[FausseSource(anciennes + [nouvelle])],
                         telegram=tg, recherches=[PSP])
        self.assertEqual(bilan["alertes"], 0)  # jamais deux fois la même annonce

        tg = Memoire()
        for _ in range(3):
            executer(dossier_data=dossier, sources=[FausseSource(erreur=True)], telegram=tg, recherches=[PSP])
        self.assertEqual(sum("en panne" in m for m in tg.messages), 1)


class TestEmailLeboncoin(unittest.TestCase):
    def test_extraction(self):
        from veille.sources.email_leboncoin import extraire_annonces
        courriel = """
        <table><tr><td>
          <a href="https://www.leboncoin.fr/ad/consoles/3309285539?utm_source=alerte">
            <img src="https://img.leboncoin.fr/a.jpg" alt="PSP 3000 noire"></a>
          <a href="https://www.leboncoin.fr/ad/consoles/3309285539?utm_source=alerte">PSP 3000 noire + chargeur</a>
          <p>45 €</p><p>Lyon 69003</p>
        </td></tr><tr><td>
          <a href="https://trk.exemple.com/c?u=https%3A%2F%2Fwww.leboncoin.fr%2Fad%2Fconsoles%2F3310000001">
            Nintendo DS Lite HS &amp; pièces <span>1&nbsp;200 €</span></a>
          <a href="https://www.leboncoin.fr/ad/consoles/3310000001">Voir l'annonce</a>
        </td></tr></table>
        <a href="https://www.leboncoin.fr/mes-recherches">Gérer mes alertes</a>"""
        annonces = {a.id_source: a for a in extraire_annonces(courriel)}
        self.assertEqual(set(annonces), {"3309285539", "3310000001"})
        self.assertEqual(annonces["3309285539"].titre, "PSP 3000 noire + chargeur")
        self.assertEqual(annonces["3309285539"].prix, 45)
        self.assertEqual(annonces["3309285539"].photo, "https://img.leboncoin.fr/a.jpg")
        self.assertEqual(annonces["3310000001"].titre, "Nintendo DS Lite HS & pièces")
        self.assertEqual(annonces["3310000001"].prix, 1200)


class TestEbay(unittest.TestCase):
    def test_conversion(self):
        it = {
            "itemId": "v1|123|0", "title": "Console Sony PSP 3004 pour pièces",
            "price": {"value": "19.90", "currency": "EUR"}, "itemWebUrl": "https://www.ebay.fr/itm/123",
            "conditionId": "7000", "condition": "Pour pièces ou ne fonctionne pas",
            "buyingOptions": ["FIXED_PRICE"], "image": {"imageUrl": "https://i.ebayimg.com/a.jpg"},
            "shippingOptions": [{"shippingCost": {"value": "5.50", "currency": "EUR"}}],
            "itemLocation": {"postalCode": "69***", "country": "FR"},
        }
        a = EbaySource._convertir(it)
        self.assertEqual((a.prix, a.port, a.prix_total, a.hs_site), (19.9, 5.5, 25.4, True))


if __name__ == "__main__":
    unittest.main()


class TestDescription(unittest.TestCase):
    def test_etat_lu_dans_la_description(self):
        a = annonce("Sony PSP 3004", description="Console testata e perfettamente funzionante, con caricatore")
        etat, indice = detecter_etat(a)
        self.assertEqual(etat, "fonctionnel")
        self.assertIn("description", indice)

    def test_panne_dans_la_description_l_emporte(self):
        a = annonce("PSP 3000 testée", description="Ne s'allume plus depuis une chute")
        self.assertEqual(detecter_etat(a)[0], "hs")

    def test_traductions(self):
        cas = {"PSP defekt": ("hs", "défectueuse"), "PSP no funciona": ("hs", "ne fonctionne pas"),
               "PSP werkt niet": ("hs", "ne fonctionne pas"), "PSP nicht getestet": ("non_teste", "non testée"),
               "PSP sprawna": ("fonctionnel", "fonctionne")}
        for titre, (etat, traduction) in cas.items():
            e, indice = detecter_etat(annonce(titre))
            self.assertEqual(e, etat, titre)
            self.assertIn(traduction, indice, titre)

    def test_extraire_description(self):
        from veille.sources.web import extraire_description
        page = ('<meta property="og:description" content="PSP">'
                '<script type="application/ld+json">{"@type":"Product","name":"PSP",'
                '"description":"Console non testée, vendue en l&#39;état"}</script>')
        self.assertEqual(extraire_description(page), "Console non testée, vendue en l'état")
        self.assertEqual(extraire_description('<meta name="description" content="Écran rayé mais fonctionne bien">'),
                         "Écran rayé mais fonctionne bien")

    def test_description_lue_avant_alerte(self):
        class SourceAvecDescription(Source):
            nom = "test"
            def chercher(self, rech):
                return [annonce("PSP 3004", prix=20, id="d1")]
            def completer(self, a):
                a.description = "Ecran noir, pour pieces"
                return True
        dossier = tempfile.mkdtemp()
        tg = Telegram(simulation=True)
        src = SourceAvecDescription(CFG)
        executer(dossier_data=dossier, sources=[SourceVide(CFG)], telegram=tg, recherches=[PSP])
        from veille.stockage import Stockage
        s = Stockage(dossier); s.marquer_initialisee("test|PSP 3000"); s.sauvegarder()
        executer(dossier_data=dossier, sources=[src], telegram=tg, recherches=[PSP])
        etats = [p["e"] for p in Stockage(dossier).historique("PSP 3000")]
        self.assertEqual(etats, ["hs"])


class SourceVide(Source):
    nom = "vide"
    def chercher(self, rech):
        return []
