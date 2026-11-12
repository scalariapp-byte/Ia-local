"""Vérification d'une correction AVANT de l'accepter.

Niveaux, du plus léger au plus lourd (on utilise ce qui est installé) :
1. Équilibre des parenthèses / accolades / crochets / guillemets (toujours, instantané).
2. ktlint (Kotlin) si installé : erreurs de syntaxe et de style.
3. Compilation : kotlinc / javac / python, si installés et si --compiler est demandé.
"""
import difflib
import re
import shutil
from collections import Counter
import subprocess
import tempfile
from pathlib import Path

_PAIRES = {")": "(", "]": "[", "}": "{"}


def equilibre(code: str) -> str | None:
    """Renvoie un message d'erreur si les délimiteurs sont déséquilibrés, sinon None.
    Ignore le contenu des chaînes et des commentaires (syntaxe type C/Kotlin/Java/Dart)."""
    pile = []
    i, n, ligne = 0, len(code), 1
    while i < n:
        c = code[i]
        if c == "\n":
            ligne += 1
        elif code.startswith("//", i):
            fin = code.find("\n", i)
            i = n if fin == -1 else fin
            continue
        elif code.startswith("/*", i):
            fin = code.find("*/", i + 2)
            if fin == -1:
                return f"commentaire /* non fermé (ligne {ligne})"
            ligne += code.count("\n", i, fin)
            i = fin + 2
            continue
        elif code.startswith('"""', i):
            fin = code.find('"""', i + 3)
            if fin == -1:
                return f'chaîne """ non fermée (ligne {ligne})'
            ligne += code.count("\n", i, fin)
            i = fin + 3
            continue
        elif c in "\"'":
            j = i + 1
            while j < n and code[j] != c and code[j] != "\n":
                j += 2 if code[j] == "\\" else 1
            if j >= n or code[j] == "\n":
                if c == "'":  # apostrophe dans un commentaire mal détecté : on tolère
                    i += 1
                    continue
                return f"chaîne non fermée (ligne {ligne})"
            i = j + 1
            continue
        elif c in "([{":
            pile.append((c, ligne))
        elif c in ")]}":
            if not pile or pile[-1][0] != _PAIRES[c]:
                return f"'{c}' inattendu (ligne {ligne})"
            pile.pop()
        i += 1
    if pile:
        c, l = pile[-1]
        return f"'{c}' ouvert ligne {l} jamais fermé"
    return None


def _lancer(cmd, cwd=None, delai=300) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=delai)
        return r.returncode, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return 1, f"délai dépassé ({delai} s) : {' '.join(cmd)}"


_DECL = [
    re.compile(r"\b(?:val|var)\s+(\w+)"),                         # Kotlin
    re.compile(r"\bfor\s*\(\s*(\w+)\s+in\b"),                       # Kotlin for (x in ...)
    re.compile(r"\bfor\s*\(\s*(?:final\s+)?[\w<>\[\]]+\s+(\w+)\s*[:=]"),  # Java for (int i = / for (T x :
]


def _declarations(lignes) -> set[str]:
    return {m.group(1) for l in lignes for r in _DECL for m in r.finditer(l)}


def variables_orphelines(ancien: str, nouveau: str) -> list[str]:
    """Détecte, sans compilateur, une erreur classique des petits modèles : renommer ou
    supprimer une variable sur une ligne, mais la laisser utilisée juste en dessous.
    Exemple : for (i in ...) devient for (article in articles), mais articles[i] reste."""
    a, n = ancien.split("\n"), nouveau.split("\n")
    problemes = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, n, autojunk=False).get_opcodes():
        if op not in {"replace", "delete"}:
            continue
        perdues = _declarations(a[i1:i2]) - _declarations(n[j1:j2])
        for nom in sorted(perdues):
            motif = re.compile(rf"\b{re.escape(nom)}\b")
            for k in range(j1, min(len(n), j2 + 25)):
                if motif.search(n[k]) and nom not in _declarations([n[k]]):
                    problemes.append(
                        f"la variable '{nom}' n'est plus déclarée mais elle est encore utilisée "
                        f"ligne {k + 1} : `{n[k].strip()}`. Inclus cette ligne dans le bloc et corrige-la aussi."
                    )
                    break
    return problemes


# Préfixe « chemin:ligne[:colonne]: » (javac, kotlinc) ou « e: file:///chemin:ligne:col » (Kotlin).
_POSITION = re.compile(r"^(?:e:\s*)?\S*?:\d+(?::\d+)?:?\s*")
_LIGNE_ERREUR = re.compile(r"(?:^e:\s|:\d+(?::\d+)?:?\s*error\b)", re.IGNORECASE)


def _erreurs_compilation(commande, fichier: Path, tmp: str) -> Counter:
    code, sortie = _lancer([*commande, str(fichier)], cwd=tmp, delai=900)
    lignes = [l for l in sortie.splitlines() if _LIGNE_ERREUR.search(l)]
    # Sans numéro de ligne : une même erreur décalée par la correction reste « la même ».
    return Counter(_POSITION.sub("", l).strip() for l in lignes)


def _compilateur(ext: str, tmp: str):
    if ext == ".kt" and shutil.which("kotlinc"):
        return ["kotlinc", "-nowarn", "-d", tmp]
    if ext == ".java" and shutil.which("javac"):
        return ["javac", "-nowarn", "-d", tmp]
    return None


def verifier(nouveaux: dict[Path, str], compiler: bool = False) -> list[str]:
    """Renvoie la liste des problèmes détectés (vide = OK)."""
    problemes = []
    with tempfile.TemporaryDirectory() as tmp:
        for chemin, contenu in nouveaux.items():
            ext = chemin.suffix
            ancien = chemin.read_text(encoding="utf-8") if chemin.exists() else ""
            if ext in {".kt", ".kts", ".java", ".dart", ".js", ".ts", ".c", ".cpp", ".swift", ".go", ".rs"}:
                err = equilibre(contenu)
                if err:
                    problemes.append(f"{chemin.name} : {err}")
                    continue
                orphelines = variables_orphelines(ancien, contenu)
                if orphelines:
                    problemes.extend(f"{chemin.name} : {o}" for o in orphelines)
                    continue
            dossier_av, dossier_ap = Path(tmp, "avant"), Path(tmp, "apres")
            dossier_av.mkdir(exist_ok=True)
            dossier_ap.mkdir(exist_ok=True)
            copie = dossier_ap / chemin.name
            copie.write_text(contenu, encoding="utf-8")

            if ext == ".py":
                code, sortie = _lancer(["python3", "-m", "py_compile", str(copie)])
                if code:
                    problemes.append(f"{chemin.name} : {sortie}")
            elif ext in {".kt", ".kts"} and shutil.which("ktlint"):
                code, sortie = _lancer(["ktlint", "--relative", str(copie)], cwd=tmp)
                # On ne bloque que sur les vraies erreurs de syntaxe, pas sur le style.
                erreurs = [l for l in sortie.splitlines() if "Not a valid Kotlin file" in l or "parse" in l.lower()]
                if erreurs:
                    problemes.append(f"{chemin.name} : " + "\n".join(erreurs))
            commande = _compilateur(ext, tmp) if compiler else None
            if commande:
                # Comparaison avant/après : hors Gradle, les références Android sont toujours
                # « non résolues ». On ne garde que les erreurs AJOUTÉES par la correction.
                original = dossier_av / chemin.name
                original.write_text(ancien, encoding="utf-8")
                avant = _erreurs_compilation(commande, original, tmp) if ancien else Counter()
                apres = _erreurs_compilation(commande, copie, tmp)
                ajoutees = list((apres - avant).elements())
                if ajoutees:
                    problemes.append(f"{chemin.name} : erreurs de compilation ajoutées :\n" + "\n".join(ajoutees[:10]))
    return problemes
