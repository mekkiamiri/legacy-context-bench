"""Lance les 20 questions sur un clone de Roller avec `claude -p`, et écrit les résultats.

Usage :
    python3 bench/run_agent.py --roller <clone> --config 1-agent-seul --passes 3 [--model claude-sonnet-5-5]
    python3 bench/run_agent.py --roller <clone> --config 2-rag ...      # + index BM25 (rag_search.py)
    python3 bench/run_agent.py --roller <clone> --config 3-graphe ...   # + graphe du code (graph_query.py)

Chaque question est posée dans une session neuve, sans les réglages de la machine
(`--safe-mode`, `--strict-mcp-config`, `--disable-slash-commands`), avec les seuls outils
de la configuration. Pour 2-rag et 3-graphe, l'agent garde Read/Grep/Glob et reçoit en plus
le droit de lancer UNE commande via Bash (règle `Bash(python3 <outil>:*)`), annoncée par une
phrase ajoutée au prompt système. L'index ou le graphe est construit avant la première question
(dans .contexte/, une fois par commit) et son temps de construction est noté dans `_meta.preparation`.
Résultat :
    results/<config>/runs.jsonl        une ligne par (question, passage) : réponse, tokens, coût, durée
    results/<config>/answers.json      réponses du passage 1, au format de bench/score.py, + _meta
    results/<config>/answers-pN.json   réponses de chaque passage
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
CONSIGNE = (
    "Réponds à la question sur l'application Apache Roller présente dans le dossier courant. "
    "Cite les fichiers qui justifient ta réponse. Question : "
)
CONTEXTE = RACINE / ".contexte"
RAG_SEARCH = RACINE / "configurations" / "2-rag" / "rag_search.py"
RAG_INDEX = RACINE / "configurations" / "2-rag" / "rag_index.py"
GRAPH_QUERY = RACINE / "configurations" / "3-graphe" / "graph_query.py"
GRAPH_BUILD = RACINE / "configurations" / "3-graphe" / "graph_build.py"

CONFIGS = {
    "1-agent-seul": {"outils": "Read,Grep,Glob"},
    "2-rag": {
        "outils": "Read,Grep,Glob,Bash",
        "commande": f"python3 {RAG_SEARCH}",
        "construire": RAG_INDEX,
        "fichier": "rag-{commit}.json.gz",
        "variable": "RAG_INDEX",
        "consigne": (
            "En plus de Read, Grep et Glob, tu peux interroger un index de recherche BM25 sur le code de ce projet, "
            "avec l'outil Bash et cette seule commande : {cmd} '<mots-clés>' --k 8 . "
            "Elle renvoie les morceaux de code les plus pertinents (chemin:lignes et extrait). "
            "L'index est lexical : utilise les mots probables du code (anglais, noms de classes, de tables, de clés). "
            "Toute autre commande Bash est refusée."
        ),
    },
    "3-graphe": {
        "outils": "Read,Grep,Glob,Bash",
        "commande": f"python3 {GRAPH_QUERY}",
        "construire": GRAPH_BUILD,
        "fichier": "graphe-{commit}.json",
        "variable": "GRAPHE_JSON",
        "consigne": (
            "En plus de Read, Grep et Glob, tu peux interroger un graphe du code de ce projet, avec l'outil Bash "
            "et cette seule commande : {cmd} <requête> <argument> . Requêtes : "
            "who-calls <Classe.méthode> (appelants), callees <Classe.méthode> (appelés), "
            "route <url> (filtres, servlet, action Struts, contrôleur), table <entité|table> (mapping, CREATE TABLE, SQL), "
            "neighbors <Classe> (héritage, usages, configuration), find <terme> (cherche un nom). "
            "Les appels sont approximatifs (analyse syntaxique). Toute autre commande Bash est refusée."
        ),
    },
}
OUTILS = {nom: c["outils"] for nom, c in CONFIGS.items()}


def commande(config: str, question: str, model: str | None, agent: str = "claude") -> list[str]:
    """Ligne de commande de l'agent pour une question (sans l'exécuter)."""
    c = CONFIGS[config]
    cmd = [agent, "-p", CONSIGNE + question, "--safe-mode", "--tools", c["outils"],
           "--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence",
           "--output-format", "json"]
    if "commande" in c:
        cmd += ["--allowedTools", f"Bash({c['commande']}:*)",
                "--append-system-prompt", c["consigne"].format(cmd=c["commande"])]
    if model:
        cmd += ["--model", model]
    return cmd


def preparer(config: str, roller: Path, commit: str, contexte: Path = CONTEXTE, reconstruire: bool = False) -> dict:
    """Construit l'index ou le graphe de la configuration s'il manque. Retourne env + mesure de préparation."""
    c = CONFIGS[config]
    if "construire" not in c:
        return {"env": {}, "preparation": None}
    fichier = contexte / c["fichier"].format(commit=commit[:12])
    duree = None
    if reconstruire or not fichier.is_file():
        debut = time.monotonic()
        p = subprocess.run([sys.executable, str(c["construire"]), str(roller), str(fichier)],
                           capture_output=True, text=True)
        if p.returncode != 0:
            sys.exit(f"Préparation de {config} en échec : {p.stderr[-500:]}")
        duree = round(time.monotonic() - debut, 2)
        print(p.stdout.strip(), flush=True)
    return {"env": {c["variable"]: str(fichier)},
            "preparation": {"outil": c["construire"].name, "fichier": fichier.name,
                            "duree_s": duree, "taille_mo": round(fichier.stat().st_size / 1e6, 2),
                            "note": None if duree is not None else "déjà construit, temps mesuré lors de la construction"}}


def poser(roller: Path, question: str, config: str, model: str | None, delai: int,
          agent: str = "claude", env: dict | None = None) -> dict:
    cmd = commande(config, question, model, agent)
    debut = time.monotonic()
    try:
        p = subprocess.run(cmd, cwd=roller, capture_output=True, text=True, timeout=delai,
                           env={**os.environ, **(env or {})})
    except subprocess.TimeoutExpired:
        return {"erreur": "délai dépassé", "duree_s": delai}
    duree = round(time.monotonic() - debut, 2)
    try:
        d = json.loads(p.stdout)
    except json.JSONDecodeError:
        return {"erreur": f"sortie illisible (code {p.returncode})", "duree_s": duree}
    u = d.get("usage") or {}
    return {
        "reponse": d.get("result", ""),
        "erreur": d.get("subtype") if d.get("is_error") else None,
        "tours": d.get("num_turns"),
        "duree_s": duree,
        "cout_usd": d.get("total_cost_usd"),
        "tokens_entree": (u.get("input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0)
        + (u.get("cache_read_input_tokens") or 0),
        "tokens_sortie": u.get("output_tokens"),
        "modeles": sorted((d.get("modelUsage") or {}).keys()),
    }


def main(argv: list[str] | None = None) -> int:
    a = argparse.ArgumentParser()
    a.add_argument("--roller", type=Path, required=True)
    a.add_argument("--config", default="1-agent-seul", choices=sorted(CONFIGS))
    a.add_argument("--passes", type=int, default=3)
    a.add_argument("--model")
    a.add_argument("--delai", type=int, default=600)
    a.add_argument("--questions", type=Path, default=RACINE / "questions" / "questions.json")
    a.add_argument("--suffixe", default="", help="ajouté au dossier de résultats, ex. -difficiles")
    a.add_argument("--agent", default="claude", help="exécutable de l'agent (un faux agent pour tester le lanceur)")
    a.add_argument("--resultats", type=Path, default=RACINE / "results")
    a.add_argument("--contexte", type=Path, default=CONTEXTE, help="dossier des index et graphes construits")
    a.add_argument("--reconstruire", action="store_true", help="reconstruit l'index ou le graphe même s'il existe")
    args = a.parse_args(argv)

    data = json.loads(args.questions.read_text(encoding="utf-8"))
    commit = subprocess.run(["git", "-C", str(args.roller), "rev-parse", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
    if commit != data["cible"]["commit"]:
        sys.exit(f"Le clone de Roller est au commit {commit}, attendu {data['cible']['commit']}")
    version = subprocess.run([args.agent, "--version"], capture_output=True, text=True).stdout.strip()
    prep = preparer(args.config, args.roller, commit, args.contexte, args.reconstruire)

    sortie = args.resultats / (args.config + args.suffixe)
    sortie.mkdir(parents=True, exist_ok=True)
    runs = sortie / "runs.jsonl"
    with runs.open("w", encoding="utf-8") as f:
        for n in range(1, args.passes + 1):
            reponses = {}
            for q in data["questions"]:
                r = poser(args.roller, q["question"], args.config, args.model, args.delai, args.agent, prep["env"])
                r.update({"id": q["id"], "passage": n})
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
                f.flush()
                if r.get("erreur") and not reponses:
                    sys.exit(f"Première question en erreur ({r.get('erreur')}) : {r.get('reponse', '')[:200]}")
                reponses[q["id"]] = r.get("reponse", "")
                print(f"passage {n} {q['id']} {r.get('duree_s')} s {r.get('erreur') or ''}", flush=True)
            meta = {"config": args.config, "passage": n, "cli": version, "modele_demande": args.model,
                    "roller_commit": commit, "date": time.strftime("%Y-%m-%d")}
            if prep["preparation"]:
                meta["preparation"] = prep["preparation"]
            reponses["_meta"] = meta
            (sortie / f"answers-p{n}.json").write_text(json.dumps(reponses, ensure_ascii=False, indent=2), encoding="utf-8")
            if n == 1:
                (sortie / "answers.json").write_text(json.dumps(reponses, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
