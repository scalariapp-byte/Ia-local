"""Téléchargement des modèles et démarrage du moteur llama.cpp (llama-server)."""
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from . import config, llm


def chemin_modele(nom: str) -> Path:
    modeles = config.charger_modeles()["modeles"]
    if nom not in modeles:
        raise SystemExit(f"Modèle inconnu : {nom}. Disponibles : {', '.join(modeles)}")
    return config.DOSSIER_MODELES / modeles[nom]["fichier"]


def telecharger(nom: str) -> Path:
    """Seule étape qui a besoin d'Internet (une fois). Ensuite tout est hors ligne."""
    infos = config.charger_modeles()["modeles"][nom]
    dest = chemin_modele(nom)
    if dest.exists():
        print(f"Déjà présent : {dest}")
        return dest
    config.DOSSIER_MODELES.mkdir(parents=True, exist_ok=True)
    partiel = dest.with_suffix(".partiel")
    deja = partiel.stat().st_size if partiel.exists() else 0
    req = urllib.request.Request(infos["url"], headers={"Range": f"bytes={deja}-"} if deja else {})
    print(f"Téléchargement de {nom} ({infos['taille']})...")
    with urllib.request.urlopen(req, timeout=60) as r, open(partiel, "ab" if deja else "wb") as f:
        total = int(r.headers.get("Content-Length", 0)) + deja
        recu = deja
        while bloc := r.read(1 << 20):
            f.write(bloc)
            recu += len(bloc)
            if total:
                sys.stdout.write(f"\r  {recu / total:6.1%}  {recu >> 20} / {total >> 20} Mo")
                sys.stdout.flush()
    partiel.rename(dest)
    print(f"\nModèle enregistré : {dest}")
    return dest


def binaire_llama() -> str:
    for candidat in (
        shutil.which("llama-server"),
        str(config.RACINE / "llama.cpp" / "build" / "bin" / "llama-server"),
    ):
        if candidat and Path(candidat).exists():
            return candidat
    raise SystemExit("llama-server introuvable. Lance d'abord : bash installer.sh")


def demarrer(nom: str, arriere_plan: bool = True) -> None:
    modele = chemin_modele(nom)
    if not modele.exists():
        raise SystemExit(f"Modèle absent. Télécharge-le : python -m ia telecharger {nom}")
    if llm.serveur_actif():
        arreter()
    port = config.URL_SERVEUR.rsplit(":", 1)[-1].split("/")[0]
    # Sur Dimensity 7025 : 2 gros cœurs A78 + 6 petits A55. 4 threads est en général le
    # meilleur réglage (au-delà, les petits cœurs ralentissent le calcul). À ajuster.
    threads = os.environ.get("IA_THREADS", "4")
    cmd = [binaire_llama(), "-m", str(modele), "-c", str(config.CONTEXTE),
           "-t", threads, "--host", "127.0.0.1", "--port", port]
    config.DOSSIER_ETAT.mkdir(parents=True, exist_ok=True)
    if not arriere_plan:
        os.execv(cmd[0], cmd)
    journal = open(config.DOSSIER_ETAT / "serveur.log", "w")
    proc = subprocess.Popen(cmd, stdout=journal, stderr=subprocess.STDOUT, start_new_session=True)
    (config.DOSSIER_ETAT / "serveur.pid").write_text(str(proc.pid))
    print(f"Chargement de {nom}...", end="", flush=True)
    for _ in range(180):
        if llm.serveur_actif():
            print(f" prêt sur {config.URL_SERVEUR} (interface web incluse : ouvre ce lien dans le navigateur)")
            return
        if proc.poll() is not None:
            raise SystemExit(f"\nLe serveur s'est arrêté. Voir {config.DOSSIER_ETAT / 'serveur.log'}")
        time.sleep(1)
        print(".", end="", flush=True)
    raise SystemExit("\nLe serveur ne répond pas après 3 minutes.")


def arreter() -> None:
    pid_f = config.DOSSIER_ETAT / "serveur.pid"
    if pid_f.exists():
        try:
            os.kill(int(pid_f.read_text()), 15)
            time.sleep(1)
        except (ProcessLookupError, ValueError):
            pass
        pid_f.unlink()
        print("Serveur arrêté.")
