# Résultats

Un dossier par configuration :

- `runs.jsonl` : une ligne par question et par passage (réponse brute, tokens, coût, durée, modèle) ;
- `answers.json` : réponses du passage 1, au format de `bench/score.py`, avec `_meta` (date, modèle demandé, commit de Roller) ;
- `answers-p1.json`, `answers-p2.json`, `answers-p3.json` : réponses de chaque passage.

Noter un passage : `python3 bench/score.py results/1-agent-seul/answers-p2.json`
(jeu difficile : ajouter `--questions questions/questions-difficiles.json`).

## État au 22/11/2026

| Dossier | Questions | Mesuré le | Score par passage (bench/score.py) | Par question (moyenne) |
|---|---|---|---|---|
| `1-agent-seul` | 20 (jeu principal) | 17/11/2026, Sonnet 5.5, 3 passages | 97 %, 97 %, 96 % | 15 s, 0,047 $, ~32 000 tokens lus |
| `1-agent-seul-difficiles` | 10 (jeu difficile) | 17/11/2026, Sonnet 5.5, 3 passages | 100 %, 95 %, 100 % | 13 s, 0,040 $, ~29 000 tokens lus |

Tokens lus : entrée, y compris la création et la lecture du cache.
Le 95 % du passage 2 du jeu difficile vient d'un faux négatif de la notation par mots-clés (H10 : « le démarrage échoue » est une réponse juste, non reconnue par les critères).

Configurations 2 à 5 (RAG, graphe, exécution, combinaison) : pas encore mesurées, publication prévue en janvier 2027. Aucun chiffre n'est publié avant d'avoir été mesuré.
