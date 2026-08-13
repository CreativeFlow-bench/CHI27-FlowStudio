# Product requirements

## Goal

Validate whether spatial operations plus language help 3D designers express, inspect and refine design intent more effectively than prompt-only generation.

## Primary user

A 3D designer exploring form directions during early ideation. The MVP assumes desktop use with mouse or trackpad.

## P0 — first testable release

- Create, open, rename and autosave a project
- Upload GLB/GLTF and view a real model
- Navigate, select a part/region and leave brush marks
- Record spatial operations and camera events
- Request an intent inference
- Edit, confirm or dismiss an inferred intent
- Combine confirmed intents into one editable statement
- Generate or mock two-axis direction keywords
- Generate or mock four direction references
- Create a child version from a direction
- Navigate and branch the version tree
- Switch English/Chinese without losing project state
- Show loading, empty, error and retry states

## P1

- OBJ/STL/FBX conversion
- Real Pull, Smooth and Add mesh editing
- Multiple version references with part annotations
- Undo/redo
- Direction-history archive
- Export generated models

## P2

- Real text/image-to-3D generation
- Collaboration and comments
- Permissions and shared projects
- Mobile/tablet adaptation

## Non-goals for P0

- Full DCC replacement
- Production-quality topology editing
- Real-time multi-user collaboration
- Training a new 3D foundation model

## Success signals

- A user can complete the full loop without facilitator intervention.
- The user can explain why a suggested intent appeared.
- A branch is visibly traceable to its source version and confirmed intents.
- Refresh or language switching does not lose work.

