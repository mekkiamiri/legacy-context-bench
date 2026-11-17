# legacy-context-bench

**Quel contexte donner à un agent IA pour qu'il comprenne une appli legacy : RAG, graphe du code, ou observation à l'exécution ?**

Ce dépôt mesure la réponse au lieu de la deviner. Même appli, mêmes questions, cinq configurations d'agent, trois mesures.

- **Appli :** [Apache Roller](https://github.com/apache/roller) 7.0.0 (Java, Struts 2, JPA/EclipseLink, Velocity, JSP), environ 70 000 lignes de code Java (hors lignes vides et commentaires, tests compris), commit figé `52e064a`.
- **Questions :** 20 questions dont la réponse est connue et prouvée par des lignes de code ([`questions/questions.json`](questions/questions.json)), en 3 familles : structure, comportement, données.
- **Mesures :** taux de bonnes réponses, tokens consommés, temps.
- **Démo :** <https://mekkiamiri.github.io/legacy-context-bench/>
- **Slides :** <https://mekkiamiri.github.io/legacy-context-bench/slides/> (flèches pour naviguer, N pour les notes)

> Support du talk « Agent IA sur du legacy : RAG, graphe ou exécution ? » (proposé à DevFest Nantes et Devoxx France 2027).

## Les 5 configurations

| # | Configuration | Ce que l'agent reçoit en plus du code |
|---|---|---|
| 1 | [Agent seul](configurations/1-agent-seul/) | rien : lecture de fichiers et recherche texte |
| 2 | [+ RAG](configurations/2-rag/) | un index de recherche sémantique sur le code et la doc |
| 3 | [+ graphe du code](configurations/3-graphe/) | un graphe de connaissance (classes, appels, dépendances) |
| 4 | [+ exécution](configurations/4-execution/) | l'appli qui tourne, observée (requêtes HTTP, SQL, traces) |
| 5 | [Combinaison](configurations/5-combinaison/) | 2 + 3 + 4 |

## État

| Étape | État |
|---|---|
| Protocole et 20 questions avec preuves | fait |
| Notation automatique + tests | fait |
| Page de démo | fait (résultats affichés quand ils existent) |
| Configuration 1 « agent seul » (Sonnet 5.5, 3 passages) | **mesurée le 17/11/2026 : 96 à 97 % de bonnes réponses, 0,047 $ et 15 s par question** ([résultats](results/1-agent-seul/)) |
| Configuration 1 sur le jeu difficile (10 questions, 3 passages) | **mesurée le 17/11/2026 : 95 à 100 %, 0,040 $ et 13 s par question** ; l'agent a relevé une erreur de l'auteur des questions (H03, voir PROTOCOLE.md) |
| Configurations 2 à 5 | en cours, publication prévue avant fin janvier 2027 |

Aucun chiffre n'est publié avant d'avoir été mesuré. Si les mesures contredisent l'intuition de départ, ce dépôt le dira.

## Lancer

Python 3.10+ suffit, sans dépendance.

```bash
python3 -m unittest discover -s tests          # tests du banc
python3 bench/score.py --check                 # vérifie les 20 questions
python3 bench/score.py results/<config>/answers.json   # note une configuration
python3 bench/build_site.py                    # régénère docs/data.js
```

Pour vérifier que chaque preuve pointe bien vers une ligne de Roller :

```bash
git clone https://github.com/apache/roller.git /tmp/roller
git -C /tmp/roller checkout 52e064a0104c89e141100d22e5bc990899ba3c2f
python3 bench/score.py --check --roller /tmp/roller
```

Le protocole complet est dans [PROTOCOLE.md](PROTOCOLE.md).

## Neutralité

L'auteur n'a écrit aucun des outils comparés. Les outils sont choisis parce qu'ils sont open source et utilisables par tous, pas pour en promouvoir un.

## Licence

Apache 2.0, comme Roller.
