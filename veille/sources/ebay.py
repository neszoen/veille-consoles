"""eBay.fr via l'API officielle « Browse » (gratuite, fiable)."""
import logging
import os
import time
from urllib.parse import quote

import requests

from ..config import Recherche
from ..modeles import Annonce
from .base import ErreurSource, Source

log = logging.getLogger("veille")

URL_JETON = "https://api.ebay.com/identity/v1/oauth2/token"
URL_RECHERCHE = "https://api.ebay.com/buy/browse/v1/item_summary/search"
ETAT_POUR_PIECES = "7000"  # code eBay « Pour pièces ou ne fonctionne pas »


class EbaySource(Source):
    nom = "ebay"
    libelle = "eBay"
    delai = 0.5

    def __init__(self, cfg, session=None):
        super().__init__(cfg, session)
        self.client_id = os.environ.get("EBAY_CLIENT_ID", "").strip()
        self.client_secret = os.environ.get("EBAY_CLIENT_SECRET", "").strip()
        self._jeton = None
        self._expiration = 0.0

    def prete(self):
        if not (self.client_id and self.client_secret):
            return False, "EBAY_CLIENT_ID / EBAY_CLIENT_SECRET non configurés"
        return True, ""

    def jeton(self) -> str:
        if self._jeton and time.time() < self._expiration - 60:
            return self._jeton
        try:
            r = self.session.post(
                URL_JETON,
                auth=(self.client_id, self.client_secret),
                data={"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"},
                timeout=20,
            )
        except requests.RequestException as e:
            raise ErreurSource(f"connexion à eBay impossible : {e}")
        if r.status_code != 200:
            raise ErreurSource(f"eBay refuse les clés API (code {r.status_code}) : {r.text[:200]}")
        data = r.json()
        self._jeton = data["access_token"]
        self._expiration = time.time() + int(data.get("expires_in", 7200))
        return self._jeton

    def chercher(self, rech: Recherche) -> list[Annonce]:
        conf = self.cfg.get("ebay", {})
        filtres = ["priceCurrency:EUR"]
        if conf.get("pays_vendeur"):
            filtres.append(f"itemLocationCountry:{conf['pays_vendeur']}")
        filtres.append("buyingOptions:{FIXED_PRICE|AUCTION}" if conf.get("inclure_encheres", True)
                       else "buyingOptions:{FIXED_PRICE}")
        # Pas de filtre de prix ici : on garde toutes les annonces pour que
        # l'historique (médiane) ne soit pas faussé. Le prix max est appliqué après.
        params = {
            "q": rech.requete,
            "limit": int(conf.get("resultats_par_recherche", 50)),
            "sort": "newlyListed",
            "filter": ",".join(filtres),
        }
        cp = str(self.cfg.get("code_postal") or "").strip()
        contexte = quote(f"country=FR,zip={cp}" if cp else "country=FR", safe="")
        headers = {
            "Authorization": f"Bearer {self.jeton()}",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_FR",
            "X-EBAY-C-ENDUSERCTX": f"contextualLocation={contexte}",
            "Accept-Language": "fr-FR",
        }
        try:
            r = self.session.get(URL_RECHERCHE, params=params, headers=headers, timeout=30)
        except requests.RequestException as e:
            raise ErreurSource(f"connexion à eBay impossible : {e}")
        if r.status_code == 429:
            raise ErreurSource("quota d'appels eBay dépassé pour aujourd'hui")
        if r.status_code != 200:
            raise ErreurSource(f"réponse eBay inattendue (code {r.status_code}) : {r.text[:200]}")
        items = r.json().get("itemSummaries", []) or []
        return [a for a in (self._convertir(it) for it in items) if a]

    @staticmethod
    def _convertir(it: dict) -> Annonce | None:
        try:
            options = it.get("buyingOptions", []) or []
            enchere = "AUCTION" in options and "FIXED_PRICE" not in options
            prix_info = it.get("currentBidPrice") if enchere and it.get("currentBidPrice") else it.get("price")
            if not prix_info or prix_info.get("currency", "EUR") != "EUR":
                return None
            prix = float(prix_info["value"])

            couts = []
            for opt in it.get("shippingOptions", []) or []:
                cout = opt.get("shippingCost")
                if cout and cout.get("value") is not None:
                    couts.append(float(cout["value"]))
            port = min(couts) if couts else None

            image = (it.get("image") or {}).get("imageUrl")
            if not image and it.get("thumbnailImages"):
                image = it["thumbnailImages"][0].get("imageUrl")

            lieu = it.get("itemLocation") or {}
            localisation = " ".join(x for x in (lieu.get("postalCode", ""), lieu.get("city", "")) if x).strip()

            condition_id = str(it.get("conditionId", ""))
            return Annonce(
                source="ebay",
                id_source=str(it["itemId"]),
                titre=it.get("title", ""),
                prix=prix,
                url=it.get("itemWebUrl", ""),
                port=port,
                photo=image,
                description=it.get("shortDescription", "") or "",
                etat_site=it.get("condition", "") or "",
                hs_site=(condition_id == ETAT_POUR_PIECES) if condition_id else None,
                enchere=enchere,
                localisation=localisation,
                date=it.get("itemCreationDate", "") or "",
            )
        except (KeyError, ValueError, TypeError) as e:
            log.debug("Annonce eBay illisible ignorée : %s", e)
            return None
