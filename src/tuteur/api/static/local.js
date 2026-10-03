"use strict";

/* Version « tout dans le navigateur » (GitHub Pages) : exécute le tuteur Python dans la page
   grâce à Pyodide, servi depuis ce même site. Chargé uniquement par le site construit avec
   scripts/construire_site.py ; la version serveur ne l'utilise pas.

   - aucune donnée d'élève n'est envoyée sur le réseau ;
   - les bases SQLite (identité, journal) sont gardées dans le stockage du navigateur (IndexedDB),
     ce qui conserve la progression d'une visite à l'autre sur cet appareil. */

(() => {
  const etape = (texte) => {
    const n = document.getElementById("chargement-etape");
    if (n) n.textContent = texte;
  };
  let py = null;
  let service = null;
  let persistant = false;

  const synchroniser = (lecture) => new Promise((ok) => {
    if (!persistant) return ok();
    py.FS.syncfs(lecture, (err) => { if (err) console.warn("synchronisation du stockage", err); ok(); });
  });

  const pret = (async () => {
    etape("Chargement du moteur de calcul (Python)…");
    py = await loadPyodide({ indexURL: new URL("pyodide/", document.baseURI).href });
    etape("Chargement des outils mathématiques (SymPy, NumPy)…");
    const manquants = [];
    await py.loadPackage(["numpy", "sympy", "pyyaml", "sqlite3"], { errorCallback: (m) => manquants.push(m) });
    if (manquants.length) throw new Error(`paquets indisponibles (${manquants.join(" ; ")})`);
    etape("Chargement du tuteur…");
    const zip = await (await fetch("tuteur.zip")).arrayBuffer();
    py.unpackArchive(zip, "zip", { extractDir: "/tuteur" });
    py.FS.mkdirTree("/donnees");
    try {
      py.FS.mount(py.FS.filesystems.IDBFS, {}, "/donnees");
      persistant = true;
      await synchroniser(true);
    } catch (e) {
      console.warn("stockage persistant indisponible, la progression ne sera pas conservée", e);
    }
    py.runPython(`
import os, sys
sys.path.insert(0, "/tuteur/src")
os.environ["TUTEUR_CONTENU"] = "/tuteur/content"
from tuteur.service import Service
service = Service.creer("/donnees")
`);
    service = py.globals.get("service");
  })();

  let sauvegarde = null;
  const planifierSauvegarde = () => {
    clearTimeout(sauvegarde);
    sauvegarde = setTimeout(() => synchroniser(false), 300);
  };
  window.addEventListener("pagehide", () => { if (persistant && py) py.FS.syncfs(false, () => {}); });

  async function requete(methode, chemin, corps, jeton) {
    await pret;
    const brut = service.requete_json(methode, chemin, corps ? JSON.stringify(corps) : "", jeton || null);
    planifierSauvegarde();
    return JSON.parse(brut);
  }

  window.tuteurLocal = { pret, requete, get pyodide() { return py; } };
})();
