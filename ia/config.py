"""Configuration : chemins, modèles disponibles, paramètres du serveur."""
import json
import os
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_MODELES = Path(os.environ.get("IA_MODELES", RACINE / "models"))
DOSSIER_DEPOTS = Path(os.environ.get("IA_DEPOTS", RACINE / "depots"))
DOSSIER_ETAT = Path(os.environ.get("IA_ETAT", RACINE / ".ia"))
FICHIER_MODELES = RACINE / "modeles.json"

URL_SERVEUR = os.environ.get("IA_SERVEUR", "http://127.0.0.1:8080")

# Taille de contexte réservée par le serveur (en tokens). 16384 avec 12 Go de RAM :
# ~0,6 Go de cache pour le 3B, ~0,9 Go pour le 7B. Descends à 8192 si Android ferme Termux.
CONTEXTE = int(os.environ.get("IA_CONTEXTE", "16384"))

# Plafond de code envoyé par requête, indépendant du contexte : sur téléphone, la lecture
# coûte ~1 s pour 30 à 80 tokens. 14 000 caractères ~ 4 000 tokens ~ 1 à 2 min avec le 3B.
# Monte-le pour analyser plus de fichiers d'un coup, au prix du temps.
MAX_CODE = int(os.environ.get("IA_MAX_CODE", "14000"))

# Approximation : 1 token ~ 3,5 caractères de code.
CARACTERES_PAR_TOKEN = 3.5

EXTENSIONS_CODE = {
    ".kt", ".kts", ".java", ".dart", ".xml", ".gradle", ".py", ".js", ".ts",
    ".c", ".cpp", ".h", ".swift", ".go", ".rs",
}
DOSSIERS_IGNORES = {
    ".git", "build", ".gradle", ".idea", "node_modules", ".dart_tool",
    "__pycache__", "generated", ".cxx", "intermediates",
}


def charger_modeles() -> dict:
    with open(FICHIER_MODELES, encoding="utf-8") as f:
        return json.load(f)


def budget_caracteres(reserve_tokens: int = 2500) -> int:
    """Nombre de caractères de code qu'on peut envoyer en laissant de la place à la réponse."""
    return min(MAX_CODE, int((CONTEXTE - reserve_tokens) * CARACTERES_PAR_TOKEN))
