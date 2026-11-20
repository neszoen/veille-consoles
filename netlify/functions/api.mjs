// API du site « Veille consoles » (fonction Netlify).
// Le site ne garde rien lui-même : il lit et modifie le dépôt GitHub du robot.
//
// Variables d'environnement à définir sur Netlify :
//   MOT_DE_PASSE   ton mot de passe pour entrer sur le site
//   GITHUB_TOKEN   jeton GitHub « fine-grained » limité au dépôt (Contents, Actions, Secrets : lecture/écriture)
//   GITHUB_REPO    ex. « pseudo/veille-consoles »
//   GITHUB_BRANCH  (facultatif) branche du robot, « main » par défaut
import crypto from "node:crypto";
import YAML from "yaml";
import nacl from "tweetnacl";
import blake from "blakejs";

export const config = { path: "/api/*" };

const DUREE_SESSION = 30 * 24 * 3600; // 30 jours
const WORKFLOW = "veille.yml";
const MODES = ["perso", "revente", "les_deux"];
const DEFAUTS = {
  frais_plateforme_pct: 10, frais_port_revente: 6, seuil_bonne_affaire_pct: 25, seuil_marge_eur: 30,
  seuil_marge_pct: 50, echantillon_min: 5,
  sources: { ebay: true, vinted: true, leboncoin: false, leboncoin_email: true, label_emmaus: true },
};
const LIBELLES = { ebay: "eBay", vinted: "Vinted", leboncoin: "Leboncoin", leboncoin_email: "Leboncoin (e-mails)", label_emmaus: "Label Emmaüs" };
const SECRETS = ["TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID", "EBAY_CLIENT_ID", "EBAY_CLIENT_SECRET", "GMAIL_ADRESSE", "GMAIL_MOT_DE_PASSE_APPLI"];

class ErreurUtilisateur extends Error {
  constructor(message, code = 400) { super(message); this.code = code; }
}

const env = (k) => (process.env[k] || "").trim();
const branche = () => env("GITHUB_BRANCH") || "main";
const json = (donnees, code = 200, entetes = {}) =>
  new Response(JSON.stringify(donnees), { status: code, headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store", ...entetes } });

// ───────────── session (cookie signé) ─────────────
function cleSession() {
  return crypto.createHash("sha256").update(`veille|${env("MOT_DE_PASSE")}|${env("GITHUB_TOKEN")}`).digest();
}
function signer(texte) {
  return crypto.createHmac("sha256", cleSession()).update(texte).digest("base64url");
}
function creerCookie() {
  const exp = Math.floor(Date.now() / 1000) + DUREE_SESSION;
  const valeur = `${exp}.${signer(String(exp))}`;
  return `veille_session=${valeur}; Path=/; Max-Age=${DUREE_SESSION}; HttpOnly; Secure; SameSite=Strict`;
}
function sessionValide(req) {
  const m = (req.headers.get("cookie") || "").match(/(?:^|;\s*)veille_session=([^;]+)/);
  if (!m) return false;
  const [exp, sig] = m[1].split(".");
  if (!exp || !sig || Number(exp) < Date.now() / 1000) return false;
  const attendu = signer(exp);
  return sig.length === attendu.length && crypto.timingSafeEqual(Buffer.from(sig), Buffer.from(attendu));
}
function egal(a, b) {
  const ha = crypto.createHash("sha256").update(a).digest(), hb = crypto.createHash("sha256").update(b).digest();
  return crypto.timingSafeEqual(ha, hb);
}

// ───────────── GitHub ─────────────
async function gh(chemin, options = {}) {
  const r = await fetch(`https://api.github.com/repos/${env("GITHUB_REPO")}${chemin}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${env("GITHUB_TOKEN")}`, "X-GitHub-Api-Version": "2022-11-28",
      Accept: "application/vnd.github+json", "User-Agent": "veille-consoles-site", ...(options.headers || {}),
    },
  });
  if (r.status === 401) throw new ErreurUtilisateur("GitHub refuse le jeton (GITHUB_TOKEN expiré ou faux). Crée-en un nouveau et mets-le dans Netlify.", 502);
  if (r.status === 403 || r.status === 404) {
    const d = await r.json().catch(() => ({}));
    throw new ErreurUtilisateur(`GitHub : accès impossible à ${chemin.split("?")[0]} (${d.message || r.status}). Vérifie GITHUB_REPO et les permissions du jeton.`, 502);
  }
  return r;
}
async function lireBrut(chemin, defaut) {
  const r = await gh(`/contents/${chemin}?ref=${branche()}`, { headers: { Accept: "application/vnd.github.raw+json" } }).catch((e) => {
    if (defaut !== undefined && /accès impossible/.test(e.message)) return null;
    throw e;
  });
  if (!r) return defaut;
  return r.text();
}
async function lireJson(chemin, defaut) {
  const t = await lireBrut(chemin, null);
  try { return t ? JSON.parse(t) : defaut; } catch { return defaut; }
}
async function lireAvecSha(chemin) {
  const r = await gh(`/contents/${chemin}?ref=${branche()}`);
  const d = await r.json();
  return { texte: Buffer.from(d.content, "base64").toString("utf8"), sha: d.sha };
}
async function ecrireFichier(chemin, texte, sha, message) {
  const r = await gh(`/contents/${chemin}`, {
    method: "PUT",
    body: JSON.stringify({ message, sha, branch: branche(), content: Buffer.from(texte, "utf8").toString("base64"),
      committer: { name: "veille-site", email: "41898282+github-actions[bot]@users.noreply.github.com" } }),
  });
  if (r.status === 409 || r.status === 422) throw new ErreurUtilisateur("Le fichier a changé entre-temps (le robot vient peut-être de passer). Réessaie.", 409);
  if (!r.ok) throw new ErreurUtilisateur(`GitHub n'a pas enregistré la modification (${r.status}).`, 502);
}

// Chiffrement des secrets GitHub (équivalent de crypto_box_seal de libsodium).
function sceller(message, clePubliqueB64) {
  const pk = Buffer.from(clePubliqueB64, "base64");
  const eph = nacl.box.keyPair();
  const nonce = blake.blake2b(Buffer.concat([Buffer.from(eph.publicKey), pk]), null, 24);
  const boite = nacl.box(Buffer.from(message, "utf8"), nonce, pk, eph.secretKey);
  return Buffer.concat([Buffer.from(eph.publicKey), Buffer.from(boite)]).toString("base64");
}
async function enregistrerSecrets(valeurs) {
  const cle = await (await gh("/actions/secrets/public-key")).json();
  for (const [nom, valeur] of Object.entries(valeurs)) {
    const r = await gh(`/actions/secrets/${nom}`, { method: "PUT", body: JSON.stringify({ encrypted_value: sceller(String(valeur), cle.key), key_id: cle.key_id }) });
    if (!r.ok) throw new ErreurUtilisateur(`GitHub n'a pas enregistré le secret ${nom} (${r.status}).`, 502);
  }
}
async function secretsPresents() {
  try {
    const d = await (await gh("/actions/secrets?per_page=100")).json();
    return Object.fromEntries((d.secrets || []).map((s) => [s.name, s.updated_at]));
  } catch { return null; }
}

// ───────────── watchlist & config ─────────────
const liste = (v) => (v == null ? [] : Array.isArray(v) ? v.map(String) : [String(v)]);
function nombre(v, champ, nom) {
  if (v == null || v === "") return null;
  const n = Number(v);
  if (!Number.isFinite(n)) throw new ErreurUtilisateur(`« ${nom} » : « ${champ} » doit être un nombre.`);
  return n;
}
function valider(data) {
  const vus = new Set(), sortie = [];
  for (const [i, r] of (data?.recherches || []).entries()) {
    const nom = String(r?.nom || "").trim();
    if (!nom) throw new ErreurUtilisateur(`La recherche n°${i + 1} n'a pas de nom.`);
    if (vus.has(nom.toLowerCase())) throw new ErreurUtilisateur(`Deux recherches s'appellent « ${nom} ».`);
    vus.add(nom.toLowerCase());
    const mode = String(r.mode || "les_deux");
    if (!MODES.includes(mode)) throw new ErreurUtilisateur(`« ${nom} » : mode inconnu.`);
    const prix_max = nombre(r.prix_max, "prix_max", nom);
    if (prix_max == null) throw new ErreurUtilisateur(`« ${nom} » : le prix maximum est obligatoire.`);
    const inclure = liste(r.inclure);
    const requete = String(r.requete || "").trim() || inclure.map((g) => g.split("|")[0].trim()).join(" ");
    if (!requete) throw new ErreurUtilisateur(`« ${nom} » : il faut un texte de recherche ou des mots obligatoires.`);
    sortie.push({ nom, requete, inclure, exclure: liste(r.exclure), prix_max, mode, actif: r.actif !== false,
      prix_max_hs: nombre(r.prix_max_hs, "prix_max_hs", nom), prix_revente_ref: nombre(r.prix_revente_ref, "prix_revente_ref", nom),
      cout_pieces: nombre(r.cout_pieces, "cout_pieces", nom) });
  }
  return { recherches: sortie, exclusions: liste(data?.exclusions_globales) };
}
async function chargerWatchlist() {
  const { texte, sha } = await lireAvecSha("watchlist.yaml");
  const doc = YAML.parseDocument(texte);
  if (doc.errors.length) throw new ErreurUtilisateur(`watchlist.yaml est mal formé : ${doc.errors[0].message}`);
  return { doc, sha, ...valider(doc.toJS()) };
}
async function sauverWatchlist(doc, sha, message) {
  const texte = doc.toString({ lineWidth: 0, flowCollectionPadding: false });
  valider(YAML.parse(texte)); // on vérifie avant d'enregistrer
  await ecrireFichier("watchlist.yaml", texte, sha, message);
}
async function chargerConfig() {
  const t = await lireBrut("config.yaml", "");
  const lu = (t && YAML.parse(t)) || {};
  return { ...DEFAUTS, ...lu, sources: { ...DEFAUTS.sources, ...(lu.sources || {}) } };
}
function trouver(doc, nom) {
  const seq = doc.get("recherches");
  const i = (seq?.items || []).findIndex((it) => String(it.get("nom") || "").trim().toLowerCase() === String(nom).trim().toLowerCase());
  return { seq, i, noeud: i >= 0 ? seq.items[i] : null };
}
function listeFlow(doc, valeurs) {
  const n = doc.createNode(valeurs.map((v) => String(v).trim()).filter(Boolean), { flow: true });
  n.items.forEach((s) => (s.type = "QUOTE_DOUBLE"));
  return n;
}
const entier = (v) => (v == null || v === "" ? null : Number(v) === Math.round(Number(v)) ? Math.round(Number(v)) : Number(v));

// ───────────── prix (même méthode que le robot) ─────────────
function quartiles(d) {
  const n = d.length;
  if (n < 2) return [d[0], d[0], d[0]];
  const m = n + 1, q = [];
  for (let i = 1; i < 4; i++) {
    let j = Math.floor((i * m) / 4);
    j = Math.min(Math.max(j, 1), n - 1);
    const delta = i * m - j * 4;
    q.push((d[j - 1] * (4 - delta) + d[j] * delta) / 4);
  }
  return q;
}
const mediane = (d) => (d.length % 2 ? d[(d.length - 1) / 2] : (d[d.length / 2 - 1] + d[d.length / 2]) / 2);
const r2 = (x) => Math.round(x * 100) / 100;
const arrondi5 = (x) => Math.round(x / 5) * 5;
function statistiques(points) {
  const prix = points.map((p) => p.p).filter((p) => typeof p === "number").sort((a, b) => a - b);
  if (!prix.length) return null;
  const q = quartiles(prix);
  const jours = [...new Set(points.filter((p) => p.d).map((p) => p.d.slice(0, 10)))].sort();
  return { n: prix.length, min: prix[0], max: prix.at(-1), p25: r2(q[0]), mediane: r2(mediane(prix)), p75: r2(q[2]),
    premier_jour: jours[0] || null, dernier_jour: jours.at(-1) || null, nb_jours: jours.length };
}
function parJour(points) {
  const g = {};
  for (const p of points) if (p.d) (g[p.d.slice(0, 10)] ||= []).push(p.p);
  return Object.keys(g).sort().map((j) => ({ jour: j, mediane: r2(mediane(g[j].sort((a, b) => a - b))), n: g[j].length }));
}
function conseils(s, r, cfg) {
  const revente = arrondi5(s.mediane * 0.9);
  const hsCalc = arrondi5(revente * (1 - cfg.frais_plateforme_pct / 100) - cfg.frais_port_revente - (r.cout_pieces || 0) - cfg.seuil_marge_eur);
  const hs = Math.max(hsCalc, r.prix_max_hs || 0);
  return { prix_max: arrondi5(s.mediane * 0.7), prix_max_hs: hs || null, prix_revente_ref: revente, hs_garde: hsCalc < (r.prix_max_hs || 0) };
}
async function donneesPrix() {
  const [{ recherches }, cfg, hist] = await Promise.all([chargerWatchlist(), chargerConfig(), lireJson("data/prix.json", {})]);
  return {
    echantillon_min: cfg.echantillon_min,
    recherches: recherches.map((r) => {
      const points = hist[r.nom] || [];
      const stats = statistiques(points);
      return { nom: r.nom, actif: r.actif, mode: r.mode, stats,
        actuel: { prix_max: r.prix_max, prix_max_hs: r.prix_max_hs, prix_revente_ref: r.prix_revente_ref, cout_pieces: r.cout_pieces },
        conseils: stats && stats.n >= cfg.echantillon_min ? conseils(stats, r, cfg) : null,
        points: points.map((p) => ({ p: p.p, e: p.e || "inconnu", s: p.s || "", d: p.d || "" })), par_jour: parJour(points) };
    }),
  };
}

// ───────────── robot (GitHub Actions) ─────────────
async function dernieresExecutions() {
  const d = await (await gh(`/actions/workflows/${WORKFLOW}/runs?per_page=5&branch=${branche()}`)).json();
  return (d.workflow_runs || []).map((r) => ({ id: r.id, statut: r.status, resultat: r.conclusion, debut: r.run_started_at || r.created_at,
    fin: r.updated_at, declencheur: r.event, url: r.html_url }));
}

// ───────────── routes ─────────────
const ROUTES = {
  "GET /session": async () => ({ ok: true, depot: env("GITHUB_REPO") }),

  "GET /resume": async () => {
    const [etat, alertes, vues, cfg, wl, runs, secrets] = await Promise.all([
      lireJson("data/etat.json", {}), lireJson("data/alertes.json", []), lireJson("data/vues.json", {}),
      chargerConfig(), chargerWatchlist().catch((e) => ({ erreur: e.message, recherches: [] })), dernieresExecutions().catch(() => []), secretsPresents(),
    ]);
    const sante = etat.sante || {};
    return {
      depot: env("GITHUB_REPO"),
      secrets,
      comptes: secrets && {
        telegram: !!(secrets.TELEGRAM_TOKEN && secrets.TELEGRAM_CHAT_ID),
        ebay: !!(secrets.EBAY_CLIENT_ID && secrets.EBAY_CLIENT_SECRET),
        gmail: !!(secrets.GMAIL_ADRESSE && secrets.GMAIL_MOT_DE_PASSE_APPLI),
      },
      watchlist: { actives: wl.recherches.filter((r) => r.actif).length, total: wl.recherches.length, erreur: wl.erreur || null },
      sources: Object.entries(cfg.sources).map(([nom, actif]) => ({ nom, libelle: LIBELLES[nom] || nom, actif: !!actif,
        echecs: sante[nom]?.echecs || 0, dernier_succes: sante[nom]?.dernier_succes || null })),
      ...(() => {
        const triees = [...alertes].sort((a, b) => (b.date_alerte || "").localeCompare(a.date_alerte || ""));
        const vendues = triees.filter((a) => a.vendue);
        return { alertes: triees.filter((a) => !a.vendue).slice(0, 60), vendues: vendues.slice(0, 30), nb_vendues: vendues.length };
      })(),
      nb_vues: Object.keys(vues).length,
      executions: runs,
    };
  },

  "GET /prix": donneesPrix,

  "POST /prix/appliquer": async (c) => {
    const p = await donneesPrix();
    const { doc, sha } = await chargerWatchlist();
    const faits = [];
    for (const nom of c.noms || []) {
      const cons = p.recherches.find((r) => r.nom === nom)?.conseils;
      const { noeud } = trouver(doc, nom);
      if (!cons || !noeud) continue;
      for (const k of ["prix_max", "prix_max_hs", "prix_revente_ref"]) if (cons[k] != null) noeud.set(k, cons[k]);
      faits.push(nom);
    }
    if (faits.length) await sauverWatchlist(doc, sha, `watchlist : prix conseillés appliqués (${faits.join(", ")})`);
    return { ok: true, faits };
  },

  "GET /watchlist": async () => {
    const { recherches, exclusions } = await chargerWatchlist();
    return { recherches, exclusions };
  },

  "POST /watchlist/recherche": async (c) => {
    const e = c.recherche || {};
    const nom = String(e.nom || "").trim();
    if (!nom) throw new ErreurUtilisateur("Donne un nom à la recherche.");
    if (entier(e.prix_max) == null) throw new ErreurUtilisateur("Le prix maximum est obligatoire.");
    if (!MODES.includes(e.mode || "les_deux")) throw new ErreurUtilisateur("Mode inconnu.");
    const { doc, sha } = await chargerWatchlist();
    let { noeud, seq } = trouver(doc, c.ancien_nom || nom);
    if (c.ancien_nom && !noeud) throw new ErreurUtilisateur(`Recherche « ${c.ancien_nom} » introuvable.`);
    if (!c.ancien_nom && noeud) throw new ErreurUtilisateur(`Une recherche s'appelle déjà « ${nom} ».`);
    if (c.ancien_nom && nom.toLowerCase() !== c.ancien_nom.toLowerCase() && trouver(doc, nom).noeud)
      throw new ErreurUtilisateur(`Une recherche s'appelle déjà « ${nom} ».`);
    if (!noeud) {
      noeud = doc.createNode({});
      if (!seq) { doc.set("recherches", doc.createNode([])); seq = doc.get("recherches"); }
      seq.items.push(noeud);
    }
    noeud.set("nom", nom);
    noeud.set("requete", String(e.requete || "").trim());
    noeud.set("inclure", listeFlow(doc, e.inclure || []));
    noeud.set("exclure", listeFlow(doc, e.exclure || []));
    noeud.set("prix_max", entier(e.prix_max));
    for (const k of ["prix_max_hs"]) entier(e[k]) == null ? noeud.delete(k) : noeud.set(k, entier(e[k]));
    noeud.set("mode", e.mode || "les_deux");
    for (const k of ["prix_revente_ref", "cout_pieces"]) entier(e[k]) == null ? noeud.delete(k) : noeud.set(k, entier(e[k]));
    if (!noeud.has("actif")) noeud.set("actif", true);
    await sauverWatchlist(doc, sha, c.ancien_nom ? `watchlist : « ${nom} » modifiée` : `watchlist : « ${nom} » ajoutée`);
    return { ok: true };
  },

  "POST /watchlist/champs": async (c) => {
    const { doc, sha } = await chargerWatchlist();
    const { noeud } = trouver(doc, c.nom);
    if (!noeud) throw new ErreurUtilisateur(`Recherche « ${c.nom} » introuvable.`);
    for (const [k, v] of Object.entries(c.champs || {})) {
      if (k === "actif") noeud.set("actif", !!v);
      else if (["prix_max", "prix_max_hs", "prix_revente_ref", "cout_pieces"].includes(k)) noeud.set(k, entier(v));
    }
    const libelle = "actif" in (c.champs || {}) ? (c.champs.actif ? "activée" : "mise en pause") : "modifiée";
    await sauverWatchlist(doc, sha, `watchlist : « ${c.nom} » ${libelle}`);
    return { ok: true };
  },

  "POST /watchlist/supprimer": async (c) => {
    const { doc, sha } = await chargerWatchlist();
    const { seq, i } = trouver(doc, c.nom);
    if (i < 0) throw new ErreurUtilisateur(`Recherche « ${c.nom} » introuvable.`);
    seq.items.splice(i, 1);
    await sauverWatchlist(doc, sha, `watchlist : « ${c.nom} » supprimée`);
    return { ok: true };
  },

  "POST /watchlist/exclusions": async (c) => {
    const { doc, sha } = await chargerWatchlist();
    const mots = (c.mots || []).map((m) => String(m).trim()).filter(Boolean);
    const seq = doc.get("exclusions_globales");
    if (seq?.items) seq.items = mots.map((m) => doc.createNode(m));
    else doc.set("exclusions_globales", mots);
    await sauverWatchlist(doc, sha, "watchlist : mots exclus modifiés");
    return { ok: true };
  },

  "GET /robot": async () => ({ executions: await dernieresExecutions() }),

  "POST /robot/lancer": async () => {
    const enCours = (await dernieresExecutions()).find((r) => r.statut !== "completed");
    if (enCours) return { ok: true, deja: true };
    const r = await gh(`/actions/workflows/${WORKFLOW}/dispatches`, { method: "POST", body: JSON.stringify({ ref: branche() }) });
    if (r.status !== 204) throw new ErreurUtilisateur(`GitHub n'a pas lancé le robot (${r.status}).`, 502);
    return { ok: true };
  },

  "POST /comptes/telegram/jeton": async (c) => {
    const jeton = String(c.jeton || "").trim();
    if (!jeton) throw new ErreurUtilisateur("Colle le jeton donné par BotFather.");
    const moi = await telegram(jeton, "getMe");
    if (!moi.ok) throw new ErreurUtilisateur(`Telegram refuse ce jeton : ${moi.description}. Vérifie le copier-coller.`);
    return { bot: moi.result.username };
  },

  "POST /comptes/telegram/verifier": async (c) => {
    const jeton = String(c.jeton || "").trim();
    const maj = await telegram(jeton, "getUpdates");
    const chats = (maj.result || []).map((m) => m.message?.chat).filter((ch) => ch && ch.type === "private");
    if (!chats.length) throw new ErreurUtilisateur("Je ne vois pas encore ton message. Envoie « bonjour » à ton bot puis réessaie.");
    const chat = chats.at(-1);
    await enregistrerSecrets({ TELEGRAM_TOKEN: jeton, TELEGRAM_CHAT_ID: String(chat.id) });
    const test = await telegram(jeton, "sendMessage", { chat_id: chat.id, text: "👋 Bonjour ! Ton bot de veille consoles rétro est bien connecté. 🎮" });
    return { prenom: chat.first_name || "", test: !!test.ok };
  },

  "POST /comptes/ebay": async (c) => {
    const id = String(c.client_id || "").trim(), secret = String(c.secret || "").trim();
    if (!id || !secret) throw new ErreurUtilisateur("Remplis les deux champs (App ID et Cert ID).");
    const r = await fetch("https://api.ebay.com/identity/v1/oauth2/token", {
      method: "POST",
      headers: { Authorization: "Basic " + Buffer.from(`${id}:${secret}`).toString("base64"), "Content-Type": "application/x-www-form-urlencoded" },
      body: "grant_type=client_credentials&scope=https%3A%2F%2Fapi.ebay.com%2Foauth%2Fapi_scope",
    }).catch(() => null);
    const valide = !!r?.ok;
    let message = "";
    if (!valide) message = r ? `eBay refuse ces clés (${(await r.json().catch(() => ({}))).error_description || r.status}).` : "Impossible de joindre eBay.";
    if (valide || c.forcer) await enregistrerSecrets({ EBAY_CLIENT_ID: id, EBAY_CLIENT_SECRET: secret });
    return { valide, message, enregistre: valide || !!c.forcer };
  },

  "POST /comptes/gmail": async (c) => {
    const adresse = String(c.adresse || "").trim(), code = String(c.code || "").replace(/\s+/g, "");
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(adresse)) throw new ErreurUtilisateur("Adresse e-mail invalide.");
    if (code.length !== 16) throw new ErreurUtilisateur("Le code d'application Google fait 16 lettres.");
    await enregistrerSecrets({ GMAIL_ADRESSE: adresse, GMAIL_MOT_DE_PASSE_APPLI: code });
    return { ok: true };
  },
};

async function telegram(jeton, methode, params = {}) {
  try {
    const r = await fetch(`https://api.telegram.org/bot${jeton}/${methode}`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(params) });
    return await r.json();
  } catch { return { ok: false, description: "impossible de joindre Telegram" }; }
}

// ───────────── point d'entrée ─────────────
export default async function (req) {
  const url = new URL(req.url);
  const chemin = url.pathname.replace(/^\/api/, "") || "/";

  if (!env("MOT_DE_PASSE") || !env("GITHUB_TOKEN") || !env("GITHUB_REPO"))
    return json({ erreur: "Site pas encore configuré : ajoute MOT_DE_PASSE, GITHUB_TOKEN et GITHUB_REPO dans Netlify (Site configuration → Environment variables), puis redéploie." }, 500);

  if (req.method === "POST" && chemin === "/connexion") {
    const corps = await req.json().catch(() => ({}));
    if (!egal(String(corps.mot_de_passe || ""), env("MOT_DE_PASSE"))) {
      await new Promise((r) => setTimeout(r, 1200)); // ralentit les essais au hasard
      return json({ erreur: "Mot de passe incorrect." }, 401);
    }
    return json({ ok: true }, 200, { "Set-Cookie": creerCookie() });
  }
  if (req.method === "POST" && chemin === "/deconnexion")
    return json({ ok: true }, 200, { "Set-Cookie": "veille_session=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Strict" });

  if (!sessionValide(req)) return json({ erreur: "Connecte-toi.", connexion: true }, 401);
  // Protection contre les requêtes forcées depuis un autre site.
  if (req.method !== "GET" && req.headers.get("x-veille") !== "1") return json({ erreur: "Requête refusée." }, 403);

  const route = ROUTES[`${req.method} ${chemin}`];
  if (!route) return json({ erreur: "Introuvable." }, 404);
  try {
    const corps = req.method === "POST" ? await req.json().catch(() => ({})) : {};
    return json(await route(corps));
  } catch (e) {
    if (e instanceof ErreurUtilisateur) return json({ erreur: e.message }, e.code);
    console.error(e);
    return json({ erreur: `Erreur inattendue : ${e.message}` }, 500);
  }
}

export const _test = { sceller, valider, statistiques, conseils, quartiles };
