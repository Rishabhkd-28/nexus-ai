#!/bin/bash
# Run this before every git push to make sure no secrets leak

echo "🔍 Checking for secrets before push..."
echo ""

FAIL=0

# Check .env is not staged
if git ls-files --error-unmatch backend/.env 2>/dev/null; then
  echo "❌ backend/.env is tracked by git — run: git rm --cached backend/.env"
  FAIL=1
else
  echo "✅ backend/.env not tracked"
fi

# Check credentials.json is not staged
if git ls-files --error-unmatch backend/credentials.json 2>/dev/null; then
  echo "❌ credentials.json is tracked by git — run: git rm --cached backend/credentials.json"
  FAIL=1
else
  echo "✅ credentials.json not tracked"
fi

# Check token_output.json is not staged
if git ls-files --error-unmatch backend/token_output.json 2>/dev/null; then
  echo "❌ token_output.json is tracked by git — run: git rm --cached backend/token_output.json"
  FAIL=1
else
  echo "✅ token_output.json not tracked"
fi

# Grep for obvious secrets in tracked files
echo ""
echo "🔍 Scanning tracked files for secrets..."
SECRETS=$(git grep -l "SUPABASE_SERVICE_ROLE_KEY\|TWILIO_AUTH_TOKEN\|GEMINI_API_KEY" -- '*.py' '*.js' '*.jsx' '*.json' 2>/dev/null)
if [ -n "$SECRETS" ]; then
  echo "❌ Possible secrets found in: $SECRETS"
  FAIL=1
else
  echo "✅ No secrets found in source files"
fi

echo ""
if [ $FAIL -eq 0 ]; then
  echo "✅ All checks passed — safe to push"
else
  echo "❌ Fix the issues above before pushing"
  exit 1
fi
