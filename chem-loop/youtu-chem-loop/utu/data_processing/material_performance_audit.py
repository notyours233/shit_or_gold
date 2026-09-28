"""Audit material-to-performance labels before building a GRPO dataset.

The current source package has two shapes:

* Fifteen established task directions store freshly extracted material objects,
  while their performance labels remain in the project's existing datasets.
* Four newly added directions store material objects and property extractions in
  the same JSONL record.

This module joins and classifies those records without modifying the sources.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from utu.data_processing.material_performance_quality import (
    AuditObservation,
    analyze_cross_record_observations,
    canonical_text,
    vague_material_name_reasons,
)

OLD_FILE_TASKS: dict[str, str] = {
    "batch_1__co2rr_1431.jsonl": "CO2RR",
    "batch_1__eor_76.jsonl": "EOR",
    "batch_1__her_2945.jsonl": "HER",
    "batch_1__hor_87.jsonl": "HOR",
    "batch_1__hzor_72.jsonl": "HZOR",
    "batch_1__o5h_59.jsonl": "O5H",
    "batch_1__oer_219.jsonl": "OER",
    "batch_1__orr_240.jsonl": "ORR",
    "batch_1__uor_92.jsonl": "UOR",
    "batch_2__Antiferromagnetism_1134.jsonl": "antiferromagnetism",
    "batch_2__Conductivity_1457.jsonl": "conductivity",
    "batch_2__Ferrimagnetism_66.jsonl": "ferrimagnetism",
    "batch_2__Ferromagnetism_835.jsonl": "ferromagnetism",
    "batch_2__Photothermal_conversion_efficiency_1516.jsonl": "photothermal_conversion_efficiency",
    "batch_2__Thermal_Conductivity_1245.jsonl": "thermal_conductivity",
}

NEW_FILE_TASKS: dict[str, str] = {
    "batch_3__光催化h2o2_1585.jsonl": "photocatalytic_h2o2",
    "batch_3__抑菌_2886.jsonl": "antibacterial",
    "batch_3__热电_1696.jsonl": "thermoelectric",
    "batch_3__糠醛加氢_461.jsonl": "furfural_hydrogenation",
}

MATERIAL_METRIC_KEYS: dict[str, str] = {
    "antiferromagnetism": "neel_temperature",
    "conductivity": "conductivity",
    "ferrimagnetism": "saturation_magnetization",
    "ferromagnetism": "saturation_magnetization",
    "photothermal_conversion_efficiency": "photothermal_conversion_efficiency",
    "thermal_conductivity": "thermal_conductivity",
}

CHROMA_TASK_ALIASES: dict[str, str] = {
    "co2rr": "CO2RR",
    "eor": "EOR",
    "her": "HER",
    "hor": "HOR",
    "hzor": "HZOR",
    "o5h": "O5H",
    "oer": "OER",
    "orr": "ORR",
    "uor": "UOR",
    "antiferromagnetism": "antiferromagnetism",
    "conductivity": "conductivity",
    "ferrimagnetism": "ferrimagnetism",
    "ferromagnetism": "ferromagnetism",
    "photothermal conversion efficiency": "photothermal_conversion_efficiency",
    "thermal conductivity": "thermal_conductivity",
    "antibacterial": "antibacterial",
    "thermoelectric": "thermoelectric",
    "hydrogenation of furfural": "furfural_hydrogenation",
    "photocatalytic h2o2 production": "photocatalytic_h2o2",
}

GENERIC_MATERIAL_NAMES = {
    "",
    "-",
    "n/a",
    "na",
    "none",
    "not specified",
    "unknown",
    "unspecified",
    "material",
    "the material",
    "sample",
    "the sample",
    "catalyst",
    "the catalyst",
    "photocatalyst",
    "electrocatalyst",
    "composite",
    "nanocomposite",
    "nanoparticle",
    "nanoparticles",
}

ELEMENT_SYMBOLS = {
    "Ac",
    "Ag",
    "Al",
    "Am",
    "Ar",
    "As",
    "At",
    "Au",
    "B",
    "Ba",
    "Be",
    "Bh",
    "Bi",
    "Bk",
    "Br",
    "C",
    "Ca",
    "Cd",
    "Ce",
    "Cf",
    "Cl",
    "Cm",
    "Cn",
    "Co",
    "Cr",
    "Cs",
    "Cu",
    "Db",
    "Ds",
    "Dy",
    "Er",
    "Es",
    "Eu",
    "F",
    "Fe",
    "Fl",
    "Fm",
    "Fr",
    "Ga",
    "Gd",
    "Ge",
    "H",
    "He",
    "Hf",
    "Hg",
    "Ho",
    "Hs",
    "I",
    "In",
    "Ir",
    "K",
    "Kr",
    "La",
    "Li",
    "Lr",
    "Lu",
    "Lv",
    "Mc",
    "Md",
    "Mg",
    "Mn",
    "Mo",
    "Mt",
    "N",
    "Na",
    "Nb",
    "Nd",
    "Ne",
    "Nh",
    "Ni",
    "No",
    "Np",
    "O",
    "Og",
    "Os",
    "P",
    "Pa",
    "Pb",
    "Pd",
    "Pm",
    "Po",
    "Pr",
    "Pt",
    "Pu",
    "Ra",
    "Rb",
    "Re",
    "Rf",
    "Rg",
    "Rh",
    "Rn",
    "Ru",
    "S",
    "Sb",
    "Sc",
    "Se",
    "Sg",
    "Si",
    "Sm",
    "Sn",
    "Sr",
    "Ta",
    "Tb",
    "Tc",
    "Te",
    "Th",
    "Ti",
    "Tl",
    "Tm",
    "Ts",
    "U",
    "V",
    "W",
    "Xe",
    "Y",
    "Yb",
    "Zn",
    "Zr",
}

ELEMENT_NAME_ALIASES: dict[str, str] = {
    "aluminium": "Al",
    "aluminum": "Al",
    "antimony": "Sb",
    "arsenic": "As",
    "barium": "Ba",
    "bismuth": "Bi",
    "cadmium": "Cd",
    "calcium": "Ca",
    "cerium": "Ce",
    "chromium": "Cr",
    "cobalt": "Co",
    "copper": "Cu",
    "gallium": "Ga",
    "gold": "Au",
    "hafnium": "Hf",
    "indium": "In",
    "iridium": "Ir",
    "iron": "Fe",
    "lanthanum": "La",
    "lead": "Pb",
    "lithium": "Li",
    "magnesium": "Mg",
    "manganese": "Mn",
    "mercury": "Hg",
    "molybdenum": "Mo",
    "nickel": "Ni",
    "niobium": "Nb",
    "osmium": "Os",
    "palladium": "Pd",
    "platinum": "Pt",
    "potassium": "K",
    "rhenium": "Re",
    "rhodium": "Rh",
    "ruthenium": "Ru",
    "silver": "Ag",
    "sodium": "Na",
    "strontium": "Sr",
    "tantalum": "Ta",
    "tin": "Sn",
    "titanium": "Ti",
    "tungsten": "W",
    "vanadium": "V",
    "zinc": "Zn",
    "zirconium": "Zr",
}

_NUMERIC_RE = re.compile(
    r"^\s*(?P<comparator>>=|<=|>|<|~|≈|≥|≤)?\s*"
    r"(?P<value>[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)"
)
_DOI_PREFIX_RE = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi\s*:\s*)", re.IGNORECASE)
_FORMULA_SYMBOL_RE = re.compile(r"(?<![a-z])([A-Z][a-z]?)(?![a-z])")
_UNIT_SUFFIX_RE = re.compile(r"^\s*(?:>=|<=|>|<|~|≈|≥|≤)?\s*[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?\s*(.*)$")


@dataclass(frozen=True)
class NumericValue:
    value: float
    comparator: str
    raw: str


@dataclass(frozen=True)
class TruthTarget:
    task_type: str
    doi: str
    row_number: int | None
    metrics: Mapping[str, Any]
    units: Mapping[str, Any]
    metals: tuple[str, ...]
    product: str | None
    source_file: str | None = None
    source_index: int | None = None

    @property
    def context_key(self) -> tuple[str, str, tuple[str, ...]]:
        return self.task_type, self.product or "", tuple(sorted(self.metrics))

    @property
    def label_key(self) -> str:
        return json.dumps(dict(self.metrics), ensure_ascii=False, sort_keys=True)


def _numeric_metric_audit(metrics: Mapping[str, Any]) -> dict[str, int]:
    stats: Counter[str] = Counter()
    for raw_value in metrics.values():
        stats["truth_metric_values"] += 1
        parsed = parse_numeric(raw_value)
        if parsed is None:
            stats["unparseable_truth_metric_values"] += 1
            continue
        stats["parseable_truth_metric_values"] += 1
        if parsed.comparator:
            stats["truth_metric_values_with_comparator"] += 1
    return dict(stats)


def _unit_suffix(value: object) -> str:
    match = _UNIT_SUFFIX_RE.match(str(value or ""))
    return " ".join((match.group(1) if match else "").strip().split())


def _truth_unit_contract(task: str, metric_key: str, value: object, declared_unit: object = None) -> str:
    """Return a conservative unit/semantic contract for one established truth value."""
    declared = " ".join(str(declared_unit or "").strip().split())
    suffix = declared or _unit_suffix(value)
    compact = unicodedata.normalize("NFKC", suffix).casefold().replace(" ", "")
    if task == "HOR" and metric_key == "exchange_current_density":
        return "canonical" if compact in {"macm-2", "macm−2"} else "noncanonical_or_relative"
    expected_material_suffixes = {
        "antiferromagnetism": {"k"},
        "conductivity": {"scm-1", "s/cm", "sm-1", "s/m", "mscm-1", "ms/cm", "msm-1", "ms/m"},
        "ferrimagnetism": {"emu/g"},
        "ferromagnetism": {"emu/g"},
        "photothermal_conversion_efficiency": {"%"},
        "thermal_conductivity": {"wm-1k-1"},
    }
    expected = expected_material_suffixes.get(task)
    if expected is not None:
        return "canonical" if compact in expected else "noncanonical_or_missing"
    return "declared" if suffix or metric_key in {"faradaic_efficiency", "hmf_conversion", "fdca_yield"} else "missing"


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    """Yield JSON objects from a JSONL file and fail with a useful line number."""
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON in {path}:{line_number}: {exc}") from exc
            if isinstance(value, dict):
                yield value


def normalize_doi(value: object) -> str:
    """Normalize a DOI for conservative equality joins without inventing repairs."""
    text = unicodedata.normalize("NFKC", str(value or "")).strip().lower()
    text = _DOI_PREFIX_RE.sub("", text)
    text = text.strip().strip("*`\"'")
    return text.rstrip(".,; ")


def normalize_material_name(value: object) -> str:
    """Normalize a material name for exact and conservative substring matching."""
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    text = re.sub(r"[\s\-_/‐-―·⋅•@()[\]{}]+", "", text)
    return re.sub(r"[^0-9a-zα-ω一-鿿]+", "", text)


def is_generic_material_name(value: object) -> bool:
    text = " ".join(unicodedata.normalize("NFKC", str(value or "")).casefold().split())
    if text in GENERIC_MATERIAL_NAMES:
        return True
    return bool(re.fullmatch(r"(?:the\s+)?(?:prepared\s+|synthesized\s+)?(?:material|sample|catalyst)s?", text))


def parse_numeric(value: object) -> NumericValue | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return NumericValue(number, "", str(value)) if math.isfinite(number) else None
    raw = str(value).strip()
    match = _NUMERIC_RE.match(raw)
    if not match:
        return None
    number = float(match.group("value"))
    if not math.isfinite(number):
        return None
    return NumericValue(number, match.group("comparator") or "", raw)


def material_names(record: Mapping[str, Any]) -> list[str]:
    names: list[str] = []
    materials = record.get("final_materials")
    if not isinstance(materials, list):
        return names
    for material in materials:
        if isinstance(material, dict):
            names.append(str(material.get("material_name") or "").strip())
    return names


def infer_material_elements(material: Mapping[str, Any]) -> set[str]:
    """Infer element symbols conservatively from names plus explicit element lists."""
    explicit: list[Any] = []
    for key in ("metal_elements", "nonmetal_elements"):
        values = material.get(key)
        if isinstance(values, list):
            explicit.extend(values)

    text_parts = [str(material.get("material_name") or "")]
    components = material.get("components")
    if isinstance(components, list):
        for component in components:
            if not isinstance(component, dict):
                continue
            text_parts.append(str(component.get("component_name") or ""))
            for key in ("metal_elements", "nonmetal_elements"):
                values = component.get(key)
                if isinstance(values, list):
                    explicit.extend(values)

    elements = {str(value).strip() for value in explicit if str(value).strip() in ELEMENT_SYMBOLS}
    joined = " ".join(text_parts)
    elements.update(symbol for symbol in _FORMULA_SYMBOL_RE.findall(joined) if symbol in ELEMENT_SYMBOLS)
    lowered = joined.casefold()
    for name, symbol in ELEMENT_NAME_ALIASES.items():
        if re.search(rf"\b{re.escape(name)}\b", lowered):
            elements.add(symbol)
    return elements


def _deduplicate_truth_targets(targets: Sequence[TruthTarget]) -> tuple[list[TruthTarget], int, bool]:
    unique: list[TruthTarget] = []
    seen: set[tuple[tuple[str, str, tuple[str, ...]], str]] = set()
    values_by_context: dict[tuple[str, str, tuple[str, ...]], set[str]] = defaultdict(set)
    for target in targets:
        key = target.context_key, target.label_key
        values_by_context[target.context_key].add(target.label_key)
        if key not in seen:
            seen.add(key)
            unique.append(target)
    has_conflict = any(len(values) > 1 for values in values_by_context.values())
    return unique, len(targets) - len(unique), has_conflict


def _bind_truth_by_elements(
    materials: Sequence[Mapping[str, Any]], target: TruthTarget
) -> tuple[int | None, str | None]:
    target_elements = {symbol for symbol in target.metals if symbol in ELEMENT_SYMBOLS}
    if not target_elements:
        return None, None

    inferred = [infer_material_elements(material) for material in materials]
    exact = [index for index, symbols in enumerate(inferred) if symbols == target_elements]
    if len(exact) == 1:
        return exact[0], "unique_exact_element_match"
    superset = [index for index, symbols in enumerate(inferred) if target_elements.issubset(symbols)]
    if len(superset) == 1:
        return superset[0], "unique_element_subset_match"
    return None, None


def load_established_truth(
    reaction_dataset: Path, material_truth: Path
) -> tuple[
    dict[tuple[str, str], list[TruthTarget]],
    dict[tuple[str, str, int], list[TruthTarget]],
    Counter[str],
    dict[str, Any],
]:
    by_doi: dict[tuple[str, str], list[TruthTarget]] = defaultdict(list)
    by_row: dict[tuple[str, str, int], list[TruthTarget]] = defaultdict(list)
    counts: Counter[str] = Counter()
    metric_stats: dict[str, Counter[str]] = defaultdict(Counter)
    unit_contracts: dict[str, Counter[str]] = defaultdict(Counter)

    for sample in iter_jsonl(reaction_dataset):
        meta = sample.get("meta")
        if not isinstance(meta, dict):
            continue
        task = str(meta.get("reaction_type") or "").strip().upper()
        if task == "HZOR":
            task = "HZOR"
        doi = normalize_doi(meta.get("doc_id"))
        metrics = meta.get("metrics_gt")
        if not task or not doi or not isinstance(metrics, dict) or not metrics:
            continue
        metals_raw = meta.get("metals")
        metals = tuple(str(x).strip() for x in metals_raw) if isinstance(metals_raw, list) else ()
        product = str(meta.get("product") or "").strip() or None
        sample_units = meta.get("units") if isinstance(meta.get("units"), dict) else {}
        raw_source_index = meta.get("id")
        try:
            source_index = int(raw_source_index) if raw_source_index is not None else None
        except (TypeError, ValueError):
            source_index = None
        target = TruthTarget(
            task,
            doi,
            None,
            dict(metrics),
            dict(sample_units),
            metals,
            product,
            str(meta.get("source_file") or reaction_dataset.name),
            source_index,
        )
        by_doi[(task, doi)].append(target)
        counts[task] += 1
        for metric_key, raw_metric in metrics.items():
            metric_stats[task].update(_numeric_metric_audit({metric_key: raw_metric}))
            contract = _truth_unit_contract(task, metric_key, raw_metric, sample_units.get(metric_key))
            metric_stats[task][f"unit_contract_{contract}_values"] += 1
            unit_contracts[f"{task}/{metric_key}"][
                str(sample_units.get(metric_key) or _unit_suffix(raw_metric) or "<missing>")
            ] += 1

    for record in iter_jsonl(material_truth):
        task = str(record.get("_schema") or "").strip()
        metric_key = MATERIAL_METRIC_KEYS.get(task)
        doi = normalize_doi(record.get("doi"))
        row_number = record.get("row_number")
        raw_metric = record.get(metric_key) if metric_key else None
        if not task or not metric_key or not doi or raw_metric in (None, ""):
            continue
        metals_raw = record.get("metals")
        metals = tuple(str(x).strip() for x in metals_raw) if isinstance(metals_raw, list) else ()
        row = int(row_number) if isinstance(row_number, int) else None
        target = TruthTarget(
            task,
            doi,
            row,
            {metric_key: raw_metric},
            {},
            metals,
            None,
            material_truth.name,
            row,
        )
        by_doi[(task, doi)].append(target)
        if row is not None:
            by_row[(task, doi, row)].append(target)
        counts[task] += 1
        metric_stats[task].update(_numeric_metric_audit({metric_key: raw_metric}))
        contract = _truth_unit_contract(task, metric_key, raw_metric)
        metric_stats[task][f"unit_contract_{contract}_values"] += 1
        unit_contracts[f"{task}/{metric_key}"][_unit_suffix(raw_metric) or "<missing>"] += 1

    totals: Counter[str] = Counter()
    for stats in metric_stats.values():
        totals.update(stats)
    truth_quality = {
        "totals": dict(totals),
        "by_task": {task: dict(stats) for task, stats in sorted(metric_stats.items())},
        "unit_contracts": {key: dict(sorted(values.items())) for key, values in sorted(unit_contracts.items())},
        "interpretation": (
            "Parseability only means a leading numeric value is present. Unit-contract outliers still require "
            "normalization, task splitting, or exclusion before numeric GRPO."
        ),
    }
    return by_doi, by_row, counts, truth_quality


def load_chroma_doc_ids(chroma_db: Path, collection_name: str) -> tuple[dict[str, set[str]], dict[str, Any]]:
    """Load task-filterable DOI sets from one Chroma metadata collection."""
    result: dict[str, set[str]] = defaultdict(set)
    metadata: dict[str, Any] = {
        "database": str(chroma_db),
        "collection": collection_name,
        "available": False,
        "error": None,
    }
    if not chroma_db.exists():
        metadata["error"] = "database_not_found"
        return result, metadata

    try:
        connection = sqlite3.connect(f"file:{chroma_db}?mode=ro", uri=True)
        collection_row = connection.execute("SELECT id FROM collections WHERE name = ?", (collection_name,)).fetchone()
        if not collection_row:
            names = [row[0] for row in connection.execute("SELECT name FROM collections ORDER BY name")]
            metadata["error"] = "collection_not_found"
            metadata["available_collections"] = names
            connection.close()
            return result, metadata
        collection_id = collection_row[0]
        segment_row = connection.execute(
            "SELECT id FROM segments WHERE collection = ? AND scope = 'METADATA'", (collection_id,)
        ).fetchone()
        if not segment_row:
            metadata["error"] = "metadata_segment_not_found"
            connection.close()
            return result, metadata

        query = """
            SELECT task.string_value, doc.string_value
            FROM embeddings AS e
            JOIN embedding_metadata AS task ON task.id = e.id AND task.key = 'reaction_type'
            JOIN embedding_metadata AS doc ON doc.id = e.id AND doc.key = 'doc_id'
            WHERE e.segment_id = ?
        """
        for raw_task, raw_doi in connection.execute(query, (segment_row[0],)):
            canonical = CHROMA_TASK_ALIASES.get(str(raw_task or "").strip().casefold())
            doi = normalize_doi(raw_doi)
            if canonical and doi:
                result[canonical].add(doi)
        connection.close()
        metadata["available"] = True
        metadata["documents_by_task"] = {task: len(dois) for task, dois in sorted(result.items())}
    except sqlite3.Error as exc:
        metadata["error"] = f"sqlite_error: {exc}"
    return result, metadata


def _record_material_stats(record: Mapping[str, Any]) -> dict[str, int]:
    materials = record.get("final_materials")
    material_list = [item for item in materials if isinstance(item, dict)] if isinstance(materials, list) else []
    names = [str(item.get("material_name") or "").strip() for item in material_list]
    vague_reasons = [
        vague_material_name_reasons(item.get("material_name"), item.get("evidence")) for item in material_list
    ]
    return {
        "material_objects": len(material_list),
        "missing_material_names": sum(not name for name in names),
        "generic_material_names": sum(is_generic_material_name(name) for name in names),
        "vague_or_group_material_names": sum(bool(reasons) for reasons in vague_reasons),
        "records_with_vague_or_group_material_name": int(any(vague_reasons)),
        "materials_with_components": sum(bool(item.get("components")) for item in material_list),
        "materials_with_structure_relationships": sum(
            bool(item.get("structure_relationships")) for item in material_list
        ),
        "materials_with_evidence_text": sum(bool(str(item.get("evidence") or "").strip()) for item in material_list),
        "materials_with_explicit_metal_elements": sum("metal_elements" in item for item in material_list),
        "materials_with_explicit_nonmetal_elements": sum("nonmetal_elements" in item for item in material_list),
    }


def _material_identity(name: object, material_index: int | None) -> str:
    normalized = normalize_material_name(name)
    return normalized or f"<missing-material-{material_index if material_index is not None else 'unknown'}>"


def _metric_context_key(task: str, metrics: Mapping[str, Any], product: object = None) -> str:
    return json.dumps(
        {
            "metric_keys": sorted(str(key) for key in metrics),
            "product": canonical_text(product),
            "task_type": task,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _new_extraction_context(task: str, extraction: Mapping[str, Any]) -> dict[str, Any]:
    if task == "photocatalytic_h2o2":
        evidence = _evidence_text(extraction)
        wavelengths = sorted(set(re.findall(r"\b\d+(?:\.\d+)?\s*nm\b", evidence.casefold())))
        return {"metric": "apparent_quantum_efficiency", "wavelengths": wavelengths or ["unspecified"]}
    if task == "thermoelectric":
        temperature = parse_numeric(extraction.get("temperature"))
        return {
            "metric": "figure_of_merit",
            "temperature": temperature.value if temperature else "unspecified",
            "temperature_unit": _unit_suffix(extraction.get("temperature")) or "unspecified",
        }
    if task == "antibacterial":
        evidence = canonical_text(_evidence_text(extraction))
        organisms = sorted(
            set(
                re.findall(
                    r"e\.\s*coli|s\.\s*aureus|p\.\s*aeruginosa|b\.\s*subtilis|"
                    r"escherichia\s+coli|staphylococcus\s+aureus|pseudomonas\s+aeruginosa|bacillus\s+subtilis",
                    evidence,
                )
            )
        )
        return {"metric": "antibacterial", "organisms": organisms or ["unspecified"]}
    if task == "furfural_hydrogenation":
        evidence = canonical_text(_evidence_text(extraction))
        conditions = sorted(
            set(
                re.findall(
                    r"\b\d+(?:\.\d+)?\s*(?:k|°c|c|bar|mpa|h|min)\b",
                    evidence,
                    flags=re.IGNORECASE,
                )
            )
        )
        return {"metric": "furfuryl_alcohol_yield", "conditions": conditions or ["unspecified"]}
    return {"metric": task}


def audit_established_tasks(
    source_dir: Path,
    truth_by_doi: Mapping[tuple[str, str], Sequence[TruthTarget]],
    truth_by_row: Mapping[tuple[str, str, int], Sequence[TruthTarget]],
    truth_counts: Mapping[str, int],
    chroma_doc_ids: Mapping[str, set[str]],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[AuditObservation]]:
    by_task: dict[str, dict[str, Any]] = {}
    review_queue: list[dict[str, Any]] = []
    observations: list[AuditObservation] = []

    for filename, task in OLD_FILE_TASKS.items():
        path = source_dir / filename
        stats: Counter[str] = Counter()
        reasons: Counter[str] = Counter()
        unique_dois: set[str] = set()
        maskable_dois: set[str] = set()
        vague_examples: list[dict[str, Any]] = []

        for record in iter_jsonl(path):
            stats["source_records"] += 1
            doi = normalize_doi(record.get("doi"))
            if doi:
                unique_dois.add(doi)
            else:
                stats["records_missing_doi"] += 1

            material_list_raw = record.get("final_materials")
            materials = (
                [item for item in material_list_raw if isinstance(item, dict)]
                if isinstance(material_list_raw, list)
                else []
            )
            names = material_names(record)
            material_stats = _record_material_stats(record)
            stats.update(material_stats)
            vague_by_index = [
                vague_material_name_reasons(material.get("material_name"), material.get("evidence"))
                for material in materials
            ]
            for material_index, vague_reasons in enumerate(vague_by_index):
                if vague_reasons and len(vague_examples) < 10:
                    vague_examples.append(
                        {
                            "doi": doi,
                            "row_number": record.get("row_number"),
                            "material_name": names[material_index],
                            "reasons": list(vague_reasons),
                        }
                    )
            if len(materials) == 1:
                stats["records_with_one_material"] += 1
            elif len(materials) > 1:
                stats["records_with_multiple_materials"] += 1
            else:
                stats["records_without_materials"] += 1

            row_number = record.get("row_number")
            targets: Sequence[TruthTarget] = ()
            join_mode = "none"
            if doi and isinstance(row_number, int):
                targets = truth_by_row.get((task, doi, row_number), ())
                if targets:
                    join_mode = "task_doi_row"
            if not targets and doi:
                targets = truth_by_doi.get((task, doi), ())
                if targets:
                    join_mode = "task_doi"

            unique_targets, duplicate_count, has_conflict = _deduplicate_truth_targets(list(targets))
            stats["truth_rows_matched"] += len(targets)
            stats["unique_truth_targets"] += len(unique_targets)
            stats["duplicate_truth_rows"] += duplicate_count
            if targets:
                stats["records_with_truth"] += 1
                stats[f"join_{join_mode}"] += 1
            else:
                stats["records_without_truth"] += 1
            if has_conflict:
                stats["records_with_conflicting_truth"] += 1

            if doi and doi in chroma_doc_ids.get(task, set()):
                stats["records_maskable_in_chroma"] += 1
                maskable_dois.add(doi)

            sample_statuses: list[str] = []
            binding_modes: Counter[str] = Counter()
            record_reasons: set[str] = set()
            if not targets:
                record_reasons.add("missing_performance_truth")
            if not materials:
                record_reasons.add("missing_material_object")
            if names and all(is_generic_material_name(name) for name in names):
                record_reasons.add("only_generic_material_names")
            if has_conflict:
                record_reasons.add("conflicting_labels_for_same_context")

            for target_index, target in enumerate(unique_targets):
                bound_material_index: int | None = None
                if has_conflict:
                    sample_statuses.append("manual_review")
                elif len(materials) == 1 and names and not is_generic_material_name(names[0]):
                    sample_statuses.append("direct")
                    binding_modes["single_material"] += 1
                    bound_material_index = 0
                elif len(materials) > 1:
                    matched_index, mode = _bind_truth_by_elements(materials, target)
                    if matched_index is not None and mode and not is_generic_material_name(names[matched_index]):
                        sample_statuses.append("recoverable")
                        binding_modes[mode] += 1
                        bound_material_index = matched_index
                    else:
                        record_reasons.add("multiple_materials_not_uniquely_bound")
                        sample_statuses.append("manual_review")
                else:
                    sample_statuses.append("manual_review")

                status = sample_statuses[-1]
                material_name = names[bound_material_index] if bound_material_index is not None else "<ambiguous>"
                name_is_vague = bool(bound_material_index is not None and vague_by_index[bound_material_index])
                if name_is_vague:
                    stats["candidate_samples_with_vague_or_group_name"] += 1
                observations.append(
                    AuditObservation(
                        task_type=task,
                        doi=doi,
                        material_identity=_material_identity(material_name, bound_material_index),
                        material_name=material_name,
                        context_key=_metric_context_key(task, target.metrics, target.product),
                        label_key=target.label_key,
                        status=status,
                        numeric_prediction_ready=(
                            status in {"direct", "recoverable"}
                            and not name_is_vague
                            and all(parse_numeric(value) is not None for value in target.metrics.values())
                            and all(
                                _truth_unit_contract(task, metric_key, raw_value, target.units.get(metric_key))
                                in {"canonical", "declared"}
                                for metric_key, raw_value in target.metrics.items()
                            )
                        ),
                        source_file=filename,
                        row_number=row_number if isinstance(row_number, int) else None,
                        extraction_index=target_index,
                    )
                )

            for status in sample_statuses:
                stats[f"{status}_samples"] += 1

            if not targets or not sample_statuses or "manual_review" in sample_statuses:
                record_status = "manual_review"
            elif "recoverable" in sample_statuses:
                record_status = "recoverable"
            else:
                record_status = "direct"
            stats[f"{record_status}_records"] += 1
            for reason in record_reasons:
                reasons[reason] += 1

            if record_status != "direct":
                review_queue.append(
                    {
                        "source_group": "established_15",
                        "status": record_status,
                        "task_type": task,
                        "source_file": filename,
                        "row_number": row_number,
                        "doi": doi,
                        "material_names": names,
                        "truth_target_count": len(unique_targets),
                        "join_mode": join_mode,
                        "binding_modes": dict(binding_modes),
                        "reasons": sorted(record_reasons),
                    }
                )

        stats["source_unique_dois"] = len(unique_dois)
        stats["truth_records_available"] = int(truth_counts.get(task, 0))
        stats["unique_dois_maskable_in_chroma"] = len(maskable_dois)
        by_task[task] = {
            **dict(stats),
            "review_reasons": dict(reasons),
            "vague_material_name_examples": vague_examples,
            "source_file": filename,
        }

    totals = _sum_numeric_task_stats(by_task)
    return {"by_task": by_task, "totals": totals}, review_queue, observations


def _evidence_text(extraction: Mapping[str, Any]) -> str:
    fields = ("evidence", "metric_evidence", "context_evidence")
    return " ".join(str(extraction.get(field) or "") for field in fields).strip()


def _metric_quality(task: str, extraction: Mapping[str, Any]) -> tuple[str, list[str], dict[str, Any]]:
    reasons: list[str] = []
    parsed: dict[str, Any] = {}
    if task == "photocatalytic_h2o2":
        raw = extraction.get("apparent_quantum_efficiency")
        value = parse_numeric(raw)
        if value is None:
            return "unusable", ["unparseable_apparent_quantum_efficiency"], parsed
        parsed["apparent_quantum_efficiency"] = value.value
        if "%" not in str(raw):
            reasons.append("quantum_efficiency_unit_not_explicit_percent")
            return "recoverable", reasons, parsed
        return "direct", reasons, parsed

    if task == "furfural_hydrogenation":
        raw = extraction.get("furfuryl_alcohol_yield")
        value = parse_numeric(raw)
        if value is None:
            return "unusable", ["unparseable_furfuryl_alcohol_yield"], parsed
        parsed["furfuryl_alcohol_yield"] = value.value
        if "%" not in str(raw):
            reasons.append("yield_unit_not_explicit_percent")
            return "recoverable", reasons, parsed
        return "direct", reasons, parsed

    if task == "thermoelectric":
        figure = parse_numeric(extraction.get("figure_of_merit"))
        temperature = parse_numeric(extraction.get("temperature"))
        if figure is not None:
            parsed["figure_of_merit"] = figure.value
        if temperature is not None:
            parsed["temperature"] = temperature.value
        if figure is None:
            return "unusable", ["unparseable_figure_of_merit"], parsed
        # Temperature is useful context, but the minimum dataset contract is
        # material name plus a numeric performance truth.
        if extraction.get("temperature") not in (None, "") and temperature is None:
            return "recoverable", ["unparseable_optional_temperature"], parsed
        if temperature is not None and "k" not in str(extraction.get("temperature") or "").casefold():
            return "recoverable", ["temperature_unit_not_explicit_kelvin"], parsed
        return "direct", reasons, parsed

    if task == "antibacterial":
        threshold_raw = extraction.get("bactericidal_threshold")
        concentration_raw = extraction.get("minimum_concentration")
        threshold = parse_numeric(threshold_raw)
        concentration = parse_numeric(concentration_raw)
        if threshold is not None:
            parsed["bactericidal_threshold"] = threshold.value
        if concentration is not None:
            parsed["minimum_concentration"] = concentration.value
        threshold_complete = str(threshold_raw or "").strip().casefold() in {"complete", "completely", "full"}
        if threshold is not None and concentration is not None:
            return "direct", reasons, parsed
        if threshold_complete and concentration is not None:
            return "recoverable", ["categorical_complete_threshold_requires_policy"], parsed
        if threshold is not None or concentration is not None:
            return "recoverable", ["partial_antibacterial_metric_label"], parsed
        return "unusable", ["no_parseable_antibacterial_metric"], parsed

    return "unusable", ["unknown_task_metric_contract"], parsed


def _bind_new_extraction(
    materials: Sequence[Mapping[str, Any]], extraction: Mapping[str, Any]
) -> tuple[str, int | None, list[str]]:
    names = [str(item.get("material_name") or "").strip() for item in materials]
    explicit = str(extraction.get("material_name") or "").strip()
    reasons: list[str] = []
    if explicit:
        normalized = normalize_material_name(explicit)
        exact = [index for index, name in enumerate(names) if normalize_material_name(name) == normalized]
        if len(exact) == 1 and not is_generic_material_name(names[exact[0]]):
            return "direct", exact[0], reasons

        substring = [
            index
            for index, name in enumerate(names)
            if normalized
            and normalize_material_name(name)
            and (normalized in normalize_material_name(name) or normalize_material_name(name) in normalized)
        ]
        if len(substring) == 1 and not is_generic_material_name(names[substring[0]]):
            return "recoverable", substring[0], ["material_name_requires_normalized_substring_match"]
        if len(materials) == 1 and names and not is_generic_material_name(names[0]):
            return "recoverable", 0, ["explicit_material_name_mismatch_but_record_is_singleton"]
        return "manual_review", None, ["explicit_material_name_not_uniquely_matched"]

    if len(materials) == 1 and names and not is_generic_material_name(names[0]):
        return "direct", 0, reasons
    if not materials:
        return "manual_review", None, ["missing_material_object"]

    evidence = normalize_material_name(_evidence_text(extraction))
    evidence_matches = [
        index
        for index, name in enumerate(names)
        if normalize_material_name(name) and normalize_material_name(name) in evidence
    ]
    if len(evidence_matches) == 1 and not is_generic_material_name(names[evidence_matches[0]]):
        return "recoverable", evidence_matches[0], ["material_bound_by_unique_evidence_mention"]
    return "manual_review", None, ["multiple_materials_without_material_name"]


def _condition_flags(task: str, extraction: Mapping[str, Any]) -> dict[str, bool]:
    evidence = _evidence_text(extraction)
    lowered = evidence.casefold()
    if task == "thermoelectric":
        return {"primary_condition_present": parse_numeric(extraction.get("temperature")) is not None}
    if task == "photocatalytic_h2o2":
        return {"primary_condition_present": bool(re.search(r"\b\d+(?:\.\d+)?\s*nm\b|wavelength", lowered))}
    if task == "antibacterial":
        species_pattern = (
            r"e\.\s*coli|s\.\s*aureus|p\.\s*aeruginosa|b\.\s*subtilis|escherichia|staphylococcus|bacteria|strain"
        )
        return {"primary_condition_present": bool(re.search(species_pattern, lowered))}
    if task == "furfural_hydrogenation":
        condition_pattern = r"\b\d+(?:\.\d+)?\s*(?:k|c|°c|bar|mpa|h|min)\b|temperature|pressure|time"
        return {"primary_condition_present": bool(re.search(condition_pattern, lowered))}
    return {"primary_condition_present": False}


def _new_extraction_label_key(task: str, extraction: Mapping[str, Any]) -> str:
    fields = {
        "photocatalytic_h2o2": ("apparent_quantum_efficiency",),
        "antibacterial": ("bactericidal_threshold", "minimum_concentration"),
        "thermoelectric": ("figure_of_merit",),
        "furfural_hydrogenation": ("furfuryl_alcohol_yield",),
    }.get(task, ())
    return json.dumps(
        {field: canonical_text(extraction.get(field)) for field in fields},
        ensure_ascii=False,
        sort_keys=True,
    )


def audit_new_tasks(
    source_dir: Path, chroma_doc_ids: Mapping[str, set[str]]
) -> tuple[dict[str, Any], list[dict[str, Any]], list[AuditObservation]]:
    by_task: dict[str, dict[str, Any]] = {}
    review_queue: list[dict[str, Any]] = []
    observations: list[AuditObservation] = []

    for filename, task in NEW_FILE_TASKS.items():
        path = source_dir / filename
        stats: Counter[str] = Counter()
        reasons: Counter[str] = Counter()
        unique_dois: set[str] = set()
        maskable_dois: set[str] = set()
        vague_examples: list[dict[str, Any]] = []

        for record in iter_jsonl(path):
            stats["source_records"] += 1
            doi = normalize_doi(record.get("doi"))
            if doi:
                unique_dois.add(doi)
            else:
                stats["records_missing_doi"] += 1
            if doi and doi in chroma_doc_ids.get(task, set()):
                stats["records_maskable_in_chroma"] += 1
                maskable_dois.add(doi)

            material_list_raw = record.get("final_materials")
            materials = (
                [item for item in material_list_raw if isinstance(item, dict)]
                if isinstance(material_list_raw, list)
                else []
            )
            names = material_names(record)
            stats.update(_record_material_stats(record))
            vague_by_index = [
                vague_material_name_reasons(material.get("material_name"), material.get("evidence"))
                for material in materials
            ]
            for material_index, vague_reasons in enumerate(vague_by_index):
                if vague_reasons and len(vague_examples) < 10:
                    vague_examples.append(
                        {
                            "doi": doi,
                            "row_number": record.get("row_number"),
                            "material_name": names[material_index],
                            "reasons": list(vague_reasons),
                        }
                    )
            if len(materials) == 1:
                stats["records_with_one_material"] += 1
            elif len(materials) > 1:
                stats["records_with_multiple_materials"] += 1
            else:
                stats["records_without_materials"] += 1

            extractions_raw = record.get("property_extractions")
            extractions = (
                [item for item in extractions_raw if isinstance(item, dict)]
                if isinstance(extractions_raw, list)
                else []
            )
            stats["property_extractions"] += len(extractions)
            if not extractions:
                stats["records_without_property_extractions"] += 1

            extraction_statuses: list[str] = []
            for extraction_index, extraction in enumerate(extractions):
                metric_status, metric_reasons, parsed_metrics = _metric_quality(task, extraction)
                binding_status, material_index, binding_reasons = _bind_new_extraction(materials, extraction)
                condition_flags = _condition_flags(task, extraction)
                if condition_flags["primary_condition_present"]:
                    stats["extractions_with_primary_condition"] += 1
                else:
                    stats["extractions_without_primary_condition"] += 1

                if metric_status == "unusable" or binding_status == "manual_review":
                    status = "manual_review"
                elif metric_status == "recoverable" or binding_status == "recoverable":
                    status = "recoverable"
                else:
                    status = "direct"
                extraction_statuses.append(status)
                stats[f"{status}_samples"] += 1
                stats[f"metric_{metric_status}_samples"] += 1
                stats[f"binding_{binding_status}_samples"] += 1

                all_reasons = sorted(set(metric_reasons + binding_reasons))
                for reason in all_reasons:
                    reasons[reason] += 1
                material_name = names[material_index] if material_index is not None else "<ambiguous>"
                name_is_vague = bool(material_index is not None and vague_by_index[material_index])
                if name_is_vague:
                    stats["candidate_samples_with_vague_or_group_name"] += 1
                numeric_prediction_ready = (
                    status in {"direct", "recoverable"}
                    and metric_status == "direct"
                    and condition_flags["primary_condition_present"]
                    and not name_is_vague
                )
                if numeric_prediction_ready:
                    stats["numeric_prediction_ready_raw_samples"] += 1
                else:
                    stats["association_only_or_review_raw_samples"] += 1
                observations.append(
                    AuditObservation(
                        task_type=task,
                        doi=doi,
                        material_identity=_material_identity(material_name, material_index),
                        material_name=material_name,
                        context_key=json.dumps(
                            _new_extraction_context(task, extraction), ensure_ascii=False, sort_keys=True
                        ),
                        label_key=_new_extraction_label_key(task, extraction),
                        status=status,
                        numeric_prediction_ready=numeric_prediction_ready,
                        source_file=filename,
                        row_number=record.get("row_number") if isinstance(record.get("row_number"), int) else None,
                        extraction_index=extraction_index,
                    )
                )
                if status != "direct":
                    review_queue.append(
                        {
                            "source_group": "new_4",
                            "status": status,
                            "task_type": task,
                            "source_file": filename,
                            "row_number": record.get("row_number"),
                            "doi": doi,
                            "extraction_index": extraction_index,
                            "material_names": names,
                            "extraction_material_name": extraction.get("material_name"),
                            "bound_material_index": material_index,
                            "parsed_metrics": parsed_metrics,
                            "primary_condition_present": condition_flags["primary_condition_present"],
                            "reasons": all_reasons,
                        }
                    )

            if not extraction_statuses or "manual_review" in extraction_statuses:
                record_status = "manual_review"
            elif "recoverable" in extraction_statuses:
                record_status = "recoverable"
            else:
                record_status = "direct"
            stats[f"{record_status}_records"] += 1

        stats["source_unique_dois"] = len(unique_dois)
        stats["unique_dois_maskable_in_chroma"] = len(maskable_dois)
        by_task[task] = {
            **dict(stats),
            "review_reasons": dict(reasons),
            "vague_material_name_examples": vague_examples,
            "source_file": filename,
        }

    totals = _sum_numeric_task_stats(by_task)
    return {"by_task": by_task, "totals": totals}, review_queue, observations


def _sum_numeric_task_stats(by_task: Mapping[str, Mapping[str, Any]]) -> dict[str, int]:
    totals: Counter[str] = Counter()
    for stats in by_task.values():
        for key, value in stats.items():
            if isinstance(value, int) and not isinstance(value, bool):
                totals[key] += value
    return dict(totals)


def _readiness_summary(established: Mapping[str, Any], new: Mapping[str, Any]) -> dict[str, Any]:
    old_totals = established["totals"]
    new_totals = new["totals"]
    direct = int(old_totals.get("direct_samples", 0)) + int(new_totals.get("direct_samples", 0))
    recoverable = int(old_totals.get("recoverable_samples", 0)) + int(new_totals.get("recoverable_samples", 0))
    manual = int(old_totals.get("manual_review_samples", 0)) + int(new_totals.get("manual_review_samples", 0))
    total = direct + recoverable + manual
    return {
        "candidate_samples": total,
        "direct_samples": direct,
        "recoverable_samples": recoverable,
        "manual_review_samples": manual,
        "direct_rate": direct / total if total else 0.0,
        "direct_plus_recoverable_rate": (direct + recoverable) / total if total else 0.0,
        "recommendation": ("usable_with_gating" if direct > 0 else "not_ready"),
        "gating_policy": {
            "train_now": ["direct"],
            "train_after_deterministic_normalization": ["recoverable"],
            "exclude_until_reviewed": ["manual_review"],
        },
    }


def _prompt_field_coverage(established: Mapping[str, Any], new: Mapping[str, Any]) -> dict[str, Any]:
    by_group: dict[str, Any] = {}
    for group_name, section in (("established_15", established), ("new_4", new)):
        totals = section["totals"]
        material_objects = int(totals.get("material_objects", 0))
        by_group[group_name] = {
            "material_objects": material_objects,
            "material_name_present": material_objects - int(totals.get("missing_material_names", 0)),
            "free_text_material_evidence_present": int(totals.get("materials_with_evidence_text", 0)),
            "components_present": int(totals.get("materials_with_components", 0)),
            "structure_relationships_present": int(totals.get("materials_with_structure_relationships", 0)),
            "explicit_metal_elements_present": int(totals.get("materials_with_explicit_metal_elements", 0)),
            "explicit_nonmetal_elements_present": int(totals.get("materials_with_explicit_nonmetal_elements", 0)),
            "structured_precursors_present": 0,
            "structured_feed_ratio_present": 0,
            "structured_preparation_method_present": 0,
            "structured_element_content_present": 0,
        }
    return {
        "by_group": by_group,
        "schema_finding": (
            "The imported material objects do not define structured precursor, feed-ratio, preparation-method, "
            "or element-content fields. Some evidence strings mention such details, but coverage and semantics are "
            "not deterministic without a separate extraction pass."
        ),
        "grpo_implication": (
            "A first GRPO build can use material_name plus whichever optional composition, relationship, condition, "
            "or synthesis fields are actually present. Missing optional fields are omitted rather than fabricated. "
            "Training with consistently complete synthesis fields requires a separate source-text extraction pass."
        ),
    }


def build_audit(
    *,
    established_source_dir: Path,
    new_source_dir: Path,
    reaction_dataset: Path,
    material_truth: Path,
    chroma_db: Path,
    chroma_collection: str = "literature_agent2",
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    truth_by_doi, truth_by_row, truth_counts, truth_quality = load_established_truth(reaction_dataset, material_truth)
    chroma_doc_ids, chroma_metadata = load_chroma_doc_ids(chroma_db, chroma_collection)
    established, old_review, old_observations = audit_established_tasks(
        established_source_dir, truth_by_doi, truth_by_row, truth_counts, chroma_doc_ids
    )
    new, new_review, new_observations = audit_new_tasks(new_source_dir, chroma_doc_ids)
    # Dataset construction and the cross-record audit consume the same complete
    # candidate representation so their binding/deduplication keys cannot drift.
    from utu.data_processing.material_performance_candidates import (
        iter_established_candidates,
        iter_new_candidates,
    )

    shared_candidates = list(iter_established_candidates(established_source_dir, truth_by_doi, truth_by_row)) + list(
        iter_new_candidates(new_source_dir)
    )
    cross_record = analyze_cross_record_observations(
        candidate.to_audit_observation() for candidate in shared_candidates
    )
    audit = {
        "schema_version": 2,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "inputs": {
            "established_source_dir": str(established_source_dir),
            "new_source_dir": str(new_source_dir),
            "reaction_dataset": str(reaction_dataset),
            "material_truth": str(material_truth),
            "chroma_db": str(chroma_db),
            "chroma_collection": chroma_collection,
        },
        "status_definitions": {
            "direct": "Material identity, numeric truth and task context can be bound deterministically.",
            "recoverable": "A deterministic normalization or unique conservative match is required before training.",
            "manual_review": "Material identity or label context is ambiguous; exclude from automatic GRPO ingestion.",
        },
        "chroma": chroma_metadata,
        "established_truth_quality": truth_quality,
        "cross_record_quality": cross_record,
        "prompt_field_coverage": _prompt_field_coverage(established, new),
        "established_15": established,
        "new_4": new,
    }
    audit["overall"] = _readiness_summary(established, new)
    audit["overall"]["deduplicated_trainable_samples"] = int(cross_record["totals"].get("unique_trainable_samples", 0))
    audit["overall"]["numeric_metric_contract_ready_samples"] = int(
        cross_record["totals"].get("numeric_prediction_ready_samples", 0)
    )
    audit["overall"]["not_numeric_metric_contract_ready_samples"] = max(
        0,
        audit["overall"]["deduplicated_trainable_samples"] - audit["overall"]["numeric_metric_contract_ready_samples"],
    )
    audit["overall"]["conditioning_scope_note"] = (
        "The minimum dataset contract is a uniquely bound material name plus numeric performance truth. Conditions "
        "are preserved when present but are not required for automatic dataset inclusion."
    )
    cross_review = [
        {
            "source_group": "cross_record_conflict",
            "status": "manual_review",
            "task_type": item["task_type"],
            "doi": item["doi"],
            "material_names": [item["material_name"]],
            "context_key": item["context_key"],
            "conflicting_labels": item["labels"],
            "source_rows": item["source_rows"],
            "reasons": ["conflicting_labels_for_indistinguishable_material_context"],
        }
        for item in cross_record["conflict_examples"]
    ]
    review_queue = old_review + new_review + cross_review
    return audit, review_queue


def _pct(numerator: int, denominator: int) -> str:
    return f"{(100.0 * numerator / denominator):.2f}%" if denominator else "n/a"


def render_markdown(audit: Mapping[str, Any], review_queue_count: int) -> str:
    # Report prose is intentionally stored as complete Markdown lines.
    # ruff: noqa: E501
    overall = audit["overall"]
    old = audit["established_15"]
    new = audit["new_4"]
    lines = [
        "# Material Performance GRPO Readiness Audit (2026-07-28)",
        "",
        "## Conclusion",
        "",
        (
            f"The data is usable for GRPO only with a strict ingestion gate. Of {overall['candidate_samples']} "
            f"candidate material-performance samples, {overall['direct_samples']} "
            f"({_pct(overall['direct_samples'], overall['candidate_samples'])}) are directly usable, "
            f"{overall['recoverable_samples']} are deterministically recoverable, and "
            f"{overall['manual_review_samples']} must be excluded until reviewed."
        ),
        (
            f"After cross-record deduplication and conflict quarantine, "
            f"{overall.get('deduplicated_trainable_samples', 0)} unique samples are eligible after any recorded "
            "deterministic repairs. "
            f"Of these, {overall.get('numeric_metric_contract_ready_samples', 0)} meet the audit's stricter diagnostic "
            f"contract, while {overall.get('not_numeric_metric_contract_ready_samples', 0)} carry a diagnostic flag. "
            "The actual dataset builder uses the user-approved minimum contract: a uniquely bound material name plus "
            "numeric performance truth; optional conditions are retained when present but are not required."
        ),
        "",
        "Training policy:",
        "",
        "- `direct`: may enter the first GRPO build.",
        "- `recoverable`: enter only after the documented deterministic normalization/match is applied.",
        "- `manual_review`: do not copy labels across materials; keep in the review queue.",
        "- Every rollout with literature RAG must mask the sample DOI to prevent exact-paper label leakage.",
        "",
        "## Overall Counts",
        "",
        "| Group | Source records | Material objects | Candidate samples | Direct | Recoverable | Manual review |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for label, section in (("Established 15", old), ("New 4", new)):
        totals = section["totals"]
        candidates = (
            int(totals.get("direct_samples", 0))
            + int(totals.get("recoverable_samples", 0))
            + int(totals.get("manual_review_samples", 0))
        )
        lines.append(
            f"| {label} | {totals.get('source_records', 0)} | {totals.get('material_objects', 0)} | "
            f"{candidates} | {totals.get('direct_samples', 0)} | {totals.get('recoverable_samples', 0)} | "
            f"{totals.get('manual_review_samples', 0)} |"
        )
    lines.extend(["", "## Established 15 Directions", "", _task_table(old["by_task"], established=True)])
    lines.extend(["", "## Newly Added 4 Directions", "", _task_table(new["by_task"], established=False)])

    old_totals = old["totals"]
    new_totals = new["totals"]
    lines.extend(
        [
            "",
            "## Material Identity and Label Risks",
            "",
            f"- Established directions contain {old_totals.get('records_with_multiple_materials', 0)} records with multiple material objects.",
            f"- New directions contain {new_totals.get('records_with_multiple_materials', 0)} records with multiple material objects.",
            f"- Across both groups, {old_totals.get('missing_material_names', 0) + new_totals.get('missing_material_names', 0)} material objects have blank names and {old_totals.get('generic_material_names', 0) + new_totals.get('generic_material_names', 0)} use generic placeholder-like names under the audit heuristic.",
            f"- A broader review-only heuristic flags {old_totals.get('vague_or_group_material_names', 0) + new_totals.get('vague_or_group_material_names', 0)} material objects as series/group/variable-composition names; these are not automatically discarded.",
            f"- The generated review queue contains {review_queue_count} recoverable/manual items, including cross-record conflict groups.",
            f"- New-property extractions missing their primary test condition: {new_totals.get('extractions_without_primary_condition', 0)} of {new_totals.get('property_extractions', 0)}.",
            "",
            "## Cross-Record Duplicate and Conflict Check",
            "",
        ]
    )
    cross = audit["cross_record_quality"]["totals"]
    lines.extend(
        [
            f"- Raw material-label observations: {cross.get('raw_observations', 0)}.",
            f"- Exact duplicate groups: {cross.get('exact_duplicate_groups', 0)}, removing {cross.get('exact_duplicate_observations_removed', 0)} repeated observations before training.",
            f"- Indistinguishable-context conflict groups: {cross.get('conflicting_context_groups', 0)}, covering {cross.get('raw_observations_in_conflicting_contexts', 0)} raw observations that must be quarantined.",
            f"- Material identities with multiple distinguishable metric contexts: {cross.get('material_identities_with_multiple_contexts', 0)}; these are retained as legitimate condition-specific labels.",
            "",
            "## Established Truth Parseability and Unit Contracts",
            "",
        ]
    )
    truth = audit["established_truth_quality"]["totals"]
    noncanonical = (
        truth.get("unit_contract_noncanonical_or_relative_values", 0)
        + truth.get("unit_contract_noncanonical_or_missing_values", 0)
        + truth.get("unit_contract_missing_values", 0)
    )
    lines.extend(
        [
            f"- Parseable numeric truth values: {truth.get('parseable_truth_metric_values', 0)} of {truth.get('truth_metric_values', 0)}.",
            f"- Values carrying a comparator: {truth.get('truth_metric_values_with_comparator', 0)}; comparators must remain in the label contract.",
            f"- Noncanonical/relative or missing unit-contract values: {noncanonical}.",
            "- A leading number is not sufficient for GRPO: relative improvements and mass-normalized exchange-current values must not be mixed with area-normalized absolute exchange current.",
            "",
            "## Coverage of the New Material Prompt Fields",
            "",
        ]
    )
    prompt_coverage = audit["prompt_field_coverage"]["by_group"]
    old_prompt = prompt_coverage["established_15"]
    new_prompt = prompt_coverage["new_4"]
    lines.extend(
        [
            f"- Material name is present for {old_prompt['material_name_present']} of {old_prompt['material_objects']} established material objects and {new_prompt['material_name_present']} of {new_prompt['material_objects']} new material objects.",
            f"- Explicit metal-element lists exist for {old_prompt['explicit_metal_elements_present']} established and {new_prompt['explicit_metal_elements_present']} new material objects; established metals currently require conservative inference from names/components.",
            "- Structured `precursors`, `feed_ratio`, `preparation_method`, and `element_content` fields are absent from both imported schemas. Evidence text sometimes mentions them, but it is not a complete or deterministic substitute.",
            "- Therefore the first safe GRPO build uses `material_name` plus only the optional composition, relationship, condition, or synthesis fields actually present. Missing optional fields are omitted, not filled with `unspecified`.",
            "",
            "## Chroma Leakage-Masking Check",
            "",
        ]
    )
    chroma = audit["chroma"]
    if chroma.get("available"):
        lines.append(
            f"The unified collection `{chroma.get('collection')}` is readable and exposes task-filterable `doc_id` metadata. "
            "The per-task tables report how many source records can be masked under the matching task filter."
        )
    else:
        lines.append(
            f"Chroma audit failed: `{chroma.get('error')}`. GRPO with literature RAG must remain disabled until fixed."
        )

    lines.extend(
        [
            "",
            "## Required Dataset-Build Gates",
            "",
            "1. Join the established 15 directions by canonical task plus normalized DOI; use source row number when available.",
            "2. Never fan one performance label out to every material in a multi-material article.",
            "3. Deduplicate identical task/context/label targets and quarantine conflicting labels with indistinguishable input context.",
            "4. Keep comparator information such as `>90%`; do not silently replace it with an exact value.",
            "5. Preserve temperature for thermoelectric ZT and test-organism/context evidence for antibacterial data when present; do not fabricate missing optional conditions.",
            "6. Store `doc_id` in every GRPO sample and mask that DOI in Chroma retrieval during rollout/evaluation.",
            "7. Version the generated dataset and experience pack; do not seed from the old metal-only experience pack.",
            "",
            "## Reproduction",
            "",
            "Run from `chem-loop/youtu-chem-loop`:",
            "",
            "```bash",
            "python scripts/data/audit_material_performance_grpo_readiness.py",
            "```",
            "",
            "Machine-readable output and the review queue are written under `data/audits/material_performance_20260728/`.",
        ]
    )
    return "\n".join(lines) + "\n"


def _task_table(by_task: Mapping[str, Mapping[str, Any]], *, established: bool) -> str:
    # Markdown table headers are kept on one source line for readability.
    # ruff: noqa: E501
    if established:
        header = (
            "| Task | Records | Multi-material | Truth matched | Candidate samples | Direct | Recoverable | Manual | Chroma-maskable |\n"
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|"
        )
    else:
        header = (
            "| Task | Records | Multi-material | Extractions | Direct | Recoverable | Manual | Condition present | Chroma-maskable |\n"
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|"
        )
    rows = [header]
    for task, stats in by_task.items():
        if established:
            candidates = (
                int(stats.get("direct_samples", 0))
                + int(stats.get("recoverable_samples", 0))
                + int(stats.get("manual_review_samples", 0))
            )
            rows.append(
                f"| `{task}` | {stats.get('source_records', 0)} | {stats.get('records_with_multiple_materials', 0)} | "
                f"{stats.get('records_with_truth', 0)} | {candidates} | {stats.get('direct_samples', 0)} | "
                f"{stats.get('recoverable_samples', 0)} | {stats.get('manual_review_samples', 0)} | "
                f"{stats.get('records_maskable_in_chroma', 0)} |"
            )
        else:
            rows.append(
                f"| `{task}` | {stats.get('source_records', 0)} | {stats.get('records_with_multiple_materials', 0)} | "
                f"{stats.get('property_extractions', 0)} | {stats.get('direct_samples', 0)} | "
                f"{stats.get('recoverable_samples', 0)} | {stats.get('manual_review_samples', 0)} | "
                f"{stats.get('extractions_with_primary_condition', 0)} | {stats.get('records_maskable_in_chroma', 0)} |"
            )
    return "\n".join(rows)


def write_audit_outputs(
    audit: Mapping[str, Any], review_queue: Iterable[Mapping[str, Any]], output_dir: Path, report_path: Path
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    review_items = list(review_queue)
    (output_dir / "summary.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with (output_dir / "review_queue.jsonl").open("w", encoding="utf-8") as handle:
        for item in review_items:
            handle.write(json.dumps(dict(item), ensure_ascii=False, sort_keys=True) + "\n")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_markdown(audit, len(review_items)), encoding="utf-8")
