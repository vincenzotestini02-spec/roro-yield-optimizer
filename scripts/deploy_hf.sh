#!/usr/bin/env bash
# Publish the app to a Hugging Face Space.
#   scripts/deploy_hf.sh https://huggingface.co/spaces/<user>/<space>
# Git asks for the Hugging Face token through your credential manager: never put it here.
set -euo pipefail

space_url="${1:?usage: scripts/deploy_hf.sh <space-repo-url>}"
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

git clone --depth 1 "$space_url" "$work/space"
find "$work/space" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +

cd "$root"
cp Dockerfile .dockerignore requirements.txt "$work/space/"
cp deploy/hf/README.md "$work/space/README.md"
cp -r roro_yield server "$work/space/"
mkdir -p "$work/space/benchmarks"
cp benchmarks/__init__.py benchmarks/demand_table.py "$work/space/benchmarks/"
cp -r benchmarks/results "$work/space/benchmarks/"
mkdir -p "$work/space/web"
tar --exclude=node_modules --exclude=dist --exclude=test-results --exclude=playwright-report -cf - -C web . \
  | tar -xf - -C "$work/space/web"
find "$work/space" -name __pycache__ -type d -prune -exec rm -rf {} +

cd "$work/space"
git add -A
if git diff --cached --quiet; then
  echo "Nothing to publish."
  exit 0
fi
git commit -m "Deploy $(git -C "$root" rev-parse --short HEAD)"
git push
echo "Published. Follow the build at $space_url"
