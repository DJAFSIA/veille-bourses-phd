#!/bin/sh
# Assemble le tableau de bord dans _site/ (utilisé par GitHub Pages et par Vercel)
set -e
rm -rf _site && mkdir -p _site/data
cp site/* _site/
cp data/offres.json data/statuts.json _site/data/
DEPOT="${GITHUB_REPOSITORY:-}"
if [ -z "$DEPOT" ] && [ -n "${VERCEL_GIT_REPO_OWNER:-}" ]; then DEPOT="$VERCEL_GIT_REPO_OWNER/$VERCEL_GIT_REPO_SLUG"; fi
DEPOT="${DEPOT:-DJAFSIA/veille-bourses-phd}"
printf '{"depot":"%s","maj":"%s"}\n' "$DEPOT" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > _site/config.json
echo "Site assemblé pour $DEPOT"
