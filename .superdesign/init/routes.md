# Routes

Flow Studio is a Vite single-page application without React Router.

| URL | Entry | Layout |
| --- | --- | --- |
| `/` | `frontend/src/main.tsx` → `App` | `studio-shell` with left StudioMenu, central VersionCanvas, Perception/AI Behavior floats, Solution Space rail, and IntentComposer |

Vite entry is `frontend/index.html`, which mounts `frontend/src/main.tsx` into `#root`.

