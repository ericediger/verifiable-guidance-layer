#!/usr/bin/env sh
# Install the pre-commit hook that stops a secret from ever being committed.
# Requires gitleaks (brew install gitleaks). Run once after cloning:
#     sh scripts/install-hooks.sh
# To scan the whole history by hand:
#     gitleaks detect --redact --no-banner
set -e
cd "$(git rev-parse --show-toplevel)"
cat > .git/hooks/pre-commit <<'HOOK'
#!/usr/bin/env sh
if command -v gitleaks >/dev/null 2>&1; then
  gitleaks protect --staged --redact --no-banner || {
    echo "gitleaks: a staged change looks like a secret. Commit aborted." >&2; exit 1; }
else
  echo "gitleaks not installed; skipping secret scan (brew install gitleaks)" >&2
fi
HOOK
chmod +x .git/hooks/pre-commit
echo "pre-commit hook installed"
