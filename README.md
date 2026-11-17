# 🎮 Veille bons plans consoles rétro

Un petit robot qui surveille les annonces de consoles d'occasion et t'envoie
une alerte Telegram quand une bonne affaire apparaît :

- **achat perso** : une console qui marche, moins chère que d'habitude ;
- **achat-revente** : une console HS ou pour pièces, avec la **marge estimée** après réparation.

Il tourne tout seul sur GitHub, toutes les 30 minutes, même quand ton PC est éteint.

```
GitHub Actions (toutes les 30 min)
   │
   ├─ lit ta watchlist.yaml
   ├─ interroge eBay, Vinted, Label Emmaüs + lit les alertes e-mail Leboncoin
   ├─ écarte accessoires, jeux et annonces déjà vues  ← data/vues.json
   ├─ devine l'état (HS, testée…), calcule le score et la marge
   │                                                  ← data/prix.json (historique)
   ├─ envoie les alertes sur Telegram 📱
   └─ enregistre ses données dans le repo
```

---

## ▶ Lancer le logiciel

**Double-clique sur l'icône « Veille consoles » 🎮 de ton Bureau**
(ou sur `Veille.bat` dans le dossier du projet).

La première fois, il s'installe tout seul (environ 1 minute). Ensuite, **le logiciel s'ouvre
dans sa propre fenêtre**, avec des boutons à cliquer :

| Écran | Ce qu'on y fait |
|---|---|
| 🏠 **Accueil** | Les dernières alertes du robot (photo, prix, marge), l'état des sites, les boutons « Lancer une veille » et « Démonstration ». |
| 📊 **Prix** | La répartition des prix relevés par console, la médiane, et les **prix conseillés** à appliquer en un clic. |
| 📋 **Watchlist** | Ajouter, modifier, mettre en pause ou supprimer une console, gérer les mots exclus. Plus besoin d'ouvrir le fichier. |
| 🔍 **Tester** | Voir tout de suite ce qu'un site renvoie pour une recherche. |
| 👤 **Comptes** | Telegram, eBay, Gmail et GitHub avec des assistants pas à pas, l'accès depuis le téléphone, le raccourci Bureau. |

Après une modification, clique sur **Synchroniser** (en bas à gauche) pour l'envoyer à GitHub :
le robot l'utilisera à son prochain passage. Le logiciel récupère tout seul les nouveautés de
GitHub à l'ouverture.

**Sur ton téléphone :** Comptes → « Sur mon téléphone » → active l'interrupteur et scanne le
QR code (le téléphone doit être sur le même Wi-Fi, et le PC allumé avec le logiciel ouvert).

Le logiciel s'arrête tout seul quelques minutes après la fermeture de la fenêtre.

> L'ancien menu dans le terminal existe toujours : `Veille.bat menu` (ou `./veille.sh menu`).

> Si l'icône a disparu du Bureau, double-clique sur `Veille.bat`, puis Comptes → Raccourci Bureau.

---

## Sommaire

1. [Les sites surveillés](#1-les-sites-surveillés)
2. [Créer ton bot Telegram](#2-créer-ton-bot-telegram)
3. [Obtenir les clés API eBay](#3-obtenir-les-clés-api-ebay)
4. [Leboncoin par e-mail (Gmail)](#4-leboncoin-par-e-mail-gmail)
5. [Mettre le projet sur GitHub](#5-mettre-le-projet-sur-github)
6. [Configurer les secrets GitHub](#6-configurer-les-secrets-github)
7. [Lancer et vérifier](#7-lancer-et-vérifier)
8. [Travailler depuis un autre PC](#8-travailler-depuis-un-autre-pc)
9. [Ajouter ou modifier une recherche](#9-ajouter-ou-modifier-une-recherche)
10. [Comprendre une alerte](#10-comprendre-une-alerte)
11. [Fréquence et quota gratuit GitHub](#11-fréquence-et-quota-gratuit-github)
12. [Dépannage](#12-dépannage)

---

## 1. Les sites surveillés

| Site | Comment | Depuis GitHub (cloud) | Remarques |
|---|---|---|---|
| **eBay.fr** | API officielle | ✅ fiable | Clés gratuites à créer (étape 3). |
| **Vinted** | lecture de la page de résultats | ⚠️ à confirmer au 1ᵉʳ lancement | Catégorie « Consoles » uniquement. Annonces aussi d'Espagne, d'Italie, d'Allemagne. Port estimé à 4 €. |
| **Leboncoin** | **alertes e-mail** lues dans Gmail | ✅ | Leboncoin bloque les robots, même depuis un PC normal : on passe par ses propres e-mails d'alerte (étape 4). |
| **Label Emmaüs** | lecture de la page de résultats | ✅ | Boutique solidaire, peu de consoles mais à petit prix. |
| ~~Rakuten~~ | — | — | La marketplace Rakuten France **a fermé**. |

Chaque site est indépendant : si l'un tombe en panne, les autres continuent. Après 3 échecs
de suite, tu reçois **« ⚠️ source X en panne »** sur Telegram, puis l'outil ne réessaie ce site
que toutes les 3 heures (pour ne pas insister). Un message ✅ arrive quand il refonctionne.

Les sites sont interrogés **poliment** : 3 à 4 secondes entre deux pages d'un même site,
quelques pages par demi-heure seulement.

---

## 2. Créer ton bot Telegram

1. Dans Telegram, cherche **@BotFather** (il a un badge bleu ✔️) et ouvre la conversation.
2. Envoie `/newbot`.
3. Il demande un **nom** : par exemple `Veille Consoles`.
4. Il demande un **identifiant** qui doit finir par `bot`, par exemple `ma_veille_consoles_bot`.
5. Il te répond avec un **jeton** (token) qui ressemble à
   `7123456789:AAH...xyz`. **C'est un mot de passe** : ne le partage pas.

👉 Ouvre ensuite le logiciel : **2 – Configurer mes comptes → Telegram**. L'assistant vérifie
le jeton, te demande d'envoyer « bonjour » à ton bot, trouve tout seul le numéro de ta
conversation (*chat id*) et t'envoie un message de test.

## 3. Obtenir les clés API eBay

L'API eBay est **gratuite** (5 000 recherches par jour, largement assez).

1. Va sur <https://developer.ebay.com> et clique sur **Register** (en haut à droite).
   Crée un compte développeur (il est distinct de ton compte eBay acheteur).
2. Confirme ton e-mail. ⏳ eBay vérifie parfois les nouveaux comptes : ça peut prendre
   **de quelques heures à quelques jours**.
3. Une fois accepté, ouvre le menu à ton nom → **Application Keysets**.
4. Donne un nom à l'application (ex. `veille-consoles`) et crée un jeu de clés **Production**
   (pas *Sandbox*, qui est un faux eBay de test).
5. eBay peut afficher que tes clés Production sont **désactivées** tant que tu n'as pas réglé
   les « notifications de suppression de compte ». Clique sur le lien proposé, puis choisis
   l'**exemption** (« I do not persist eBay data », je ne conserve pas les données des membres
   eBay). C'est vrai pour cet outil : il ne garde ni noms ni adresses de vendeurs.
6. Recopie deux valeurs : **App ID (Client ID)** et **Cert ID (Client Secret)**.
   (Le *Dev ID* ne sert pas.)

👉 Dans le logiciel : **2 – Configurer mes comptes → eBay**, colle les deux valeurs,
l'assistant vérifie qu'eBay les accepte. Puis **3 – Tester une recherche** pour voir de vraies annonces.

## 4. Leboncoin par e-mail (Gmail)

Leboncoin bloque les programmes qui lisent son site. En revanche, **il envoie lui-même
des alertes par e-mail** quand une annonce correspond à une recherche enregistrée.
L'outil lit ces e-mails (en **lecture seule** : rien n'est supprimé ni marqué comme lu).

**A. Sur Leboncoin** (connecté à ton compte) :
1. Cherche par exemple `psp`, choisis la catégorie **Consoles**.
2. Clique sur **Enregistrer la recherche** et active les **alertes par e-mail**.
3. Recommence pour chaque console de ta watchlist (DS Lite, Game Boy…).
   Pas besoin d'être précis : l'outil refiltre tout avec ta watchlist (prix, mots exclus, état).

**B. Sur ton compte Google** (celui qui reçoit les e-mails de Leboncoin) :
1. Active la **Validation en deux étapes** : <https://myaccount.google.com/signinoptions/twosv>
2. Va sur <https://myaccount.google.com/apppasswords>, crée un mot de passe nommé `veille`.
3. Google affiche un **code de 16 lettres** : copie-le (il ne sera plus jamais affiché).

> 🔐 Ce code donne accès à la boîte mail. Il reste sur ton PC (`.env`) et dans les secrets
> GitHub, et tu peux le révoquer à tout moment sur la même page. Pour plus de tranquillité,
> tu peux utiliser une **adresse Gmail dédiée** et y faire suivre les e-mails de Leboncoin.

**C. Dans le logiciel** : **2 – Configurer mes comptes → Gmail**. L'assistant teste la
connexion et affiche les annonces trouvées dans tes e-mails.

> ℹ️ Leboncoin peut regrouper ses e-mails d'alerte : ces annonces arrivent parfois avec un
> peu de retard par rapport à l'application. Si l'assistant dit qu'il trouve des e-mails mais
> « n'a pas su en lire les annonces », signale-le : le format de l'e-mail a changé et la
> lecture doit être ajustée.

## 5. Mettre le projet sur GitHub

Le code vit dans un **repo privé** sur GitHub : c'est là que tourne le robot, et c'est ce qui
te permet de travailler depuis plusieurs PC.

1. Ouvre le logiciel → **7 – Synchroniser avec GitHub**.
2. L'assistant te demande ton pseudo GitHub (et propose l'adresse e-mail anonyme de GitHub).
3. Il te fait créer le repo :
   - sur <https://github.com/new>, **Repository name** : `veille-consoles`
   - coche **Private** 🔒, ne coche **rien** d'autre, puis **Create repository**
   - copie l'adresse affichée (`https://github.com/…/veille-consoles.git`) et colle-la dans l'assistant.
4. Il envoie le projet. La première fois, une **fenêtre de connexion GitHub** s'ouvre : connecte-toi.

## 6. Configurer les secrets GitHub

Les secrets sont stockés chiffrés par GitHub, jamais visibles dans le code ni dans les logs.

1. Sur la page de ton repo : **Settings** → **Secrets and variables** → **Actions**.
2. Clique sur **New repository secret** pour chacun (nom exact, en majuscules).
   Toutes les valeurs sont dans le fichier **`.env`** du projet (ouvre-le avec le Bloc-notes).

| Name | Secret |
|---|---|
| `TELEGRAM_TOKEN` | le jeton donné par BotFather |
| `TELEGRAM_CHAT_ID` | le numéro trouvé par l'assistant Telegram |
| `EBAY_CLIENT_ID` | l'App ID eBay |
| `EBAY_CLIENT_SECRET` | le Cert ID eBay |
| `GMAIL_ADRESSE` | l'adresse Gmail qui reçoit les alertes Leboncoin |
| `GMAIL_MOT_DE_PASSE_APPLI` | le code Google de 16 lettres |

Un secret manquant n'est pas grave : le site correspondant est simplement ignoré.

## 7. Lancer et vérifier

1. Onglet **Actions** du repo → **Veille consoles** → bouton **Run workflow**.
2. Après environ 1 minute, la ligne passe au vert ✅. Clique dessus puis sur
   **Lancer la veille** pour lire le journal (tu y verras quels sites ont répondu).
3. Sur Telegram, tu reçois **un message 🆕 par site** : c'est la première exécution.
   Les annonces déjà en ligne servent à construire l'historique des prix ; le message liste
   les 5 plus intéressantes. Ensuite, **seules les nouvelles annonces** déclenchent une alerte.
4. Ensuite, tout se fait seul toutes les 30 minutes.

Si une exécution échoue (❌ rouge), GitHub t'envoie aussi un e-mail.

## 8. Travailler depuis un autre PC

GitHub garde la version de référence ; chaque ordinateur en a une copie.
Prérequis : le projet est déjà relié à GitHub depuis ton PC Windows (étape 5).

### Depuis un Chromebook (ou n'importe quel ordinateur, sans rien installer)

On utilise **GitHub Codespaces** : le logiciel tourne sur un ordinateur de GitHub et s'affiche
dans un onglet Chrome, avec exactement le même menu.

**La première fois :**
1. Dans Chrome, ouvre ton repo : `https://github.com/TON-PSEUDO/veille-consoles` (connecté à ton compte).
2. Clique sur le bouton vert **`<> Code`** → onglet **Codespaces** → **Create codespace on main**.
   La préparation prend 1 à 2 minutes la première fois.
3. Un éditeur s'ouvre dans l'onglet, avec un **terminal** en bas. Tape :
   ```
   ./veille.sh
   ```
   puis Entrée : le menu apparaît. (Si le terminal n'est pas visible : menu ☰ en haut à gauche
   → **Terminal** → **New Terminal**.)
4. Tes comptes : le plus pratique est de donner tes secrets une fois pour toutes à Codespaces.
   Sur <https://github.com/settings/codespaces>, section **Codespaces secrets** → **New secret**,
   crée les mêmes 6 secrets qu'à l'étape 6 (mêmes noms, valeurs copiées du fichier `.env` de ton PC),
   et pour chacun choisis le repo `veille-consoles` dans **Repository access**. Rouvre ensuite le
   codespace : le menu les voit tout seul. (Sinon, utilise les assistants du choix 2.)

**Les fois suivantes :** va sur <https://github.com/codespaces> et clique sur ton codespace :
il s'ouvre tel que tu l'as laissé. Tape `./veille.sh` si le menu n'est pas affiché.

**À savoir :**
- Pour modifier la watchlist (choix 6), le fichier s'ouvre dans un onglet au-dessus ;
  ferme l'onglet pour revenir au menu, puis accepte l'**envoi sur GitHub**.
- Le codespace s'arrête tout seul après 30 minutes sans activité. Un codespace inutilisé pendant
  30 jours est supprimé : envoie toujours tes modifications sur GitHub (choix 7) avant de partir.
- C'est **gratuit** dans la limite de 60 heures d'utilisation par mois environ (120 « heures-cœur »
  sur la machine de base à 2 cœurs). Sans carte bancaire enregistrée, GitHub met en pause au-delà,
  il ne facture rien.
- Le robot, lui, continue de tourner toutes les 30 minutes que ton codespace soit ouvert ou non.

### Depuis un autre PC Windows

**Installation (une seule fois)** :
1. Installe **Git** : <https://git-scm.com/download/win> (options par défaut).
2. Installe **Python** : <https://www.python.org/downloads/> — coche bien
   **« Add python.exe to PATH »** en bas de la première fenêtre.
3. Ouvre **PowerShell** (touche Windows, tape « PowerShell ») et colle :
   ```
   cd $HOME\Documents
   git clone https://github.com/TON-PSEUDO/veille-consoles.git
   ```
   Une fenêtre de connexion GitHub s'ouvre : connecte-toi.
4. Ouvre le dossier `Documents\veille-consoles` et double-clique sur **`Veille.bat`**.
5. Dans le logiciel : **Comptes** → « Créer le raccourci », puis reconfigure tes comptes
   sur ce PC (ou copie le fichier `.env` de l'autre PC, par clé USB par exemple : il n'est
   jamais envoyé sur GitHub).

**Au quotidien (Windows comme Chromebook)** :
- À l'ouverture, le logiciel **récupère automatiquement** les nouveautés (ce que tu as fait sur
  l'autre PC, et les données du robot).
- Après avoir modifié ta watchlist, il te propose de **l'envoyer sur GitHub** (« Envoyer au robot »).
- À tout moment : bouton **Synchroniser** en bas à gauche (récupère puis envoie).

### Juste modifier la watchlist, depuis un téléphone

Depuis n'importe quel navigateur, ouvre ton repo sur github.com → `watchlist.yaml` → crayon ✏️
→ modifie → **Commit changes**. (Bientôt : directement depuis Telegram avec `/ajouter`, `/pause`…)

## 9. Ajouter ou modifier une recherche

Dans le logiciel : **6 – Modifier ma watchlist** (ouvre le fichier dans le Bloc-notes et le
vérifie quand tu le fermes). Exemple de recherche :

```yaml
  - nom: Game Boy Pocket
    requete: game boy pocket
    inclure: ["game boy pocket | gameboy pocket"]
    exclure: []
    prix_max: 50          # achat + port, en euros
    prix_max_hs: 20       # pour une console HS
    mode: les_deux        # perso / revente / les_deux
    prix_revente_ref: 65  # optionnel
    cout_pieces: 10       # optionnel
    actif: true           # false = en pause
```

Règles à respecter :
- garde exactement les **espaces** en début de ligne (2 espaces, jamais de tabulation) ;
- `inclure` : **tous** les éléments doivent être dans le titre, et `"a | b"` veut dire « a ou b » ;
- les accents et majuscules ne comptent pas (`ecran` = `Écran`).

Les autres réglages (frais de plateforme 10 %, frais de port, seuils 🔥, sites activés…)
sont dans **`config.yaml`**.

## 10. Comprendre une alerte

```
🔥🔧 PSP 3000 HS ne s'allume plus pour pièces
💶 20 € (12 € + 8 € de port estimé) · eBay
État : 🔧 HS / pour pièces (hs)
💰 Marge estimée : +31 € (+155 %)
   revente 80 € − achat 20 € − pièces 15 € − port 6 € − frais 8 €
🔎 PSP 3000
👉 Voir l'annonce
```

| Emoji | Signification |
|---|---|
| 🔥 | très bonne affaire : au moins 25 % sous la médiane, ou marge ≥ 30 € et ≥ 50 % |
| 🔧 | console HS / pour pièces, à réparer |
| 📦 | lot de plusieurs consoles ou jeux (bientôt) |
| ❓ | « non testée » : risqué, souvent HS en réalité |

- **Prix** : toujours **port compris**. Si le site ne l'indique pas, il est estimé (« port estimé »).
- **Score** (📊) : écart avec le **prix médian** des annonces déjà vues pour cette recherche.
  Il faut au moins 5 annonces dans l'historique avant de pouvoir le calculer.
- **Marge** (💰) = prix de revente − prix d'achat − pièces (si HS) − port de revente − 10 % de frais.
  Le prix de revente vient de `prix_revente_ref`, sinon de la médiane.
- **État** : deviné à partir des mots du titre, en français et dans les langues fréquentes sur
  Vinted (« HS », « ne s'allume pas », « pantalla rota », « defekt », « testée »…) et de la catégorie
  du site. C'est fiable la plupart du temps, mais pas à 100 % : lis toujours l'annonce.
- **Accessoires et jeux écartés** : « Chargeur pour PSP », « Funda PSP », « Tetris DX »… sont
  ignorés, ainsi qu'une console « en état » vendue à moins de 20 % de sa valeur (presque toujours
  un accessoire ou une arnaque).

> ℹ️ L'historique est fait de **prix demandés**, pas de prix de vente réels.
> La médiane est donc un peu optimiste : pour la revente, préfère renseigner
> `prix_revente_ref` d'après ton expérience.

## 11. Fréquence et quota gratuit GitHub

- Un repo **privé** a droit à **2 000 minutes gratuites par mois**.
- Une exécution dure environ 1 minute (les sites sont interrogés en parallèle), et GitHub
  **arrondit à la minute supérieure**.
- Toutes les 30 min : 48 × 30 jours ≈ **1 440 min/mois**, ça passe. ✅
- Toutes les 15 min : ≈ 2 900 min/mois, **ça dépasse le quota** (GitHub bloque jusqu'au mois suivant). ❌
- Le réglage est dans `.github/workflows/veille.yml`, à la ligne `cron`.
- GitHub ne garantit pas l'heure exacte : un retard de 5 à 20 minutes est normal.
- Pour voir ta consommation : avatar en haut à droite → **Settings** → **Billing and licensing**.
  Si tu approches de la limite, passe à `"7 * * * *"` (une fois par heure).

## 12. Dépannage

| Problème | Solution |
|---|---|
| Aucune alerte | Normal s'il n'y a pas de nouvelle annonce sous ton prix max. Regarde le journal dans **Actions**. |
| `Source … ignorée : … non configurés` | Les secrets correspondants sont absents ou mal nommés (étape 6). |
| `eBay refuse les clés API (code 401)` | Mauvaises clés, clés *Sandbox* au lieu de *Production*, ou compte pas encore validé (étape 3). |
| `Gmail refuse la connexion` | Utilise le **code de 16 lettres** (pas ton mot de passe Gmail habituel) ; la validation en deux étapes doit être active. |
| `Vinted bloque l'accès (protection anti-robot)` | Vinted refuse les serveurs de GitHub. Tu peux le désactiver dans `config.yaml` (`vinted: false`). |
| `Erreur de configuration` | Faute dans `watchlist.yaml`, souvent un espace en trop ou en moins. Le message dit quelle recherche. |
| `chat not found` sur Telegram | Tu n'as pas envoyé de premier message à ton bot, ou le chat id est faux. |
| Synchronisation : « la même chose a été modifiée ici et ailleurs » | Rien n'est perdu. Demande de l'aide pour fusionner les deux versions. |

### Pour aller plus loin (VPS / Raspberry Pi)

Le même code tourne en continu avec Docker, sans modification :

```
docker build -t veille .
docker run -d --restart unless-stopped --env-file .env -v "$PWD/data:/app/data" veille
```

---

## Feuille de route

- [x] eBay + watchlist + dédoublonnage + alertes Telegram + GitHub Actions
- [x] Menu, assistants de configuration, lancement en double-clic
- [x] Vinted, Label Emmaüs, Leboncoin (alertes e-mail)
- [x] Travail depuis plusieurs PC (synchronisation GitHub)
- [ ] Commandes Telegram : `/liste`, `/ajouter`, `/supprimer`, `/pause`, `/prixmax`, `/resume`
- [ ] Détection des lots 📦
- [ ] Tableau de bord web sur Netlify
