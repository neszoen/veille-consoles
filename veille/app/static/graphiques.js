/* Petits graphiques SVG faits maison (aucune dépendance). */
(function () {
  const NS = "http://www.w3.org/2000/svg";
  const el = (nom, attrs = {}, parent) => {
    const n = document.createElementNS(NS, nom);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    if (parent) parent.appendChild(n);
    return n;
  };
  const euros = (v) => (v == null ? "—" : Math.round(v) + " €");

  function graduations(min, max, n = 5) {
    const brut = (max - min) / n || 1;
    const p = Math.pow(10, Math.floor(Math.log10(brut)));
    const pas = [1, 2, 2.5, 5, 10].map((m) => m * p).find((s) => s >= brut);
    const ticks = [];
    for (let v = Math.ceil(min / pas) * pas; v <= max + 1e-9; v += pas) ticks.push(+v.toFixed(6));
    return ticks;
  }

  function bulle(conteneur) {
    const b = document.createElement("div");
    b.className = "info-bulle";
    b.hidden = true;
    conteneur.appendChild(b);
    return b;
  }

  /* Histogramme des prix + lignes de repère (prix max, max HS, revente, médiane). */
  function histogramme(conteneur, prix, reperes) {
    conteneur.innerHTML = "";
    conteneur.classList.add("graph");
    if (!prix.length) return;
    const W = 760, H = 300, m = { h: 34, d: 14, b: 34, g: 40 };
    const tries = [...prix].sort((a, b) => a - b);
    // On coupe les valeurs extrêmes (lots, collectors) pour garder un graphique lisible.
    const p95 = tries[Math.floor(tries.length * 0.95)] || tries[tries.length - 1];
    const refs = reperes.filter((r) => r.valeur != null);
    let xmax = Math.max(p95, ...refs.map((r) => r.valeur)) * 1.08;
    const xmin = 0;
    const largeur = Math.max(5, graduations(xmin, xmax, 14)[1] - graduations(xmin, xmax, 14)[0]);
    const nb = Math.ceil(xmax / largeur);
    xmax = nb * largeur;
    const bacs = Array.from({ length: nb }, (_, i) => ({ de: i * largeur, a: (i + 1) * largeur, n: 0 }));
    let horsCadre = 0;
    for (const p of prix) {
      if (p >= xmax) { horsCadre++; continue; }
      bacs[Math.min(nb - 1, Math.floor(p / largeur))].n++;
    }
    const ymax = Math.max(...bacs.map((b) => b.n), 1);
    const x = (v) => m.g + ((v - xmin) / (xmax - xmin)) * (W - m.g - m.d);
    const y = (v) => H - m.b - (v / ymax) * (H - m.h - m.b);
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Répartition des prix relevés" }, conteneur);

    const axe = el("g", { class: "axe" }, svg);
    for (const t of graduations(0, ymax, 4).filter((t) => Number.isInteger(t))) {
      el("line", { x1: m.g, x2: W - m.d, y1: y(t), y2: y(t), class: "grille-l" }, axe);
      el("text", { x: m.g - 8, y: y(t) + 4, "text-anchor": "end" }, axe).textContent = t;
    }
    for (const t of graduations(0, xmax, 8)) {
      el("text", { x: x(t), y: H - m.b + 18, "text-anchor": "middle" }, axe).textContent = t + " €";
    }

    const b = bulle(conteneur);
    const gb = el("g", {}, svg);
    for (const bac of bacs) {
      if (!bac.n) continue;
      const x0 = x(bac.de) + 1, x1 = x(bac.a) - 1, y0 = y(bac.n), yb = y(0);
      const r = Math.min(4, (x1 - x0) / 2, yb - y0);
      const d = `M${x0},${yb} V${y0 + r} Q${x0},${y0} ${x0 + r},${y0} H${x1 - r} Q${x1},${y0} ${x1},${y0 + r} V${yb} Z`;
      const barre = el("path", { d, class: "barre" }, gb);
      const zone = el("rect", { x: x(bac.de), y: m.h, width: x(bac.a) - x(bac.de), height: H - m.h - m.b, fill: "transparent" }, gb);
      zone.addEventListener("mouseenter", () => {
        barre.classList.add("survol");
        b.hidden = false;
        b.innerHTML = `<b>${bac.de}–${bac.a} €</b><br>${bac.n} annonce${bac.n > 1 ? "s" : ""}`;
        const rect = svg.getBoundingClientRect(), k = rect.width / W;
        b.style.left = ((x0 + x1) / 2) * k + "px";
        b.style.top = y0 * k + "px";
      });
      zone.addEventListener("mouseleave", () => { barre.classList.remove("survol"); b.hidden = true; });
    }

    // Lignes de repère, étiquetées directement (en quinconce si elles sont proches).
    const places = [];
    for (const r of refs.sort((a, b) => a.valeur - b.valeur)) {
      const xv = x(r.valeur);
      el("line", { x1: xv, x2: xv, y1: m.h - 4, y2: H - m.b, stroke: r.couleur, class: "ligne-ref",
        "stroke-dasharray": r.pointille ? "4 4" : "" }, svg);
      let rangee = 0;
      while (places.some((p) => p.rangee === rangee && Math.abs(p.x - xv) < 96)) rangee++;
      places.push({ x: xv, rangee });
      const t = el("text", { x: xv, y: m.h - 10 - rangee * 14, "text-anchor": "middle", class: "etiq",
        style: "fill: var(--text-2); font-weight: 600" }, svg);
      t.textContent = `${r.nom} ${euros(r.valeur)}`;
    }
    if (rangeeMax(places) > 0) svg.setAttribute("viewBox", `0 ${-14 * rangeeMax(places)} ${W} ${H + 14 * rangeeMax(places)}`);
    return { horsCadre, xmax };
  }
  const rangeeMax = (places) => Math.max(0, ...places.map((p) => p.rangee));

  /* Courbe de la médiane jour par jour, avec réticule au survol. */
  function courbe(conteneur, points) {
    conteneur.innerHTML = "";
    conteneur.classList.add("graph");
    if (points.length < 2) return;
    const W = 760, H = 220, m = { h: 16, d: 16, b: 30, g: 44 };
    const vals = points.map((p) => p.mediane);
    const lo = Math.min(...vals) * 0.9, hi = Math.max(...vals) * 1.1;
    const x = (i) => m.g + (i / (points.length - 1)) * (W - m.g - m.d);
    const y = (v) => H - m.b - ((v - lo) / (hi - lo || 1)) * (H - m.h - m.b);
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Évolution de la médiane des prix" }, conteneur);
    const axe = el("g", { class: "axe" }, svg);
    for (const t of graduations(lo, hi, 4)) {
      el("line", { x1: m.g, x2: W - m.d, y1: y(t), y2: y(t), class: "grille-l" }, axe);
      el("text", { x: m.g - 8, y: y(t) + 4, "text-anchor": "end" }, axe).textContent = Math.round(t) + " €";
    }
    const pas = Math.max(1, Math.ceil(points.length / 7));
    points.forEach((p, i) => {
      if (i % pas === 0 || i === points.length - 1)
        el("text", { x: x(i), y: H - 8, "text-anchor": "middle" }, axe).textContent = p.jour.slice(8, 10) + "/" + p.jour.slice(5, 7);
    });
    el("path", { d: points.map((p, i) => `${i ? "L" : "M"}${x(i)},${y(p.mediane)}`).join(" "), fill: "none",
      stroke: "var(--serie-1)", "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }, svg);
    const viseur = el("line", { y1: m.h, y2: H - m.b, stroke: "var(--border-fort)", visibility: "hidden" }, svg);
    const pt = el("circle", { r: 5, fill: "var(--serie-1)", stroke: "var(--surface)", "stroke-width": 2, visibility: "hidden" }, svg);
    const b = bulle(conteneur);
    const zone = el("rect", { x: m.g, y: m.h, width: W - m.g - m.d, height: H - m.h - m.b, fill: "transparent" }, svg);
    zone.addEventListener("mousemove", (ev) => {
      const rect = svg.getBoundingClientRect(), k = rect.width / W;
      const xs = (ev.clientX - rect.left) / k;
      const i = Math.max(0, Math.min(points.length - 1, Math.round(((xs - m.g) / (W - m.g - m.d)) * (points.length - 1))));
      const p = points[i];
      viseur.setAttribute("x1", x(i)); viseur.setAttribute("x2", x(i)); viseur.setAttribute("visibility", "visible");
      pt.setAttribute("cx", x(i)); pt.setAttribute("cy", y(p.mediane)); pt.setAttribute("visibility", "visible");
      b.hidden = false;
      b.innerHTML = `<b>${p.jour.split("-").reverse().join("/")}</b><br>Médiane ${euros(p.mediane)} · ${p.n} annonces`;
      b.style.left = x(i) * k + "px"; b.style.top = y(p.mediane) * k + "px";
    });
    zone.addEventListener("mouseleave", () => { viseur.setAttribute("visibility", "hidden"); pt.setAttribute("visibility", "hidden"); b.hidden = true; });
  }

  window.Graphiques = { histogramme, courbe };
})();
