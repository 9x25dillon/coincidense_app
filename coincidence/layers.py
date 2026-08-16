"""The Layer type.

A layer is a set of located observations plus the provenance that travels with them.
Tier is not decoration — `docs/EVIDENCE_STANDARDS.md` requires it to survive ingest,
analysis, and render, so it lives on the object rather than in a sidecar note.
"""

from __future__ import annotations

from dataclasses import dataclass, field

TIERS = {
    "A": "instrumented or authoritative",
    "B": "derived or secondary",
    "C": "asserted, no open dataset",
    "D": "uncertain provenance (quarantine only)",
}


@dataclass
class Layer:
    """Located observations with provenance.

    points: (lon, lat) in degrees.
    weights: per-point weight. Counts by default.
    """

    name: str
    points: list[tuple[float, float]] = field(default_factory=list)
    weights: list[float] = field(default_factory=list)
    # Per feature, its polygon geometry in (lon, lat), or None where the feature is a
    # point. Aligned with `points`, which keeps a representative coordinate for every
    # feature either way so extent, projection and the point path all still work.
    shapes: list | None = None
    tier: str = "D"
    custodian: str | None = None
    source_path: str | None = None
    confounds: list[str] = field(default_factory=list)
    notes: str | None = None
    dropped_rows: int = 0

    def __post_init__(self) -> None:
        if self.tier not in TIERS:
            raise ValueError(f"unknown tier {self.tier!r}; expected one of {sorted(TIERS)}")
        if not self.weights:
            self.weights = [1.0] * len(self.points)
        if len(self.weights) != len(self.points):
            raise ValueError(
                f"layer {self.name!r}: {len(self.points)} points but "
                f"{len(self.weights)} weights"
            )

    def __len__(self) -> int:
        return len(self.points)

    @property
    def has_areas(self) -> bool:
        return bool(self.shapes) and any(s for s in self.shapes)

    def outline_points(self) -> list[tuple[float, float]]:
        """Every vertex the layer occupies, for extent and window purposes.

        A polygon's representative point says nothing about how far the polygon
        reaches, so a grid or a hull built from centroids alone can be smaller than the
        data it is supposed to contain.
        """
        if not self.has_areas:
            return list(self.points)
        out = list(self.points)
        for shape in self.shapes or []:
            if shape:
                out.extend(v for polygon in shape for ring in polygon for v in ring)
        return out

    @property
    def lons(self) -> list[float]:
        return [p[0] for p in self.points]

    @property
    def lats(self) -> list[float]:
        return [p[1] for p in self.points]

    @property
    def total_weight(self) -> float:
        return sum(self.weights)

    def provenance(self) -> dict:
        """Everything a reader needs to judge the layer. Emitted into every result
        bundle so a shared analysis carries its own evidence standard."""
        return {
            "name": self.name,
            "tier": self.tier,
            "tier_meaning": TIERS[self.tier],
            "custodian": self.custodian,
            "source_path": self.source_path,
            "n_points": len(self.points),
            "total_weight": self.total_weight,
            "n_areal_features": sum(1 for s in (self.shapes or []) if s),
            "declared_confounds": list(self.confounds),
            "dropped_rows": self.dropped_rows,
            "notes": self.notes,
        }


def tier_rank(tier: str) -> int:
    return "ABCD".index(tier)


def lowest_tier(layers: list[Layer]) -> str:
    """A conclusion is only as auditable as its weakest input."""
    return max((l.tier for l in layers), key=tier_rank) if layers else "D"
