# Range & React 04/27 UI + Logic Update

This package contains the targeted replacement files and a clean full project copy for the latest Range & React update.

## UI updates applied

- Standardized native dropdown/select styling globally so caret icons are centered and consistently spaced.
- Added additional small-screen responsive guardrails for shared layouts, public hero sections, cards, nav/button widths, and content grids.
- Reworked the hand debrief page into a cleaner, more concise coaching-style review:
  - top score cards for Overall, Villain Ranging, and Action Prediction
  - clear Final Truth panel
  - separate Ranging and Action Response sections
  - compact street rows instead of noisy raw detail blocks
  - removed model-output clutter from the main visual flow
- Improved Results filter grid responsiveness and dropdown caret alignment.
- Improved Coach/Admin Members tab readability:
  - cleaner member account cards
  - clearer invite cards
  - stronger Admin Tools presentation
  - orange filled CTA buttons for create/link/save actions
  - responsive columns
- Added a coach-facing individual member performance snapshot to the Analytics tab.
- Changed Assignments "Quick start" links to filled orange CTA buttons.
- Made Privacy, Terms, and Status page section labels stand out more clearly.

## Logic fixes applied

- Fixed postflop street advancement randomness so turn/river runouts are based on the saved hand seed plus current hand state, not a constant route-level seed. This prevents repeated turn cards across hands.
- Removed the fixed `seed: 1` from the preflop scenario setup request so stack generation is not locked to the same values.
- Updated preflop stack generation:
  - hero stack is randomly sampled and weighted toward ~250–400bb, clamped above 100bb
  - villain stack is randomly sampled from 75–600bb with weighting by villain archetype

## Branding cleanup

- Replaced user-facing legacy product names such as "Villain Range Trainer", "Live Range Lab", and "LRL" with Range & React / R&R.
- Kept the internal `VRT_` environment-variable prefix unchanged to avoid breaking existing Railway/Vercel configuration and deployment scripts.

## Validation performed

- Backend Python syntax compilation passed for `api/`.
- Legacy user-facing naming grep passed for precise deprecated strings.
- Full Next.js build was not completed in this sandbox because dependency folders were intentionally excluded from the clean project package.
