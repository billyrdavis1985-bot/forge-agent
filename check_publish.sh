#!/usr/bin/env bash
# Run BEFORE pushing public: shows what git will publish, flags anything private.
cd "$(dirname "$0")"
echo "SAFETY CHECK — each should say 'clean':"
echo -n "  staged critic verdicts: "; git ls-files scratch/ | grep -v gitkeep | head -1 || echo clean
echo -n "  provenance records:     "; git ls-files | grep provenance | grep -v '\.py' | head -1 || echo clean
echo -n "  research log:           "; git ls-files | grep research_log | head -1 || echo clean
echo -n "  adjudications:          "; git ls-files | grep adjudications | head -1 || echo clean
echo -n "  real .env secret:       "; git ls-files | grep -E '^\.env$' | head -1 || echo clean
echo "(anything other than 'clean' above must be removed before pushing public)"
