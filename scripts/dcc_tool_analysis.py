#!/usr/bin/env python3
"""Clean the DCC geometry-tool table, draft coding, summarize, and plot a Sankey."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Iterable, Sequence

import pandas as pd

try:
    import plotly.graph_objects as go
except ModuleNotFoundError as exc:
    raise SystemExit(
        "缺少 Plotly。请先运行：python -m pip install pandas plotly"
    ) from exc


REQUIRED_COLUMNS = [
    "工具类别",
    "几何层级",
    "几何效果",
    "代表性内置工具",
    "创意应用场景",
    "对应的操作语义",
    "ai是否有类似工具可以用（通过mcp或者算法模拟）",
]

OUTPUT_COLUMNS = [
    "software",
    "native_tool",
    "operation_family",
    "geometry_level",
    "geometry_effect",
    "creative_scenario",
    "operation_semantics",
    "ai_available",
    "semantic_replaceability",
    "spatial_agency",
    "system_decision",
    "frontend_primitive",
    "backend_action",
    "coding_note",
]

SOFTWARE_ALIASES = {
    "blender": "Blender",
    "maya": "Maya",
    "3ds max": "3ds Max",
    "3dsmax": "3ds Max",
    "cinema 4d": "Cinema 4D",
    "c4d": "Cinema 4D",
    "zbrush": "ZBrush",
    "nomad sculpt": "Nomad Sculpt",
    "nomad": "Nomad Sculpt",
    "houdini": "Houdini",
}


def discover_csv(explicit_path: str | Path | None = None) -> Path:
    """Find the most likely DCC geometry-tool CSV without modifying it."""
    if explicit_path:
        path = Path(explicit_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"指定的 CSV 不存在：{path}")
        return path

    cwd = Path.cwd()
    search_roots = [
        cwd,
        cwd / "upload",
        cwd / "uploads",
        Path("/mnt/data"),
        Path.home() / "Downloads",
    ]
    candidates: list[Path] = []
    for root in search_roots:
        if not root.is_dir():
            continue
        candidates.extend(path for path in root.glob("*.csv") if path.is_file())
        if root in {cwd / "upload", cwd / "uploads", Path("/mnt/data")}:
            candidates.extend(path for path in root.rglob("*.csv") if path.is_file())

    candidates = list(dict.fromkeys(path.resolve() for path in candidates))
    if not candidates:
        raise FileNotFoundError(
            "未在当前目录、upload/uploads、/mnt/data 或 Downloads 找到 CSV。"
        )

    def score(path: Path) -> tuple[int, float]:
        name = path.name.lower()
        value = 0
        if "dcc几何工具清单" in name:
            value += 200
        if "dcc" in name:
            value += 50
        if "几何工具" in name:
            value += 50
        if "coding" in name:
            value += 10
        return value, path.stat().st_mtime

    return max(candidates, key=score)


def read_csv_robust(path: Path) -> tuple[pd.DataFrame, str]:
    """Read common Chinese CSV encodings and report the source preview."""
    errors: list[str] = []
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            frame = pd.read_csv(path, encoding=encoding)
            print(f"读取文件：{path}")
            print(f"编码：{encoding}")
            print(f"shape: {frame.shape}")
            print(f"columns: {list(frame.columns)}")
            print("前 5 行：")
            print(frame.head(5).to_string(index=False))
            return frame, encoding
        except UnicodeDecodeError as exc:
            errors.append(f"{encoding}: {exc}")
    raise UnicodeError("CSV 编码识别失败；尝试结果：\n" + "\n".join(errors))


def clean_source_table(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Strip header edges and remove columns that contain no meaningful values."""
    cleaned = frame.copy()
    cleaned.columns = [str(column).strip() for column in cleaned.columns]
    cleaned = cleaned.replace(r"^\s*$", pd.NA, regex=True)

    removed = [
        column for column in cleaned.columns if cleaned[column].isna().all()
    ]
    cleaned = cleaned.drop(columns=removed)

    icon_columns = [column for column in cleaned.columns if "Icon截图" in column]
    empty_icons = [
        column for column in icon_columns if cleaned[column].isna().all()
    ]
    if empty_icons:
        cleaned = cleaned.drop(columns=empty_icons)
        removed.extend(column for column in empty_icons if column not in removed)

    print(f"删除的全空列：{removed}")
    print(f"清洗后 shape: {cleaned.shape}")
    print(f"清洗后 columns: {list(cleaned.columns)}")
    return cleaned, removed


def validate_required_columns(frame: pd.DataFrame) -> None:
    """Require exact Chinese headers after removing only outer whitespace."""
    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        print(f"当前列名：{list(frame.columns)}")
        raise ValueError(
            "缺少必要中文列（需精确匹配）："
            + "、".join(missing)
            + "。请检查表头拼写、全半角标点或隐藏空格。"
        )


def canonical_software(value: str) -> str | None:
    key = re.sub(r"\s+", " ", value.strip()).lower()
    return SOFTWARE_ALIASES.get(key)


def split_native_tools(value: object) -> list[tuple[str, str]]:
    """Split software-prefixed tool entries; retain every unparseable fragment."""
    if pd.isna(value):
        return [("Unparsed", "")]

    raw = str(value).strip()
    if not raw:
        return [("Unparsed", raw)]

    fragments = [
        fragment.strip()
        for fragment in re.split(r"[；;\n\r]+", raw)
        if fragment.strip()
    ]
    parsed: list[tuple[str, str]] = []
    for fragment in fragments:
        match = re.match(r"^\s*([^：:]+?)\s*[：:]\s*(.*)$", fragment)
        if not match:
            parsed.append(("Unparsed", fragment))
            continue
        software = canonical_software(match.group(1))
        if software is None:
            parsed.append(("Unparsed", fragment))
        else:
            parsed.append((software, match.group(2).strip()))
    return parsed or [("Unparsed", raw)]


def text_or_empty(value: object) -> str:
    return "" if pd.isna(value) else str(value).strip()


def make_tidy(frame: pd.DataFrame) -> pd.DataFrame:
    """Expand each source row into one software/native-tool record per fragment."""
    rows: list[dict[str, str]] = []
    for _, source in frame.iterrows():
        for software, native_tool in split_native_tools(source["代表性内置工具"]):
            rows.append(
                {
                    "software": software,
                    "native_tool": native_tool,
                    "operation_family": text_or_empty(source["工具类别"]),
                    "geometry_level": text_or_empty(source["几何层级"]),
                    "geometry_effect": text_or_empty(source["几何效果"]),
                    "creative_scenario": text_or_empty(source["创意应用场景"]),
                    "operation_semantics": text_or_empty(
                        source["对应的操作语义"]
                    ),
                    "ai_available": text_or_empty(
                        source[
                            "ai是否有类似工具可以用（通过mcp或者算法模拟）"
                        ]
                    ),
                }
            )
    return pd.DataFrame(rows)


def compact_label(value: str) -> str:
    return re.sub(r"[\s／/]+", "/", value.strip())


def classify_system_decision(row: pd.Series) -> tuple[str, str, str]:
    """Apply the requested draft coding rubric with exact-family precedence."""
    family = compact_label(row["operation_family"])

    preserve = {
        compact_label(value)
        for value in [
            "组件变换",
            "弯曲 / 扭转 / 锥化",
            "晶格 / 软选择变形",
            "雕刻抓取 / 移动",
            "雕刻膨胀 / 收紧 / 刻痕",
            "遮罩 / 隐藏 / 保护区域 / 权重绘制",
            "刀切 / 切片 / 平面切割",
        ]
    }
    hybrid_add = {
        compact_label(value)
        for value in [
            "挤出",
            "雕刻黏土 / 堆体积",
            "扫掠 / 放样 / 蒙皮",
            "桥接 / 补面 / 封口",
        ]
    }
    hybrid_smooth = {
        compact_label(value)
        for value in [
            "雕刻平滑 / 压平 / 放松",
            "细分 / 平滑 / 重构网格",
        ]
    }
    semanticize = {
        compact_label(value)
        for value in [
            "基础体创建",
            "曲线 / 样条绘制",
            "倒角 / 切角",
            "环切 / 连接边",
            "内插 / 内缩",
            "镜像 / 对称",
            "阵列 / 重复复制",
            "车削 / 旋转成形",
            "布尔运算",
            "吸附 / 对齐 / 约束",
        ]
    }
    delegate = {
        compact_label(value)
        for value in [
            "合并 / 焊接 / 溶解",
            "重拓扑",
            "投射 / 贴合 / 收缩包裹",
            "实体化 /蒙皮等",
        ]
    }

    if family in preserve:
        return (
            "Preserve",
            "Drag",
            "None",
        )
    if family in hybrid_add:
        return (
            "Hybrid",
            "Add",
            "Hybrid Backend",
        )
    if family in hybrid_smooth:
        return (
            "Hybrid",
            "Smooth",
            "Hybrid Backend",
        )
    if family in semanticize:
        return (
            "Semanticize",
            "None",
            "Semanticized Backend",
        )
    if family in delegate:
        return (
            "Delegate",
            "None",
            "Delegated Backend",
        )

    combined = " ".join(
        [
            row["operation_family"],
            row["geometry_effect"],
            row["operation_semantics"],
            row["ai_available"],
        ]
    )
    if re.search(r"轨迹|力度|方向|停止点|拖拽|笔触|局部位置|空间定位", combined):
        return "Preserve", "Drag", "None"
    if re.search(r"新增|生长|体积|挤出|连接|补面|封口|放样|扫掠", combined):
        return "Hybrid", "Add", "Hybrid Backend"
    if re.search(r"平滑|压平|放松|消去局部变化", combined):
        return "Hybrid", "Smooth", "Hybrid Backend"
    if re.search(r"拓扑|优化|清理|修复|转换|模拟|贴合", combined):
        return "Delegate", "None", "Delegated Backend"
    if re.search(r"语义|约束|描述|目标", combined):
        return "Semanticize", "None", "Semanticized Backend"
    return "Hybrid", "None", "Hybrid Backend"


def draft_code(row: pd.Series) -> dict[str, str]:
    decision, primitive, backend = classify_system_decision(row)
    ai_text = row["ai_available"].strip()
    ai_signal = "有" if ai_text == "有" else "无" if ai_text == "无" else "未知"

    if decision == "Preserve":
        replaceability, agency = "Low", "High"
        rationale = "依赖局部空间位置、方向或连续操作，优先保留人的空间控制。"
    elif decision == "Hybrid" and primitive == "Add":
        replaceability, agency = "Medium", "Medium"
        rationale = "涉及局部新增或连接，用户指定区域，后端完成几何执行。"
    elif decision == "Hybrid" and primitive == "Smooth":
        replaceability, agency = "Medium", "Medium"
        rationale = "涉及局部平滑或重构，保留直觉调节并结合后端处理。"
    elif decision == "Semanticize":
        replaceability = "High" if ai_signal == "有" else "Medium"
        agency = "Low"
        rationale = "可用目标、约束或语义指令表达，不必复现具体手势轨迹。"
    elif decision == "Delegate":
        replaceability = "High" if ai_signal == "有" else "Medium"
        agency = "Low"
        rationale = "偏技术执行、表示转换、贴合或拓扑处理，适合后端代理。"
    else:
        replaceability, agency = "Medium", "Medium"
        rationale = "未命中明确规则，暂按混合协作处理，需人工复核。"

    if row["operation_family"] == "细分 / 平滑 / 重构网格":
        rationale += " 该混合类别同时含技术重构语义，建议逐项复核。"

    return {
        "semantic_replaceability": replaceability,
        "spatial_agency": agency,
        "system_decision": decision,
        "frontend_primitive": primitive,
        "backend_action": backend,
        "coding_note": f"{rationale} AI可用性原始标记={ai_signal}；本结果仅为draft coding。",
    }


def add_draft_coding(tidy: pd.DataFrame) -> pd.DataFrame:
    coding = pd.DataFrame(
        [draft_code(row) for _, row in tidy.iterrows()],
        index=tidy.index,
    )
    review = pd.concat([tidy, coding], axis=1)
    return review[OUTPUT_COLUMNS]


def count_rows(
    group: str,
    counts: pd.Series,
    denominator: int | None = None,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for item, count in counts.items():
        rows.append(
            {
                "metric_group": group,
                "item": item,
                "count": int(count),
                "proportion": (
                    float(count) / denominator if denominator else pd.NA
                ),
            }
        )
    return rows


def build_statistics(
    source: pd.DataFrame, review: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, pd.Series | int]]:
    total_entries = len(review)
    total_families = source["工具类别"].nunique(dropna=True)
    software = review["software"].value_counts()
    family = review["operation_family"].value_counts()
    decision = review["system_decision"].value_counts()
    primitive = review["frontend_primitive"].value_counts()

    rows: list[dict[str, object]] = [
        {
            "metric_group": "headline",
            "item": "total_operation_families",
            "count": int(total_families),
            "proportion": pd.NA,
        },
        {
            "metric_group": "headline",
            "item": "total_software_tool_entries",
            "count": int(total_entries),
            "proportion": pd.NA,
        },
    ]
    rows.extend(count_rows("software", software))
    rows.extend(count_rows("operation_family", family))
    rows.extend(count_rows("system_decision", decision, total_entries))
    rows.extend(count_rows("frontend_primitive", primitive))

    summary = pd.DataFrame(rows)
    detail: dict[str, pd.Series | int] = {
        "total_families": total_families,
        "total_entries": total_entries,
        "software": software,
        "family": family,
        "decision": decision,
        "primitive": primitive,
    }
    return summary, detail


def markdown_table(counts: pd.Series, denominator: int | None = None) -> str:
    lines = ["| 项目 | 数量 | 比例 |", "|---|---:|---:|"]
    for item, count in counts.items():
        proportion = (
            f"{count / denominator:.1%}" if denominator else "—"
        )
        safe_item = str(item).replace("|", "\\|")
        lines.append(f"| {safe_item} | {int(count)} | {proportion} |")
    return "\n".join(lines)


def write_statistics_markdown(
    path: Path, source_path: Path, detail: dict[str, pd.Series | int]
) -> None:
    decision = detail["decision"]
    assert isinstance(decision, pd.Series)
    total_entries = int(detail["total_entries"])
    content = f"""# DCC Geometry Tool Draft Coding Statistics

- 源文件：`{source_path}`
- 原始工具类别数量：**{int(detail["total_families"])}**
- 拆分后的 software-tool 条目数量：**{total_entries}**
- 统计口径：software、operation family、decision 与 primitive 均按拆分后的 software-tool 条目计数。
- 标注状态：以下为自动生成的 **draft coding**，必须经过人工审阅后才能作为最终研究编码。
- 解释边界：Drag / Add / Smooth 不是“新手势”，而是从 DCC 工具分析中筛选出的、在 AI-native 3D ideation 中仍值得保留的代表性直觉操作。

## 每个 software 的工具数量

{markdown_table(detail["software"])}

## 每个 operation_family 的数量

{markdown_table(detail["family"])}

## 每个 system_decision 的数量与比例

{markdown_table(decision, total_entries)}

## Frontend Primitive 数量

{markdown_table(detail["primitive"])}

## Semanticize / Delegate / Hybrid / Preserve 比例

{markdown_table(decision.reindex(["Semanticize", "Delegate", "Hybrid", "Preserve"], fill_value=0), total_entries)}
"""
    path.write_text(content, encoding="utf-8")


def terminal_node(row: pd.Series) -> str:
    primitive = row["frontend_primitive"]
    if primitive == "Drag":
        return "Preserve: Drag"
    if primitive == "Add":
        return "Hybrid/Preserve: Add"
    if primitive == "Smooth":
        return "Hybrid/Preserve: Smooth"
    if row["system_decision"] == "Semanticize":
        return "Semanticized Backend"
    if row["system_decision"] == "Delegate":
        return "Delegated Backend"
    if row["backend_action"] == "Hybrid Backend":
        return "Hybrid Backend"
    return "No retained primitive/backend"


def aggregate_edges(
    rows: Iterable[tuple[str, str]]
) -> list[tuple[str, str, int]]:
    counts: dict[tuple[str, str], int] = {}
    for source, target in rows:
        counts[(source, target)] = counts.get((source, target), 0) + 1
    return [
        (source, target, count)
        for (source, target), count in counts.items()
    ]


def build_sankey(
    review: pd.DataFrame,
    output_path: Path,
    image_path: Path | None = None,
) -> None:
    chart = review.copy()
    chart["terminal"] = chart.apply(terminal_node, axis=1)

    stages: Sequence[tuple[str, str, str]] = [
        ("software", "software", "#BFD7EA"),
        ("family", "operation_family", "#D7C6E8"),
        ("decision", "system_decision", "#F3C58B"),
        ("terminal", "terminal", "#C7CDD3"),
    ]
    node_ids: list[str] = []
    labels: list[str] = []
    colors: list[str] = []
    for stage, column, color in stages:
        for value in chart[column].drop_duplicates():
            node_ids.append(f"{stage}::{value}")
            labels.append(str(value))
            if stage == "terminal" and value in {
                "Preserve: Drag",
                "Hybrid/Preserve: Add",
                "Hybrid/Preserve: Smooth",
            }:
                colors.append("#A8D5BA")
            else:
                colors.append(color)
    node_index = {node_id: index for index, node_id in enumerate(node_ids)}

    first = aggregate_edges(
        (
            f"software::{row.software}",
            f"family::{row.operation_family}",
        )
        for row in chart.itertuples()
    )
    second = aggregate_edges(
        (
            f"family::{row.operation_family}",
            f"decision::{row.system_decision}",
        )
        for row in chart.itertuples()
    )
    third = aggregate_edges(
        (
            f"decision::{row.system_decision}",
            f"terminal::{row.terminal}",
        )
        for row in chart.itertuples()
    )
    edges = first + second + third

    link_colors = (
        ["rgba(126, 170, 205, 0.28)"] * len(first)
        + ["rgba(163, 131, 190, 0.28)"] * len(second)
        + [
            (
                "rgba(101, 161, 122, 0.32)"
                if edge[1]
                in {
                    "terminal::Preserve: Drag",
                    "terminal::Hybrid/Preserve: Add",
                    "terminal::Hybrid/Preserve: Smooth",
                }
                else "rgba(136, 143, 151, 0.28)"
            )
            for edge in third
        ]
    )

    figure = go.Figure(
        go.Sankey(
            arrangement="snap",
            valueformat=",d",
            node={
                "pad": 13,
                "thickness": 18,
                "line": {"color": "rgba(60, 66, 72, 0.45)", "width": 0.6},
                "label": labels,
                "color": colors,
                "hovertemplate": "%{label}<br>条目数：%{value}<extra></extra>",
            },
            link={
                "source": [node_index[source] for source, _, _ in edges],
                "target": [node_index[target] for _, target, _ in edges],
                "value": [count for _, _, count in edges],
                "color": link_colors,
                "hovertemplate": (
                    "%{source.label} → %{target.label}"
                    "<br>条目数：%{value}<extra></extra>"
                ),
            },
        )
    )
    figure.update_layout(
        title={
            "text": (
                "DCC Geometry Tools: Software → Operation Family → "
                "System Decision → Retained Primitive / Backend"
                "<br><sup>Automated draft coding; software-tool entry counts; "
                "requires human review</sup>"
            ),
            "x": 0.02,
            "xanchor": "left",
            "font": {"size": 21, "color": "#252A31"},
        },
        width=1600,
        height=max(940, 30 * chart["operation_family"].nunique()),
        margin={"l": 30, "r": 30, "t": 100, "b": 30},
        paper_bgcolor="white",
        plot_bgcolor="white",
        font={
            "family": "Arial, Noto Sans CJK SC, Microsoft YaHei, sans-serif",
            "size": 12,
            "color": "#30343B",
        },
    )
    figure.write_html(
        output_path,
        include_plotlyjs=True,
        full_html=True,
        config={
            "displaylogo": False,
            "responsive": True,
            "toImageButtonOptions": {
                "format": "png",
                "filename": "dcc_tool_sankey",
                "scale": 2,
            },
        },
    )
    if image_path is not None:
        figure.write_image(
            image_path,
            format="png",
            width=1600,
            height=max(940, 30 * chart["operation_family"].nunique()),
            scale=2,
        )


def run_pipeline(input_path: Path, output_dir: Path) -> list[Path]:
    source, _ = read_csv_robust(input_path)
    cleaned, _ = clean_source_table(source)
    validate_required_columns(cleaned)

    tidy = make_tidy(cleaned)
    review = add_draft_coding(tidy)
    output_dir.mkdir(parents=True, exist_ok=True)

    review_path = (output_dir / "dcc_tool_mapping_review.csv").resolve()
    summary_path = (output_dir / "dcc_tool_summary.csv").resolve()
    statistics_path = (output_dir / "dcc_tool_statistics.md").resolve()
    sankey_path = (output_dir / "dcc_tool_sankey.html").resolve()
    sankey_image_path = (output_dir / "dcc_tool_sankey.png").resolve()

    review.to_csv(review_path, index=False, encoding="utf-8-sig")
    summary, detail = build_statistics(cleaned, review)
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    write_statistics_markdown(statistics_path, input_path, detail)
    build_sankey(review, sankey_path, sankey_image_path)

    print(f"\n总工具类别数量：{detail['total_families']}")
    print(f"拆分后的 software-tool 条目数量：{detail['total_entries']}")
    print("\n每个 software 的工具数量：")
    print(detail["software"].to_string())
    print("\n每个 operation_family 的数量：")
    print(detail["family"].to_string())
    print("\n每个 system_decision 的数量：")
    print(detail["decision"].to_string())
    print("\nDrag / Add / Smooth / None 的数量：")
    print(detail["primitive"].reindex(["Drag", "Add", "Smooth", "None"], fill_value=0).to_string())
    print("\nSemanticize / Delegate / Hybrid / Preserve 的比例：")
    decision = detail["decision"].reindex(
        ["Semanticize", "Delegate", "Hybrid", "Preserve"], fill_value=0
    )
    print((decision / int(detail["total_entries"])).map(lambda value: f"{value:.1%}").to_string())

    outputs = [
        review_path,
        summary_path,
        statistics_path,
        sankey_path,
        sankey_image_path,
    ]
    print("\n生成文件（绝对路径）：")
    for path in outputs:
        print(path)
    return outputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        help="可选；不提供时自动寻找最可能的 DCC 几何工具 CSV。",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path.cwd() / "outputs" / "dcc_tool_analysis",
        help="输出目录；默认：./outputs/dcc_tool_analysis",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = discover_csv(args.input)
    run_pipeline(input_path, args.output_dir.expanduser().resolve())


if __name__ == "__main__":
    main()
