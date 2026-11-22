"""Construit l'index BM25 d'un projet, une fois.

Usage :
    python3 configurations/2-rag/rag_index.py <projet> <sortie.json.gz>

Affiche le nombre de fichiers et de morceaux, le temps de construction et la taille de l'index.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bm25  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("projet", type=Path)
    a.add_argument("sortie", type=Path)
    args = a.parse_args(argv)
    if not args.projet.is_dir():
        a.error(f"{args.projet} n'est pas un dossier")
    debut = time.monotonic()
    index = bm25.construire(args.projet)
    bm25.sauver(index, args.sortie)
    duree = time.monotonic() - debut
    fichiers = len({d[0] for d in index["docs"]})
    print(f"{fichiers} fichiers, {len(index['docs'])} morceaux, {len(index['postings'])} termes")
    print(f"construit en {duree:.1f} s, {args.sortie.stat().st_size / 1e6:.1f} Mo -> {args.sortie}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
