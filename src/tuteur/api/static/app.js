"use strict";

/* Interface élève — sans framework, sans dépendance tierce chargée depuis un CDN.
   Tout le texte venant du serveur est inséré avec textContent (jamais innerHTML). */

const $ = (s) => document.querySelector(s);

const stock = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* navigation privée */ } },
  del(k) { try { localStorage.removeItem(k); } catch { /* idem */ } },
};

const LIBELLES_MODE = {
  revision: "Révision", diagnostic: "Test de départ", remediation: "Rattrapage",
  transfert: "Retour au chapitre", termine: "Terminé",
};
const STATUT_KC = {
  maitrisee: "acquise", consolidee: "acquise", transferee: "acquise", presumee: "sans doute acquise",
  en_cours: "en cours", a_travailler: "à travailler", non_evaluee: "pas encore vue",
};

let jeton = stock.get("jeton");
const etat = { seance: null, chapitre: null, question: 0, enAttente: false };

/* ------------------------------------------------------------------ utilitaires */

function el(tag, attrs = {}, ...enfants) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") n.className = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? "" : v);
  }
  for (const e of enfants.flat()) if (e !== null && e !== undefined) n.append(e);
  return n;
}

async function api(chemin, { methode = "GET", corps } = {}) {
  if (window.tuteurLocal) {
    // version navigateur : le moteur Python tourne dans la page (Pyodide), aucun appel réseau
    const r = await window.tuteurLocal.requete(methode, chemin, corps, jeton);
    if (r.statut === 401) { oublierJeton(); vueInscription(); throw new Error("session expirée"); }
    if (r.statut >= 400) throw new Error(r.donnees?.erreur || `erreur ${r.statut}`);
    return r.donnees;
  }
  const r = await fetch(chemin, {
    method: methode,
    headers: { "Content-Type": "application/json", ...(jeton ? { Authorization: `Bearer ${jeton}` } : {}) },
    body: corps ? JSON.stringify(corps) : undefined,
  });
  if (r.status === 401) { oublierJeton(); vueInscription(); throw new Error("session expirée"); }
  const donnees = r.headers.get("content-type")?.includes("json") ? await r.json() : null;
  if (!r.ok) throw new Error(donnees?.erreur || donnees?.detail?.[0]?.msg || `erreur ${r.status}`);
  return donnees;
}

function afficher(id) {
  for (const v of document.querySelectorAll(".vue")) v.hidden = v.id !== id;
  window.scrollTo({ top: 0 });
}

function oublierJeton() { jeton = null; stock.del("jeton"); $("#menu").hidden = true; $("#btn-recommencer").hidden = true; }

/* ------------------------------------------------------------------ inscription */

function vueInscription() {
  afficher("vue-inscription");
  const f = $("#form-inscription");
  const annee = f.elements.annee_naissance;
  const majParent = () => {
    const a = parseInt(annee.value, 10);
    $("#bloc-parent").hidden = !(a && new Date().getFullYear() - a - 1 < 15);
  };
  annee.oninput = majParent;
  majParent();
  f.onsubmit = async (ev) => {
    ev.preventDefault();
    const err = $("#erreur-inscription");
    err.hidden = true;
    const corps = {
      prenom: f.elements.prenom.value.trim(),
      niveau: f.elements.niveau.value,
      annee_naissance: parseInt(f.elements.annee_naissance.value, 10),
      contact_parent: f.elements.contact_parent.value.trim() || null,
      accord_service: f.elements.accord_service.checked,
      accord_parent: f.elements.accord_parent.checked,
    };
    if (!corps.prenom || !corps.annee_naissance) { err.textContent = "Indique ton prénom et ton année de naissance."; err.hidden = false; return; }
    try {
      const r = await api("/api/eleves", { methode: "POST", corps });
      jeton = r.jeton;
      stock.set("jeton", jeton);
      await demarrer();
    } catch (e) { err.textContent = e.message; err.hidden = false; }
  };
}

/* ------------------------------------------------------------------ chapitres */

async function vueChapitres() {
  afficher("vue-chapitres");
  const liste = $("#liste-chapitres");
  liste.replaceChildren(el("p", { class: "petit" }, "Chargement…"));
  const chapitres = await api("/api/chapitres");
  liste.replaceChildren(...chapitres.map((c) => el("article", { class: "carte chapitre" },
    el("div", { class: "etiquette" }, el("span", { class: "niveau" }, c.niveau)),
    el("h2", {}, c.titre),
    el("p", { class: "meta" }, `${c.acquises} objectif${c.acquises > 1 ? "s" : ""} sur ${c.cibles} acquis · ${c.competences} notions vérifiées au besoin`),
    el("div", { class: "jauge", role: "img", "aria-label": `${c.acquises} sur ${c.cibles}` },
      el("span", { style: `width:${Math.round(100 * c.acquises / c.cibles)}%` })),
    el("button", { class: "principal", type: "button", onclick: () => commencer(c.id) },
      c.acquises ? "Reprendre" : "Commencer"),
  )));
}

/* ------------------------------------------------------------------ séance */

async function commencer(chapitre) {
  const r = await api("/api/seances", { methode: "POST", corps: { chapitre } });
  Object.assign(etat, { seance: r.seance, chapitre, question: 0 });
  afficher("vue-seance");
  await suivant();
}

async function suivant() {
  const a = await api(`/api/seances/${etat.seance}/action`);
  const pastille = $("#pastille-mode");
  pastille.textContent = LIBELLES_MODE[a.mode] || a.mode;
  pastille.className = `pastille ${a.mode}`;
  const carte = $("#carte-action");
  if (a.type === "question") { etat.question += 1; carte.replaceChildren(...rendreQuestion(a)); }
  else if (a.type === "cours") carte.replaceChildren(...rendreTexte("Le cours", a.texte, "J'ai compris"));
  else if (a.type === "exemple") carte.replaceChildren(...rendreExemple(a.texte));
  else if (a.type === "message") carte.replaceChildren(...rendreMessage(a.texte));
  else if (a.type === "fin") carte.replaceChildren(...rendreFin(a));
  $("#compteur").textContent = a.type === "question" ? `Question ${etat.question}` : "";
  majCarte(a);
  const focus = carte.querySelector("math-field, input.texte, .choix button, button.principal");
  if (focus) setTimeout(() => focus.focus(), 30);
}

function boutonContinuer(libelle = "Continuer") {
  return el("div", { class: "actions" }, el("button", { class: "principal", type: "button", onclick: suivant }, libelle));
}

function rendreTexte(titre, texte, libelle) {
  return [el("h2", {}, titre), el("p", { class: "bloc-texte" }, texte), boutonContinuer(libelle)];
}

function rendreExemple(texte) {
  const lignes = texte.split("\n");
  const titre = lignes.shift().replace(/^Exemple corrigé — /, "");
  return [
    el("div", { class: "etiquette" }, "Exemple corrigé"),
    el("p", { class: "enonce" }, titre),
    el("ol", { class: "etapes" }, lignes.map((l) => el("li", {}, l.trim()))),
    boutonContinuer("À moi d'essayer"),
  ];
}

function rendreMessage(texte) {
  const [tete, ...reste] = texte.split("\n");
  const bloc = el("div", { class: "bilan" }, el("h2", {}, tete));
  if (reste.length) bloc.append(el("ul", {}, reste.map((l) => el("li", {}, l))));
  return [bloc, boutonContinuer()];
}

function rendreFin(a) {
  return [
    el("h2", {}, "Bravo pour cette séance !"),
    el("p", {}, a.texte),
    el("div", { class: "actions" }, el("button", { class: "principal", type: "button", onclick: vueChapitres }, "Retour aux chapitres")),
  ];
}

function aideSaisie(q) {
  if (q.type_reponse === "solutions") return `Écris par exemple ${q.variable} = 3. Plusieurs solutions : sépare-les par « ; ».`;
  return "Fractions : utilise le bouton fraction ou « / ». Puissance : « ^ ».";
}

function champSaisie(q) {
  if (window.customElements?.get("math-field")) {
    const mf = el("math-field", { "aria-label": "Ta réponse" });
    mf.mathVirtualKeyboardPolicy = "auto";
    mf.addEventListener("change", () => mf.closest(".saisie")?.querySelector("button.principal")?.click());
    return { noeud: mf, valeur: () => ({ saisie: mf.value, format: "latex" }) };
  }
  const inp = el("input", { class: "texte", "aria-label": "Ta réponse", autocomplete: "off", autocapitalize: "off", spellcheck: "false",
    placeholder: q.type_reponse === "solutions" ? `${q.variable} = …` : "Ta réponse" });
  inp.addEventListener("keydown", (e) => { if (e.key === "Enter") inp.closest(".saisie")?.querySelector("button.principal")?.click(); });
  return { noeud: inp, valeur: () => ({ saisie: inp.value, format: "texte" }) };
}

/* Résolution rédigée « comme sur la copie » : une égalité par ligne, la dernière donne la solution.
   Le serveur localise la première ligne fausse et reconnaît l'erreur (preuve directe). */
function editeurCopie(q) {
  const avecMathLive = !!window.customElements?.get("math-field");
  const liste = el("ol", { class: "copie-lignes" });
  const champs = [];
  const valider = () => liste.closest(".saisie")?.querySelector("button.principal")?.click();
  const ajouter = (apres = null) => {
    let champ;
    if (avecMathLive) {
      champ = el("math-field", { "aria-label": `Ligne ${champs.length + 1} de ta résolution` });
      champ.mathVirtualKeyboardPolicy = "auto";
    } else {
      champ = el("input", { class: "texte", autocomplete: "off", autocapitalize: "off", spellcheck: "false",
        "aria-label": `Ligne ${champs.length + 1} de ta résolution`, placeholder: champs.length ? "" : "première étape…" });
    }
    champ.addEventListener("keydown", (e) => {
      if (e.key !== "Enter") return;
      e.preventDefault();
      e.stopPropagation();
      if (e.ctrlKey || e.metaKey) return valider();
      const nouveau = ajouter(champ);
      setTimeout(() => nouveau.focus(), 20);
    }, true);
    const li = el("li", {}, champ);
    const idx = apres ? champs.indexOf(apres) + 1 : champs.length;
    champs.splice(idx, 0, champ);
    if (apres) apres.closest("li").after(li); else liste.append(li);
    return champ;
  };
  ajouter();
  const noeud = el("div", { class: "copie" },
    el("p", { class: "copie-depart" }, el("span", { class: "petit" }, "Énoncé : "), q.depart),
    liste,
    el("button", { type: "button", class: "discret", onclick: () => setTimeout(() => ajouter().focus(), 20) }, "＋ Ajouter une ligne"));
  return {
    noeud,
    champs,
    valeur: () => {
      const lignes = champs.map((c) => (avecMathLive ? c.value : c.value).trim()).filter(Boolean);
      return { lignes, saisie: lignes[lignes.length - 1] || "", format: avecMathLive ? "latex" : "texte" };
    },
    verrouiller: () => champs.forEach((c) => { c.setAttribute("read-only", ""); c.disabled = true; }),
  };
}

function afficherEtapes(zone, etapes) {
  if (!etapes || !etapes.length) { zone.hidden = true; return; }
  const apres = etapes.some((e) => e.statut === "suite")
    ? el("p", { class: "petit" }, "Les lignes suivantes découlent de l'erreur : corrige d'abord celle-ci.") : null;
  zone.replaceChildren(el("p", { class: "petit" }, "Ta résolution, ligne par ligne :"),
    el("ol", {}, etapes.map((e) => el("li", { class: e.statut },
      el("span", { class: "marque-ligne", "aria-hidden": "true" }, { ok: "✓", suite: "·" }[e.statut] || "✗"),
      el("span", { class: "texte-ligne" }, e.texte),
      e.erreur ? el("span", { class: "erreur-ligne" }, ` — ${e.erreur}`) : null))), apres);
  zone.hidden = false;
}

function rendreQuestion(a) {
  const q = a.question;
  const retour = el("div", { class: "retour", hidden: true, role: "status" });
  const zoneIndice = el("p", { class: "indice", hidden: true });
  const etiquette = el("div", { class: "etiquette" }, q.competence, el("span", { class: "niveau" }, q.niveau),
    el("span", { class: "difficulte", title: `Difficulté ${q.difficulte} sur 3`, "aria-label": `Difficulté ${q.difficulte} sur 3` },
      [1, 2, 3].map((n) => el("i", { class: n <= q.difficulte ? "plein" : "" }))));
  const enonce = el("p", { class: "enonce" }, q.enonce);
  const zoneEtapes = el("div", { class: "etapes-retour", hidden: true });
  let zone;

  const envoyer = async (corps, verrouiller) => {
    if (etat.enAttente || (!corps.saisie || !corps.saisie.trim())) return;
    etat.enAttente = true;
    try {
      const r = await api(`/api/seances/${etat.seance}/reponse`, { methode: "POST", corps });
      afficherRetour(retour, r, a.mode);
      afficherEtapes(zoneEtapes, a.mode === "diagnostic" ? [] : r.etapes);
      if (r.statut !== "illisible") {
        verrouiller();
        zone.querySelector(".actions")?.replaceWith(boutonContinuer());
      }
    } catch (e) { afficherRetour(retour, { statut: "illisible", texte: e.message }, a.mode); }
    finally { etat.enAttente = false; }
  };

  if (q.choix.length || q.type_reponse === "booleen") {
    const options = q.choix.length ? q.choix : ["oui", "non"];
    const boutons = options.map((c) => el("button", { type: "button", onclick: (e) => {
      boutons.forEach((b) => b.setAttribute("aria-pressed", String(b === e.currentTarget)));
      envoyer({ saisie: c, format: "texte" }, () => boutons.forEach((b) => (b.disabled = true)));
    } }, q.type_reponse === "booleen" ? c[0].toUpperCase() + c.slice(1) : c));
    zone = el("div", { class: "saisie" }, el("div", { class: "choix" }, boutons), retour,
      el("div", { class: "actions" }, boutonIndice(zoneIndice)));
  } else if (q.etapes_possibles) {
    const copie = editeurCopie(q);
    const valider = el("button", { class: "principal", type: "button" }, "Valider");
    valider.onclick = () => envoyer(copie.valeur(), copie.verrouiller);
    zone = el("div", { class: "saisie" }, copie.noeud,
      el("p", { class: "aide-saisie" }, "Rédige comme sur ta copie : une égalité par ligne (Entrée = ligne suivante). "
        + `La dernière ligne donne la solution (${q.variable} = …). Tu peux aussi n'écrire que la solution.`),
      zoneIndice, retour, zoneEtapes, el("div", { class: "actions" }, valider, boutonIndice(zoneIndice)));
  } else {
    const champ = champSaisie(q);
    const valider = el("button", { class: "principal", type: "button" }, "Valider");
    valider.onclick = () => envoyer(champ.valeur(), () => { champ.noeud.setAttribute("read-only", ""); champ.noeud.disabled = true; });
    zone = el("div", { class: "saisie" }, champ.noeud, el("p", { class: "aide-saisie" }, aideSaisie(q)), zoneIndice, retour,
      el("div", { class: "actions" }, valider, boutonIndice(zoneIndice)));
  }
  if (q.choix.length || q.type_reponse === "booleen") zone.insertBefore(zoneIndice, retour);
  return [etiquette, enonce, zone, a.raison ? el("p", { class: "raison" }, `Pourquoi cette question : ${a.raison}.`) : null];
}

function boutonIndice(zone) {
  return el("button", { class: "discret", type: "button", onclick: async (e) => {
    e.target.disabled = true;
    const r = await api(`/api/seances/${etat.seance}/aide`, { methode: "POST" });
    zone.textContent = r.texte;
    zone.hidden = false;
  } }, "Un indice ?");
}

function afficherRetour(zone, r, mode) {
  let classe = { correct: "ok", incorrect: "ko", forme_non_conforme: "forme", illisible: "illisible" }[r.statut] || "neutre";
  let titre = { ok: "Exact !", ko: "Pas tout à fait.", forme: "Presque !", illisible: "Je n'ai pas compris ta réponse." }[classe];
  if (mode === "diagnostic" && r.statut !== "illisible") { classe = "neutre"; titre = "Réponse enregistrée."; }
  zone.className = `retour ${classe}`;
  const corps = mode === "diagnostic" && r.statut !== "illisible" ? "On fait le point à la fin du test." : r.texte;
  zone.replaceChildren(el("strong", {}, titre), corps && corps !== "Exact !" ? el("p", {}, corps) : "");
  zone.hidden = false;
}

/* ------------------------------------------------------------------ carte des compétences */

async function majCarte(a) {
  const prog = await api(`/api/chapitres/${etat.chapitre}/progression`);
  const courante = a.question?.competence;
  $("#liste-kc").replaceChildren(...prog.kcs.map((k) => el("li", {
    class: [k.titre === courante ? "courante" : "", k.cible ? "cible" : ""].join(" ").trim() || null,
    title: `${STATUT_KC[k.statut] || k.statut} · probabilité de maîtrise ${Math.round(k.p * 100)} %`,
  }, el("i", { class: `point ${k.statut}`, "aria-hidden": "true" }), el("span", {}, k.titre), el("span", { class: "niveau" }, k.niveau))));
  const parcours = $("#parcours");
  if (a.mode === "remediation" && a.parcours.length) {
    parcours.replaceChildren(el("strong", {}, "Ton parcours de rattrapage"),
      el("ol", {}, a.parcours.slice(0, 6).map((p) => el("li", {}, `${p.titre} (${p.niveau})`))));
    parcours.hidden = false;
  } else parcours.hidden = true;
}

/* ------------------------------------------------------------------ menu RGPD */

function brancherMenu() {
  $("#btn-export").onclick = async () => {
    const blob = window.tuteurLocal
      ? new Blob([JSON.stringify(await api("/api/moi/export"), null, 2)], { type: "application/json" })
      : await (await fetch("/api/moi/export", { headers: { Authorization: `Bearer ${jeton}` } })).blob();
    const url = URL.createObjectURL(blob);
    el("a", { href: url, download: "mes-donnees.json" }).click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  $("#btn-recommencer").onclick = async () => {
    if (!confirm("Recommencer à zéro ? Toutes tes réponses et ta progression seront effacées (ton compte est conservé).")) return;
    await api("/api/moi/reinitialiser", { methode: "POST" });
    Object.assign(etat, { seance: null, chapitre: null, question: 0 });
    await vueChapitres();
  };
  $("#btn-effacer").onclick = async () => {
    if (!confirm("Effacer définitivement ton compte et toutes tes réponses ?")) return;
    await api("/api/moi", { methode: "DELETE" });
    oublierJeton();
    vueInscription();
  };
  $("#btn-deconnexion").onclick = () => {
    if (!confirm("Sans compte en ligne pour l'instant, tu ne pourras pas retrouver ta progression sur cet appareil. Continuer ?")) return;
    oublierJeton();
    vueInscription();
  };
  $("#lien-accueil").onclick = (e) => { e.preventDefault(); if (jeton) vueChapitres(); };
}

async function demarrer() {
  const moi = await api("/api/moi");
  $("#menu-prenom").textContent = moi.prenom;
  $("#menu").hidden = false;
  $("#btn-recommencer").hidden = false;
  await vueChapitres();
}

window.addEventListener("DOMContentLoaded", async () => {
  if (window.MathfieldElement) {
    MathfieldElement.soundsDirectory = null;
    MathfieldElement.decimalSeparator = ",";
  }
  brancherMenu();
  if (window.matchMedia("(max-width: 860px)").matches) $("#details-carte").open = false;
  if (window.tuteurLocal) {
    $("#bandeau-demo").hidden = false;
    afficher("vue-chargement");
    try { await window.tuteurLocal.pret; } catch (e) {
      const cause = String(e.message || e).trim().split("\n").filter(Boolean).pop();
      console.error(e);
      $("#chargement-etape").textContent = `Le chargement a échoué (${cause}). Recharge la page pour réessayer.`;
      return;
    }
  }
  if (!jeton) return vueInscription();
  try { await demarrer(); } catch { vueInscription(); }
});
