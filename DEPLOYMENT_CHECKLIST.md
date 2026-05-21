# Graph Save Fix - Deployment Checklist

## Critical Fix Overview

**What's Fixed**: Schedule changes (б, кп, д, н, от, п) now save correctly even when department/position filters are applied.

**Root Cause**: Type inconsistency in day column handling between GET (render) and POST (save) handlers.

**Affected Commits**:
- `b0195aa` - Fix graph save: consistent string handling for day columns in POST handler
- `de959a1` - Update graph save logic docs
- `d83da70` - Add comprehensive fix summary
- `2b4b983` - Improve GET handler consistency

## Pre-Deployment Checklist

- [ ] Verify all 4 commits are in the repository
- [ ] Run tests (if any exist)
- [ ] Review changes in `shifts/graph_views.py`
- [ ] Confirm no database migrations needed
- [ ] Verify no new dependencies added

## Deployment Steps

1. **Merge/Cherry-pick commits to production branch**
   ```bash
   git cherry-pick b0195aa de959a1 d83da70 2b4b983
   # OR merge if on a feature branch
   git merge fix/graph-save-day-columns
   ```

2. **Deploy to server**
   ```bash
   git pull origin main
   python manage.py collectstatic --noinput
   # If using gunicorn/uwsgi, restart the service
   systemctl restart biota-django
   ```

3. **Verify deployment**
   - [ ] Access the graph page at `/graph/`
   - [ ] Verify initial load works
   - [ ] Check that existing data is displayed

## Post-Deployment Testing

**Test Case 1: No Filters**
- [ ] Add changes without filters
- [ ] Save
- [ ] Refresh page
- [ ] ✓ Changes should persist

**Test Case 2: Single Filter**
- [ ] Filter by department "1"
- [ ] Set values (б, кп, etc.) for visible employees
- [ ] Save
- [ ] Change filter to "all"
- [ ] ✓ Changes should be in correct rows only

**Test Case 3: Multiple Filters**
- [ ] Filter by dept "1" AND position "Нач"
- [ ] Set values
- [ ] Save
- [ ] Filter by dept "1" AND position "Опер"
- [ ] Set different values
- [ ] Save
- [ ] Show all
- [ ] ✓ Each filter combination should have correct data

**Test Case 4: Edit, Filter, Edit, Verify**
- [ ] Filter dept "1", set values, save
- [ ] Change filter to dept "2", set values, save
- [ ] Change back to dept "1"
- [ ] ✓ Data from step 1 should still be there unchanged

## Known Limitations / Future Improvements

- No real-time conflict resolution if multiple users edit same schedule simultaneously
- Backup/restore functionality is separate (already implemented)
- Undo functionality not available (use backups to restore)

## Rollback Plan

If critical issues are discovered:

```bash
# Revert the changes
git revert 2b4b983
git revert d83da70
git revert de959a1
git revert b0195aa

# Restart service
systemctl restart biota-django
```

**Data integrity**: All existing schedule data remains unchanged during rollback.

## Support Information

**If issues arise**:
1. Check server logs for any errors
2. Verify database file permissions
3. Run test cases from "Post-Deployment Testing" section
4. Review FIX_SUMMARY.md for detailed explanation

**Contact**: [Your contact info]

---

## Sign-Off

- [ ] Deployment completed
- [ ] Post-deployment testing passed
- [ ] Issues resolved (if any)
- [ ] Users notified of fix

**Deployed by**: _________________
**Date**: _________________
**Version**: Fix for b0195aa commit
