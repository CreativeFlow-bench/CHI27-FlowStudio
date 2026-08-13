"""Case report rendering and index helpers (refactor plan P2)."""

from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.services.divergence.cross_domain import _prompt_chip_evidence_rows

from app.models import Candidate, CaseRecord, SessionRecord

_STORE: Any = None
_FILES_ROOT: Any = None


def configure_cases(*, studio_store: Any, files_root: Any) -> None:
    global _STORE, _FILES_ROOT
    _STORE = studio_store
    _FILES_ROOT = files_root


def render_case_report(
    case: CaseRecord,
    stage: StageState,
    session_metadata: dict[str, object],
    asset: object,
    accepted_candidates: list[object],
) -> str:
    asset_label = getattr(asset, "label", case.asset_id)
    mesh_url = getattr(asset, "mesh_url", None) or getattr(asset, "obj_url", None) or ""
    rows = "\n".join(
        "<tr>"
        f"<td>{escape(getattr(candidate, 'candidate_id', ''))}</td>"
        f"<td>{escape(getattr(candidate, 'label', ''))}</td>"
        f"<td>{_preview_cell(str(getattr(candidate, 'thumbnail_url', '') or ''))}</td>"
        f"<td>{escape(str(getattr(candidate, 'mesh_url', '') or ''))}</td>"
        f"<td>{escape(str(getattr(candidate, 'obj_url', '') or ''))}</td>"
        "</tr>"
        for candidate in accepted_candidates
    )
    if not rows:
        rows = '<tr><td colspan="5">No accepted candidates were attached.</td></tr>'
    memory_rows = _direction_memory_rows(session_metadata)
    pipeline_rows = _pipeline_evidence_rows(accepted_candidates)
    prompt_chip_rows = _prompt_chip_evidence_rows(accepted_candidates)
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{escape(case.title)}</title>
    <style>
      body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 36px; color: #172033; line-height: 1.5; }}
      main {{ max-width: 880px; }}
      h1 {{ margin-bottom: 4px; }}
      section {{ border-top: 1px solid #d7e0eb; padding-top: 18px; margin-top: 18px; }}
      dl {{ display: grid; grid-template-columns: 160px 1fr; gap: 8px 14px; }}
      dt {{ color: #5f6f82; }}
      dd {{ margin: 0; overflow-wrap: anywhere; }}
      table {{ width: 100%; border-collapse: collapse; }}
      th, td {{ border: 1px solid #d7e0eb; padding: 8px; text-align: left; vertical-align: top; }}
      th {{ background: #f3f6fa; }}
      .preview-img {{ display: block; max-width: 180px; max-height: 130px; object-fit: contain; border: 1px solid #d7e0eb; background: #f8fafc; margin-bottom: 6px; }}
      a {{ color: #1d5fd3; overflow-wrap: anywhere; }}
    </style>
  </head>
  <body>
    <main>
      <h1>{escape(case.title)}</h1>
      <p>Saved FlowStudio case: {escape(case.case_id)}</p>
      <section>
        <h2>Design State</h2>
        <dl>
          <dt>Session</dt><dd>{escape(case.session_id)}</dd>
          <dt>Asset</dt><dd>{escape(case.asset_id)} - {escape(asset_label)}</dd>
          <dt>Mesh</dt><dd>{escape(mesh_url)}</dd>
          <dt>Phase</dt><dd>{escape(stage.phase.value)}</dd>
          <dt>Goal</dt><dd>{escape(stage.current_goal or "")}</dd>
        </dl>
      </section>
      <section>
        <h2>Direction Memory</h2>
        <table>
          <thead><tr><th>Candidate</th><th>Stage</th><th>Commit</th><th>Label</th></tr></thead>
          <tbody>{memory_rows}</tbody>
        </table>
      </section>
      <section>
        <h2>Accepted Candidates</h2>
        <table>
          <thead><tr><th>ID</th><th>Label</th><th>Preview</th><th>Mesh</th><th>OBJ</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </section>
      <section>
        <h2>Pipeline Evidence</h2>
        <table>
          <thead><tr><th>Candidate</th><th>Remote Job</th><th>Stage</th><th>Direction</th><th>Preview</th><th>Socket</th><th>Result</th></tr></thead>
          <tbody>{pipeline_rows}</tbody>
        </table>
      </section>
      <section>
        <h2>Prompt Chip Evidence</h2>
        <table>
          <thead><tr><th>Candidate</th><th>Mode</th><th>Selected Tokens</th><th>Source Directions</th><th>Final Prompt</th></tr></thead>
          <tbody>{prompt_chip_rows}</tbody>
        </table>
      </section>
      <section>
        <h2>Notes</h2>
        <p>{escape(case.notes or "")}</p>
      </section>
    </main>
  </body>
</html>
"""


def write_case_index(cases_root: Path, cases: object) -> None:
    cases_root.mkdir(parents=True, exist_ok=True)
    rows_by_id = {
        str(row["case_id"]): row
        for row in _read_existing_case_index_rows(cases_root / "index.json")
        if row.get("case_id")
    }
    current_rows = [
        {
            "case_id": case.case_id,
            "session_id": case.session_id,
            "title": case.title,
            "asset_id": case.asset_id,
            "report_url": case.report_url,
            "case_url": case.metadata.get("case_url"),
            "accepted_candidate_ids": case.accepted_candidate_ids,
            "created_at": case.created_at.isoformat(),
        }
        for case in cases
    ]
    rows_by_id.update({str(row["case_id"]): row for row in current_rows})
    rows = list(rows_by_id.values())
    rows.sort(key=lambda item: str(item["created_at"]), reverse=True)
    (cases_root / "index.json").write_text(
        json.dumps(
            {
                "schema_version": "flowstudio.case_index.v1",
                "cases": rows,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _direction_memory_rows(session_metadata: dict[str, object]) -> str:
    memory = session_metadata.get("candidate_memory")
    if not isinstance(memory, dict):
        return '<tr><td colspan="4">No direction memory was recorded.</td></tr>'
    accepted = memory.get("accepted")
    if not isinstance(accepted, list) or not accepted:
        return '<tr><td colspan="4">No direction memory was recorded.</td></tr>'
    rows = []
    for item in accepted:
        if not isinstance(item, dict):
            continue
        rows.append(
            "<tr>"
            f"<td>{escape(str(item.get('candidate_id') or ''))}</td>"
            f"<td>{escape(str(item.get('stage') or ''))}</td>"
            f"<td>{escape(str(item.get('commit_policy') or ''))}</td>"
            f"<td>{escape(str(item.get('label') or ''))}</td>"
            "</tr>"
        )
    return "\n".join(rows) or '<tr><td colspan="4">No direction memory was recorded.</td></tr>'


def _case_direction_memory(session_metadata: dict[str, object]) -> dict[str, object]:
    memory = session_metadata.get("candidate_memory")
    return memory if isinstance(memory, dict) else {}


def _read_existing_case_index_rows(index_path: Path) -> list[dict[str, object]]:
    if not index_path.exists():
        return []
    try:
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    rows = payload.get("cases") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _preview_cell(url: str) -> str:
    if not url:
        return ""
    safe = escape(url)
    return f'<img class="preview-img" src="{safe}" alt="candidate preview" /><a href="{safe}">{safe}</a>'


def _pipeline_evidence_rows(candidates: list[object]) -> str:
    rows = []
    for candidate in candidates:
        metadata = getattr(candidate, "metadata", {})
        evidence = metadata.get("pipeline_evidence") if isinstance(metadata, dict) else None
        if not isinstance(evidence, dict):
            evidence = {}
        socket = _socket_evidence_label(evidence)
        rows.append(
            "<tr>"
            f"<td>{escape(getattr(candidate, 'candidate_id', ''))}</td>"
            f"<td>{escape(_evidence_value(evidence, metadata, 'remote_job_id'))}</td>"
            f"<td>{escape(_evidence_value(evidence, metadata, 'stage'))}</td>"
            f"<td>{escape(_evidence_value(evidence, metadata, 'direction_id'))}</td>"
            f"<td>{_preview_cell(_evidence_value(evidence, metadata, 'remote_image_url'))}</td>"
            f"<td>{escape(socket)}</td>"
            f"<td>{escape(_evidence_value(evidence, metadata, 'result_path', 'remote_result_path'))}</td>"
            "</tr>"
        )
    return "\n".join(rows) or '<tr><td colspan="7">No pipeline evidence was recorded.</td></tr>'


def _socket_evidence_label(evidence: dict[str, object]) -> str:
    source_part = evidence.get("source_part_id") or evidence.get("target_part_id")
    face_count = evidence.get("socket_face_count")
    if source_part and face_count:
        return f"{source_part} / {face_count} faces"
    if source_part:
        return str(source_part)
    if face_count:
        return f"{face_count} faces"
    return ""


def _evidence_value(
    evidence: dict[str, object],
    metadata: object,
    key: str,
    metadata_key: str | None = None,
) -> str:
    value = evidence.get(key)
    if value is None and isinstance(metadata, dict):
        value = metadata.get(metadata_key or key)
    return str(value or "")
