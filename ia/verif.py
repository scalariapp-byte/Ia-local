"""Vérification d'une correction AVANT de l'accepter.

Niveaux, du plus léger au plus lourd (on utilise ce qui est installé) :
1. Équilibre des parenthèses / accolades / crochets / guillemets (toujours, instantané).
2. ktlint (Kotlin) si installé : erreurs de syntaxe et de style.
3. Compilation : kotlinc / javac / python, si installés et si --compiler est demandé.
"""
import shutil
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


def verifier(nouveaux: dict[Path, str], compiler: bool = False) -> list[str]:
    """Renvoie la liste des problèmes détectés (vide = OK)."""
    problemes = []
    with tempfile.TemporaryDirectory() as tmp:
        for chemin, contenu in nouveaux.items():
            ext = chemin.suffix
            if ext in {".kt", ".kts", ".java", ".dart", ".js", ".ts", ".c", ".cpp", ".swift", ".go", ".rs"}:
                err = equilibre(contenu)
                if err:
                    problemes.append(f"{chemin.name} : {err}")
                    continue
            copie = Path(tmp) / chemin.name
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
            if compiler:
                if ext == ".kt" and shutil.which("kotlinc"):
                    code, sortie = _lancer(["kotlinc", str(copie), "-d", tmp], delai=900)
                    # Les références Android non résolues sont normales hors Gradle : on
                    # ne garde que les erreurs de syntaxe.
                    erreurs = [l for l in sortie.splitlines()
                               if "error:" in l and "unresolved reference" not in l]
                    if erreurs:
                        problemes.append(f"{chemin.name} :\n" + "\n".join(erreurs[:15]))
                elif ext == ".java" and shutil.which("javac"):
                    code, sortie = _lancer(["javac", "-d", tmp, str(copie)])
                    erreurs = [l for l in sortie.splitlines()
                               if "error:" in l and "cannot find symbol" not in l
                               and "does not exist" not in l]
                    if erreurs:
                        problemes.append(f"{chemin.name} :\n" + "\n".join(erreurs[:15]))
    return problemes
