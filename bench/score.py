"""Note les réponses d'une configuration d'agent sur les 20 questions.

Usage :
    python3 bench/score.py results/<configuration>/answers.json
    python3 bench/score.py --check [--roller <clone de Roller>]

Le fichier answers.json associe chaque id de question au texte de la réponse
de l'agent, et peut contenir "_meta" (tokens, durée, modèle).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
QUESTIONS = RACINE / "questions" / "questions.json"
FAMILLES = {"structure", "comportement", "donnees"}


def charger_questions(chemin: Path = QUESTIONS) -> dict:
    return json.loads(chemin.read_text(encoding="utf-8"))


def verifier(data: dict, roller: Path | None = None) -> list[str]:
    """Retourne la liste des erreurs du fichier de questions."""
    erreurs = []
    qs = data.get("questions", [])
    if len(qs) != 20:
        erreurs.append(f"{len(qs)} questions au lieu de 20")
    ids = [q.get("id") for q in qs]
    if len(set(ids)) != len(ids):
        erreurs.append("ids en double")
    for q in qs:
        for champ in ("id", "famille", "question", "reponse", "criteres", "preuves"):
            if not q.get(champ):
                erreurs.append(f"{q.get('id', '?')} : champ {champ} manquant")
        if q.get("famille") not in FAMILLES:
            erreurs.append(f"{q.get('id')} : famille inconnue {q.get('famille')}")
        for critere in q.get("criteres", []):
            if not critere or not all(isinstance(m, str) and m for m in critere):
                erreurs.append(f"{q.get('id')} : critère vide")
        if roller:
            for preuve in q.get("preuves", []):
                fichier, _, ligne = preuve.partition(":")
                f = roller / fichier
                if not f.is_file():
                    erreurs.append(f"{q['id']} : preuve introuvable {fichier}")
                elif ligne and int(ligne) > len(f.read_text(encoding="utf-8", errors="replace").splitlines()):
                    erreurs.append(f"{q['id']} : ligne {ligne} hors de {fichier}")
    return erreurs


def noter_reponse(question: dict, reponse: str) -> float:
    texte = (reponse or "").lower()
    criteres = question["criteres"]
    points = sum(1 for c in criteres if any(m.lower() in texte for m in c))
    return points / len(criteres)


def noter(data: dict, reponses: dict) -> dict:
    detail = {}
    for q in data["questions"]:
        detail[q["id"]] = round(noter_reponse(q, reponses.get(q["id"], "")), 2)
    par_famille = {}
    for fam in sorted(FAMILLES):
        notes = [detail[q["id"]] for q in data["questions"] if q["famille"] == fam]
        par_famille[fam] = round(sum(notes) / len(notes), 2) if notes else 0.0
    total = round(sum(detail.values()) / len(detail), 2)
    return {"total": total, "par_famille": par_famille, "detail": detail, "meta": reponses.get("_meta", {})}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("reponses", nargs="?", type=Path)
    p.add_argument("--check", action="store_true", help="vérifie le fichier de questions")
    p.add_argument("--roller", type=Path, help="clone de Roller pour vérifier les preuves")
    args = p.parse_args(argv)
    data = charger_questions()

    if args.check:
        erreurs = verifier(data, args.roller)
        for e in erreurs:
            print(f"ERREUR {e}")
        print(f"{len(data['questions'])} questions, {len(erreurs)} erreur(s)")
        return 1 if erreurs else 0

    if not args.reponses:
        p.error("donner un fichier answers.json ou --check")
    reponses = json.loads(args.reponses.read_text(encoding="utf-8"))
    print(json.dumps(noter(data, reponses), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
