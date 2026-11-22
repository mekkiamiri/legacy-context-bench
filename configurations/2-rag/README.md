# 2. Agent + RAG

L'agent garde ses outils de base (Read, Grep, Glob) et peut en plus interroger un index de recherche sur le code, la configuration et la documentation du projet.

- **Outil :** index lexical BM25 écrit pour le banc (`bm25.py`, Python, bibliothèque standard seulement). Pas d'embeddings, pas de modèle, pas de réseau : la recherche est reproductible à l'identique et la préparation ne coûte aucun token.
- **Préparation sur Roller :** 2,3 s, index de 1,5 Mo (1 146 fichiers, 10 073 morceaux). Voir [DEMO.md](DEMO.md).
- **Ce qu'on attend :** bon pour retrouver un concept quand on a les bons mots, faible pour suivre un enchaînement d'appels, et faible sur une question en français posée à du code anglais.
- **Résultats :** `results/2-rag/` (à venir).

## Commandes

```bash
# une fois par projet (et par commit) :
python3 configurations/2-rag/rag_index.py <projet> .contexte/rag-index.json.gz
# autant que l'on veut :
python3 configurations/2-rag/rag_search.py "runtime properties default value" --k 8
```

`rag_search.py` renvoie, pour chaque résultat : `chemin:début-fin`, le type de morceau (`méthode Classe.nom`, `classe`, `bloc`), le score, les termes trouvés et les lignes les plus parlantes du morceau. Index par défaut : variable `RAG_INDEX`, sinon `.contexte/rag-index.json.gz`.

Mesure avec un agent (le lanceur construit l'index s'il manque et note son temps dans `_meta.preparation`) :

```bash
python3 bench/run_agent.py --roller /tmp/roller --config 2-rag --passes 3 --model claude-sonnet-5-5
```

L'agent reçoit `--tools Read,Grep,Glob,Bash`, la seule règle `Bash(python3 <banc>/configurations/2-rag/rag_search.py:*)` (toute autre commande Bash est refusée) et une phrase ajoutée au prompt système qui lui présente l'outil. La consigne et la question restent celles de la configuration 1.

## Réglages

| Réglage | Valeur |
|---|---|
| Fichiers indexés | `.java .jsp .jspf .tag .tld .xml .sql .ddl .properties .vm .ftl .gradle .kts .yml .yaml .md .adoc .txt .html .xhtml .js`, 1 Mo au plus ; dossiers cachés, `target`, `build`, `out`, `bin`, `node_modules`, `dist` ignorés |
| Découpage Java | une méthode par morceau (javadoc et annotations comprises) ; en-têtes et champs regroupés en morceaux « classe » ; méthodes de plus de 120 lignes coupées en fenêtres de 80 lignes (recouvrement 10) |
| Découpage des autres fichiers | blocs de 12 à 50 lignes, coupés de préférence sur une frontière naturelle (balise XML de premier niveau, `create`/`insert` en SQL, commentaire en `.properties`, titre en Markdown/AsciiDoc) |
| Tokenisation | identifiants découpés (camelCase, snake_case, points) et gardés entiers (`roller_properties` donne `roller_properties`, `roller`, `property`) ; minuscules ; accents retirés ; pluriel anglais simple retiré ; petite liste de mots vides français et anglais |
| Champs | chemin du fichier et nom du symbole indexés avec le contenu (le nom compte double) |
| BM25 | k1 = 1,2, b = 0,75, idf = ln(1 + (N - df + 0,5) / (df + 0,5)) |

## Limites, honnêtement

- **Lexical, pas sémantique.** « réglages modifiables à chaud » ne trouve pas `runtimeConfigDefs.xml` ; « runtime properties default value » le trouve (voir DEMO.md). Le protocole prévoyait au départ un index à embeddings : on commence par la base la plus simple et la plus reproductible. Un index à embeddings pourra être ajouté comme variante, mesurée à part.
- **Analyse Java légère** (la même que le graphe, `configurations/commun/javalite.py`) : si un fichier ne se découpe pas proprement, il est indexé par blocs de lignes.
- **Pas de mise à jour incrémentale** : on reconstruit l'index (2 à 3 s sur Roller).
- **Templates et SQL générés** (`createdb.vm`) sont indexés comme du texte, sans être évalués.
