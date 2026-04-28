# Range & React 04/27 UI + Logic Update

This package contains the current clean project with the 04/27 UI revisions and follow-up polish pass applied.

## UI updates applied

- Standardized native dropdown/select styling globally so caret icons are centered and consistently spaced.
- Removed the duplicate filter caret issue on the Results page.
- Added a coach/admin member selector to the Results page so coaches review selected organization member results instead of their own results.
- Reworked the hand debrief page into a cleaner, more concise coaching-style review:
  - top score cards for Overall, Villain Ranging, and Action Prediction
  - clear Final Truth panel
  - separate Ranging and Action Response sections
  - compact street rows instead of noisy raw detail blocks
  - removed model-output clutter from the main visual flow
- Updated the Coach analytics tab:
  - fixed trend chart x-axis labels to a capped, dynamic tick set
  - removed the low-value individual-results section
  - replaced separate help/excelling lists with one Member focus scrollbox ordered by lowest combined score
  - member rows link directly to that member's filtered Results page
- Updated the Coach assignments tab:
  - Active coach assignments now render in a fixed-size scrollbox
  - rows show assignment name, member, progress, status, and due date
  - active assignments are ordered by due date ascending
- Updated the Coach members tab:
  - Members, pending invites, and recent audit activity use consistent fixed-size scrollboxes
  - pending invites hide consumed links and are ordered by expiration
  - member rows focus on name, role, email, org, and allowed maintenance actions
  - admin tools now use minimal divider-based expandable sections with a standard dropdown icon
- Changed dashboard Account and Coach stat badges to filled orange CTA styling where requested.
- Changed Assignments quick-start links to filled orange CTA buttons.
- Made Privacy, Terms, and Status page section labels stand out more clearly.

## Logic fixes applied

- Fixed postflop street advancement randomness so turn/river runouts are based on the saved hand seed plus current hand state, not a constant route-level seed.
- Removed the fixed frontend preflop scenario seed so stack generation is not locked to the same values.
- Updated preflop stack generation:
  - hero stack is randomly sampled and weighted toward roughly 250-400bb, clamped above 100bb
  - villain stack is randomly sampled from 75-600bb with weighting by villain archetype
- Updated postflop response matrix behavior:
  - the W/win response pill now uses the green call tone
  - matrix selections reset for a new response node even when the same buckets appear again
  - OOP workflow order displays as Fill Matrix -> Take Action -> Prune Range
  - OOP matrix selections persist while pruning the current instance
- Expanded safe coach-side member maintenance so coaches can maintain member accounts in their org while backend restrictions prevent coach/admin escalation.

## Branding cleanup

- Cleaned remaining user-facing legacy product naming references and kept Range & React / R&R consistently visible.
- Kept the internal `VRT_` environment-variable prefix unchanged to avoid breaking existing Railway/Vercel configuration and deployment scripts.

## Validation performed

- Backend Python source files were syntax-checked with direct compilation.
- Deprecated user-facing naming grep passed after excluding generated/dependency folders.
- Frontend dependencies installed successfully in the sandbox.
- Full Next.js production build started but could not complete in this sandbox because the environment repeatedly timed out during Next's build/file-tracing phase. Please run `npm run build` locally before pushing.
