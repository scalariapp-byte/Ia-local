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


def discuter(messages, temperature=0.2, max_tokens=2048, flux=True, url=None) -> str:
    """Envoie une conversation au modèle et renvoie sa réponse complète.

    Avec flux=True, la réponse s'affiche au fur et à mesure (utile : le téléphone est lent,
    tu vois que ça avance).
    """
    url = url or config.URL_SERVEUR
    corps = json.dumps({
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": flux,
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

    morceaux = []
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
                delta = json.loads(charge)["choices"][0]["delta"].get("content") or ""
            except (json.JSONDecodeError, KeyError, IndexError):
                continue
            morceaux.append(delta)
            sys.stderr.write(delta)
            sys.stderr.flush()
    texte = "".join(morceaux)
    sys.stderr.write(f"\n[{time.time() - debut:.0f} s]\n")
    return texte
