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
                                          ├──► opportunity cards (cards.json)
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
- **Learn.** Thumbs, comments and notes on the page are stored in the page's
  database. The next run reads them, adjusts scores and searches, and once a
  week writes what it learnt as plain-English rules in `config/preferences.md`.

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
| `data/feedback.jsonl`, `data/notes.jsonl` | Feedback and notes copied from the page |
| `data/runs.jsonl` | One line per run |
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
- This runs on ben's Claude account, outside MTC systems. Bringing it inside MTC
  would need a locally hosted model and recorded data provenance.
