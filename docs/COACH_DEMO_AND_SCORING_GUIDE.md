# Coach Demo and Scoring Guide

This guide is written for coaches, members, and pitch walkthroughs. It avoids model language and explains what Range & React is measuring in plain English.

## Demo Flow

1. Start on `/demo`.
2. Log in as the owner to show the platform view, organization setup, and demo workspace.
3. Switch to the coach account and open `/admin`.
4. Walk through the coach command center: cohort completion, struggling members, weakest scenarios, weakest villains, overdue work, next actions, and sample reporting.
5. Download the member results CSV to show how an organization can review the whole roster outside the app.
6. Switch to a member and open `/dashboard`.
7. Show recent reps, trendline, assigned work, and the next recommended drill.
8. Open `/guide` whenever someone asks how the scores are calculated.

## Range Score

Range Score measures whether the member kept the real villain hand, bucket, and hand family alive while narrowing the range.

High Range Score means:

- The real hand was not removed too early.
- The correct bucket stayed plausible.
- The correct subgroup stayed plausible.
- The member still trimmed enough unlikely hands to make the range useful.

Example: villain actually has a set. If the member keeps sets alive after a flop check-call and turn bet, they get credit. If they remove all sets after the flop action, the score falls because the real answer was no longer possible.

## Action Score

Action Score measures whether the member predicted how villain's current range would respond to hero's action.

High Action Score means:

- The member understood how each bucket reacts.
- The member accounted for opponent type.
- The member picked the correct response for the actual bucket.

Example: hero bets small into a calling-station opponent. If the actual hand is a flush draw and the member marks that bucket as call, they get credit. If they mark fold, the score falls.

## Overall Score

Overall Score is the average of Range Score and Action Score.

Example: a member scores 82 on Range Score and 64 on Action Score. Overall Score is 73. Coaches should still look at the split because the useful coaching note is that Action Score is lagging behind range work.

## Why Opponent Type Matters

Opponent type is intentionally central. The same board and action can mean different things from a nit, calling station, loose regular, or maniac.

Coach use case:

- If members miss against maniacs, assign pressure and response drills.
- If members miss against calling stations, assign overcall and value-heavy continuation drills.
- If members miss against nits, assign under-bluff and value-heavy aggression drills.

## Coach Command Center

The command center answers six questions:

- Are cohorts completing their work?
- Which members are struggling?
- Which scenarios are weakest?
- Which opponents are weakest?
- Which assignments are overdue?
- What should the coach do next?

This lets a coach move from data to action quickly.

## Member Growth View

The member dashboard answers four questions:

- What did I do recently?
- Am I trending up or down?
- What did my coach assign?
- What should I drill next?

## CSV Export

The member results CSV gives one row per member with:

- Current Range Score
- Current Action Score
- Current Overall Score
- Worst Opponent
- Reps completed
- Active assignments
- Completed assignments
- Overdue assignments
- Organization membership

This is useful for coaching calls, weekly accountability, and external organization reporting.
