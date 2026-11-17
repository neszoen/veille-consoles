/* Veille consoles — interface */
(function () {
  "use strict";

  // ───────────── outils ─────────────
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const contenu = $("#contenu");
  const echap = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const eurosRond = (v) => (v == null ? "—" : Math.round(v) + " €");
  const euros = (v) => (v == null || v === "" ? "—" : (Math.abs(v - Math.round(v)) < 0.005 ? Math.round(v) : v.toFixed(2).replace(".", ",")) + " €");
  const lienSur = (u) => (/^https?:\/\//i.test(u || "") ? u : "#");
  const MODES = { perso: "Perso", revente: "Revente", les_deux: "Perso + revente" };
  const ETATS = { hs: ["HS", "hs"], non_teste: ["Non testée", "warn"], fonctionnel: ["Fonctionne", "ok"], inconnu: ["Non précisé", ""] };

  function depuis(iso) {
    if (!iso) return "jamais";
    const d = new Date(iso.length === 16 ? iso + ":00Z" : iso);
    const s = (Date.now() - d.getTime()) / 1000;
    if (isNaN(s)) return iso;
    if (s < 90) return "à l'instant";
    if (s < 3600) return `il y a ${Math.round(s / 60)} min`;
    if (s < 86400) return `il y a ${Math.round(s / 3600)} h`;
    if (s < 86400 * 7) return `il y a ${Math.round(s / 86400)} j`;
    return d.toLocaleDateString("fr-FR");
  }

  async function api(chemin, corps) {
    const options = { headers: { "X-Veille-Jeton": window.JETON } };
    if (corps !== undefined) {
      options.method = "POST";
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(corps);
    }
    let r;
    try { r = await fetch(chemin, options); }
    catch { throw new Error("Le logiciel ne répond plus. Relance-le depuis l'icône du Bureau."); }
    const donnees = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(donnees.erreur || `Erreur ${r.status}`);
    return donnees;
  }

  function toast(texte, type = "ok", action) {
    const t = document.createElement("div");
    t.className = `toast ${type}`;
    t.innerHTML = `<p>${echap(texte)}</p>`;
    if (action) {
      const b = document.createElement("button");
      b.className = "btn petit"; b.textContent = action.libelle;
      b.onclick = () => { t.remove(); action.faire(); };
      t.appendChild(b);
    }
    $("#toasts").appendChild(t);
    setTimeout(() => t.remove(), action ? 9000 : 4500);
  }

  async function avecAttente(bouton, fn) {
    const html = bouton.innerHTML;
    bouton.disabled = true;
    bouton.innerHTML = `<span class="rond"></span>${echap(bouton.textContent.trim())}`;
    try { return await fn(); }
    catch (e) { toast(e.message, "bad"); }
    finally { bouton.disabled = false; bouton.innerHTML = html; }
  }

  function modale(titre, corpsHtml, boutons = []) {
    const d = $("#modale");
    d.innerHTML = `<div class="m-tete"><h2>${echap(titre)}</h2><button class="btn fantome petit" data-fermer aria-label="Fermer">✕</button></div>
      <div class="m-corps">${corpsHtml}</div>${boutons.length ? '<div class="m-pied"></div>' : ""}`;
    const pied = $(".m-pied", d);
    for (const b of boutons) {
      const el = document.createElement("button");
      el.className = `btn ${b.classe || ""}`; el.textContent = b.libelle;
      el.onclick = () => b.faire(el);
      pied.appendChild(el);
    }
    $("[data-fermer]", d).onclick = () => d.close();
    d.showModal();
    return d;
  }

  const ICONES = {
    eclair: '<svg viewBox="0 0 24 24"><path d="M13 2 4 14h6l-1 8 9-12h-6l1-8Z"/></svg>',
    lecture: '<svg viewBox="0 0 24 24"><path d="M8 5v14l11-7L8 5Z"/></svg>',
    plus: '<svg viewBox="0 0 24 24"><path d="M11 5h2v6h6v2h-6v6h-2v-6H5v-2h6V5Z"/></svg>',
    crayon: '<svg viewBox="0 0 24 24"><path d="m14.1 5.9 4 4L8 20H4v-4L14.1 5.9Zm1.4-1.4 2-2 4 4-2 2-4-4Z"/></svg>',
    poubelle: '<svg viewBox="0 0 24 24"><path d="M9 3h6l1 2h4v2H4V5h4l1-2Zm-3 6h12l-1 12H7L6 9Z"/></svg>',
    lien: '<svg viewBox="0 0 24 24"><path d="M14 3h7v7h-2V6.4l-8.3 8.3-1.4-1.4L17.6 5H14V3ZM5 5h6v2H5v12h12v-6h2v8H3V5h2Z"/></svg>',
    image: '<svg viewBox="0 0 24 24" width="34" height="34"><path d="M4 5h16v14H4V5Zm2 2v8.6l3.5-3.5 3 3 2.5-2.5L18 15.6V7H6Zm9 1.5a1.5 1.5 0 1 1 0 3 1.5 1.5 0 0 1 0-3Z"/></svg>',
  };

  // ───────────── état partagé ─────────────
  let resume = null;
  async function chargerResume() {
    resume = await api("/api/resume");
    majSynchro();
    return resume;
  }

  function majSynchro() {
    if (!resume) return;
    const g = resume.github, badge = $("#synchro-badge"), texte = $("#synchro-texte");
    const nb = (g.modifs || []).length;
    badge.hidden = !nb; badge.textContent = nb;
    texte.textContent = !g.depot ? "GitHub (non relié)" : nb ? "Synchroniser" : "GitHub à jour";
  }

  async function synchroniser(message) {
    const btn = $("#btn-synchro");
    if (!resume?.github?.depot) { location.hash = "#comptes"; toast("Relie d'abord le projet à GitHub (en bas de la page).", "info"); return; }
    btn.classList.add("tourne"); btn.disabled = true;
    try {
      const r = await api("/api/github/synchroniser", { message: message || "" });
      toast(r.ok ? "Synchronisé avec GitHub ✨ Le robot utilisera tes changements." : (r.lignes || []).join(" ") || "Synchronisation impossible.", r.ok ? "ok" : "bad");
      await chargerResume();
      if (r.ok && ["accueil", "prix", "watchlist"].includes(pageActuelle)) afficher();
    } catch (e) { toast(e.message, "bad"); }
    finally { btn.classList.remove("tourne"); btn.disabled = false; }
  }
  $("#btn-synchro").onclick = () => synchroniser();

  function proposerEnvoi() {
    chargerResume().then(() => {
      if (resume.github.depot && resume.github.modifs.length)
        toast("Modification enregistrée sur ce PC.", "ok", { libelle: "Envoyer au robot", faire: () => synchroniser("Watchlist modifiée depuis le logiciel") });
      else toast("Modification enregistrée.", "ok");
    });
  }

  function bandeauModifs() {
    const g = resume?.github;
    if (!g?.depot || !g.modifs.length) return "";
    return `<div class="alerte-bandeau warn"><span>⚠️</span><p><b>${g.modifs.length} modification(s)</b> pas encore envoyée(s) à GitHub : le robot ne les connaît pas encore.</p>
      <button class="btn petit" data-action="synchro">Envoyer maintenant</button></div>`;
  }
  document.addEventListener("click", (e) => {
    if (e.target.closest('[data-action="synchro"]')) synchroniser();
  });

  // ───────────── carte d'annonce ─────────────
  function carteAnnonce(a) {
    const an = a.analyse || {};
    const [etatLib, etatCls] = ETATS[a.etat] || ETATS.inconnu;
    const badges = [];
    if (an.feu) badges.push('<span class="badge feu">🔥 Bonne affaire</span>');
    badges.push(`<span class="badge ${etatCls}">${a.etat === "hs" ? "🔧 " : ""}${etatLib}</span>`);
    if (an.lot) badges.push('<span class="badge">📦 Lot</span>');
    const chiffres = [];
    if (an.montrer_marge && an.marge_eur != null)
      chiffres.push(`<span>Marge <b class="${an.marge_eur >= 0 ? "plus" : "moins"}">${an.marge_eur >= 0 ? "+" : ""}${an.marge_eur} €</b></span>`);
    if (an.montrer_score && an.ecart_pct != null)
      chiffres.push(`<span>vs médiane <b class="${an.ecart_pct >= 0 ? "plus" : "moins"}">${an.ecart_pct >= 0 ? "−" : "+"}${Math.abs(an.ecart_pct)} %</b></span>`);
    const photo = a.photo && /^https?:/.test(a.photo) ? `<img src="${echap(a.photo)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">` : ICONES.image;
    const quand = a.date_alerte ? depuis(a.date_alerte) : (a.localisation || "");
    return `<article class="carte annonce">
      <div class="photo">${photo}<div class="badges">${badges.join("")}</div></div>
      <div class="corps">
        <div class="titre" title="${echap(a.titre)}">${echap(a.titre)}</div>
        <div class="ligne-prix"><span class="prix">${euros(a.prix_total)}</span><span class="badge accent">${echap(a.recherche || "")}</span></div>
        ${chiffres.length ? `<div class="chiffres">${chiffres.join("")}</div>` : ""}
        <div class="pied"><span>${echap(nomSource(a.source))}${quand ? " · " + echap(quand) : ""}</span>
          <a class="btn petit" href="${echap(lienSur(a.url))}" target="_blank" rel="noopener noreferrer">${ICONES.lien}Voir</a></div>
      </div></article>`;
  }
  const nomSource = (s) => ({ ebay: "eBay", vinted: "Vinted", label_emmaus: "Label Emmaüs", leboncoin: "Leboncoin", leboncoin_email: "Leboncoin", demo: "Démo" }[s] || s || "");

  // ───────────── page Accueil ─────────────
  let filtreAlertes = "toutes";
  async function pageAccueil() {
    const r = await chargerResume();
    const il30 = Date.now() - 30 * 86400000;
    const alertes30 = r.alertes.filter((a) => new Date(a.date_alerte).getTime() > il30);
    const feux = alertes30.filter((a) => a.analyse?.feu).length;
    const recherches = [...new Set(r.alertes.map((a) => a.recherche))];
    const liste = r.alertes.filter((a) => filtreAlertes === "toutes" || (filtreAlertes === "feu" ? a.analyse?.feu : a.recherche === filtreAlertes));
    const synchroTxt = { en_cours: "Récupération des nouveautés GitHub…", echec: "Impossible de récupérer les nouveautés GitHub (connexion ?)." }[r.github.synchro_demarrage];

    contenu.innerHTML = `
      <div class="entete"><div><h1>Bonjour 👋</h1><p>Voici ce que ton robot a trouvé.</p></div>
        <div class="actions">
          <button class="btn" id="b-demo">${ICONES.lecture}Démonstration</button>
          <button class="btn primaire" id="b-veille">${ICONES.eclair}Lancer une veille</button>
        </div></div>
      ${synchroTxt ? `<div class="alerte-bandeau info"><span>🔄</span><p>${synchroTxt}</p></div>` : ""}
      ${bandeauModifs()}
      ${!r.comptes.telegram ? `<div class="alerte-bandeau info"><span>📱</span><p>Telegram n'est pas configuré sur ce PC : les essais s'affichent ici, sans notification.</p><a class="btn petit" href="#comptes">Configurer</a></div>` : ""}
      <section class="grille g-tuiles">
        <div class="carte tuile"><div class="etiquette">Alertes (30 jours)</div><div class="valeur">${alertes30.length}</div><div class="sous">${feux} très bonne(s) affaire(s) 🔥</div></div>
        <div class="carte tuile"><div class="etiquette">Annonces analysées</div><div class="valeur">${r.nb_vues.toLocaleString("fr-FR")}</div><div class="sous">depuis le début</div></div>
        <div class="carte tuile"><div class="etiquette">Recherches actives</div><div class="valeur">${r.watchlist.actives}</div><div class="sous">${r.watchlist.total - r.watchlist.actives} en pause</div></div>
        <div class="carte tuile"><div class="etiquette">Dernier passage du robot</div><div class="valeur" style="font-size:1.35rem;padding-top:6px">${depuis(r.maj_robot)}</div><div class="sous">toutes les 30 min sur GitHub</div></div>
      </section>
      <section id="zone-tache" hidden></section>
      <section>
        <div class="titre-section"><h2>Dernières alertes</h2>
          <div class="puces" id="filtres">
            <button class="puce" data-f="toutes">Toutes</button><button class="puce" data-f="feu">🔥 Bonnes affaires</button>
            ${recherches.map((n) => `<button class="puce" data-f="${echap(n)}">${echap(n)}</button>`).join("")}
          </div></div>
        ${liste.length ? `<div class="grille g-annonces">${liste.map(carteAnnonce).join("")}</div>`
          : `<div class="carte vide"><div class="grand">🕹️</div><p><b>Aucune alerte pour l'instant.</b></p>
             <p class="petit muted" style="margin-top:6px">Le robot t'enverra une alerte dès qu'une annonce passe sous tes prix maximum.<br>Lance une démonstration pour voir à quoi elles ressemblent.</p></div>`}
      </section>
      <section>
        <div class="titre-section"><h2>Sites surveillés</h2><small class="muted">État vu par le robot sur GitHub</small></div>
        <div class="carte"><div class="liste">${r.sources.map(rangSource).join("")}</div></div>
      </section>`;
    $$("#filtres .puce").forEach((b) => {
      b.classList.toggle("actif", b.dataset.f === filtreAlertes);
      b.onclick = () => { filtreAlertes = b.dataset.f; pageAccueil(); };
    });
    $("#b-veille").onclick = (e) => lancer("veille", e.currentTarget);
    $("#b-demo").onclick = (e) => lancer("demo", e.currentTarget);
    if (r.github.synchro_demarrage === "en_cours") setTimeout(() => pageActuelle === "accueil" && pageAccueil(), 4000);
  }

  function rangSource(s) {
    const besoin = { ebay: "ebay", leboncoin_email: "gmail" }[s.nom];
    let cls = "ok", txt = s.dernier_succes ? `OK · ${depuis(s.dernier_succes)}` : "Pas encore utilisé";
    if (!s.actif) { cls = ""; txt = "Désactivé"; }
    else if (besoin && !resume.comptes[besoin] && !s.dernier_succes) { cls = "warn"; txt = "À configurer"; }
    else if (s.echecs >= 3) { cls = "bad"; txt = `En panne (${s.echecs} échecs)`; }
    else if (s.echecs) { cls = "warn"; txt = `${s.echecs} échec(s) récent(s)`; }
    else if (!s.dernier_succes) cls = "";
    return `<div class="rang"><span class="point ${cls}"></span><div class="principal"><b>${echap(s.libelle)}</b>${s.message ? `<small>${echap(s.message)}</small>` : ""}</div>
      <span class="badge ${cls}">${echap(txt)}</span></div>`;
  }

  // ───────────── veille / démo en direct ─────────────
  async function lancer(type, bouton) {
    await avecAttente(bouton, async () => {
      await api("/api/lancer", { type });
      await suivreTache(type);
    });
  }

  async function suivreTache(type) {
    const zone = $("#zone-tache");
    if (!zone) return;
    zone.hidden = false;
    for (;;) {
      const { tache: t } = await api("/api/tache");
      if (!t) return;
      const titre = type === "demo" ? "Démonstration (fausses annonces)" : "Veille sur ce PC (rien n'est envoyé sur Telegram)";
      zone.innerHTML = `<div class="carte">
        <div class="titre-section"><h2>${titre}</h2>${t.en_cours ? '<span class="badge accent">En cours…</span>' : t.erreur ? '<span class="badge bad">Erreur</span>' : `<span class="badge ok">Terminé en ${t.duree} s</span>`}</div>
        ${t.erreur ? `<div class="alerte-bandeau bad"><p>${echap(t.erreur)}</p></div>` : ""}
        ${t.bilan ? `<p class="second" style="margin-bottom:12px">${t.bilan.annonces} annonces lues · ${t.bilan.nouvelles} nouvelles · <b>${t.alertes.length} alerte(s)</b></p>` : ""}
        ${t.alertes.length ? `<div class="grille g-annonces" style="margin-bottom:14px">${t.alertes.map(carteAnnonce).join("")}</div>` : ""}
        ${t.messages.length ? `<div class="alerte-bandeau info"><p style="white-space:pre-line">${echap(t.messages.join("\n\n").slice(0, 1500))}</p></div>` : ""}
        <details ${t.en_cours ? "open" : ""}><summary class="second petit" style="cursor:pointer;margin-bottom:8px">Journal détaillé</summary>
        <div class="journal">${t.logs.map((l) => `<div class="${l.niveau}"><span class="h">${l.heure}</span>${echap(l.texte)}</div>`).join("") || '<span class="muted">Démarrage…</span>'}</div></details>
      </div>`;
      const j = $(".journal", zone); if (j) j.scrollTop = j.scrollHeight;
      if (!t.en_cours) return;
      await new Promise((r) => setTimeout(r, 900));
    }
  }

  // ───────────── page Prix ─────────────
  let prixChoisi = null;
  async function pagePrix() {
    const d = await api("/api/prix");
    const avecDonnees = d.recherches.filter((r) => r.stats);
    if (!prixChoisi || !d.recherches.some((r) => r.nom === prixChoisi)) prixChoisi = (avecDonnees[0] || d.recherches[0])?.nom;
    const r = d.recherches.find((x) => x.nom === prixChoisi);
    const aAppliquer = d.recherches.filter((x) => x.conseils && differe(x));

    contenu.innerHTML = `
      <div class="entete"><div><h1>Prix du marché</h1><p>Calculés à partir des annonces relevées par le robot.</p></div>
        <div class="actions">${aAppliquer.length ? `<button class="btn primaire" id="b-tout">Appliquer tous les prix conseillés (${aAppliquer.length})</button>` : ""}</div></div>
      ${bandeauModifs()}
      <div class="puces" style="margin-bottom:18px">${d.recherches.map((x) => `<button class="puce ${x.nom === prixChoisi ? "actif" : ""}" data-n="${echap(x.nom)}">${echap(x.nom)}${x.stats ? "" : " ·  pas de relevés"}</button>`).join("")}</div>
      ${r ? blocPrix(r, d.echantillon_min) : ""}
      <section>
        <div class="titre-section"><h2>Toutes les consoles</h2><small class="muted">Méthode : revente = médiane − 10 % · prix max = 70 % de la médiane · max HS = garde ≈ 30 € de marge</small></div>
        <div class="carte table-defile"><table>
          <thead><tr><th>Console</th><th class="num">Relevés</th><th class="num">Médiane</th><th class="num">Prix max</th><th class="num">Max HS</th><th class="num">Revente</th><th></th></tr></thead>
          <tbody>${d.recherches.map(ligneTablePrix).join("")}</tbody></table></div>
      </section>`;
    $$(".puce[data-n]").forEach((b) => (b.onclick = () => { prixChoisi = b.dataset.n; pagePrix(); }));
    $$("[data-appliquer]").forEach((b) => (b.onclick = () => appliquer([b.dataset.appliquer], b)));
    const bt = $("#b-tout"); if (bt) bt.onclick = () => appliquer(aAppliquer.map((x) => x.nom), bt);
    if (r?.stats) {
      const a = r.actuel;
      const res = Graphiques.histogramme($("#g-histo"), r.points.map((p) => p.p), [
        { nom: "Max", valeur: a.prix_max, couleur: "var(--ref-max)" },
        { nom: "Max HS", valeur: a.prix_max_hs, couleur: "var(--ref-hs)" },
        { nom: "Revente", valeur: a.prix_revente_ref, couleur: "var(--ref-revente)" },
        { nom: "Médiane", valeur: r.stats.mediane, couleur: "var(--text-2)", pointille: true },
      ]);
      if (res?.horsCadre) $("#hors-cadre").textContent = `${res.horsCadre} annonce(s) au-delà de ${res.xmax} € (lots, collectors) ne sont pas affichées.`;
      if (r.par_jour.length >= 2) Graphiques.courbe($("#g-courbe"), r.par_jour);
    }
  }

  const differe = (x) => ["prix_max", "prix_max_hs", "prix_revente_ref"].some((k) => x.conseils[k] != null && x.conseils[k] !== x.actuel[k]);

  function fleche(avant, apres) {
    if (apres == null || avant === apres) return `<span class="num">${euros(avant)}</span>`;
    return `<span class="muted num">${euros(avant)}</span><span class="fleche">→</span><span class="${apres > (avant || 0) ? "change-haut" : "change-bas"} num">${euros(apres)}</span>`;
  }

  function ligneTablePrix(x) {
    const c = x.conseils;
    return `<tr><td><b>${echap(x.nom)}</b>${x.actif ? "" : ' <span class="badge">en pause</span>'}</td>
      <td class="num">${x.stats ? x.stats.n : "—"}</td><td class="num">${x.stats ? eurosRond(x.stats.mediane) : "—"}</td>
      <td class="num">${c ? fleche(x.actuel.prix_max, c.prix_max) : euros(x.actuel.prix_max)}</td>
      <td class="num">${c ? fleche(x.actuel.prix_max_hs, c.prix_max_hs) : euros(x.actuel.prix_max_hs)}</td>
      <td class="num">${c ? fleche(x.actuel.prix_revente_ref, c.prix_revente_ref) : euros(x.actuel.prix_revente_ref)}</td>
      <td style="text-align:right">${c && differe(x) ? `<button class="btn petit" data-appliquer="${echap(x.nom)}">Appliquer</button>` : c ? '<span class="badge ok">À jour</span>' : '<span class="muted petit">pas assez de relevés</span>'}</td></tr>`;
  }

  function blocPrix(r, mini) {
    if (!r.stats) return `<div class="carte vide"><div class="grand">📉</div><p><b>Pas encore de relevés pour ${echap(r.nom)}.</b></p>
      <p class="petit muted" style="margin-top:6px">${r.actif ? "Le robot va en collecter à ses prochains passages." : "Cette recherche est en pause : active-la dans la watchlist."}</p></div>`;
    const s = r.stats, c = r.conseils;
    const etats = {};
    r.points.forEach((p) => (etats[p.e] = (etats[p.e] || 0) + 1));
    const periode = s.nb_jours > 1 ? `du ${s.premier_jour.split("-").reverse().join("/")} au ${s.dernier_jour.split("-").reverse().join("/")}` : `le ${s.premier_jour.split("-").reverse().join("/")}`;
    return `<section class="grille g-tuiles" style="margin-bottom:14px">
        <div class="carte tuile"><div class="etiquette">Prix médian</div><div class="valeur">${eurosRond(s.mediane)}</div><div class="sous">la moitié des annonces est en dessous</div></div>
        <div class="carte tuile"><div class="etiquette">Fourchette habituelle</div><div class="valeur">${eurosRond(s.p25)} – ${eurosRond(s.p75)}</div><div class="sous">la moitié des annonces</div></div>
        <div class="carte tuile"><div class="etiquette">Annonces relevées</div><div class="valeur">${s.n}</div><div class="sous">${periode}</div></div>
      </section>
      <section class="grille g-prix">
        <div class="carte">
          <div class="titre-section"><h2>Répartition des prix</h2><small class="muted">port compris</small></div>
          <div id="g-histo"></div>
          <div class="legende"><span><i class="carre" style="background:var(--serie-1)"></i>Nombre d'annonces</span>
            <span><i style="background:var(--ref-max)"></i>Ton prix max</span><span><i style="background:var(--ref-hs)"></i>Max HS</span>
            <span><i style="background:var(--ref-revente)"></i>Revente</span><span><i style="background:var(--text-2)"></i>Médiane</span></div>
          <p class="petit muted" id="hors-cadre" style="margin-top:8px"></p>
        </div>
        <div class="carte">
          <h2 style="margin-bottom:12px">Prix conseillés</h2>
          ${c ? `<div class="liste">
              <div class="rang"><div class="principal">Prix max<small>console qui marche</small></div>${fleche(r.actuel.prix_max, c.prix_max)}</div>
              <div class="rang"><div class="principal">Max HS<small>${c.hs_garde ? "calcul trop bas : ta valeur est gardée" : "≈ 30 € de marge après réparation"}</small></div>${fleche(r.actuel.prix_max_hs, c.prix_max_hs)}</div>
              <div class="rang"><div class="principal">Revente<small>médiane − 10 %</small></div>${fleche(r.actuel.prix_revente_ref, c.prix_revente_ref)}</div>
            </div>
            <div style="margin-top:14px">${differe(r) ? `<button class="btn primaire" style="width:100%" data-appliquer="${echap(r.nom)}">Appliquer ces prix</button>` : '<span class="badge ok">Tes prix sont à jour ✓</span>'}</div>`
            : `<p class="second">Il faut au moins ${mini} annonces pour conseiller des prix.</p>`}
          <p class="petit muted" style="margin-top:14px">${Object.entries(etats).map(([e, n]) => `${n} ${(ETATS[e] || ETATS.inconnu)[0].toLowerCase()}`).join(" · ")}.<br>Ce sont des prix <b>demandés</b>, pas des prix de vente.</p>
        </div>
      </section>
      ${r.par_jour.length >= 2 ? `<section class="carte"><div class="titre-section"><h2>Évolution de la médiane</h2><small class="muted">jour par jour</small></div><div id="g-courbe"></div></section>` : ""}`;
  }

  async function appliquer(noms, bouton) {
    await avecAttente(bouton, async () => {
      await api("/api/prix/appliquer", { noms });
      proposerEnvoi();
      await pagePrix();
    });
  }

  // ───────────── page Watchlist ─────────────
  let watchlist = null;
  async function pageWatchlist() {
    watchlist = await api("/api/watchlist");
    await chargerResume();
    contenu.innerHTML = `
      <div class="entete"><div><h1>Ma watchlist</h1><p>Les consoles que le robot surveille. Prix toujours <b>port compris</b>.</p></div>
        <div class="actions"><button class="btn primaire" id="b-ajout">${ICONES.plus}Ajouter une console</button></div></div>
      ${bandeauModifs()}
      <section class="grille">${watchlist.recherches.map(carteRecherche).join("")}</section>
      <section>
        <div class="titre-section"><h2>Mots exclus partout</h2><small class="muted">une annonce dont le titre contient l'un de ces mots est ignorée</small></div>
        <div class="carte"><div class="etiquettes" id="excl"></div>
          <div class="actions" style="margin-top:12px;justify-content:flex-end"><button class="btn" id="b-excl">Enregistrer les mots exclus</button></div></div>
      </section>`;
    const excl = editeurEtiquettes($("#excl"), watchlist.exclusions, "Ajouter un mot puis Entrée…");
    $("#b-excl").onclick = (e) => avecAttente(e.currentTarget, async () => { await api("/api/watchlist/exclusions", { mots: excl() }); proposerEnvoi(); });
    $("#b-ajout").onclick = () => formulaireRecherche(null);
    $$("[data-actif]").forEach((c) => (c.onchange = async () => {
      try { await api("/api/watchlist/champs", { nom: c.dataset.actif, champs: { actif: c.checked } }); proposerEnvoi(); pageWatchlist(); }
      catch (e) { toast(e.message, "bad"); c.checked = !c.checked; }
    }));
    $$("[data-modif]").forEach((b) => (b.onclick = () => formulaireRecherche(watchlist.recherches.find((r) => r.nom === b.dataset.modif))));
    $$("[data-suppr]").forEach((b) => (b.onclick = () => {
      const nom = b.dataset.suppr;
      modale("Supprimer cette recherche ?", `<p>« <b>${echap(nom)}</b> » sera retirée de ta watchlist. Tu peux aussi simplement la mettre en pause.</p>`, [
        { libelle: "Annuler", faire: () => $("#modale").close() },
        { libelle: "Supprimer", classe: "danger", faire: async (el) => avecAttente(el, async () => { await api("/api/watchlist/supprimer", { nom }); $("#modale").close(); proposerEnvoi(); pageWatchlist(); }) },
      ]);
    }));
  }

  function carteRecherche(r) {
    return `<div class="carte recherche ${r.actif ? "" : "pause"}">
      <label class="interrupteur" title="${r.actif ? "Active : cliquer pour mettre en pause" : "En pause : cliquer pour activer"}"><input type="checkbox" data-actif="${echap(r.nom)}" ${r.actif ? "checked" : ""}><span></span></label>
      <div><div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap"><h3>${echap(r.nom)}</h3><span class="badge">${MODES[r.mode]}</span>${r.actif ? "" : '<span class="badge">En pause</span>'}</div>
        <div class="prix-ligne"><span>Max <b>${euros(r.prix_max)}</b></span>${r.prix_max_hs ? `<span>Max HS <b>${euros(r.prix_max_hs)}</b></span>` : ""}
          <span>Revente <b>${r.prix_revente_ref ? euros(r.prix_revente_ref) : "auto"}</b></span>${r.cout_pieces ? `<span>Pièces <b>${euros(r.cout_pieces)}</b></span>` : ""}
          <span class="muted">« ${echap(r.requete)} »</span></div></div>
      <div class="actions"><button class="btn petit" data-modif="${echap(r.nom)}">${ICONES.crayon}Modifier</button>
        <button class="btn petit fantome danger" data-suppr="${echap(r.nom)}" aria-label="Supprimer">${ICONES.poubelle}</button></div></div>`;
  }

  function editeurEtiquettes(boite, valeurs, invite) {
    let liste = [...valeurs];
    const dessiner = () => {
      boite.innerHTML = liste.map((v, i) => `<span class="etq">${echap(v)}<button type="button" data-i="${i}" aria-label="Retirer">×</button></span>`).join("") + `<input type="text" placeholder="${echap(invite)}">`;
      $$("button", boite).forEach((b) => (b.onclick = () => { liste.splice(+b.dataset.i, 1); dessiner(); }));
      const inp = $("input", boite);
      inp.onkeydown = (e) => {
        if ((e.key === "Enter" || e.key === ",") && inp.value.trim()) { e.preventDefault(); liste.push(inp.value.trim()); dessiner(); $("input", boite).focus(); }
        else if (e.key === "Backspace" && !inp.value && liste.length) { liste.pop(); dessiner(); $("input", boite).focus(); }
      };
      inp.onblur = () => { if (inp.value.trim()) { liste.push(inp.value.trim()); dessiner(); } };
    };
    dessiner();
    return () => { const inp = $("input", boite); if (inp && inp.value.trim()) liste.push(inp.value.trim()); return liste; };
  }

  function formulaireRecherche(r) {
    const n = r || { nom: "", requete: "", inclure: [], exclure: [], prix_max: "", prix_max_hs: "", mode: "les_deux", prix_revente_ref: "", cout_pieces: "", actif: true };
    const v = (x) => (x == null ? "" : x);
    const d = modale(r ? `Modifier « ${r.nom} »` : "Ajouter une console", `
      <form class="formulaire" id="f-rech" onsubmit="return false">
        <div class="deux">
          <label class="champ">Nom affiché<input type="text" name="nom" value="${echap(n.nom)}" placeholder="ex. GameCube" required></label>
          <label class="champ">Texte recherché sur les sites<input type="text" name="requete" value="${echap(n.requete)}" placeholder="ex. nintendo gamecube"></label>
        </div>
        <div class="champ"><span>Type d'achat</span><div class="segment" id="seg-mode">
          ${Object.entries(MODES).map(([k, l]) => `<button type="button" data-m="${k}" class="${n.mode === k ? "actif" : ""}">${l}</button>`).join("")}</div>
          <span class="aide" id="aide-mode"></span></div>
        <div class="trois">
          <label class="champ">Prix max (marche)<input type="number" name="prix_max" min="0" step="1" value="${v(n.prix_max)}" required></label>
          <label class="champ">Prix max HS<input type="number" name="prix_max_hs" min="0" step="1" value="${v(n.prix_max_hs)}" placeholder="facultatif"></label>
          <label class="champ">Prix de revente<input type="number" name="prix_revente_ref" min="0" step="1" value="${v(n.prix_revente_ref)}" placeholder="auto"></label>
        </div>
        <div class="deux">
          <label class="champ">Coût des pièces (réparation)<input type="number" name="cout_pieces" min="0" step="1" value="${v(n.cout_pieces)}" placeholder="facultatif"></label>
          <div></div>
        </div>
        <div class="champ"><span>Mots obligatoires dans le titre</span><div class="etiquettes" id="e-incl"></div>
          <span class="aide">Chaque étiquette doit être présente. « a | b » = l'un OU l'autre (ex. <code>3000 | 3004</code>).</span></div>
        <div class="champ"><span>Mots qui font rejeter l'annonce</span><div class="etiquettes" id="e-excl"></div></div>
      </form>`, [
      { libelle: "Annuler", faire: () => d.close() },
      { libelle: r ? "Enregistrer" : "Ajouter", classe: "primaire", faire: (el) => avecAttente(el, async () => {
          const f = $("#f-rech");
          const val = (k) => f.elements[k].value;
          const recherche = { nom: val("nom"), requete: val("requete"), mode, inclure: incl(), exclure: excl(), prix_max: val("prix_max"),
            prix_max_hs: val("prix_max_hs"), prix_revente_ref: val("prix_revente_ref"), cout_pieces: val("cout_pieces"), actif: n.actif };
          await api("/api/watchlist/recherche", { recherche, ancien_nom: r ? r.nom : null });
          d.close(); proposerEnvoi(); pageWatchlist();
        }) },
    ]);
    let mode = n.mode;
    const aides = { perso: "Uniquement des consoles qui marchent, moins chères que d'habitude.", revente: "Tout, y compris HS, avec la marge estimée après réparation.", les_deux: "Tout : score bon plan ET marge de revente." };
    const majMode = () => { $$("#seg-mode button").forEach((b) => b.classList.toggle("actif", b.dataset.m === mode)); $("#aide-mode").textContent = aides[mode]; };
    $$("#seg-mode button").forEach((b) => (b.onclick = () => { mode = b.dataset.m; majMode(); }));
    majMode();
    const incl = editeurEtiquettes($("#e-incl"), n.inclure, "ex. gamecube | game cube");
    const excl = editeurEtiquettes($("#e-excl"), n.exclure, "ex. manette");
  }

  // ───────────── page Tester ─────────────
  let derniereSource = null;
  async function pageTester() {
    const { sources } = await api("/api/sources");
    const choix = sources.filter((s) => s.nom !== "leboncoin");
    if (!derniereSource) derniereSource = (choix.find((s) => s.prete) || choix[0]).nom;
    contenu.innerHTML = `
      <div class="entete"><div><h1>Tester une recherche</h1><p>Vois tout de suite ce qu'un site renvoie, et comment le robot devine l'état.</p></div></div>
      <div class="carte"><form class="formulaire" id="f-test" onsubmit="return false">
        <div class="champ"><span>Site</span><div class="segment" id="seg-src">${choix.map((s) => `<button type="button" data-s="${s.nom}" ${s.prete ? "" : 'title="À configurer dans Comptes"'}>${echap(s.libelle)}${s.prete ? "" : " ⚠️"}</button>`).join("")}</div></div>
        <div style="display:flex;gap:10px"><input type="text" name="q" placeholder="ex. psp 3000" value="psp 3000"><button class="btn primaire" id="b-test">Chercher</button></div>
      </form></div>
      <section id="res-test"></section>`;
    const majSeg = () => $$("#seg-src button").forEach((b) => b.classList.toggle("actif", b.dataset.s === derniereSource));
    $$("#seg-src button").forEach((b) => (b.onclick = () => { derniereSource = b.dataset.s; majSeg(); }));
    majSeg();
    $("#b-test").onclick = (e) => avecAttente(e.currentTarget, async () => {
      const res = await api("/api/tester", { source: derniereSource, requete: $("#f-test").elements.q.value });
      $("#res-test").innerHTML = res.annonces.length
        ? `<div class="titre-section"><h2>${res.total} annonce(s) trouvée(s)</h2><small class="muted">les plus récentes d'abord</small></div><div class="grille g-annonces">${res.annonces.map(carteAnnonce).join("")}</div>`
        : `<div class="carte vide"><div class="grand">🔍</div><p>Aucune annonce trouvée.</p></div>`;
    });
  }

  // ───────────── page Comptes ─────────────
  async function pageComptes() {
    const r = await chargerResume();
    const c = r.comptes, g = r.github;
    const etat = (ok, oui = "Connecté", non = "À configurer") => `<span class="badge ${ok ? "ok" : "warn"}">${ok ? "✓ " + oui : non}</span>`;
    contenu.innerHTML = `
      <div class="entete"><div><h1>Comptes et réglages</h1><p>Tes clés restent sur ce PC (fichier .env), jamais envoyées dans le code.</p></div></div>
      <div class="grille g-2">
        <div class="carte"><div class="compte-tete"><span class="ico">📱</span><div><h2>Telegram</h2><small class="muted">pour recevoir les alertes</small></div>${etat(c.telegram)}</div>
          <div id="tg"></div></div>
        <div class="carte"><div class="compte-tete"><span class="ico">🛒</span><div><h2>eBay</h2><small class="muted">API officielle, gratuite</small></div>${etat(c.ebay, "Clés enregistrées")}</div>
          <form class="formulaire" id="f-ebay" onsubmit="return false">
            <p class="petit second">Sur <a href="https://developer.ebay.com/my/keys" target="_blank" rel="noopener">developer.ebay.com</a> → <b>Application Keysets</b> → colonne <b>Production</b>. eBay peut mettre quelques jours à activer un nouveau compte.</p>
            <label class="champ">App ID (Client ID)<input type="text" name="id" autocomplete="off" placeholder="${c.ebay ? "déjà enregistré — laisser vide pour tester" : ""}"></label>
            <label class="champ">Cert ID (Client Secret)<input type="password" name="secret" autocomplete="off"></label>
            <div class="actions"><button class="btn primaire" id="b-ebay">${c.ebay ? "Tester / remplacer" : "Vérifier et enregistrer"}</button></div>
          </form></div>
        <div class="carte"><div class="compte-tete"><span class="ico">📧</span><div><h2>Gmail</h2><small class="muted">lit les alertes e-mail Leboncoin</small></div>${etat(c.gmail)}</div>
          <form class="formulaire" id="f-gmail" onsubmit="return false">
            <details><summary class="petit second" style="cursor:pointer">Comment faire ? (2 minutes)</summary>
              <ol class="petit second" style="padding-left:18px;margin:10px 0 0;display:grid;gap:6px">
                <li>Sur <b>leboncoin.fr</b>, cherche une console, clique <b>Enregistrer la recherche</b> et active les <b>alertes e-mail</b>.</li>
                <li>Active la <b>validation en deux étapes</b> de ton compte Google.</li>
                <li>Va sur <a href="https://myaccount.google.com/apppasswords" target="_blank" rel="noopener">myaccount.google.com/apppasswords</a>, crée un mot de passe nommé « veille » et copie le code de 16 lettres.</li>
              </ol><p class="petit muted" style="margin-top:8px">Lecture seule : rien n'est supprimé ni marqué comme lu.</p></details>
            <label class="champ">Adresse Gmail<input type="email" name="adresse" value="${echap(c.gmail_adresse)}" placeholder="toi@gmail.com"></label>
            <label class="champ">Code de 16 lettres<input type="password" name="code" autocomplete="off" placeholder="${c.gmail ? "déjà enregistré — laisser vide pour tester" : "abcd efgh ijkl mnop"}"></label>
            <div class="actions"><button class="btn primaire" id="b-gmail">${c.gmail ? "Tester la connexion" : "Connecter"}</button></div>
            <div id="gmail-res"></div>
          </form></div>
        <div class="carte"><div class="compte-tete"><span class="ico">🐙</span><div><h2>GitHub</h2><small class="muted">là où tourne le robot</small></div>${etat(!!g.depot, "Relié", "Non relié")}</div>
          <div id="gh"></div></div>
        <div class="carte"><div class="compte-tete"><span class="ico">📲</span><div><h2>Sur mon téléphone</h2><small class="muted">même Wi-Fi que ce PC</small></div></div>
          <div id="tel"></div></div>
        ${r.windows ? `<div class="carte"><div class="compte-tete"><span class="ico">🖥️</span><div><h2>Raccourci Bureau</h2><small class="muted">icône « Veille consoles »</small></div></div>
          <p class="second petit" style="margin-bottom:12px">Recrée l'icône sur ton Bureau si elle a disparu.</p><button class="btn" id="b-racc">Créer le raccourci</button></div>` : ""}
      </div>
      <section class="carte" style="margin-top:14px;display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap">
        <p class="second">Fermer complètement le logiciel (il s'arrête aussi tout seul quand tu fermes la fenêtre).</p>
        <button class="btn danger" id="b-quitter">Quitter le logiciel</button></section>`;

    assistantTelegram(c.telegram);
    blocGithub(g);
    blocTelephone(r.telephone);
    $("#b-ebay").onclick = (e) => avecAttente(e.currentTarget, async () => {
      const f = $("#f-ebay").elements;
      const envoyer = (forcer) => api("/api/comptes/ebay", { client_id: f.id.value, secret: f.secret.value, forcer });
      const res = await envoyer(false);
      if (res.valide) { toast("eBay accepte tes clés 🎉"); pageComptes(); return; }
      modale("eBay refuse ces clés", `<p>${echap(res.message)}</p><p class="second" style="margin-top:10px">Si ton compte développeur est encore en cours de vérification chez eBay, c'est normal. Tu peux les enregistrer quand même.</p>`, [
        { libelle: "Annuler", faire: () => $("#modale").close() },
        { libelle: "Enregistrer quand même", classe: "primaire", faire: async (el) => avecAttente(el, async () => { await envoyer(true); $("#modale").close(); toast("Clés enregistrées."); pageComptes(); }) },
      ]);
    });
    $("#b-gmail").onclick = (e) => avecAttente(e.currentTarget, async () => {
      const f = $("#f-gmail").elements;
      const res = await api("/api/comptes/gmail", { adresse: f.adresse.value, code: f.code.value });
      toast("Gmail accepte la connexion ✓");
      $("#gmail-res").innerHTML = res.emails === 0
        ? `<p class="petit second">Aucun e-mail Leboncoin des 3 derniers jours : normal si tu viens de créer tes alertes.</p>`
        : `<p class="petit second">${res.emails} e-mail(s) lus, ${res.annonces.length} annonce(s) extraite(s).</p>
           <div class="liste">${res.annonces.map((a) => `<div class="rang"><div class="principal">${echap(a.titre)}</div><b class="num">${euros(a.prix)}</b></div>`).join("")}</div>`;
    });
    const rac = $("#b-racc");
    if (rac) rac.onclick = (e) => avecAttente(e.currentTarget, async () => { await api("/api/raccourci", {}); toast("Raccourci créé sur ton Bureau 🎮"); });
    $("#b-quitter").onclick = async () => {
      await api("/api/quitter", {}).catch(() => {});
      document.body.innerHTML = '<div class="chargement"><div style="text-align:center"><div style="font-size:2rem">👋</div><p>Logiciel fermé. Tu peux fermer cette fenêtre.</p></div></div>';
      window.close();
    };
  }

  function assistantTelegram(dejaFait) {
    const zone = $("#tg");
    if (dejaFait) {
      zone.innerHTML = `<p class="second petit" style="margin-bottom:12px">Ton bot est connecté. Les alertes du robot arrivent sur ton téléphone.</p>
        <div class="actions"><button class="btn" id="tg-test">Envoyer un message de test</button><button class="btn fantome" id="tg-refaire">Reconfigurer</button></div>`;
      $("#tg-test").onclick = (e) => avecAttente(e.currentTarget, async () => { await api("/api/comptes/telegram/test", {}); toast("Message envoyé : regarde ton téléphone 📱"); });
      $("#tg-refaire").onclick = () => assistantTelegram(false);
      return;
    }
    zone.innerHTML = `<div class="etapes">
      <div class="etape" id="tg-e1"><div><b>Crée ton bot</b><p class="petit second">Dans Telegram, cherche <b>@BotFather</b> (badge bleu), envoie <code>/newbot</code>, choisis un nom puis un identifiant qui finit par « bot ». Il te donne un jeton.</p>
        <div style="display:flex;gap:8px"><input type="password" id="tg-jeton" placeholder="7123456789:AAH…" autocomplete="off"><button class="btn primaire" id="tg-b1">Vérifier</button></div></div></div>
      <div class="etape" id="tg-e2"><div><b>Dis bonjour à ton bot</b><p class="petit second" id="tg-txt2">Une fois le jeton vérifié, ouvre ton bot et envoie-lui « bonjour ».</p>
        <div><button class="btn" id="tg-b2" disabled>C'est fait</button></div></div></div>
    </div>`;
    $("#tg-b1").onclick = (e) => avecAttente(e.currentTarget, async () => {
      const r = await api("/api/comptes/telegram/jeton", { jeton: $("#tg-jeton").value });
      $("#tg-e1").classList.add("fait");
      $("#tg-txt2").innerHTML = `Ouvre <a href="https://t.me/${echap(r.bot)}" target="_blank" rel="noopener">t.me/${echap(r.bot)}</a>, appuie sur <b>Démarrer</b> et envoie « bonjour ».`;
      $("#tg-b2").disabled = false; $("#tg-b2").classList.add("primaire");
    });
    $("#tg-b2").onclick = (e) => avecAttente(e.currentTarget, async () => {
      const r = await api("/api/comptes/telegram/verifier", {});
      toast(`Connecté avec ${r.prenom} ! ${r.test ? "Un message de test est parti 📱" : ""}`);
      toast("Pense à mettre le jeton dans les secrets GitHub pour le robot (voir le guide).", "info");
      pageComptes();
    });
  }

  function blocGithub(g) {
    const zone = $("#gh");
    if (!g.git) { zone.innerHTML = `<p class="second petit">Git n'est pas installé sur ce PC. Installe-le depuis <a href="https://git-scm.com/download/win" target="_blank" rel="noopener">git-scm.com</a> (options par défaut), puis relance le logiciel.</p>`; return; }
    if (g.depot) {
      zone.innerHTML = `<p class="second petit" style="margin-bottom:12px">Relié à <a href="https://github.com/${echap(g.depot)}" target="_blank" rel="noopener"><b>${echap(g.depot)}</b></a>.
          ${g.modifs.length ? `<br>${g.modifs.length} modification(s) en attente : ${g.modifs.map(echap).join(", ")}.` : "<br>Tout est à jour."}</p>
        <div class="actions"><button class="btn primaire" data-action="synchro">Synchroniser maintenant</button>
          <a class="btn fantome" href="https://github.com/${echap(g.depot)}/actions" target="_blank" rel="noopener">Voir le robot</a></div>
        <details style="margin-top:14px"><summary class="petit muted" style="cursor:pointer">Changer le nom qui signe les modifications</summary>
          <form class="formulaire" id="f-id" style="margin-top:10px" onsubmit="return false"><label class="champ">Pseudo GitHub<input type="text" name="pseudo"></label>
          <button class="btn" id="b-id">Enregistrer</button></form></details>`;
      $("#b-id").onclick = (e) => avecAttente(e.currentTarget, async () => { await api("/api/github/identite", { pseudo: $("#f-id").elements.pseudo.value }); toast("Enregistré."); });
      return;
    }
    zone.innerHTML = `<form class="formulaire" id="f-gh" onsubmit="return false">
      <p class="petit second">1. Sur <a href="https://github.com/new" target="_blank" rel="noopener">github.com/new</a>, crée un repo <b>veille-consoles</b> en <b>Private</b>, sans rien cocher d'autre.<br>2. Copie son adresse ci-dessous.</p>
      <label class="champ">Adresse du repo<input type="text" name="adresse" placeholder="https://github.com/pseudo/veille-consoles.git"></label>
      <label class="champ">Ton pseudo GitHub<input type="text" name="pseudo"></label>
      <div class="actions"><button class="btn primaire" id="b-gh">Relier et envoyer</button></div>
      <p class="petit muted">Une fenêtre de connexion GitHub peut s'ouvrir.</p></form>`;
    $("#b-gh").onclick = (e) => avecAttente(e.currentTarget, async () => {
      const f = $("#f-gh").elements;
      await api("/api/github/relier", { adresse: f.adresse.value, pseudo: f.pseudo.value });
      toast("Projet envoyé sur GitHub 🎉 Ajoute maintenant les secrets (voir le guide).");
      pageComptes();
    });
  }

  function blocTelephone(t) {
    const zone = $("#tel");
    const surPC = ["127.0.0.1", "localhost"].includes(location.hostname);
    if (!surPC) { zone.innerHTML = `<p class="second petit">Tu utilises déjà le logiciel sur ton téléphone 👍</p>`; return; }
    zone.innerHTML = `<div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">
        <label class="interrupteur"><input type="checkbox" id="tel-on" ${t.actif ? "checked" : ""}><span></span></label>
        <span>${t.actif ? "Accès téléphone activé" : "Activer l'accès depuis mon téléphone"}</span></div>
      ${t.actif ? `<div style="display:flex;gap:16px;align-items:center;flex-wrap:wrap"><div class="qr">${t.qr}</div>
          <p class="petit second" style="flex:1;min-width:180px">Scanne ce QR code avec l'appareil photo du téléphone (connecté au <b>même Wi-Fi</b>).<br><br>
          Ça marche tant que ce PC est allumé et le logiciel ouvert. Ailleurs, les alertes Telegram continuent d'arriver.</p></div>`
        : `<p class="petit muted">Windows peut te demander d'autoriser l'accès réseau : choisis « Réseaux privés ».</p>`}`;
    $("#tel-on").onchange = async (e) => {
      try { const r = await api("/api/telephone", { actif: e.target.checked }); blocTelephone(r); }
      catch (err) { toast(err.message, "bad"); e.target.checked = false; }
    };
  }

  // ───────────── navigation ─────────────
  const PAGES = { accueil: pageAccueil, prix: pagePrix, watchlist: pageWatchlist, tester: pageTester, comptes: pageComptes };
  let pageActuelle = null;
  async function afficher() {
    const nom = (location.hash || "#accueil").slice(1);
    const page = PAGES[nom] ? nom : "accueil";
    const changement = page !== pageActuelle;
    pageActuelle = page;
    $$(".nav nav a").forEach((a) => a.classList.toggle("actif", a.dataset.page === page));
    if (changement) {
      contenu.innerHTML = `<div class="squelette" style="height:46px;width:260px;margin-bottom:24px"></div><div class="grille g-tuiles">${'<div class="squelette" style="height:104px"></div>'.repeat(4)}</div>`;
      window.scrollTo(0, 0);
    }
    try { await PAGES[page](); }
    catch (e) {
      contenu.innerHTML = `<div class="carte vide"><div class="grand">😕</div><p><b>Oups, un problème.</b></p><p class="petit muted" style="margin-top:6px">${echap(e.message)}</p>
        <button class="btn" style="margin-top:14px" onclick="location.reload()">Réessayer</button></div>`;
    }
  }
  window.addEventListener("hashchange", afficher);
  afficher();

  // Signe de vie : quand la fenêtre est fermée, le logiciel s'arrête tout seul.
  setInterval(() => fetch("/api/ping").catch(() => {}), 10000);
  fetch("/api/ping").catch(() => {});
})();
