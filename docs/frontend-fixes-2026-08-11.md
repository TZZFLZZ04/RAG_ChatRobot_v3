# Frontend Bug Fixes — 2026-08-11

## Summary

Fixed critical error handling bugs and CSS consistency issues across the frontend.

## JavaScript Fixes

### 1. **Critical: FastAPI 422 Validation Error Messages**

**Problem:** FastAPI returns `{"detail": [...]}` for 422 validation errors, but all three JS files only read `payload.message`, causing validation failures to show a generic "请求失败" instead of the actual field-level errors.

**Fix:** Added `extractErrorMessage()` helper to all three files (app.js, register.js, evaluations.js) that handles three error shapes:
- Backend custom errors: `{"code": "...", "message": "..."}`
- FastAPI validation errors: `{"detail": [{"msg": "...", "loc": [...]}]}`
- Plain text responses

**Files Changed:**
- `app/frontend/static/app.js:97-107` — added helper
- `app/frontend/static/app.js:449` — replaced in assertOkResponse
- `app/frontend/static/app.js:1407` — replaced in streaming error handler
- `app/frontend/static/register.js:46-60` — added helper + replaced in assertOkResponse
- `app/frontend/static/evaluations.js:92-106` — added helper + replaced in assertOkResponse

**Impact:** Users now see actual validation errors like "Field 'email' is required" instead of "请求失败".

### 2. **Session Notice Tone Support**

**Problem:** `setSessionNotice()` couldn't display error/warning tones — always showed success styling.

**Fix:**
- Added `state.sessionTone` field
- Modified `renderSessionNotice()` to apply `.notice-error` or `.notice-warning` classes
- Updated `setSessionNotice(message, tone = "success")` signature

**Files Changed:**
- `app/frontend/static/app.js:181-196`

## CSS Fixes

### 3. **Hardcoded Topbar Heights**

**Problem:** Topbar height was defined as `--topbar-h: 70px` but dozens of rules hardcoded `70px` literals, breaking when the variable changed.

**Fix:** Replaced all hardcoded heights with `var(--topbar-h)`:
- `.main-content` min-height
- `.sidebar` top/height
- `.doc-detail-overlay` top
- Responsive breakpoints at 900px and 760px

**Files Changed:**
- `app/frontend/static/app.css:305,347,776,783,785,1696,1741`

### 4. **Anchor Scroll Offset**

**Problem:** Section anchors scrolled behind the fixed topbar because `scroll-margin-top` was hardcoded as `82px` (70px topbar + 12px gap), ignoring the sticky-nav height when present.

**Fix:** Changed to `calc(var(--topbar-h) + var(--sticky-nav-h) + 12px)` so it adapts when the 900px breakpoint activates sticky nav.

**Files Changed:**
- `app/frontend/static/app.css:317`

### 5. **Missing CSS Hooks**

**Problem:** HTML referenced classes that were never defined in CSS:
- `.notice-error`, `.notice-warning` (session notice variants)
- `.toast-error` (toast error styling)
- `.user-message.error` (error message styling)
- `.placeholder-text` (empty state text)

**Fix:** Added all missing classes as a coherent block after `.panel` definitions:
- `.notice-error` / `.notice-warning` — red/amber backgrounds
- `.toast-error` — inline background override removed, now uses class
- `.user-message.error` — red border + background
- `.placeholder-text` — muted gray text

**Files Changed:**
- `app/frontend/static/app.css:710-742`

### 6. **Toast Tone as Class**

**Problem:** `showToast()` set inline `background-color` styles, fighting CSS specificity and preventing theme changes.

**Fix:**
- Removed inline style logic from `showToast()`
- Added `.toast-error` class instead via `classList.toggle()`
- CSS now fully controls toast appearance

**Files Changed:**
- `app/frontend/static/app.js:89-95` (JS side)
- `app/frontend/static/app.css:722-727` (CSS side)

### 7. **Sticky Nav Height Not Set**

**Problem:** `--sticky-nav-h` was declared as `0` at root but never updated when the 900px breakpoint activated sticky nav, breaking anchor offsets on tablet layouts.

**Fix:** Set `--sticky-nav-h: 52px;` inside the `@media (max-width: 900px)` block.

**Files Changed:**
- `app/frontend/static/app.css` (900px breakpoint)

### 8. **Responsive Topbar Height Inconsistency**

**Problem:** At 760px breakpoint, topbar height changes to 60px but derived calculations (`.topbar-content` min-height) were still hardcoded as `70px`.

**Fix:** Changed hardcoded `70px` to `var(--topbar-h)` so the 760px override propagates automatically.

**Files Changed:**
- `app/frontend/static/app.css:1741`

## Testing Recommendations

1. **422 Validation Errors:**
   - Try registering with invalid email format
   - Try login with empty password
   - Verify field-level error messages appear in toast

2. **Session Notice Tones:**
   - Trigger error conditions that call `setSessionNotice(..., "error")`
   - Verify red background appears

3. **CSS Variables:**
   - Resize browser to 900px, 760px breakpoints
   - Verify topbar height changes propagate
   - Click section anchors — verify scroll position accounts for fixed headers

4. **Toast Error Styling:**
   - Trigger any API error
   - Verify toast shows red background without inline styles

## Files Modified

- `app/frontend/static/app.js` (7 changes)
- `app/frontend/static/register.js` (2 changes)
- `app/frontend/static/evaluations.js` (2 changes)
- `app/frontend/static/app.css` (8 changes)

## Verification

```bash
# Verify extractErrorMessage is defined in all three JS files
grep -n "extractErrorMessage" app/frontend/static/*.js

# Verify CSS variable usage
grep -n "var(--topbar-h)" app/frontend/static/app.css

# Verify no hardcoded 70px remains (except in root definition)
grep -n "70px" app/frontend/static/app.css
```

## Notes

- All fixes are backward-compatible
- No API contract changes
- No database schema changes
- Pure frontend refinement
