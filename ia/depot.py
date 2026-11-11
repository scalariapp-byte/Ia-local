"""Gestion du dépôt GitHub : clonage, lecture des fichiers, sélection, branches, commits."""
import os
import re
import subprocess
from pathlib import Path

from . import config


def _git(args, cwd=None, verifier=True) -> str:
    res = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if verifier and res.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} a échoué :\n{res.stderr.strip()}")
    return res.stdout.strip()


def _url_avec_jeton(url: str) -> str:
    """Pour les dépôts privés : utilise GITHUB_TOKEN s'il est défini (jamais écrit sur disque)."""
    jeton = os.environ.get("GITHUB_TOKEN")
    if jeton and url.startswith("https://github.com/"):
        return url.replace("https://", f"https://x-access-token:{jeton}@", 1)
    return url


def normaliser_url(cible: str) -> str:
    if re.fullmatch(r"[\w.-]+/[\w.-]+", cible):
        return f"https://github.com/{cible}.git"
    return cible


def recuperer(cible: str) -> Path:
    """Clone le dépôt (ou le met à jour). `cible` : 'utilisateur/depot', une URL, ou un dossier local."""
    if Path(cible).is_dir():
        return Path(cible).resolve()
    url = normaliser_url(cible)
    nom = url.rstrip("/").removesuffix(".git").split("/")[-1]
    dossier = config.DOSSIER_DEPOTS / nom
    if (dossier / ".git").is_dir():
        try:
            _git(["pull", "--ff-only"], cwd=dossier)
            print(f"Dépôt mis à jour : {dossier}")
        except RuntimeError as e:
            print(f"(Hors ligne ou pull impossible, j'utilise la copie locale) {e}")
    else:
        config.DOSSIER_DEPOTS.mkdir(parents=True, exist_ok=True)
        _git(["clone", "--depth", "50", _url_avec_jeton(url), str(dossier)])
        # On retire le jeton de l'URL enregistrée.
        _git(["remote", "set-url", "origin", url], cwd=dossier)
        print(f"Dépôt cloné : {dossier}")
    return dossier


def lister_fichiers(dossier: Path) -> list[Path]:
    fichiers = []
    for racine, dossiers, noms in os.walk(dossier):
        dossiers[:] = [d for d in dossiers if d not in config.DOSSIERS_IGNORES]
        for nom in noms:
            p = Path(racine) / nom
            if p.suffix in config.EXTENSIONS_CODE and p.stat().st_size < 200_000:
                fichiers.append(p)
    return sorted(fichiers)


def arborescence(dossier: Path, fichiers: list[Path], limite: int = 300) -> str:
    """Vue d'ensemble du projet : permet au modèle de 'ne pas se perdre'."""
    lignes = [str(f.relative_to(dossier)) for f in fichiers[:limite]]
    if len(fichiers) > limite:
        lignes.append(f"... (+{len(fichiers) - limite} fichiers)")
    return "\n".join(lignes)


_MOTS = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")


def selectionner(dossier: Path, fichiers: list[Path], demande: str, budget: int) -> list[Path]:
    """Choisit les fichiers les plus pertinents pour la demande, sans dépasser le budget.

    Score simple et sans IA (donc instantané) : mots de la demande trouvés dans le chemin
    (poids fort) et dans le contenu, bonus pour le code source principal.
    """
    mots = {m.lower() for m in _MOTS.findall(demande)}
    scores = []
    for f in fichiers:
        rel = str(f.relative_to(dossier)).lower()
        try:
            contenu = f.read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            continue
        score = sum(5 for m in mots if m in rel) + sum(min(contenu.count(m), 5) for m in mots)
        if f.suffix in {".kt", ".java", ".dart"}:
            score += 1
        if "test" in rel:
            score -= 1
        scores.append((score, len(contenu), f))
    scores.sort(key=lambda t: (-t[0], t[1]))
    choisis, total = [], 0
    for score, taille, f in scores:
        if mots and score <= 1 and choisis:
            break
        if total + taille > budget:
            continue
        choisis.append(f)
        total += taille
    return choisis


def creer_branche(dossier: Path, nom: str) -> str:
    nom = "ia/" + re.sub(r"[^a-z0-9-]+", "-", nom.lower()).strip("-")[:40]
    existantes = _git(["branch", "--list", nom], cwd=dossier)
    _git(["checkout", nom] if existantes else ["checkout", "-b", nom], cwd=dossier)
    return nom


def commit(dossier: Path, fichiers: list[Path], message: str) -> None:
    _git(["add", *[str(f) for f in fichiers]], cwd=dossier)
    _git(["commit", "-m", message], cwd=dossier)


def pousser(dossier: Path) -> None:
    branche = _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=dossier)
    url = _git(["remote", "get-url", "origin"], cwd=dossier)
    _git(["push", "-u", _url_avec_jeton(url), branche], cwd=dossier)
