# Heatmap

A daily horizon scan for MTC's thermal management roadmap. It looks for
places where three things overlap:

1. a real problem, ideally a UK one (data-centre energy, aircraft emissions,
   racing regulations),
2. a thermal management technology, emerging or newly applied, and
3. an MTC capability: additive manufacture, laser processes, robotics,
   metrology and inspection, modelling and simulation, design for manufacture,

and names the organisations worth talking to. Small companies count as much
as large ones.

V1 covers three areas: data-centre cooling, aerospace heat exchangers
(precoolers and oil coolers in commercial turbofans) and motorsport thermal
management. Thermal items outside those still get a card, tagged Other.

The output is a private Claude page:
https://claude.ai/artifact/WCo5GAu4ZQpZQ6N8rTSYVS

## How it works

```
web search ──► read pages ──► thermal gate ──► items.jsonl
                                                   │
         feedback + notes from the page ──┐        ▼
           └──► learned facts ────────────┤──► opportunity cards (cards.json)
         rubric + preferences ────────────┘        │
                                                   ▼
                                     check (score, rank) ──► build ──► page
```

- **Collect.** Each morning a scheduled Claude session runs the steps in
  `CLAUDE.md`. It searches with the queries in `config/areas.yaml`, plus leads
  from Henry's feedback and notes, and reads new pages.
- **Gate.** Anything where thermal management isn't central is dropped but
  remembered, so it isn't read again.
- **Judge.** Claude groups items into opportunities (one problem and technology
  pairing each), maps them to the grid, and scores each from 0 to 5 on six
  criteria in `config/rubric.md`. It records whether the source itself links the
  technology to the problem ("stated") or Claude made the link ("inferred").
- **Rank and build.** `tools/heatmap.py check` turns scores into a 0 to 100 rank;
  `build` writes the page.
- **Learn.** Thumbs and comments on cards, comments on whole runs, and notes
  are stored in the page's database. Each run reads them first. It makes small
  changes itself (scores, searches, plain-English rules in
  `config/preferences.md`) and proposes bigger ones (weights, the gate, areas)
  for ben or Henry to approve on the page.
- **Remember.** Facts people teach it in comments ("this can't be sold in the
  UK because of an EU rule", "that company was bought last year") are distilled
  into `data/knowledge.jsonl`, one plain sentence each, tagged by card,
  organisation, technology, capability or area, with the comment and person it
  came from. Every run reads them before scoring, applies them to the cards they
  touch (and to new cards later), and says in its notes which fact changed
  what. Facts are replaced or retired, never deleted, so git keeps the history.
  Preferences are taste; knowledge is about the world.
- **Keep.** Every run is logged in `data/runs.jsonl` and its report is frozen
  in `data/runs/`, so the Runs tab can show any earlier run with its feedback.
  `tools/heatmap.py stats` counts the up and down votes each run's cards got,
  which is the simplest check that the report is getting better.

## Files

| Path | What it is |
| --- | --- |
| `CLAUDE.md` | The daily-run instructions Claude follows |
| `config/rubric.md` | How items are gated and opportunities scored |
| `config/preferences.md` | Rules learnt from Henry's ratings and feedback |
| `config/areas.yaml` | The application areas and their search queries |
| `config/sources.yaml` | Sites worth checking, by status |
| `config/taxonomy.yaml` | Capability, application and keyword lists |
| `examples/calibration.csv` | Henry's first ten rated articles |
| `data/items.jsonl` | Every article read, with summary, orgs and gate result |
| `data/cards.json` | The opportunity cards and run metadata |
| `data/feedback.jsonl`, `data/run_feedback.jsonl`, `data/comments.jsonl`, `data/notes.jsonl` | Votes, comments and notes copied from the page |
| `data/knowledge.jsonl` | Facts and constraints learned from comments, with their sources |
| `data/runs.jsonl` | One line per run, with what feedback changed |
| `data/runs/` | Each run's frozen report, published as `runs/<id>.json` |
| `data/inbox/` | Each run's raw batch of new items |
| `site/template.html` | The page; `build` fills in the data |
| `tools/heatmap.py` | Standard-library Python helper |

## Changing it

Most changes are plain English, no code:

- Add or drop a search query, or add an area: `config/areas.yaml`.
- Change what counts as interesting: `config/rubric.md` or
  `config/preferences.md`.
- Change a weight: `config/rubric.md` and `WEIGHTS` in `tools/heatmap.py`.

To rebuild the page locally:

```
python3 tools/heatmap.py check
python3 tools/heatmap.py build      # writes site/index.html
python3 tools/heatmap.py stats
```

## Limits

- Public sources only, read through web search. Paywalled journals, LinkedIn
  and anything behind a login are out of reach.
- Scores are Claude's judgement, steered by feedback. They aren't measurements.
- Comments and the knowledge file live outside MTC systems, so they must stay
  non-confidential. A run won't record a comment that looks confidential, but
  that is a backstop, not a control; opening comments company-wide would need
  that said clearly on the page.
- One page version holds at most 511 files, so after about 500 runs the older
  frozen reports will need merging into fewer files.
- This runs on ben's Claude account, outside MTC systems. Bringing it inside MTC
  would need a locally hosted model and recorded data provenance.
