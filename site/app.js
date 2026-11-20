/* Veille consoles — site privé */
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
  const attendre = (ms) => new Promise((r) => setTimeout(r, ms));
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
    const options = { headers: { "X-Veille": "1" }, credentials: "same-origin" };
    if (corps !== undefined) {
      options.method = "POST";
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(corps);
    }
    let r;
    try { r = await fetch("/api" + chemin, options); }
    catch { throw new Error("Pas de connexion internet ?"); }
    const donnees = await r.json().catch(() => ({}));
    if (r.status === 401 && donnees.connexion) { montrerConnexion(); throw new Error("Connecte-toi."); }
    if (!r.ok) throw new Error(donnees.erreur || `Erreur ${r.status}`);
    return donnees;
  }

  function toast(texte, type = "ok") {
    const t = document.createElement("div");
    t.className = `toast ${type}`;
    t.innerHTML = `<p>${echap(texte)}</p>`;
    $("#toasts").appendChild(t);
    setTimeout(() => t.remove(), type === "bad" ? 7000 : 4500);
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

  // Pas de JavaScript dans le HTML (sécurité) : on gère ici les formulaires et les images cassées.
  document.addEventListener("submit", (e) => { if (e.target.id !== "f-connexion") e.preventDefault(); });
  document.addEventListener("error", (e) => { if (e.target.tagName === "IMG") e.target.remove(); }, true);

  const ICONES = {
    eclair: '<svg viewBox="0 0 24 24"><path d="M13 2 4 14h6l-1 8 9-12h-6l1-8Z"/></svg>',
    plus: '<svg viewBox="0 0 24 24"><path d="M11 5h2v6h6v2h-6v6h-2v-6H5v-2h6V5Z"/></svg>',
    crayon: '<svg viewBox="0 0 24 24"><path d="m14.1 5.9 4 4L8 20H4v-4L14.1 5.9Zm1.4-1.4 2-2 4 4-2 2-4-4Z"/></svg>',
    poubelle: '<svg viewBox="0 0 24 24"><path d="M9 3h6l1 2h4v2H4V5h4l1-2Zm-3 6h12l-1 12H7L6 9Z"/></svg>',
    lien: '<svg viewBox="0 0 24 24"><path d="M14 3h7v7h-2V6.4l-8.3 8.3-1.4-1.4L17.6 5H14V3ZM5 5h6v2H5v12h12v-6h2v8H3V5h2Z"/></svg>',
    image: '<svg viewBox="0 0 24 24" width="34" height="34"><path d="M4 5h16v14H4V5Zm2 2v8.6l3.5-3.5 3 3 2.5-2.5L18 15.6V7H6Zm9 1.5a1.5 1.5 0 1 1 0 3 1.5 1.5 0 0 1 0-3Z"/></svg>',
  };

  // ───────────── connexion ─────────────
  function montrerConnexion() {
    $("#app").hidden = true;
    $("#ecran-connexion").hidden = false;
    $("#f-connexion").elements.mdp.focus();
  }
  $("#f-connexion").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = e.target, err = $("#erreur-connexion"), btn = $("button", f);
    err.hidden = true; btn.disabled = true;
    try {
      const r = await fetch("/api/connexion", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mot_de_passe: f.elements.mdp.value }) });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.erreur || "Connexion impossible.");
      f.reset();
      demarrer();
    } catch (ex) { err.textContent = ex.message; err.hidden = false; }
    finally { btn.disabled = false; }
  });

  // ───────────── robot ─────────────
  let resume = null;
  async function chargerResume() {
    resume = await api("/resume");
    majRobot(resume.executions);
    return resume;
  }

  function texteExecution(x) {
    if (!x) return { cls: "", txt: "Robot : aucun passage" };
    if (x.statut !== "completed") return { cls: "tourne", txt: "Robot en train de chercher…" };
    if (x.resultat === "success") return { cls: "ok", txt: `Robot OK · ${depuis(x.fin)}` };
    return { cls: "bad", txt: `Robot en échec · ${depuis(x.fin)}` };
  }
  function majRobot(executions) {
    const { cls, txt } = texteExecution(executions?.[0]);
    $("#etat-robot").innerHTML = `<span class="point ${cls}"></span><span>${echap(txt)}</span>`;
  }

  async function lancerRobot(bouton) {
    await avecAttente(bouton, async () => {
      const r = await api("/robot/lancer", {});
      toast(r.deja ? "Le robot tourne déjà, je suis son avancement." : "Robot lancé sur GitHub 🚀 Il met 1 à 2 minutes.", "info");
      await suivreRobot();
    });
  }

  async function suivreRobot() {
    const zone = $("#zone-robot");
    const debut = Date.now();
    let vuEnCours = false;
    while (Date.now() - debut < 8 * 60000) {
      await attendre(6000);
      const { executions } = await api("/robot").catch(() => ({ executions: null }));
      if (!executions) continue;
      majRobot(executions);
      const x = executions[0];
      if (x && x.statut !== "completed") vuEnCours = true;
      if (zone) zone.innerHTML = x && x.statut !== "completed"
        ? `<div class="alerte-bandeau info"><span class="rond-attente"></span><p>Le robot cherche de nouvelles annonces… (${Math.round((Date.now() - new Date(x.debut)) / 1000)} s)</p><a class="btn petit" href="${echap(lienSur(x.url))}" target="_blank" rel="noopener">Voir sur GitHub</a></div>` : "";
      if (vuEnCours && x?.statut === "completed") {
        toast(x.resultat === "success" ? "Veille terminée ✓ Les nouvelles alertes sont aussi parties sur Telegram." : "Le robot a rencontré une erreur. Regarde le détail sur GitHub.", x.resultat === "success" ? "ok" : "bad");
        if (pageActuelle === "accueil") pageAccueil();
        return;
      }
    }
  }

  // ───────────── carte d'annonce ─────────────
  const nomSource = (s) => ({ ebay: "eBay", vinted: "Vinted", label_emmaus: "Label Emmaüs", leboncoin: "Leboncoin", leboncoin_email: "Leboncoin" }[s] || s || "");
  function carteAnnonce(a) {
    const an = a.analyse || {};
    const [etatLib, etatCls] = ETATS[a.etat] || ETATS.inconnu;
    const badges = [];
    if (an.feu) badges.push('<span class="badge feu">🔥 Bonne affaire</span>');
    badges.push(`<span class="badge ${etatCls}">${a.etat === "hs" ? "🔧 " : ""}${etatLib}</span>`);
    if (an.lot) badges.push('<span class="badge">📦 Lot</span>');
    if (a.vendue) badges.unshift(`<span class="badge bad">${a.motif_vendue === "retiree" ? "Retirée" : "Vendue"} · ${depuis(a.vendue)}</span>`);
    const chiffres = [];
    if (an.montrer_marge && an.marge_eur != null)
      chiffres.push(`<span>Marge <b class="${an.marge_eur >= 0 ? "plus" : "moins"}">${an.marge_eur >= 0 ? "+" : ""}${an.marge_eur} €</b></span>`);
    if (an.montrer_score && an.ecart_pct != null)
      chiffres.push(`<span>vs médiane <b class="${an.ecart_pct >= 0 ? "plus" : "moins"}">${an.ecart_pct >= 0 ? "−" : "+"}${Math.abs(an.ecart_pct)} %</b></span>`);
    const photo = a.photo && /^https:/.test(a.photo) ? `<img src="${echap(a.photo)}" alt="" loading="lazy" referrerpolicy="no-referrer">` : ICONES.image;
    return `<article class="carte annonce">
      <div class="photo">${photo}<div class="badges">${badges.join("")}</div></div>
      <div class="corps">
        <div class="titre" title="${echap(a.titre)}">${echap(a.titre)}</div>
        <div class="ligne-prix"><span class="prix">${euros(a.prix_total)}</span><span class="badge accent">${echap(a.recherche || "")}</span></div>
        ${chiffres.length ? `<div class="chiffres">${chiffres.join("")}</div>` : ""}
        <div class="pied"><span>${echap(nomSource(a.source))}${a.date_alerte ? " · " + echap(depuis(a.date_alerte)) : ""}</span>
          <a class="btn petit" href="${echap(lienSur(a.url))}" target="_blank" rel="noopener noreferrer">${ICONES.lien}Voir</a></div>
      </div></article>`;
  }

  // ───────────── page Accueil ─────────────
  let filtreAlertes = "toutes";
  let voirVendues = false;
  async function pageAccueil() {
    const r = await chargerResume();
    const il30 = Date.now() - 30 * 86400000;
    const alertes30 = r.alertes.filter((a) => new Date(a.date_alerte).getTime() > il30);
    const vendues30 = (r.vendues || []).filter((a) => new Date(a.date_alerte).getTime() > il30).length;
    const feux = alertes30.filter((a) => a.analyse?.feu).length;
    const recherches = [...new Set(r.alertes.map((a) => a.recherche))];
    const source = voirVendues ? r.vendues || [] : r.alertes;
    const liste = source.filter((a) => filtreAlertes === "toutes" || (filtreAlertes === "feu" ? a.analyse?.feu : a.recherche === filtreAlertes));
    const derniere = r.executions[0];
    const enCours = derniere && derniere.statut !== "completed";
    const sansTelegram = r.comptes && !r.comptes.telegram;

    contenu.innerHTML = `
      <div class="entete"><div><h1>Bonjour 👋</h1><p>Voici ce que ton robot a trouvé.</p></div>
        <div class="actions"><button class="btn primaire" id="b-veille">${ICONES.eclair}Lancer une veille maintenant</button></div></div>
      <div id="zone-robot"></div>
      ${sansTelegram ? `<div class="alerte-bandeau warn"><span>📱</span><p>Telegram n'est pas configuré : le robot ne peut pas t'envoyer d'alertes.</p><a class="btn petit" href="#comptes">Configurer</a></div>` : ""}
      ${r.watchlist.erreur ? `<div class="alerte-bandeau bad"><span>⚠️</span><p>${echap(r.watchlist.erreur)}</p></div>` : ""}
      ${derniere && derniere.statut === "completed" && derniere.resultat !== "success" ? `<div class="alerte-bandeau bad"><span>⚠️</span><p>Le dernier passage du robot a échoué.</p><a class="btn petit" href="${echap(lienSur(derniere.url))}" target="_blank" rel="noopener">Voir le détail</a></div>` : ""}
      <section class="grille g-tuiles">
        <div class="carte tuile"><div class="etiquette">Alertes encore en vente</div><div class="valeur">${alertes30.length}</div><div class="sous">${feux} 🔥 · ${vendues30} déjà vendue(s) (30 j)</div></div>
        <div class="carte tuile"><div class="etiquette">Annonces analysées</div><div class="valeur">${r.nb_vues.toLocaleString("fr-FR")}</div><div class="sous">depuis le début</div></div>
        <div class="carte tuile"><div class="etiquette">Recherches actives</div><div class="valeur">${r.watchlist.actives}</div><div class="sous">${r.watchlist.total - r.watchlist.actives} en pause</div></div>
        <div class="carte tuile"><div class="etiquette">Dernier passage du robot</div><div class="valeur" style="font-size:1.35rem;padding-top:6px">${enCours ? "en cours…" : depuis(derniere?.fin)}</div><div class="sous">toutes les 30 min sur GitHub</div></div>
      </section>
      <section>
        <div class="titre-section"><h2>${voirVendues ? "Annonces vendues ou retirées" : "Dernières alertes"}</h2>
          <div class="puces" id="filtres">
            <button class="puce" data-f="toutes">Toutes</button><button class="puce" data-f="feu">🔥 Bonnes affaires</button>
            ${recherches.map((n) => `<button class="puce" data-f="${echap(n)}">${echap(n)}</button>`).join("")}
            ${r.nb_vendues ? `<button class="puce ${voirVendues ? "actif" : ""}" id="b-vendues">${voirVendues ? "↩ Annonces en vente" : `Vendues (${r.nb_vendues})`}</button>` : ""}
          </div></div>
        ${liste.length ? `<div class="grille g-annonces">${liste.map(carteAnnonce).join("")}</div>`
          : `<div class="carte vide"><div class="grand">🕹️</div><p><b>Aucune alerte pour l'instant.</b></p>
             <p class="petit muted" style="margin-top:6px">Le robot t'enverra une alerte dès qu'une annonce passe sous tes prix maximum.</p></div>`}
      </section>
      <section>
        <div class="titre-section"><h2>Sites surveillés</h2><small class="muted">état vu par le robot</small></div>
        <div class="carte"><div class="liste">${r.sources.map(rangSource).join("")}</div></div>
      </section>`;
    $$("#filtres .puce").forEach((b) => {
      b.classList.toggle("actif", b.dataset.f === filtreAlertes);
      b.onclick = () => { filtreAlertes = b.dataset.f; pageAccueil(); };
    });
    $("#b-veille").onclick = (e) => lancerRobot(e.currentTarget);
    const bv = $("#b-vendues");
    if (bv) bv.onclick = () => { voirVendues = !voirVendues; filtreAlertes = "toutes"; pageAccueil(); };
    if (enCours) suivreRobot();
  }

  function rangSource(s) {
    const besoin = { ebay: "ebay", leboncoin_email: "gmail" }[s.nom];
    let cls = "ok", txt = s.dernier_succes ? `OK · ${depuis(s.dernier_succes)}` : "Pas encore utilisé";
    if (!s.actif) { cls = ""; txt = "Désactivé"; }
    else if (besoin && resume.comptes && !resume.comptes[besoin]) { cls = "warn"; txt = "À configurer"; }
    else if (s.echecs >= 3) { cls = "bad"; txt = `En panne (${s.echecs} échecs)`; }
    else if (s.echecs) { cls = "warn"; txt = `${s.echecs} échec(s) récent(s)`; }
    else if (!s.dernier_succes) cls = "";
    return `<div class="rang"><span class="point ${cls}"></span><div class="principal"><b>${echap(s.libelle)}</b></div>
      <span class="badge ${cls}">${echap(txt)}</span></div>`;
  }

  // ───────────── page Prix ─────────────
  let prixChoisi = null;
  const differe = (x) => ["prix_max", "prix_max_hs", "prix_revente_ref"].some((k) => x.conseils[k] != null && x.conseils[k] !== x.actuel[k]);

  async function pagePrix() {
    const d = await api("/prix");
    const avecDonnees = d.recherches.filter((r) => r.stats);
    if (!prixChoisi || !d.recherches.some((r) => r.nom === prixChoisi)) prixChoisi = (avecDonnees[0] || d.recherches[0])?.nom;
    const r = d.recherches.find((x) => x.nom === prixChoisi);
    const aAppliquer = d.recherches.filter((x) => x.conseils && differe(x));

    contenu.innerHTML = `
      <div class="entete"><div><h1>Prix du marché</h1><p>Calculés à partir des annonces relevées par le robot.</p></div>
        <div class="actions">${aAppliquer.length ? `<button class="btn primaire" id="b-tout">Appliquer tous les prix conseillés (${aAppliquer.length})</button>` : ""}</div></div>
      <div class="puces" style="margin-bottom:18px">${d.recherches.map((x) => `<button class="puce ${x.nom === prixChoisi ? "actif" : ""}" data-n="${echap(x.nom)}">${echap(x.nom)}${x.stats ? "" : " · pas de relevés"}</button>`).join("")}</div>
      ${r ? blocPrix(r, d.echantillon_min) : ""}
      <section>
        <div class="titre-section"><h2>Toutes les consoles</h2><small class="muted">revente = médiane − 10 % · prix max = 70 % de la médiane · max HS = garde ≈ 30 € de marge</small></div>
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
    const fr = (j) => j.split("-").reverse().join("/");
    const periode = s.nb_jours > 1 ? `du ${fr(s.premier_jour)} au ${fr(s.dernier_jour)}` : `le ${fr(s.premier_jour)}`;
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

  const MSG_ENREGISTRE = "Enregistré sur GitHub ✓ Le robot l'utilisera à son prochain passage.";

  async function appliquer(noms, bouton) {
    await avecAttente(bouton, async () => {
      await api("/prix/appliquer", { noms });
      toast(MSG_ENREGISTRE);
      await pagePrix();
    });
  }

  // ───────────── page Watchlist ─────────────
  let watchlist = null;
  async function pageWatchlist() {
    watchlist = await api("/watchlist");
    contenu.innerHTML = `
      <div class="entete"><div><h1>Ma watchlist</h1><p>Les consoles que le robot surveille. Prix toujours <b>port compris</b>.</p></div>
        <div class="actions"><button class="btn primaire" id="b-ajout">${ICONES.plus}Ajouter une console</button></div></div>
      <section class="grille">${watchlist.recherches.map(carteRecherche).join("")}</section>
      <section>
        <div class="titre-section"><h2>Mots exclus partout</h2><small class="muted">une annonce dont le titre contient l'un de ces mots est ignorée</small></div>
        <div class="carte"><div class="etiquettes" id="excl"></div>
          <div class="actions" style="margin-top:12px;justify-content:flex-end"><button class="btn" id="b-excl">Enregistrer les mots exclus</button></div></div>
      </section>`;
    const excl = editeurEtiquettes($("#excl"), watchlist.exclusions, "Ajouter un mot puis Entrée…");
    $("#b-excl").onclick = (e) => avecAttente(e.currentTarget, async () => { await api("/watchlist/exclusions", { mots: excl() }); toast(MSG_ENREGISTRE); });
    $("#b-ajout").onclick = () => formulaireRecherche(null);
    $$("[data-actif]").forEach((c) => (c.onchange = async () => {
      c.disabled = true;
      try { await api("/watchlist/champs", { nom: c.dataset.actif, champs: { actif: c.checked } }); toast(c.checked ? "Recherche activée ✓" : "Recherche mise en pause ✓"); pageWatchlist(); }
      catch (e) { toast(e.message, "bad"); c.checked = !c.checked; c.disabled = false; }
    }));
    $$("[data-modif]").forEach((b) => (b.onclick = () => formulaireRecherche(watchlist.recherches.find((r) => r.nom === b.dataset.modif))));
    $$("[data-suppr]").forEach((b) => (b.onclick = () => {
      const nom = b.dataset.suppr;
      modale("Supprimer cette recherche ?", `<p>« <b>${echap(nom)}</b> » sera retirée de ta watchlist. Tu peux aussi simplement la mettre en pause.</p>`, [
        { libelle: "Annuler", faire: () => $("#modale").close() },
        { libelle: "Supprimer", classe: "danger", faire: (el) => avecAttente(el, async () => { await api("/watchlist/supprimer", { nom }); $("#modale").close(); toast(MSG_ENREGISTRE); pageWatchlist(); }) },
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
    const liste = [...valeurs];
    const ajouter = (inp, garderFocus = true) => {
      liste.push(inp.value.trim());
      inp.value = ""; inp.onblur = null; // évite un double ajout quand le champ est recréé
      dessiner();
      if (garderFocus) $("input", boite).focus();
    };
    const dessiner = () => {
      boite.innerHTML = liste.map((v, i) => `<span class="etq">${echap(v)}<button type="button" data-i="${i}" aria-label="Retirer">×</button></span>`).join("") + `<input type="text" placeholder="${echap(invite)}" enterkeyhint="done">`;
      $$("button", boite).forEach((b) => (b.onclick = () => { liste.splice(+b.dataset.i, 1); dessiner(); }));
      const inp = $("input", boite);
      inp.onkeydown = (e) => {
        if ((e.key === "Enter" || e.key === ",") && inp.value.trim()) { e.preventDefault(); ajouter(inp); }
        else if (e.key === "Backspace" && !inp.value && liste.length) { liste.pop(); inp.onblur = null; dessiner(); $("input", boite).focus(); }
      };
      inp.onblur = () => { if (inp.value.trim()) ajouter(inp, false); };
    };
    dessiner();
    return () => { const inp = $("input", boite); if (inp && inp.value.trim()) liste.push(inp.value.trim()); return liste; };
  }

  function formulaireRecherche(r) {
    const n = r || { nom: "", requete: "", inclure: [], exclure: [], prix_max: "", prix_max_hs: "", mode: "les_deux", prix_revente_ref: "", cout_pieces: "", actif: true };
    const v = (x) => (x == null ? "" : x);
    const d = modale(r ? `Modifier « ${r.nom} »` : "Ajouter une console", `
      <form class="formulaire" id="f-rech">
        <div class="deux">
          <label class="champ">Nom affiché<input type="text" name="nom" value="${echap(n.nom)}" placeholder="ex. GameCube" required></label>
          <label class="champ">Texte recherché sur les sites<input type="text" name="requete" value="${echap(n.requete)}" placeholder="ex. nintendo gamecube"></label>
        </div>
        <div class="champ"><span>Type d'achat</span><div class="segment" id="seg-mode">
          ${Object.entries(MODES).map(([k, l]) => `<button type="button" data-m="${k}">${l}</button>`).join("")}</div>
          <span class="aide" id="aide-mode"></span></div>
        <div class="trois">
          <label class="champ">Prix max (marche)<input type="number" inputmode="numeric" name="prix_max" min="0" step="1" value="${v(n.prix_max)}" required></label>
          <label class="champ">Prix max HS<input type="number" inputmode="numeric" name="prix_max_hs" min="0" step="1" value="${v(n.prix_max_hs)}" placeholder="facultatif"></label>
          <label class="champ">Prix de revente<input type="number" inputmode="numeric" name="prix_revente_ref" min="0" step="1" value="${v(n.prix_revente_ref)}" placeholder="auto"></label>
        </div>
        <div class="deux">
          <label class="champ">Coût des pièces (réparation)<input type="number" inputmode="numeric" name="cout_pieces" min="0" step="1" value="${v(n.cout_pieces)}" placeholder="facultatif"></label>
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
            prix_max_hs: val("prix_max_hs"), prix_revente_ref: val("prix_revente_ref"), cout_pieces: val("cout_pieces") };
          await api("/watchlist/recherche", { recherche, ancien_nom: r ? r.nom : null });
          d.close(); toast(MSG_ENREGISTRE); pageWatchlist();
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

  // ───────────── page Comptes ─────────────
  async function pageComptes() {
    const r = await chargerResume();
    const c = r.comptes;
    const etat = (ok, oui = "Configuré", non = "À configurer") => !c ? '<span class="badge">?</span>' : `<span class="badge ${ok ? "ok" : "warn"}">${ok ? "✓ " + oui : non}</span>`;
    contenu.innerHTML = `
      <div class="entete"><div><h1>Comptes</h1><p>Tes clés sont enregistrées dans les <b>secrets GitHub</b> du robot : chiffrées, jamais visibles, même par ce site.</p></div></div>
      ${!c ? `<div class="alerte-bandeau warn"><span>🔒</span><p>Je ne peux pas lire l'état des secrets : donne au jeton GitHub la permission « Secrets : Read and write ».</p></div>` : ""}
      <div class="grille g-2">
        <div class="carte"><div class="compte-tete"><span class="ico">📱</span><div><h2>Telegram</h2><small class="muted">pour recevoir les alertes</small></div>${etat(c?.telegram, "Connecté")}</div>
          <div id="tg"></div></div>
        <div class="carte"><div class="compte-tete"><span class="ico">🛒</span><div><h2>eBay</h2><small class="muted">API officielle, gratuite</small></div>${etat(c?.ebay, "Clés enregistrées")}</div>
          <form class="formulaire" id="f-ebay">
            <p class="petit second">Sur <a href="https://developer.ebay.com/my/keys" target="_blank" rel="noopener">developer.ebay.com</a> → <b>Application Keysets</b> → colonne <b>Production</b>. eBay peut mettre quelques jours à activer un nouveau compte.</p>
            <label class="champ">App ID (Client ID)<input type="text" name="id" autocomplete="off"></label>
            <label class="champ">Cert ID (Client Secret)<input type="password" name="secret" autocomplete="off"></label>
            <div class="actions"><button class="btn primaire" id="b-ebay">${c?.ebay ? "Remplacer les clés" : "Vérifier et enregistrer"}</button></div>
          </form></div>
        <div class="carte"><div class="compte-tete"><span class="ico">📧</span><div><h2>Gmail</h2><small class="muted">lit les alertes e-mail Leboncoin</small></div>${etat(c?.gmail, "Connecté")}</div>
          <form class="formulaire" id="f-gmail">
            <details><summary class="petit second" style="cursor:pointer">Comment faire ? (2 minutes)</summary>
              <ol class="petit second" style="padding-left:18px;margin:10px 0 0;display:grid;gap:6px">
                <li>Sur <b>leboncoin.fr</b>, cherche une console, clique <b>Enregistrer la recherche</b> et active les <b>alertes e-mail</b>.</li>
                <li>Active la <b>validation en deux étapes</b> de ton compte Google.</li>
                <li>Va sur <a href="https://myaccount.google.com/apppasswords" target="_blank" rel="noopener">myaccount.google.com/apppasswords</a>, crée un mot de passe nommé « veille » et copie le code de 16 lettres.</li>
              </ol><p class="petit muted" style="margin-top:8px">Lecture seule : rien n'est supprimé ni marqué comme lu. La connexion est vérifiée au prochain passage du robot (voir « Sites surveillés » sur l'accueil).</p></details>
            <label class="champ">Adresse Gmail<input type="email" name="adresse" placeholder="toi@gmail.com" autocomplete="off"></label>
            <label class="champ">Code de 16 lettres<input type="password" name="code" autocomplete="off" placeholder="abcd efgh ijkl mnop"></label>
            <div class="actions"><button class="btn primaire" id="b-gmail">${c?.gmail ? "Remplacer" : "Enregistrer"}</button></div>
          </form></div>
        <div class="carte"><div class="compte-tete"><span class="ico">🐙</span><div><h2>GitHub</h2><small class="muted">là où tourne le robot</small></div><span class="badge ok">✓ Relié</span></div>
          <p class="second petit" style="margin-bottom:12px">Dépôt <a href="https://github.com/${echap(r.depot)}" target="_blank" rel="noopener"><b>${echap(r.depot)}</b></a>. Le robot passe toutes les 30 minutes.</p>
          <div class="liste" style="margin-bottom:12px">${r.executions.slice(0, 5).map((x) => { const t = texteExecution(x); return `<div class="rang"><span class="point ${t.cls}"></span><div class="principal">${x.statut !== "completed" ? "En cours" : x.resultat === "success" ? "Réussi" : "Échec"}<small>${depuis(x.debut)} · ${x.declencheur === "schedule" ? "automatique" : "lancé à la main"}</small></div><a class="petit" href="${echap(lienSur(x.url))}" target="_blank" rel="noopener">détail</a></div>`; }).join("") || '<p class="muted petit">Aucun passage pour l\'instant.</p>'}</div>
          <a class="btn" href="https://github.com/${echap(r.depot)}/actions" target="_blank" rel="noopener">${ICONES.lien}Ouvrir sur GitHub</a></div>
        <div class="carte"><div class="compte-tete"><span class="ico">📲</span><div><h2>Sur l'écran d'accueil</h2><small class="muted">comme une appli</small></div></div>
          <p class="second petit"><b>iPhone</b> : dans Safari, bouton Partager ⬆️ → « Sur l'écran d'accueil ».<br><b>Android</b> : dans Chrome, menu ⋮ → « Ajouter à l'écran d'accueil ».</p></div>
      </div>
      <section class="carte" style="margin-top:14px;display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap">
        <p class="second">Tu restes connecté 30 jours sur cet appareil.</p>
        <button class="btn danger" id="b-deco">Se déconnecter</button></section>`;

    assistantTelegram(c?.telegram);
    $("#b-ebay").onclick = (e) => avecAttente(e.currentTarget, async () => {
      const f = $("#f-ebay").elements;
      const envoyer = (forcer) => api("/comptes/ebay", { client_id: f.id.value, secret: f.secret.value, forcer });
      const res = await envoyer(false);
      if (res.valide) { toast("eBay accepte tes clés 🎉 Enregistrées pour le robot."); pageComptes(); return; }
      modale("eBay refuse ces clés", `<p>${echap(res.message)}</p><p class="second" style="margin-top:10px">Si ton compte développeur est encore en cours de vérification chez eBay, c'est normal. Tu peux les enregistrer quand même.</p>`, [
        { libelle: "Annuler", faire: () => $("#modale").close() },
        { libelle: "Enregistrer quand même", classe: "primaire", faire: (el) => avecAttente(el, async () => { await envoyer(true); $("#modale").close(); toast("Clés enregistrées."); pageComptes(); }) },
      ]);
    });
    $("#b-gmail").onclick = (e) => avecAttente(e.currentTarget, async () => {
      const f = $("#f-gmail").elements;
      await api("/comptes/gmail", { adresse: f.adresse.value, code: f.code.value });
      toast("Enregistré pour le robot ✓ Vérification à son prochain passage.");
      pageComptes();
    });
    $("#b-deco").onclick = async () => {
      await fetch("/api/deconnexion", { method: "POST" }).catch(() => {});
      montrerConnexion();
    };
  }

  function assistantTelegram(dejaFait) {
    const zone = $("#tg");
    if (dejaFait) {
      zone.innerHTML = `<p class="second petit" style="margin-bottom:12px">Ton bot est connecté : les alertes du robot arrivent sur ton téléphone.</p>
        <button class="btn fantome" id="tg-refaire">Changer de bot</button>`;
      $("#tg-refaire").onclick = () => assistantTelegram(false);
      return;
    }
    let jeton = "";
    zone.innerHTML = `<div class="etapes">
      <div class="etape" id="tg-e1"><div><b>Crée ton bot</b><p class="petit second">Dans Telegram, cherche <b>@BotFather</b> (badge bleu), envoie <code>/newbot</code>, choisis un nom puis un identifiant qui finit par « bot ». Il te donne un jeton.</p>
        <div style="display:flex;gap:8px"><input type="password" id="tg-jeton" placeholder="7123456789:AAH…" autocomplete="off"><button class="btn primaire" id="tg-b1">Vérifier</button></div></div></div>
      <div class="etape" id="tg-e2"><div><b>Dis bonjour à ton bot</b><p class="petit second" id="tg-txt2">Une fois le jeton vérifié, ouvre ton bot et envoie-lui « bonjour ».</p>
        <div><button class="btn" id="tg-b2" disabled>C'est fait</button></div></div></div>
    </div>`;
    $("#tg-b1").onclick = (e) => avecAttente(e.currentTarget, async () => {
      const r = await api("/comptes/telegram/jeton", { jeton: $("#tg-jeton").value });
      jeton = $("#tg-jeton").value.trim();
      $("#tg-e1").classList.add("fait");
      $("#tg-txt2").innerHTML = `Ouvre <a href="https://t.me/${echap(r.bot)}" target="_blank" rel="noopener">t.me/${echap(r.bot)}</a>, appuie sur <b>Démarrer</b> et envoie « bonjour ».`;
      $("#tg-b2").disabled = false; $("#tg-b2").classList.add("primaire");
    });
    $("#tg-b2").onclick = (e) => avecAttente(e.currentTarget, async () => {
      const r = await api("/comptes/telegram/verifier", { jeton });
      toast(`Connecté avec ${r.prenom} ! ${r.test ? "Un message de test est parti 📱" : ""}`);
      pageComptes();
    });
  }

  // ───────────── navigation ─────────────
  const PAGES = { accueil: pageAccueil, prix: pagePrix, watchlist: pageWatchlist, comptes: pageComptes };
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
      if ($("#app").hidden) return;
      contenu.innerHTML = `<div class="carte vide"><div class="grand">😕</div><p><b>Oups, un problème.</b></p><p class="petit muted" style="margin-top:6px">${echap(e.message)}</p>
        <button class="btn" style="margin-top:14px" id="b-reessayer">Réessayer</button></div>`;
      $("#b-reessayer").onclick = () => afficher();
    }
  }
  window.addEventListener("hashchange", afficher);

  async function demarrer() {
    try {
      const r = await fetch("/api/session", { credentials: "same-origin" });
      if (r.status === 401) return montrerConnexion();
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        document.body.innerHTML = `<div class="connexion"><div class="carte connexion-carte"><h1>Site à configurer</h1><p class="second">${echap(d.erreur || "Erreur " + r.status)}</p></div></div>`;
        return;
      }
    } catch { /* hors ligne : on tente quand même */ }
    $("#ecran-connexion").hidden = true;
    $("#app").hidden = false;
    pageActuelle = null;
    afficher();
  }
  demarrer();
})();
