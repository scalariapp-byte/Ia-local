#!/usr/bin/env bash
# Compile llama.cpp sur le téléphone, optimisé pour sa puce (instructions dotprod + fp16).
# Le paquet Termux « llama-cpp » est générique : sur Poco M7 Pro il lit ~7 tokens/s au lieu
# de plusieurs dizaines. Durée : 10 à 25 minutes. Téléphone branché, écran allumé.
set -e
cd "$(dirname "$0")"
pkg install -y clang cmake git

[ -d llama.cpp ] || git clone --depth 1 https://github.com/ggml-org/llama.cpp
git -C llama.cpp pull --ff-only || true

# Dimensity 7025 (Cortex-A78 + A55) : ARMv8.2-A avec dotprod et fp16, sans i8mm.
# Pour une autre puce, remplace par : -DGGML_NATIVE=ON
ARCH="${IA_ARCH:-armv8.2-a+dotprod+fp16}"
cmake -S llama.cpp -B llama.cpp/build \
  -DCMAKE_BUILD_TYPE=Release \
  -DGGML_NATIVE=OFF \
  -DGGML_CPU_ARM_ARCH="$ARCH" \
  -DGGML_OPENMP=OFF
cmake --build llama.cpp/build --target llama-server llama-bench -j "$(nproc)"

echo
echo "Compilé : $(pwd)/llama.cpp/build/bin/llama-server"
echo "Mesure maintenant :  ia vitesse"
