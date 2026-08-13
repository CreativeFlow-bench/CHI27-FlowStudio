# Flow Studio — Development Handoff

Start here. This package turns the bilingual interaction prototype into an implementable MVP specification.

## Product

Flow Studio is an intent-driven 3D iteration workspace:

`Import → Mark/Operate → Infer Intent → Confirm → Diverge → Select Direction → Generate Version`

The user communicates design intent through spatial operations, camera behaviour and optional text. Confirmed intents are combined into a solution space; selected directions create branches in a version tree.

## Recommended MVP boundary

Build for real:

- Project creation and persistence
- GLB/GLTF/OBJ upload and 3D viewing
- Navigate, Select and Brush interactions
- Operation/event logging
- Create, edit, confirm and dismiss intents
- Combined intent and direction keywords
- Version tree, branching and autosave
- English/Chinese language switching

Use a mock or adapter in the first milestone:

- AI intent inference
- Direction reference generation
- New 3D geometry generation
- Pull, Smooth and Add mesh deformation

This boundary produces a testable product without making the first release depend on a production 3D generation model.

## Package map

- `01-Prototype/` — runnable English and Chinese reference prototypes
- `02-Product-Spec/` — scope, interaction rules and acceptance criteria
- `03-API-Spec/` — OpenAPI contract, data model and mock data
- `04-Content/` — source-of-truth bilingual UI strings
- `05-Assets/` — placeholders for production fonts, icons and sample models
- `06-References/CLAUDE.md` — original implementation notes and invariants

## Source-of-truth order

When files disagree, use this order:

1. `02-Product-Spec/acceptance-criteria.md`
2. `02-Product-Spec/interaction-spec.md`
3. `03-API-Spec/api-contract.yaml`
4. English prototype
5. Chinese prototype

## Engineering notes

- The prototype is a single-file simulation, not production architecture.
- Upload currently creates placeholder geometry from a filename.
- Intent inference and generation are simulated in the browser.
- Google Fonts are loaded remotely.
- The experience is desktop-first and requires at least 1180 px width.
- Keep the collision avoidance, version-tree layout and model-space mark behaviour documented in `06-References/CLAUDE.md`.

## Definition of ready

Before implementation starts, product, front-end and back-end owners should confirm:

- Which AI/3D generation provider will be used, if any
- Supported upload formats and maximum file size
- Authentication requirements
- Project retention and privacy requirements
- Whether mocked generation is acceptable for the first user test

