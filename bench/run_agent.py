"""Lance les 20 questions sur un clone de Roller avec `claude -p`, et écrit les résultats.

Usage :
    python3 bench/run_agent.py --roller <clone> --config 1-agent-seul --passes 3 [--model claude-sonnet-5-5]

Chaque question est posée dans une session neuve, sans les réglages de la machine
(`--safe-mode`, `--strict-mcp-config`, `--disable-slash-commands`), avec les seuls outils
de la configuration. Résultat :
    results/<config>/runs.jsonl        une ligne par (question, passage) : réponse, tokens, coût, durée
    results/<config>/answers.json      réponses du passage 1, au format de bench/score.py, + _meta
    results/<config>/answers-pN.json   réponses de chaque passage
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
CONSIGNE = (
    "Réponds à la question sur l'application Apache Roller présente dans le dossier courant. "
    "Cite les fichiers qui justifient ta réponse. Question : "
)
OUTILS = {"1-agent-seul": "Read,Grep,Glob"}


def poser(roller: Path, question: str, outils: str, model: str | None, delai: int) -> dict:
    cmd = ["claude", "-p", CONSIGNE + question, "--safe-mode", "--tools", outils,
           "--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence",
           "--output-format", "json"]
    if model:
        cmd += ["--model", model]
    debut = time.monotonic()
    try:
        p = subprocess.run(cmd, cwd=roller, capture_output=True, text=True, timeout=delai)
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


def main() -> int:
    a = argparse.ArgumentParser()
    a.add_argument("--roller", type=Path, required=True)
    a.add_argument("--config", default="1-agent-seul", choices=sorted(OUTILS))
    a.add_argument("--passes", type=int, default=3)
    a.add_argument("--model")
    a.add_argument("--delai", type=int, default=600)
    a.add_argument("--questions", type=Path, default=RACINE / "questions" / "questions.json")
    a.add_argument("--suffixe", default="", help="ajouté au dossier de résultats, ex. -difficiles")
    args = a.parse_args()

    data = json.loads(args.questions.read_text(encoding="utf-8"))
    commit = subprocess.run(["git", "-C", str(args.roller), "rev-parse", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
    if commit != data["cible"]["commit"]:
        sys.exit(f"Le clone de Roller est au commit {commit}, attendu {data['cible']['commit']}")
    version = subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout.strip()

    sortie = RACINE / "results" / (args.config + args.suffixe)
    sortie.mkdir(parents=True, exist_ok=True)
    runs = sortie / "runs.jsonl"
    with runs.open("w", encoding="utf-8") as f:
        for n in range(1, args.passes + 1):
            reponses = {}
            for q in data["questions"]:
                r = poser(args.roller, q["question"], OUTILS[args.config], args.model, args.delai)
                r.update({"id": q["id"], "passage": n})
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
                f.flush()
                if r.get("erreur") and not reponses:
                    sys.exit(f"Première question en erreur ({r.get('erreur')}) : {r.get('reponse', '')[:200]}")
                reponses[q["id"]] = r.get("reponse", "")
                print(f"passage {n} {q['id']} {r.get('duree_s')} s {r.get('erreur') or ''}", flush=True)
            meta = {"config": args.config, "passage": n, "cli": version, "modele_demande": args.model,
                    "roller_commit": commit, "date": time.strftime("%Y-%m-%d")}
            reponses["_meta"] = meta
            (sortie / f"answers-p{n}.json").write_text(json.dumps(reponses, ensure_ascii=False, indent=2), encoding="utf-8")
            if n == 1:
                (sortie / "answers.json").write_text(json.dumps(reponses, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
