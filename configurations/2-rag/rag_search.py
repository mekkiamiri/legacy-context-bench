"""Cherche dans l'index BM25 : renvoie chemin:lignes, type de morceau, score et extrait.

Usage :
    python3 configurations/2-rag/rag_search.py "<question>" [--k 8] [--index <index.json.gz>]

L'index est lexical (mots, pas de sens) : une requête avec les mots probables du code
(en anglais, noms de classes, de tables, de clés) trouve mieux qu'une question en français.
Index par défaut : variable RAG_INDEX, sinon .contexte/rag-index.json.gz à la racine du banc.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))
import bm25  # noqa: E402

INDEX_DEFAUT = ICI.parent.parent / ".contexte" / "rag-index.json.gz"


def main(argv: list[str] | None = None) -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("question", nargs="+")
    a.add_argument("--k", type=int, default=8, help="nombre de résultats (défaut 8)")
    a.add_argument("--index", type=Path, default=Path(os.environ.get("RAG_INDEX", INDEX_DEFAUT)))
    a.add_argument("--lignes", type=int, default=6, help="lignes d'extrait par résultat (défaut 6)")
    args = a.parse_args(argv)
    if not args.index.is_file():
        print(f"Index introuvable : {args.index}. Le construire avec rag_index.py <projet> <sortie>.", file=sys.stderr)
        return 2
    index = bm25.charger(args.index)
    question = " ".join(args.question)
    resultats = bm25.chercher(index, question, args.k)
    if not resultats:
        print("Aucun résultat.")
        return 0
    for rang, (score, d, termes) in enumerate(resultats, 1):
        rel, debut, fin, genre, nom, _sig = index["docs"][d]
        etiquette = f"{genre} {nom}".strip()
        print(f"{rang}. {rel}:{debut}-{fin}  [{etiquette}]  score {score:.1f}  ({', '.join(termes[:6])})")
        for n, texte in bm25.extrait(index["racine"], index["docs"][d], termes, args.lignes):
            print(f"   {n:>5} | {texte[:160]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
