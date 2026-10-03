# Architecture et décisions de conception

Ce document consigne les choix structurants et **pourquoi** ils ont été faits, y compris quand ils
corrigent des hypothèses initiales du projet.

## 1. Vue d'ensemble

```
ÉLÈVE ─ saisie structurée (clavier mathématique) ──────────────┐
      └ photo de SA résolution → OCR (UE) → CONFIRMATION élève ─┘
                                   ↓
     Analyseur maison (notation FR, sans eval) → AST → SymPy + prédicats de forme
                                   ↓
     Verdict {correct | forme non conforme | incorrect | illisible}
       + ligne fautive + erreur typique reconnue (→ KC racine)
                                   ↓
     Mise à jour BKT (Q-matrix) ─→ journal d'événements (ajout seul)
                                   ↓
     Machine à états + règles versionnées (diagnostic par gain d'information,
     parcours topologique, critères de maîtrise, rappels espacés), aléa journalisé
                                   ↓
     Contenu : exercice généré (graine) | cours / remédiation / exemple corrigé pré-validés
               | LLM UE seulement pour le dialogue ouvert, sous garde-fous
```

Le LLM ne décide **rien** : ni la correction, ni la compétence à travailler, ni la difficulté.

## 2. Hypothèses initiales corrigées

| Hypothèse initiale | Position retenue | Raison |
|---|---|---|
| « Arbre » de compétences | **DAG** avec arêtes `forte`/`faible` et justification | Une KC a plusieurs parents ; prérequis et composition sont des relations différentes. |
| « Les mauvaises réponses n'apportent rien » (arbre du vrai) | **Bibliothèque d'erreurs typiques exécutables** | Une réponse fausse précise identifie la lacune en 1 question au lieu de 4. Les erreurs sont aussi déterministes que les bonnes réponses : ce n'est pas de l'apprentissage. |
| Descente séquentielle dans le graphe | **Inférence bayésienne + gain d'information** | La descente est lente, sensible aux erreurs d'inattention, et ambiguë. Mesuré : voir `benchmarks.md`. |
| Équivalence SymPy = correction | **Équivalence + forme** | `(x+2)²` est équivalent à `x²+4x+4` mais faux si la consigne est « développer ». |
| `sympify` / `parse_expr` sur la saisie | **Analyseur maison** | Ces fonctions utilisent `eval` et évaluent automatiquement (perte de la forme). |
| QCM pour aller vite | QCM **uniquement pour le diagnostic** et seulement avec distracteurs issus d'erreurs typiques | Hasard à 25 % : mesuré moins précis que la saisie libre (exactitude 88 % vs 96 %). |
| Laya (LLM fine-tuné) comme moteur de décision | **Règles explicites au MVP** ; plus tard bandits / RL hors ligne sur données réelles | Toutes les décisions listées ont des solutions algorithmiques ; un fine-tuning supervisé imite au mieux ses étiquettes, il n'optimise pas l'apprentissage. |
| DeepSeek (API) comme professeur | **Contenu pré-validé** + LLM **auto-hébergé UE ou fournisseur UE** | L'API transfère hors UE (pays sans décision d'adéquation) du texte libre d'enfants. Les poids ouverts auto-hébergés restent possibles. |
| Simulation d'élèves par LLM | **Élèves simulés paramétriques** | Les LLM simulent mal les distributions d'erreurs réelles. La simulation sert à tester des algorithmes contre une vérité connue, pas à produire des données d'entraînement. |
| OCR de copies dès le départ | **Saisie structurée d'abord** ; OCR de *la résolution de l'élève* ensuite | Coût, fiabilité, et risque de « machine à réponses » (photo de l'énoncé). |

## 3. Graphe de compétences

- Source : `content/graphe.yaml`, relu par des enseignants via des pull requests, validé en CI
  (`tuteur valider-contenu`).
- Une KC a la bonne granularité si : testable en 3 à 5 questions de moins de 2 minutes,
  enseignable en une séance, avec une remédiation propre, et un exercice qui l'**isole**.
- **Q-matrix** : chaque modèle d'exercice déclare les KC qu'il mobilise (`kcs[0]` = principale).
  Le diagnostic n'utilise que des modèles `diagnostic=True` qui isolent leur KC.
- Pas de base graphe : quelques milliers de nœuds au plus, compilés en mémoire.
- Ordre de grandeur : 500 à 900 KC pour CP → 3e (tous domaines) ; ~200 pour « Nombres et
  calculs » 6e → 3e avec les prérequis ; 34 dans ce premier jalon.

## 4. Moteur mathématique (`mathengine/`)

- `parser.py` : virgule décimale, ×, ÷, `:`, −, ², ³, √, multiplication implicite, milliers
  « 1 000 », refus de « 3 4 » (opération manquante), longueur bornée.
- `forms.py` : prédicats de forme sur l'AST écrit par l'élève.
- `equivalence.py` : `cancel` (décision exacte pour les fractions rationnelles), sinon
  `simplify` et contrôle numérique à graine fixe.
- `answers.py` : `SpecReponse` = valeur + formes exigées + réponses des erreurs typiques ;
  formats d'ensembles de solutions (`x = 2 ou x = -3`, `S = {…}`, `aucune solution`…).
- `steps.py` : chaque ligne doit conserver l'ensemble des solutions ; la première ligne qui le
  change est confrontée aux transformations fautives connues (transposition sans changement
  de signe, distributivité incomplète, signe moins devant une parenthèse, ax = b → x = b − a…).

En production : exécuter SymPy dans un pool de processus avec délai d'expiration (~200 ms) et
mettre en cache par (exercice, réponse normalisée).

## 5. Exercices (`exercises/`)

- Solution construite d'abord ; exercice identifié par `modèle@version#graine/difficulté`.
- **Pouvoir diagnostique** vérifié à la génération : rejet si une erreur typique donne la
  bonne réponse ou si deux erreurs typiques donnent la même.
- Tests : pour chaque modèle × difficulté × 25 graines, la bonne réponse affichée est acceptée
  (valeur et forme), chaque erreur typique est reconnue comme telle, chaque QCM a exactement une
  bonne option.
- Énoncés en contexte (problèmes) générés par LLM : **aller-retour** obligatoire (extraction de
  l'équation depuis le texte généré, comparaison SymPy au modèle) — non implémenté.

## 6. Mesure de la maîtrise (`knowledge/`)

- BKT par KC (slip 0,10, transit 0,12, guess selon le format : saisie 0,02, oui/non 0,5,
  QCM 1/n). A priori selon l'écart entre le niveau de la KC et la classe de l'élève.
- Critères stricts (tous requis) : P ≥ 0,95 ; ≥ 3 réussites sans aide ; ≥ 2 variantes ; ≥ 1
  réussite au niveau cible ; pas d'erreur typique dans les 3 dernières tentatives.
- Niveaux : présumée (inférée par le diagnostic) < maîtrisée < consolidée (réussite à J+1 au
  moins) < transférée (réussite dans un exercice d'une KC parente).
- Une erreur typique sur une KC maîtrisée la rouvre.
- **Calibration** : à valider sur données réelles par l'erreur de calibration (ECE), plus
  importante ici que l'AUC puisque les décisions reposent sur des seuils.

## 7. Diagnostic (`diagnostic/`)

- Sous-graphe = fermeture des ancêtres des KC cibles du chapitre (27 KC pour les équations).
- A priori « noisy-AND » : KC improbable si un prérequis fort n'est pas maîtrisé ; probabilité
  conditionnelle **plafonnée** (sinon une notion de l'année hérite d'une fausse certitude dès
  que ses prérequis sont acquis — bug trouvé par le benchmark).
- Inférence par particules + Metropolis-Hastings ; question suivante = gain d'information
  attendu / (temps estimé)^0,5 ; arrêt quand tout est tranché, gain négligeable ou 18 questions.
- Sortie : marginales, **frontière** (lacunes racines), **parcours** (tri topologique ;
  départage par niveau, puis nombre de KC débloquées) et **explication lisible** des preuves.

## 8. Politique pédagogique (`session/`)

Règles versionnées (`VERSION_POLITIQUE = "regles-v1"`), décrites en tête de `session/moteur.py`.
Chaque décision est journalisée avec ses options, son choix et sa **probabilité** (aléa ε = 0,15
entre options équivalentes). Sans cela, les trajectoires réelles seraient biaisées par la
politique elle-même et inutilisables pour évaluer une autre politique.

**Évolution prévue** : quand quelques milliers d'élèves auront produit des trajectoires,
apprendre une politique (bandit contextuel / RL hors ligne, modèles tabulaires) qui choisit
**parmi les actions jugées valides par les règles**, évaluée hors ligne avant tout A/B test.
Un LLM n'est pas nécessaire pour cela.

## 9. Professeur (`teacher/`)

- Défaut : `EnseignantDeterministe` (cours par KC, remédiation par erreur typique, exemple
  corrigé du modèle, indice).
- Option : `PasserelleLLM` — refuse tout client dont `region != "UE"`, filtre les données
  personnelles, n'envoie que le verdict structuré, revérifie chaque égalité numérique,
  interdit la divulgation de la réponse, se replie sur le contenu déterministe en cas de doute.

## 10. OCR (`ocr/`)

- Flux imposé : suppression EXIF → transcription → **confirmation par l'élève avant verdict**
  → correction ligne par ligne → transcription figée.
- Curation : consentement exigé ; jeu de référence jamais en entraînement ; correction plausible
  (= une hypothèse alternative de l'OCR) acceptée, sinon revue humaine ; validation « à
  l'aveugle » contrôlée par échantillon ; fiabilité de l'élève mesurée par des pièges.
- Dataset versionné par manifeste (empreintes) sans identifiant élève.
- Déploiement seulement si le **taux d'inversion de verdict** baisse globalement sans régression
  par catégorie (fractions, exposants, ratures, éclairage…).
- Modèles à comparer sur nos données (licences et versions à vérifier au moment du choix) :
  petits modèles vision-langage à poids ouverts (famille Qwen-VL, GOT-OCR, PaddleOCR-VL,
  DeepSeek-OCR…) vs modèles spécialisés en expressions manuscrites entraînés sur CROHME,
  HME100K, MathWriting. Pipeline recommandé : segmentation des lignes puis reconnaissance ligne
  à ligne, sortie contrainte relue par notre analyseur.

## 11. Données et passage à l'échelle

- Journal en ajout seul ; état = projection rejouable (`reconstruire_profil`).
- 1 M élèves × 30 réponses/jour ≈ 350 événements/s en moyenne, quelques milliers en pointe
  (17 h – 21 h, dimanche soir, brevet) : PostgreSQL partitionné par élève suffit longtemps.
- Services sans état ; graphe et contenu en mémoire ; coût dominant = inférence OCR et LLM →
  explications pré-rédigées, petits modèles, plafonds par élève.

## 12. Évaluation

- Par composant : faux positifs de correction (< 0,1 %), cohérence des générateurs (CI),
  calibration BKT, exactitude du diagnostic sur élèves simulés puis sur pilote, taux
  d'inversion de verdict OCR, garde-fous LLM.
- Global : gain d'apprentissage sur **tests indépendants** du système, rétention à 1 mois,
  comparaison contrôlée (remédiation par le graphe vs entraînement au niveau de la classe).
