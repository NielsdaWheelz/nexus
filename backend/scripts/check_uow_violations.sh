#!/usr/bin/env bash
# Check for UoW pattern violations: session.commit() outside get_session()
#
# Usage: ./scripts/check_uow_violations.sh
# Exit code: 0 if clean, 1 if violations found

set -e

VIOLATIONS=$(grep -rn "session\.commit()" app/ --include="*.py" | grep -v "app/db/session.py" || true)

if [ -n "$VIOLATIONS" ]; then
    echo "❌ UoW VIOLATION: Found session.commit() outside app/db/session.py"
    echo ""
    echo "The Unit of Work pattern requires that ONLY get_session() calls commit/rollback/close."
    echo "All other code must use session.add(), session.flush(), session.refresh()."
    echo ""
    echo "Violations found:"
    echo "$VIOLATIONS"
    exit 1
fi

echo "✓ UoW pattern check passed: No rogue session.commit() calls found"
exit 0
