// Relance le robot toutes les 30 minutes (fonction programmée Netlify, gratuite).
// Pourquoi : GitHub retarde ou saute souvent ses déclenchements programmés
// (constaté : un passage toutes les 5 à 8 h au lieu de 30 min).
// Utilise les mêmes variables que le site : GITHUB_TOKEN, GITHUB_REPO, GITHUB_BRANCH.
export const config = { schedule: "*/30 * * * *" };

const WORKFLOW = "veille.yml";
const ECART_MIN = 20 * 60 * 1000; // pas de relance si le robot est passé il y a moins de 20 min

export default async function () {
  const env = (k) => (process.env[k] || "").trim();
  if (!env("GITHUB_TOKEN") || !env("GITHUB_REPO")) return new Response("non configuré", { status: 200 });
  const branche = env("GITHUB_BRANCH") || "main";
  const gh = (chemin, options = {}) =>
    fetch(`https://api.github.com/repos/${env("GITHUB_REPO")}${chemin}`, {
      ...options,
      headers: { Authorization: `Bearer ${env("GITHUB_TOKEN")}`, Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "veille-consoles-relance" },
    });

  const runs = (await (await gh(`/actions/workflows/${WORKFLOW}/runs?per_page=3&branch=${branche}`)).json()).workflow_runs || [];
  const recent = runs.find((r) => r.status !== "completed" || Date.now() - new Date(r.created_at).getTime() < ECART_MIN);
  if (recent) {
    console.log(`Robot déjà passé ou en cours (${recent.created_at}) : pas de relance.`);
    return new Response("rien à faire");
  }
  const r = await gh(`/actions/workflows/${WORKFLOW}/dispatches`, { method: "POST", body: JSON.stringify({ ref: branche }) });
  console.log(r.status === 204 ? "Robot relancé." : `Relance refusée par GitHub (${r.status}).`);
  return new Response("ok");
}
