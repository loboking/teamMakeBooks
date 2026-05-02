"""Persona YAML 로더."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Persona:
    id: str
    name: str
    genre: str
    style: str
    tone: str
    favorite_tropes: list[str] = field(default_factory=list)
    avoid: list[str] = field(default_factory=list)
    sample_passages: list[str] = field(default_factory=list)
    model_override: str | None = None


def load_persona(persona_id: str, authors_dir: Path) -> Persona:
    data = yaml.safe_load((authors_dir / f"{persona_id}.yaml").read_text(encoding="utf-8"))
    return Persona(
        id=str(data["id"]),
        name=str(data["name"]),
        genre=str(data["genre"]),
        style=str(data["style"]),
        tone=str(data["tone"]),
        favorite_tropes=list(data.get("favorite_tropes") or []),
        avoid=list(data.get("avoid") or []),
        sample_passages=list(data.get("sample_passages") or []),
        model_override=data.get("model"),
    )
