# Interaction specification

## Global flow

`MARK → INTENT → DIVERGE → DIRECTION → BUILD`

Users may return to an earlier version at any time. Reviewing a version always activates Navigate mode.

## Canvas

- Double-click empty canvas: open source-geometry picker.
- Drag: rotate active model in Navigate mode; manipulate the selected tool in operation modes.
- Wheel/pinch: zoom around pointer.
- Space + drag: pan.
- Fit all: frame every version.
- Focus: frame active version.

## Tools

- Navigate: view only; no intent evidence is added.
- Select: identify object, surface or part.
- Brush: add a model-space region mark.
- Sketch: add a model-space directional stroke.
- Pull: record direction and magnitude; P0 may preview/mock deformation.
- Smooth: record affected region and strength; P0 may preview/mock deformation.
- Add: attach a primitive; P0 may preview/mock deformation.

Marks are stored in model space, follow rotation and hide on the rear surface.

## Intent lifecycle

States: `INFERRING → STATED → CONFIRMED`.

- A live inference accumulates compatible evidence.
- Confirm locks the intent.
- Further operations create a new live intent.
- Reframe makes the text editable and requests a replacement.
- Dismiss removes the live intent but retains raw events for audit.
- Confidence and supporting evidence are visible.

## Divergence

- Diverge is disabled until at least one intent is confirmed.
- Confirmed intents are synthesized into one editable combined statement.
- Conflicts must be named, not averaged away.
- Direction terms are grouped on two axes:
  - Aesthetic: material and finish
  - Structural: form operation
- Selecting terms enables reference generation.

## Direction and build

- Return four references per request.
- A user selects one reference to create a child version.
- New depth grows right; siblings grow downward.
- Rebuilding from an older node creates a branch and never overwrites descendants.

## Layout invariants

- Floating cards must avoid models, fixed panels and other cards.
- Model scale is derived from remaining safe space.
- Loading UI says what is being computed.
- Interactive elements have visible hover/focus states.
- Below 1180 px, show the wide-window requirement.

## Localization

- Language changes presentation only, not identifiers or saved data.
- English and Chinese use the same interaction structure.
- Chinese serif headings use upright type.

