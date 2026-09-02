"""Solver adaptör arayüzü (CLAUDE.md kural 1)."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class InputArtifact:
    """Solver girdisi: tek dosya (.inp) veya klasör (OpenFOAM case)."""

    path: Path
    kind: str = "file"  # file | directory


@dataclass
class JobHandle:
    job_id: str
    work_dir: Path
    artifact: InputArtifact


@dataclass
class JobStatus:
    state: str  # pending | running | done | failed
    message: str = ""
    exit_code: int | None = None


@dataclass
class ResultSet:
    scalars: dict[str, float] = field(default_factory=dict)
    curves: dict[str, Any] = field(default_factory=dict)
    raw_result_path: Path | None = None
    # Frontend'in mesh önizlemesiyle aynı node sırasına hizalı, düğüm bazlı
    # sonuç dizilerini (von Mises, deplasman büyüklüğü) içeren JSON dosyası.
    results_preview_path: Path | None = None


class SolverError(Exception):
    """Solver girdi/çalıştırma hatası."""


class SolverAdapter(ABC):
    @abstractmethod
    def build_input(self, params: dict[str, Any]) -> InputArtifact:
        """Parametrelerden solver girdisi üretir."""

    @abstractmethod
    def submit(self, artifact: InputArtifact) -> JobHandle:
        """Solver'ı çalıştırır (senkron subprocess kabul)."""

    @abstractmethod
    def poll_status(self, job: JobHandle) -> JobStatus:
        """Job durumu."""

    @abstractmethod
    def parse_results(self, job: JobHandle) -> ResultSet:
        """Sonuç dosyasından metrikler."""
