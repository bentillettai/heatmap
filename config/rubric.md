# Scoring rubric

This is the instruction the daily run follows when it judges items and
ranks opportunities. Change it in plain English; the next run uses it.

## Who it is for

Henry leads the thermal management roadmap in the Engineering Design team
at the Manufacturing Technology Centre (MTC), a UK research and technology
organisation. He wants to know where a problem, a thermal management
technology and an MTC capability overlap, and which organisations to talk
to. Small companies are often more interesting than large ones.

MTC capabilities: additive manufacture (the big one), laser processes,
robotics, metrology and inspection, modelling and simulation, design for
manufacture.

## Step 1: thermal gate

Drop an item unless thermal management is central to it: heat transfer,
heat exchangers, cooling, heat rejection or recovery, thermal materials or
thermal modelling. Power-electronics, motor or EV news with no thermal
content fails the gate even if it mentions efficiency.

## Step 2: map to the grid

For each item record:

- **area**: datacentre, aerospace, motorsport, or other
- **problem**: the challenge it addresses (societal or industrial)
- **technology**: the thermal technology or method
- **capabilities**: which MTC capabilities it touches
- **applicability**: `stated` if the item itself makes the link to the
  problem, `inferred` if you are making it. Inferred is allowed and often
  valuable (a modelling method for complex channels applies to cold
  plates even if the paper never says so), but say why in one sentence.
- **organisations**: who does it, funds it, or has the problem, with type
  and country.

## Step 3: group into opportunities

An opportunity is one problem + technology pairing. Several items can
support one card. The same story syndicated across sites counts once:
merge it and keep every link as a source.

## Step 4: score each opportunity, 0 to 5 per criterion

| Criterion | Weight | Scores high when |
| --- | --- | --- |
| venn_fit | 30 | Problem, thermal technology and an MTC capability are all clearly present |
| manufacturing_key | 20 | The advance depends on how the part is made or designed |
| evidence | 15 | Measured results or a working prototype, not marketing claims |
| novelty | 15 | Emerging, or an existing technology newly applied; cross-area transfer counts |
| uk_relevance | 10 | A UK organisation, UK problem, or UK funding |
| contactable | 10 | A named organisation that could plausibly be approached |

Overall score = weighted sum, scaled to 0 to 100.

Rank low however well written: one-off repair or sourcing stories,
product launches with no technical change, generic market-size reports,
and opinion pieces with no new facts (they can still support a card as
context).

## Judgement first

The calibration set in `examples/calibration.csv` is a loose sanity check,
not a target. Use your own judgement about what Henry would find most
interesting, then let `config/preferences.md` and Henry's feedback steer.
