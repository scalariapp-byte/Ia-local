"""Client minimal pour llama-server (API compatible OpenAI). Aucune dépendance externe."""
import json
import sys
import time
import urllib.error
import urllib.request

from . import config


class ErreurLLM(RuntimeError):
    pass


def serveur_actif(url: str = None) -> bool:
    url = url or config.URL_SERVEUR
    try:
        with urllib.request.urlopen(url + "/health", timeout=3) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError):
        return False


def tourne_en_rond(texte: str, fenetre: int = 100) -> bool:
    """Détecte une boucle de répétition (défaut fréquent des petits modèles) : les derniers
    caractères écrits sont déjà apparus au moins 2 fois plus haut, à l'identique.
    (Une seule répétition est normale : un bloc APRES reprend souvent le texte du bloc AVANT.)"""
    if len(texte) < 3 * fenetre:
        return False
    fin = texte[-fenetre:]
    return texte[:-fenetre].count(fin) >= 2


def _afficher_vitesse(t: dict) -> str:
    try:
        return (f" | lecture {t['prompt_n']} tokens à {t['prompt_per_second']:.0f}/s"
                f", écriture {t['predicted_n']} tokens à {t['predicted_per_second']:.1f}/s")
    except (KeyError, TypeError):
        return ""


def discuter(messages, temperature=0.2, max_tokens=1500, flux=True, url=None, arret=None,
             stop=None) -> str:
    """Envoie une conversation au modèle et renvoie sa réponse complète.

    Avec flux=True, la réponse s'affiche au fur et à mesure (utile : le téléphone est lent,
    tu vois que ça avance). La génération est coupée dès que le modèle tourne en rond, ou
    quand `arret(texte)` renvoie True : sur téléphone, chaque token inutile coûte du temps.
    """
    url = url or config.URL_SERVEUR
    corps = json.dumps({
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": flux,
        "repeat_penalty": 1.1,
        "cache_prompt": True,
        # Arrêt côté serveur : il s'arrête net et envoie quand même ses mesures de vitesse.
        **({"stop": stop} if stop else {}),
    }).encode()
    req = urllib.request.Request(
        url + "/v1/chat/completions", data=corps,
        headers={"Content-Type": "application/json"},
    )
    debut = time.time()
    try:
        reponse = urllib.request.urlopen(req, timeout=1800)
    except urllib.error.URLError as e:
        raise ErreurLLM(
            f"Serveur IA injoignable ({url}). Lance d'abord : python -m ia serveur"
        ) from e

    morceaux, vitesse, coupe = [], "", ""
    with reponse:
        if not flux:
            data = json.load(reponse)
            return data["choices"][0]["message"]["content"]
        for ligne in reponse:
            ligne = ligne.decode("utf-8", "replace").strip()
            if not ligne.startswith("data:"):
                continue
            charge = ligne[5:].strip()
            if charge == "[DONE]":
                break
            try:
                data = json.loads(charge)
            except json.JSONDecodeError:
                continue
            if data.get("timings"):
                vitesse = _afficher_vitesse(data["timings"])
            try:
                delta = data["choices"][0]["delta"].get("content") or ""
            except (KeyError, IndexError):
                continue
            morceaux.append(delta)
            sys.stderr.write(delta)
            sys.stderr.flush()
            texte = "".join(morceaux)
            if tourne_en_rond(texte):
                coupe = " | coupé : le modèle se répétait"
                break
            if arret and arret(texte):
                coupe = " | coupé : réponse complète"
                break
    texte = "".join(morceaux)
    sys.stderr.write(f"\n[{time.time() - debut:.0f} s{vitesse}{coupe}]\n")
    return texte
