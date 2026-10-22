# Project log

A running record of the Heatmap project: each meeting with Henry, the work
ben does between meetings, and the action items from both.

- Page: https://claude.ai/artifact/9FPHDWSUeXCvZXuD4u4w62 (private to ben until he shares it)
- Plan for keeping it: https://claude.ai/artifact/464SGvpBZCdQ2qQzFwwEJb
- Data: `log/log.json` (meetings, work and actions, written by Claude).
  Runs come straight from `data/runs.jsonl`, so they need no entries.

```
python3 tools/projectlog.py check    # validate log.json
python3 tools/projectlog.py build    # write log/index.html, then publish it to the page URL
```

## The routine

1. **After a meeting.** ben pastes a transcript or a few bullets and says
   "log this meeting". Claude adds a `meeting` entry (`discussed`, `decided`,
   `built`), adds or closes actions, rebuilds and republishes.
2. **Between meetings.** A thread that finishes a piece of work adds one
   `work` entry for it (title, summary, 2 to 4 `items`, `links`) and turns
   anything waiting on ben or Henry into an action.
3. **Before the next meeting.** ben says "prep for Henry". Claude fills any
   gaps and gives an agenda: what changed since the last meeting, open
   actions by owner, decisions waiting on Henry.

## Entry fields

- Every entry: `id` (`m1`, `m2`… for meetings, `w1`, `w2`… for work),
  `kind` (`meeting` or `work`), `title`, `start` and `end` (UTC ISO
  times), `summary`, `links` (`[{label, url}]`), and `runs` (ids of runs
  to show inside this entry instead of on their own).
- Meetings add `with`, `discussed`, `decided`, `built` and an optional
  `time_note`. Work adds `by` and `items`.
- Actions: `id` (`a1`…), `owner` (ben, Henry or Claude), `from` (an entry
  id), `raised`, `status` (open, done or dropped), `done` when closed,
  optional `due` and `note`.

An entry belongs to the chapter of the last meeting that started before it
ended. Nothing confidential goes in: the same rule as the Heatmap page.
