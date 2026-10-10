import re

from app.schemas import ArchitecturePlan


def _escape_label(value: str) -> str:
    value = re.sub(r"[\r\n]+", " ", value).strip()
    return value.replace('"', "'").replace("[", "(").replace("]", ")")


def architecture_to_mermaid(plan: ArchitecturePlan) -> str:
    lines = ["flowchart TD"]

    for component in plan.components:
        label = _escape_label(f"{component.name}<br/>{component.technology}")
        lines.append(f'    {component.id}["{label}"]')

    for edge in plan.connections:
        if edge.label:
            label = _escape_label(edge.label)
            lines.append(f"    {edge.source} -->|{label}| {edge.target}")
        else:
            lines.append(f"    {edge.source} --> {edge.target}")

    return "\n".join(lines)
