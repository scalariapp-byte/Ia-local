"""Lecture et application des corrections proposées par le modèle.

Format demandé au modèle (simple, robuste pour les petits modèles) :

FICHIER: chemin/relatif/Fichier.kt
<<<<<<< AVANT
lignes exactes à remplacer
=======
nouvelles lignes
>>>>>>> APRES
"""
import difflib
import re
from dataclasses import dataclass
from pathlib import Path

_BLOC = re.compile(
    r"FICHIER\s*:\s*`?(?P<fichier>[^\n`]+?)`?\s*\n"
    r"(?:```[\w]*\n)?"
    r"<{5,}\s*AVANT\s*\n(?P<avant>.*?)\n?={5,}\s*\n(?P<apres>.*?)\n?>{5,}\s*APR[EÈ]S",
    re.DOTALL | re.IGNORECASE,
)


@dataclass
class Bloc:
    fichier: str
    avant: str
    apres: str


def extraire_blocs(texte: str) -> list[Bloc]:
    """Extrait les blocs, en ignorant ceux qui ne changent rien (AVANT == APRES) et les doublons."""
    blocs, vus = [], set()
    for m in _BLOC.finditer(texte):
        b = Bloc(m["fichier"].strip(), m["avant"], m["apres"])
        cle = (b.fichier, b.avant.strip(), b.apres.strip())
        if b.avant.strip() == b.apres.strip() or cle in vus:
            continue
        vus.add(cle)
        blocs.append(b)
    return blocs


def _remplacer(contenu: str, avant: str, apres: str) -> str | None:
    """Remplace `avant` par `apres`. Tolère les écarts d'espaces/indentation (fréquents
    avec les petits modèles), mais exige une correspondance unique."""
    if avant and contenu.count(avant) == 1:
        return contenu.replace(avant, apres, 1)

    lignes = contenu.split("\n")
    cible = [l.strip() for l in avant.strip("\n").split("\n")]
    if not any(cible):
        return None
    n = len(cible)
    positions = [
        i for i in range(len(lignes) - n + 1)
        if [l.strip() for l in lignes[i:i + n]] == cible
    ]
    if len(positions) != 1:
        return None
    i = positions[0]
    # Réapplique l'indentation d'origine de la première ligne.
    indent_orig = re.match(r"\s*", lignes[i]).group()
    nouvelles = apres.strip("\n").split("\n") if apres.strip() else []
    indent_modele = re.match(r"\s*", nouvelles[0]).group() if nouvelles else ""
    reindente = [
        indent_orig + l[len(indent_modele):] if l.startswith(indent_modele) else l
        for l in nouvelles
    ]
    return "\n".join(lignes[:i] + reindente + lignes[i + n:])


def appliquer(dossier: Path, blocs: list[Bloc]) -> tuple[dict[Path, str], list[str]]:
    """Applique les blocs en mémoire. Renvoie {fichier: nouveau contenu} et les erreurs."""
    nouveaux: dict[Path, str] = {}
    erreurs = []
    racine = dossier.resolve()
    for b in blocs:
        chemin = (dossier / b.fichier).resolve()
        if not chemin.is_relative_to(racine):
            erreurs.append(f"{b.fichier} : chemin hors du dépôt, ignoré.")
            continue
        if chemin in nouveaux:
            contenu = nouveaux[chemin]
        elif chemin.exists():
            contenu = chemin.read_text(encoding="utf-8")
        elif not b.avant.strip():
            contenu = ""  # création de fichier
        else:
            erreurs.append(f"{b.fichier} : fichier introuvable.")
            continue
        if not b.avant.strip() and not contenu:
            resultat = b.apres
        else:
            resultat = _remplacer(contenu, b.avant, b.apres)
        if resultat is None:
            erreurs.append(
                f"{b.fichier} : le texte AVANT ne correspond à aucun endroit unique du fichier :\n{b.avant}"
            )
            continue
        nouveaux[chemin] = resultat
    return nouveaux, erreurs


def diff(dossier: Path, nouveaux: dict[Path, str]) -> str:
    morceaux = []
    for chemin, contenu in nouveaux.items():
        ancien = chemin.read_text(encoding="utf-8") if chemin.exists() else ""
        rel = str(chemin.relative_to(dossier.resolve()))
        morceaux.extend(difflib.unified_diff(
            ancien.splitlines(keepends=True), contenu.splitlines(keepends=True),
            fromfile="a/" + rel, tofile="b/" + rel,
        ))
    return "".join(morceaux)


def ecrire(nouveaux: dict[Path, str]) -> None:
    for chemin, contenu in nouveaux.items():
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(contenu, encoding="utf-8")
