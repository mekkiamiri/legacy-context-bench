"""Génère docs/data.js (questions + résultats mesurés) pour la page de démo.

Usage :
    python3 bench/build_site.py          # écrit docs/data.js
    python3 bench/build_site.py --check  # échoue si docs/data.js n'est pas à jour
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import score  # noqa: E402

RACINE = score.RACINE
SORTIE = RACINE / "docs" / "data.js"
CONFIGS = ["1-agent-seul", "2-rag", "3-graphe", "4-execution", "5-combinaison"]


def resultats() -> dict:
    data = score.charger_questions()
    out = {}
    for c in CONFIGS:
        f = RACINE / "results" / c / "answers.json"
        if f.is_file():
            reponses = json.loads(f.read_text(encoding="utf-8"))
            out[c] = score.noter(data, reponses)
    return out


def contenu() -> str:
    payload = {"questions": score.charger_questions(), "resultats": resultats()}
    return "// Généré par bench/build_site.py : ne pas modifier à la main.\nwindow.BENCH = " + json.dumps(
        payload, ensure_ascii=False, indent=1
    ) + ";\n"


def main() -> int:
    attendu = contenu()
    if "--check" in sys.argv:
        if not SORTIE.is_file() or SORTIE.read_text(encoding="utf-8") != attendu:
            print("docs/data.js n'est pas à jour : lancer python3 bench/build_site.py")
            return 1
        print("docs/data.js à jour")
        return 0
    SORTIE.write_text(attendu, encoding="utf-8")
    print(f"écrit {SORTIE.relative_to(RACINE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
