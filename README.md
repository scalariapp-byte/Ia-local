# IA locale : analyse et correction de code sur téléphone

Une IA qui tourne **100 % hors ligne** sur Android (testée pour Poco M7 Pro 5G) et qui :

- récupère ton dépôt GitHub et en lit la structure, pour ne pas se perdre ;
- **analyse** le code et classe les problèmes dans l'ordre logique : compilation, plantages, logique, sécurité, performances, lisibilité ;
- **corrige seule** : elle propose une modification, la **vérifie**, se corrige si la vérification échoue, puis committe sur une branche `ia/...` ;
- rédige des **instructions pour une autre IA** ;
- fonctionne avec **plusieurs modèles** au choix.

Ton code ne quitte jamais le téléphone. Internet ne sert qu'à l'installation et à `git clone` / `git push`.

## Comment elle fonctionne

```
ton dépôt GitHub ──git clone──► téléphone
                                  │
   ia/depot.py   choisit les fichiers utiles à ta demande (le modèle ne peut pas tout lire)
   ia/agent.py   construit la consigne ──► llama-server + petit modèle de code (hors ligne)
   ia/modifs.py  applique les blocs AVANT/APRÈS proposés par le modèle
   ia/verif.py   vérifie : accolades, ktlint, compilation  ──échec──► renvoie l'erreur au modèle (3 essais max)
                                  │ OK
                    diff affiché ──► ta validation ──► commit sur la branche ia/...
```

Le « cerveau » est un modèle open source déjà entraîné au code (Qwen2.5-Coder). Entraîner un modèle de zéro demande des milliers de GPU. Un modèle maison entraîné sur un téléphone ou un Raspberry Pi ne corrigerait aucun bug. Ce projet apporte tout le reste : la lecture du dépôt, les consignes, la vérification, la boucle de correction et Git.

## Installation (une fois, avec Internet)

1. Installe **Termux** depuis **F-Droid**. La version du Play Store est obsolète.
2. Dans Termux :
   ```bash
   pkg install -y git
   git clone https://github.com/scalariapp-byte/ia-local
   cd ia-local
   bash installer.sh
   ```
   Pour vérifier aussi les corrections en compilant (environ 500 Mo de plus) : `bash installer.sh --complet`.

## Utilisation (hors ligne)

```bash
ia serveur                      # démarre l'IA (modèle par défaut : coder-3b)
ia serveur coder-7b             # plus précis, plus lent (ia telecharger coder-7b avant)
ia modeles                      # liste les modèles, ✓ = téléchargé

ia analyser moncompte/monapp                                  # liste les problèmes
ia analyser moncompte/monapp "pourquoi l'écran Login plante"  # analyse ciblée
ia corriger moncompte/monapp "crash quand la liste est vide"  # corrige, vérifie, demande confirmation
ia corriger moncompte/monapp -f app/src/main/java/.../MainActivity.kt   # sur un fichier précis
ia corriger moncompte/monapp "..." --auto --pousser           # sans confirmation, puis push
ia instructions moncompte/monapp "ajouter un mode sombre"     # consignes pour une autre IA
ia discuter moncompte/monapp                                  # questions libres
ia arret                                                      # libère la RAM
```

Le serveur fournit aussi une interface de chat : ouvre `http://127.0.0.1:8080` dans le navigateur du téléphone.

**Dépôt privé** : `export GITHUB_TOKEN=ghp_...` avant `ia corriger`. Le jeton reste en mémoire et n'est jamais écrit dans le dépôt.

## Ce qu'il faut savoir (limites réelles)

- **Vitesse.** Estimations sur Dimensity 7025, non mesurées (vérifie-les à ton premier essai) : un fichier de 300 lignes prend ~30 s avec le 1.5B, ~1-2 min avec le 3B (défaut) et ~3-5 min avec le 7B.
- **Qualité.** Un modèle de 1,5 à 3B corrige bien les bugs localisés (null, indices, conditions, oublis). Il est fragile dès qu'une correction touche plusieurs fichiers. Plus ta demande est précise (fichier, symptôme, message d'erreur), meilleur est le résultat. Garde la confirmation tant que tu n'as pas confiance : `--auto` sert pour les cas simples.
- **Vérification.** Sans `--compiler`, la vérification se limite à la structure (accolades, guillemets) et à ktlint s'il est installé. La compilation Kotlin hors Gradle ignore les références Android : elle détecte la syntaxe, pas tout. La vraie compilation du projet doit passer par GitHub Actions après `--pousser`.
- **Mémoire (12 Go).** Le 3B occupe ~3 Go et le 7B ~6 Go : ferme les autres apps avec le 7B. Variables utiles : `IA_MAX_CODE=14000` (code envoyé par requête : plus = plus de fichiers lus d'un coup, mais plus lent), `IA_CONTEXTE=16384` (descends à 8192 si Android ferme Termux) et `IA_THREADS=4` (essaie 2 à 6).

## Tests

```bash
python -m unittest tests.test_ia -v
```

Les tests utilisent un faux serveur qui imite llama.cpp, sans vrai modèle. Ils vérifient la boucle complète : correction refusée, nouvel essai, correction acceptée, commit.
