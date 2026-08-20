# Navigation View Switching — 2026-08-11

## Problem

The sidebar navigation had **five items** that all pointed to the same page:

- **概览 / 知识库 / 文档任务 / AI 对话** were anchor links (`#workspaceOverview`, `#knowledgePanel`, etc.) on the same page
- **知识库 and AI 对话** sat side-by-side in a 2-column grid, so both were already visible on wide screens — clicking either scrolled a few pixels or not at all
- **文档任务** was nested *inside* 知识库, so two nav items pointed to the same region
- **Active state** was hardcoded to 概览 in HTML and never updated, so clicking anything left the highlight unchanged

Result: **Five nav items, but only two real destinations.** Clicking felt broken.

## Solution

Converted the workspace into **true view switching** — each nav item now shows a distinct full-width panel.

### Architecture

1. **Four sibling views** replace the old 2-column `workspace-grid`:
   - **概览** — Entry cards that route into the other views (new)
   - **知识库** — Collection selector, create form, upload queue
   - **文档任务** — Document list and detail panel (extracted from 知识库)
   - **AI 对话** — Chat interface (unchanged)

2. **View state** tracked in `state.activeView`, synced to URL hash for deep-linking
3. **Nav buttons** update `aria-pressed` and `.active` class
4. **Entry cards** in 概览 are shortcuts to the other views
5. **Live badge** on 文档任务 shows pending count without opening the view

### Files Changed

#### `app/frontend/index.html`

- Split `workspace-grid` into `.workspace-views` container with four `.workspace-view[data-view-panel]` siblings
- Extracted `#documentsWorkspace` from inside `#knowledgePanel` so each is independent
- Added `.view-overview` with four `.entry-card` shortcuts
- Changed nav items from `<a href="#...">` to `<button data-view="...">` with `aria-pressed`
- Added `<span id="navDocumentsBadge" class="nav-badge hidden">0</span>` to 文档任务 nav item
- Added `<p id="documentsViewContext">` under 文档任务 heading
- Wrapped 概览 description in `<p id="workspaceViewCopy">` so it updates per view
- Added refresh button `#refreshDocumentsViewButton` to documents view

#### `app/frontend/evaluations.html`

- Nav now has three links back to workspace views (`/`, `/#knowledge`, `/#documents`) with external-link icon
- Current page (RAG 评估) uses `<span class="nav-item active" aria-current="page">` instead of a dead anchor

#### `app/frontend/static/app.css`

**View switching:**
```css
.workspace-views { display: block; }
.workspace-view { display: none; }
.workspace-view.is-active { display: block; }
```

**Nav buttons:**
- Changed `.nav-item` from flex-inline to `width: 100%` button
- Added `.nav-badge` (pill with pending count)
- Added `.nav-external` (icon for page-load links)
- Active state now uses `aria-pressed` instead of hardcoded class

**Entry cards:**
- `.entry-grid` — auto-fit grid for overview cards
- `.entry-card` — surface with icon, heading, description, "前往 →" label
- `.entry-icon` — 34×34 rounded square with accent soft bg

**Layout:**
- Removed `.workspace-grid` (2-column)
- Added `.documents-grid` (queue + list, 0.9fr / 1.6fr)
- Responsive: 1320px breakpoint stacks `.documents-grid` to 1 column

**Cleanup:**
- Replaced scroll-margin selector list with `.workspace-view` class
- Removed stale anchor ids (`#knowledgePanel`, `#documentsWorkspace`, etc.)

#### `app/frontend/static/app.js`

**State:**
```js
state.activeView = "overview"
```

**Elements:**
```js
elements.workspaceViewCopy
elements.documentsViewContext
elements.navDocumentsBadge
elements.refreshDocumentsViewButton
elements.navItems  // Array<button[data-view]>
elements.viewPanels  // Array<section[data-view-panel]>
```

**Functions:**
- `setActiveView(view, {focusPanel})` — Show one view, update nav active state, sync URL hash
- `readViewFromHash()` — Parse `location.hash`, tolerate legacy anchor ids
- `viewCopy` — Per-view description strings

**Event listeners:**
- Nav buttons: `click` → `setActiveView()`
- Entry cards: `click` → `setActiveView()`
- Document list: `click` → switch to documents view if not already there
- `window.hashchange` → read hash and switch view
- Refresh documents button

**Bootstrap:**
- `setActiveView(readViewFromHash() || "overview")` at startup

**Summary render:**
- `renderWorkspaceSummary()` now updates `navDocumentsBadge` and `documentsViewContext`

### Behavior

**On load:**
- Reads URL hash (`#knowledge`, `#documents`, `#chat`) and shows that view
- Falls back to 概览 if no hash
- Tolerates old anchor ids (`#knowledgePanel`, `#chatPanel`) for existing links

**Navigation:**
- Clicking a nav button shows that view and updates the hash
- Back/forward navigate between views via `hashchange` listener
- Entry cards in 概览 route to views the same way
- Opening a document detail auto-switches to documents view

**Live feedback:**
- Badge on 文档任务 shows pending count (hidden when zero)
- Context line under 文档任务 heading shows `"知识库名 · N 份文档"`
- Description under "知识工作台" updates per view

## Verification

Run these commands to check the changes:

```bash
# Validate HTML structure
cd app/frontend
python -c "
from html.parser import HTMLParser
VOID={'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr','path','svg','circle','rect','line','polyline','polygon','ellipse'}
class P(HTMLParser):
    def __init__(s):
        super().__init__(convert_charrefs=True); s.stack=[]; s.errs=[]
    def handle_starttag(s,t,a):
        if t not in VOID: s.stack.append((t,s.getpos()[0]))
    def handle_endtag(s,t):
        if t in VOID: return
        if not s.stack: s.errs.append(f'stray </{t}> line {s.getpos()[0]}'); return
        if s.stack[-1][0]!=t:
            s.errs.append(f'mismatch: </{t}> at {s.getpos()[0]} but open <{s.stack[-1][0]}> from {s.stack[-1][1]}')
        else: s.stack.pop()
for f in ['index.html','evaluations.html','register.html']:
    p=P(); p.feed(open(f,encoding='utf-8').read())
    print(f'{f:<20}', 'OK' if not p.errs and not p.stack else (p.errs or f'unclosed: {p.stack}'))
"

# Check JS syntax
cd static
node --check app.js && node --check evaluations.js && echo "JS syntax OK"
```

## Testing Checklist

**View switching:**
- [ ] Click each nav item — panel changes, active state updates
- [ ] URL hash updates when switching views
- [ ] Browser back/forward navigate between views
- [ ] Reload with `#knowledge` / `#documents` / `#chat` hash lands in that view

**概览 entry cards:**
- [ ] Click 知识库配置 → knowledge view
- [ ] Click 文档任务 → documents view
- [ ] Click AI 对话 → chat view
- [ ] Click RAG 评估 → navigates to `/evaluations` (page load)

**Live state:**
- [ ] Upload a file → badge appears on 文档任务 with count
- [ ] Wait for indexing to finish → badge disappears
- [ ] Switch to documents view → context line shows `"知识库名 · N 份文档"`

**Evaluations page:**
- [ ] Nav shows three workspace links with external icon
- [ ] RAG 评估 nav item is `<span>` with `aria-current="page"`, not clickable

**Responsive:**
- [ ] Wide screen: entry-grid shows 3 cards per row
- [ ] 1320px: documents-grid stacks to 1 column
- [ ] 760px: nav items still readable

## Rollback

If something breaks:

```bash
git diff HEAD app/frontend/index.html app/frontend/evaluations.html app/frontend/static/app.{css,js}
git checkout HEAD -- app/frontend/
```

Then downgrade version refs:
```bash
cd app/frontend
sed -i 's/?v=20260811\.[0-9]*/?v=20260811.3/g' index.html evaluations.html register.html
```

## Design Notes

The entry cards follow the existing design system:
- **Surface ladder:** `var(--surface)` base, `var(--surface-subtle)` on hover
- **Accent soft:** Icon well uses `var(--accent-soft)` bg, `var(--accent-ink)` stroke
- **Border:** `var(--line)` default, `#aeb5f0` (accent-tinted) on hover
- **Typography:** `var(--font-display)` for card titles, tight tracking
- **Spacing:** 18px card padding, 8px internal gap (aligns with existing rhythm)
- **Geometry:** `var(--radius-lg)` on cards, `var(--radius)` on icon wells

Icons are 18×18px stroked SVGs at 1.65px weight — matching the nav icon density.
