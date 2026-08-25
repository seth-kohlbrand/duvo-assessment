#!/bin/bash
# Find error handling violations in the codebase

echo "=== ERROR HANDLING AUDIT ==="
echo ""

echo "--- Catch blocks with generic messages (no error.message) ---"
grep -rn "catch" --include="*.ts" --include="*.tsx" -A 5 src/ | \
  grep -B 1 "toast\|alert\|notify" | \
  grep -v "error\.\(message\|details\)" | \
  grep "Failed\|Something went wrong\|Error occurred" || echo "None found"
echo ""

echo "--- Supabase queries ignoring error variable ---"
grep -rn "const { data }" --include="*.ts" --include="*.tsx" src/ | \
  grep "supabase\|from(" | \
  grep -v "error\|, error\|data, error" || echo "None found"
echo ""

echo "--- Empty catch blocks ---"
grep -rn "catch.*{}" --include="*.ts" --include="*.tsx" src/ || echo "None found"
echo ""

echo "--- console.log in catch (should be console.error) ---"
grep -rn "catch" --include="*.ts" --include="*.tsx" -A 3 src/ | \
  grep "console.log" || echo "None found"
echo ""

echo "=== AUDIT COMPLETE ==="
