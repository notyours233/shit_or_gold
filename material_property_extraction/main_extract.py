#!/usr/bin/env python3
"""Extract property metrics and metal elements from XLSX abstracts via Alibaba DashScope."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple
from zipfile import ZipFile

try:
    from tqdm import tqdm
except ModuleNotFoundError:
    def tqdm(iterable: Iterable, **_: Any) -> Iterable:
        return iterable


DATA_DIR = Path(__file__).resolve().parent / "data"
OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"
DEFAULT_ENV_FILE = Path(__file__).resolve().parent / ".env"
DEFAULT_MODEL = "qwen3.5-flash"
MODEL_OPTIONS = (
    "qwen3.5-flash",
    "qwen3.6-plus",
)
DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_API_KEY_ENV = "DASHSCOPE_API_KEY"
DEFAULT_MODEL_ENV = "DASHSCOPE_MODEL"
LEGACY_API_KEY_ENV = "OPENROUTER_API_KEY"
DEFAULT_BATCH_COMPLETION_WINDOW = "24h"
DEFAULT_BATCH_POLL_INTERVAL = 10
DEFAULT_BATCH_MAX_REQUESTS = 50000
CHAT_COMPLETIONS_ENDPOINT = "/v1/chat/completions"
JSON_BLOCK_REGEX = re.compile(r"\{.*\}", re.S)
NUMBER_PATTERN = r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"
HTML_TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")
CELL_REF_RE = re.compile(r"([A-Z]+)")

XML_NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "doc_rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}

METAL_ELEMENTS = {
    "Li", "Be", "Na", "Mg", "Al", "K", "Ca", "Sc", "Ti", "V", "Cr", "Mn", "Fe", "Co",
    "Ni", "Cu", "Zn", "Ga", "Rb", "Sr", "Y", "Zr", "Nb", "Mo", "Tc", "Ru", "Rh", "Pd",
    "Ag", "Cd", "In", "Sn", "Cs", "Ba", "La", "Ce", "Pr", "Nd", "Pm", "Sm", "Eu", "Gd",
    "Tb", "Dy", "Ho", "Er", "Tm", "Yb", "Lu", "Hf", "Ta", "W", "Re", "Os", "Ir", "Pt",
    "Au", "Hg", "Tl", "Pb", "Bi", "Po", "Fr", "Ra", "Ac", "Th", "Pa", "U", "Np", "Pu",
    "Am", "Cm", "Bk", "Cf", "Es", "Fm", "Md", "No", "Lr", "Rf", "Db", "Sg", "Bh", "Hs",
    "Mt", "Ds", "Rg", "Cn", "Nh", "Fl", "Mc", "Lv",
}


def _format_number(value: float) -> str:
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return text if text else "0"


def _normalize_text(value: str) -> str:
    replacements = {
        "\u2212": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2011": "-",
        "\u2043": "-",
        "\u207b": "-",
        "\u00b7": " ",
        "\u22c5": " ",
        "\u00d7": "x",
        "\u00a0": " ",
        "cm−1": "cm-1",
        "cm–1": "cm-1",
        "cm⁻1": "cm-1",
        "cm^-1": "cm-1",
        "m−1": "m-1",
        "m–1": "m-1",
        "m⁻1": "m-1",
        "m^-1": "m-1",
        "K−1": "K-1",
        "K–1": "K-1",
        "K⁻1": "K-1",
        "K^-1": "K-1",
    }
    for source, target in replacements.items():
        value = value.replace(source, target)
    value = html.unescape(value)
    return SPACE_RE.sub(" ", value).strip()


def _normalize_property_label(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _match_number_with_unit(value: str, unit_patterns: Sequence[Tuple[str, str]]) -> Optional[str]:
    normalized = _normalize_text(value)
    for pattern, canonical_unit in unit_patterns:
        match = re.fullmatch(rf"({NUMBER_PATTERN})\s*{pattern}", normalized, flags=re.IGNORECASE)
        if match:
            return f"{_format_number(float(match.group(1)))} {canonical_unit}"
    return None


def normalize_percentage(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return f"{_format_number(float(value))} %"

    normalized = _normalize_text(str(value))
    percent_match = re.fullmatch(rf"({NUMBER_PATTERN})\s*%", normalized, flags=re.IGNORECASE)
    if percent_match:
        return f"{_format_number(float(percent_match.group(1)))} %"

    word_match = re.fullmatch(rf"({NUMBER_PATTERN})\s*(percent|percentage)", normalized, flags=re.IGNORECASE)
    if word_match:
        return f"{_format_number(float(word_match.group(1)))} %"

    if re.fullmatch(NUMBER_PATTERN, normalized):
        return f"{_format_number(float(normalized))} %"

    return None


def normalize_conductivity(value: Any) -> Optional[str]:
    if value is None:
        return None
    unit_patterns = (
        (r"mS\s*/\s*m", "mS/m"),
        (r"S\s*/\s*m", "S/m"),
        (r"mS\s*/\s*cm", "mS/cm"),
        (r"S\s*/\s*cm", "S/cm"),
        (r"mS\s*m-1", "mS m-1"),
        (r"S\s*m-1", "S m-1"),
        (r"mS\s*cm-1", "mS cm-1"),
        (r"S\s*cm-1", "S cm-1"),
    )
    return _match_number_with_unit(str(value), unit_patterns)


def normalize_thermal_conductivity(value: Any) -> Optional[str]:
    if value is None:
        return None

    normalized = _normalize_text(str(value))
    match = re.fullmatch(
        rf"({NUMBER_PATTERN})\s*W\s*(?:m-1\s*K-1|/\s*\(\s*m\s*K\s*\)|/\s*m\s*K)",
        normalized,
        flags=re.IGNORECASE,
    )
    if match:
        return f"{_format_number(float(match.group(1)))} W m-1 K-1"
    return None


def normalize_saturation_magnetization(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return f"{_format_number(float(value))} emu/g"

    normalized = _normalize_text(str(value))
    match = re.fullmatch(
        rf"({NUMBER_PATTERN})\s*emu\s*(?:/\s*g|g-1)",
        normalized,
        flags=re.IGNORECASE,
    )
    if match:
        return f"{_format_number(float(match.group(1)))} emu/g"

    if re.fullmatch(NUMBER_PATTERN, normalized):
        return f"{_format_number(float(normalized))} emu/g"

    return None


def normalize_neel_temperature(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return f"{_format_number(float(value))} K"

    normalized = _normalize_text(str(value))
    match = re.fullmatch(rf"({NUMBER_PATTERN})\s*(K|Kelvin)", normalized, flags=re.IGNORECASE)
    if match:
        return f"{_format_number(float(match.group(1)))} K"

    if re.fullmatch(NUMBER_PATTERN, normalized):
        return f"{_format_number(float(normalized))} K"

    return None


@dataclass(frozen=True)
class PropertySchema:
    key: str
    property_type: str
    input_filename: str
    metric_field: str
    metric_aliases: Tuple[str, ...]
    metric_prompt: str
    metric_validator: Callable[[Any], Optional[str]]
    example_metric: str

    @property
    def output_template(self) -> Dict[str, Any]:
        return {
            "metals": ["M1", "M2"],
            "property_type": self.property_type,
            self.metric_field: self.example_metric,
        }


SCHEMAS: Dict[str, PropertySchema] = {
    "photothermal_conversion_efficiency": PropertySchema(
        key="photothermal_conversion_efficiency",
        property_type="Photothermal conversion efficiency",
        input_filename="Photothermal conversion efficiency 2026-2010.xlsx",
        metric_field="photothermal_conversion_efficiency",
        metric_aliases=("Photothermal conversion efficiency", "photothermalEfficiency"),
        metric_prompt=(
            '- Extract the photothermal conversion efficiency explicitly reported in the abstract.\n'
            '- The JSON key must be "photothermal_conversion_efficiency".\n'
            '- The value must include the number and the percent unit, formatted like "78.8 %".\n'
            '- If multiple efficiencies are reported, choose the one emphasized for the main studied material.'
        ),
        metric_validator=normalize_percentage,
        example_metric="78.8 %",
    ),
    "conductivity": PropertySchema(
        key="conductivity",
        property_type="Conductivity",
        input_filename="Conductivity 2010-2026.xlsx",
        metric_field="conductivity",
        metric_aliases=("Conductivity", "electrical_conductivity"),
        metric_prompt=(
            '- Extract the conductivity explicitly reported in the abstract.\n'
            '- The JSON key must be "conductivity".\n'
            '- The value must include the number and one accepted unit: S/m, mS/m, mS/cm, S/cm, '
            'S m-1, mS m-1, S cm-1, or mS cm-1.\n'
            '- If multiple conductivity values are reported, choose the one emphasized as the main/best result.'
        ),
        metric_validator=normalize_conductivity,
        example_metric="7781 S cm-1",
    ),
    "thermal_conductivity": PropertySchema(
        key="thermal_conductivity",
        property_type="Thermal Conductivity",
        input_filename="Thermal Conductivity 2010-2026.xlsx",
        metric_field="thermal_conductivity",
        metric_aliases=("Thermal Conductivity", "thermalConductivity"),
        metric_prompt=(
            '- Extract the thermal conductivity explicitly reported in the abstract.\n'
            '- The JSON key must be "thermal_conductivity".\n'
            '- The value must include the number and either Wm-1K-1 / W m-1 K-1 or W/(mK) style units.\n'
            '- Normalize the final value to a string like "4.2 W m-1 K-1".'
        ),
        metric_validator=normalize_thermal_conductivity,
        example_metric="4.2 W m-1 K-1",
    ),
    "ferromagnetism": PropertySchema(
        key="ferromagnetism",
        property_type="Ferromagnetism",
        input_filename="Ferromagnetism 2026-2010.xlsx",
        metric_field="saturation_magnetization",
        metric_aliases=("Ms", "saturation magnetization", "saturationMagnetization"),
        metric_prompt=(
            '- Extract the saturation magnetization explicitly reported in the abstract.\n'
            '- The JSON key must be "saturation_magnetization".\n'
            '- The value must include the number and unit emu/g, formatted like "45.3 emu/g".\n'
            '- The abstract may call it saturation magnetization or Ms.'
        ),
        metric_validator=normalize_saturation_magnetization,
        example_metric="45.3 emu/g",
    ),
    "ferrimagnetism": PropertySchema(
        key="ferrimagnetism",
        property_type="Ferrimagnetism",
        input_filename="Ferrimagnetism 2026-2010.xlsx",
        metric_field="saturation_magnetization",
        metric_aliases=("Ms", "saturation magnetization", "saturationMagnetization"),
        metric_prompt=(
            '- Extract the saturation magnetization explicitly reported in the abstract.\n'
            '- The JSON key must be "saturation_magnetization".\n'
            '- The value must include the number and unit emu/g, formatted like "45.3 emu/g".\n'
            '- The abstract may call it saturation magnetization or Ms.'
        ),
        metric_validator=normalize_saturation_magnetization,
        example_metric="45.3 emu/g",
    ),
    "antiferromagnetism": PropertySchema(
        key="antiferromagnetism",
        property_type="Antiferromagnetism",
        input_filename="Antiferromagnetism 2026-2010.xlsx",
        metric_field="neel_temperature",
        metric_aliases=("Néel Temperature", "Neel Temperature", "neelTemperature"),
        metric_prompt=(
            '- Extract the Néel temperature explicitly reported in the abstract.\n'
            '- The JSON key must be "neel_temperature".\n'
            '- The value must include the number and unit K, formatted like "370 K".\n'
            '- The abstract may spell it as Néel temperature or Neel temperature.'
        ),
        metric_validator=normalize_neel_temperature,
        example_metric="370 K",
    ),
}


PROMPT_TEMPLATE = """
You are an expert in materials-science literature extraction.

Given the abstract of a scientific paper, extract ONLY the following JSON with EXACT format:

1) Metal elements in the studied material/system.
   - Return only explicit metal element symbols such as Fe, Ni, Co, Ti, Cu, Zn.
   - Do not return non-metals, generic material classes, formulas, or words that are not element symbols.
   - Deduplicate the symbols and keep the most central metals first.

2) Property type:
   - It MUST be exactly "{property_type}".
   - If the abstract is not about this property, output exactly INVALID.

3) Required metric:
{metric_prompt}

If ANY of the following is true, output exactly INVALID:
- the abstract is not about "{property_type}",
- there are no explicit metal element symbols for the studied material/system,
- the required metric is not explicitly reported with the required unit.

Output exactly in JSON:
{json_template}

Abstract:
\"\"\"{abstract}\"\"\"
""".strip()


def load_env_file(path: Optional[Path]) -> None:
    if path is None or not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def _normalize_metal_symbol(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    symbol = value.strip()
    if not symbol:
        return None
    if len(symbol) == 1:
        symbol = symbol.upper()
    else:
        symbol = symbol[0].upper() + symbol[1:].lower()
    return symbol if symbol in METAL_ELEMENTS else None


def _normalize_metals(values: Any) -> Optional[List[str]]:
    if not isinstance(values, list):
        return None

    normalized: List[str] = []
    seen = set()
    for value in values:
        symbol = _normalize_metal_symbol(value)
        if symbol and symbol not in seen:
            normalized.append(symbol)
            seen.add(symbol)

    return normalized or None


def normalize_doi(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_answer(
    text: str,
    schema: PropertySchema,
    *,
    return_reason: bool = False,
) -> Any:
    def _ret(payload: Any, reason: str) -> Any:
        return (payload, reason) if return_reason else payload

    if not text:
        return _ret(None, "empty_response")

    stripped = text.strip()
    if stripped == "INVALID":
        return _ret(None, "model_returned_INVALID")

    match = JSON_BLOCK_REGEX.search(stripped)
    if not match:
        if "INVALID" in stripped:
            return _ret(None, "model_returned_INVALID")
        return _ret(None, "no_json_object_found")

    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        return _ret(None, "json_decode_error")

    metals = _normalize_metals(data.get("metals"))
    if not metals:
        return _ret(None, "missing_or_invalid_metals")

    property_type = str(
        data.get("property_type")
        or data.get("property")
        or data.get("feature_type")
        or ""
    ).strip()
    if _normalize_property_label(property_type) != _normalize_property_label(schema.property_type):
        return _ret(None, "property_type_mismatch")

    metric_value = data.get(schema.metric_field)
    if metric_value is None:
        for alias in schema.metric_aliases:
            if alias in data:
                metric_value = data.get(alias)
                break

    normalized_metric = schema.metric_validator(metric_value)
    if not normalized_metric:
        return _ret(None, "missing_or_invalid_metric")

    return _ret(
        {
            "metals": metals,
            "property_type": schema.property_type,
            schema.metric_field: normalized_metric,
        },
        "ok",
    )


def build_prompt(schema: PropertySchema, abstract: str) -> str:
    return PROMPT_TEMPLATE.format(
        property_type=schema.property_type,
        metric_prompt=schema.metric_prompt,
        json_template=json.dumps(schema.output_template, ensure_ascii=False, indent=2),
        abstract=abstract.strip(),
    )


def build_chat_request_body(
    schema: PropertySchema,
    abstract: str,
    *,
    model: str,
    temperature: float,
    thinking_enabled: bool,
) -> Dict[str, Any]:
    return {
        "model": model,
        "messages": [{"role": "user", "content": build_prompt(schema, abstract)}],
        "temperature": temperature,
        # DashScope docs note that Qwen3/Qwen3.5 models enable thinking by default.
        "enable_thinking": bool(thinking_enabled),
    }


def _message_to_text(message: Any) -> str:
    if isinstance(message, dict):
        content = message.get("content", "")
    else:
        content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content") or ""
                if text:
                    parts.append(str(text))
            else:
                text = getattr(item, "text", None)
                if text:
                    parts.append(str(text))
        return "\n".join(parts).strip()
    return str(content or "")


def get_client(api_key: str, base_url: str) -> Any:
    try:
        from openai import OpenAI
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            'Missing dependency "openai". Activate the venv and run: pip install -r requirements.txt'
        ) from exc

    return OpenAI(base_url=base_url, api_key=api_key)


def call_model(
    client: Any,
    schema: PropertySchema,
    abstract: str,
    *,
    model: str,
    temperature: float,
    thinking_enabled: bool,
    max_retries: int,
) -> str:
    last_error: Optional[Exception] = None

    for attempt in range(1, max_retries + 1):
        try:
            request_body = build_chat_request_body(
                schema,
                abstract,
                model=model,
                temperature=temperature,
                thinking_enabled=thinking_enabled,
            )
            kwargs: Dict[str, Any] = {
                "model": request_body["model"],
                "messages": request_body["messages"],
                "temperature": request_body["temperature"],
                "extra_body": {"enable_thinking": request_body["enable_thinking"]},
            }
            response = client.chat.completions.create(**kwargs)
            return _message_to_text(response.choices[0].message)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt >= max_retries:
                break
            time.sleep(min(2 ** (attempt - 1), 8))

    assert last_error is not None
    raise last_error


def prepare_batch_input_file(
    schema: PropertySchema,
    input_path: Path,
    output_dir: Path,
    *,
    model: str,
    temperature: float,
    thinking_enabled: bool,
    max_rows: Optional[int],
    request_limit: Optional[int],
) -> Dict[str, Any]:
    file_output_dir = output_dir / schema.key
    file_output_dir.mkdir(parents=True, exist_ok=True)
    batch_input_path = file_output_dir / "batch_requests.jsonl"
    request_map_path = file_output_dir / "batch_request_map.json"

    rows_seen = 0
    requests_written = 0
    skipped_empty_abstract = 0
    skipped_missing_doi = 0
    request_map: Dict[str, Dict[str, Any]] = {}

    with batch_input_path.open("w", encoding="utf-8") as handle:
        for row_number, row in iter_xlsx_rows(input_path):
            if max_rows is not None and rows_seen >= max_rows:
                break
            if request_limit is not None and requests_written >= request_limit:
                break

            rows_seen += 1
            abstract = clean_abstract(row.get("abstract", ""))
            if not abstract:
                skipped_empty_abstract += 1
                continue

            doi = normalize_doi(row.get("doi"))
            if not doi:
                skipped_missing_doi += 1
                continue

            custom_id = str(row_number)
            request_map[custom_id] = {
                "row_number": row_number,
                "doi": doi,
            }
            request_body = build_chat_request_body(
                schema,
                abstract,
                model=model,
                temperature=temperature,
                thinking_enabled=thinking_enabled,
            )
            batch_record = {
                "custom_id": custom_id,
                "method": "POST",
                "url": CHAT_COMPLETIONS_ENDPOINT,
                "body": request_body,
            }
            handle.write(json.dumps(batch_record, ensure_ascii=False) + "\n")
            requests_written += 1

    request_map_path.write_text(json.dumps(request_map, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "schema": schema.key,
        "input_file": input_path.name,
        "batch_input_file": str(batch_input_path),
        "request_map_file": str(request_map_path),
        "rows_seen": rows_seen,
        "requests_written": requests_written,
        "skipped_empty_abstract": skipped_empty_abstract,
        "skipped_missing_doi": skipped_missing_doi,
    }


def wait_for_batch_completion(client: Any, batch_id: str, poll_interval: int) -> Any:
    terminal_statuses = {"completed", "failed", "cancelled", "expired"}
    while True:
        batch = client.batches.retrieve(batch_id)
        status = getattr(batch, "status", None)
        if status in terminal_statuses:
            return batch
        time.sleep(max(1, poll_interval))


def download_file(client: Any, file_id: str, destination: Path) -> None:
    content = client.files.content(file_id)
    content.write_to_file(destination)


def split_batch_input_file(
    batch_input_path: Path,
    request_map_path: Path,
    file_output_dir: Path,
    *,
    max_requests: int,
) -> List[Dict[str, Any]]:
    if max_requests <= 0:
        raise ValueError("batch max requests must be positive")

    request_map = json.loads(request_map_path.read_text(encoding="utf-8"))
    total_requests = sum(1 for line in batch_input_path.read_text(encoding="utf-8").splitlines() if line.strip())
    if total_requests <= max_requests:
        return [
            {
                "part_number": 1,
                "request_count": total_requests,
                "batch_input_file": str(batch_input_path),
                "request_map_file": str(request_map_path),
            }
        ]

    for stale_path in file_output_dir.glob("batch_requests.part*.jsonl"):
        stale_path.unlink()
    for stale_path in file_output_dir.glob("batch_request_map.part*.json"):
        stale_path.unlink()
    for stale_path in file_output_dir.glob("batch_output_raw.part*.jsonl"):
        stale_path.unlink()
    for stale_path in file_output_dir.glob("batch_error_raw.part*.jsonl"):
        stale_path.unlink()

    parts: List[Dict[str, Any]] = []
    part_number = 0
    part_count = 0
    current_handle: Optional[Any] = None
    current_batch_input_path: Optional[Path] = None
    current_request_map: Dict[str, Dict[str, Any]] = {}

    def close_part() -> None:
        nonlocal current_handle, current_batch_input_path, current_request_map, part_count
        if current_handle is None or current_batch_input_path is None:
            return
        current_handle.close()
        current_request_map_path = file_output_dir / f"batch_request_map.part{part_number:03d}.json"
        current_request_map_path.write_text(
            json.dumps(current_request_map, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        parts.append(
            {
                "part_number": part_number,
                "request_count": part_count,
                "batch_input_file": str(current_batch_input_path),
                "request_map_file": str(current_request_map_path),
            }
        )
        current_handle = None
        current_batch_input_path = None
        current_request_map = {}
        part_count = 0

    with batch_input_path.open("r", encoding="utf-8") as source_handle:
        for raw_line in source_handle:
            line = raw_line.strip()
            if not line:
                continue

            if current_handle is None or part_count >= max_requests:
                close_part()
                part_number += 1
                current_batch_input_path = file_output_dir / f"batch_requests.part{part_number:03d}.jsonl"
                current_handle = current_batch_input_path.open("w", encoding="utf-8")

            current_handle.write(line + "\n")
            item = json.loads(line)
            custom_id = str(item.get("custom_id") or "")
            if custom_id in request_map:
                current_request_map[custom_id] = request_map[custom_id]
            part_count += 1

    close_part()
    return parts


def parse_batch_output_file(
    schema: PropertySchema,
    output_file_path: Path,
    request_map: Dict[str, Dict[str, Any]],
    results_path: Path,
    debug_path: Path,
    *,
    results_mode: str = "w",
) -> Counter:
    summary = Counter()

    with (
        output_file_path.open("r", encoding="utf-8") as raw_handle,
        results_path.open(results_mode, encoding="utf-8") as results_handle,
        debug_path.open("a", encoding="utf-8") as debug_handle,
    ):
        for raw_line in raw_handle:
            line = raw_line.strip()
            if not line:
                continue
            summary["batch_lines_seen"] += 1

            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                summary["batch_json_decode_error"] += 1
                debug_handle.write(json.dumps({"reason": "batch_json_decode_error", "raw_head": line[:500]}, ensure_ascii=False) + "\n")
                continue

            custom_id = str(item.get("custom_id") or "")
            request_meta = request_map.get(custom_id, {})
            response = item.get("response") or {}
            status_code = response.get("status_code")
            body = response.get("body") or {}

            if status_code != 200:
                summary["batch_http_error"] += 1
                debug_handle.write(
                    json.dumps(
                        {
                            "row_number": request_meta.get("row_number"),
                            "doi": request_meta.get("doi"),
                            "reason": "batch_http_error",
                            "status_code": status_code,
                            "body": body,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                continue

            choices = body.get("choices") or []
            message = (choices[0] or {}).get("message") if choices else None
            raw_text = _message_to_text(message)
            parsed, reason = parse_answer(raw_text, schema, return_reason=True)
            if not parsed:
                summary[reason] += 1
                debug_handle.write(
                    json.dumps(
                        {
                            "row_number": request_meta.get("row_number"),
                            "doi": request_meta.get("doi"),
                            "reason": reason,
                            "raw_head": raw_text[:800],
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                continue

            out_record = {
                "row_number": request_meta.get("row_number"),
                "doi": normalize_doi(request_meta.get("doi")),
                "metals": parsed["metals"],
                "application_name": parsed["property_type"],
                schema.metric_field: parsed[schema.metric_field],
            }
            if not out_record["doi"]:
                summary["missing_doi"] += 1
                debug_handle.write(
                    json.dumps(
                        {
                            "row_number": request_meta.get("row_number"),
                            "doi": request_meta.get("doi"),
                            "reason": "missing_doi",
                            "raw_head": raw_text[:800],
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                continue
            results_handle.write(json.dumps(out_record, ensure_ascii=False) + "\n")
            summary["kept"] += 1

    return summary


def append_batch_error_file(
    error_file_path: Path,
    request_map: Dict[str, Dict[str, Any]],
    debug_path: Path,
) -> Counter:
    summary = Counter()
    if not error_file_path.exists():
        return summary

    with (
        error_file_path.open("r", encoding="utf-8") as raw_handle,
        debug_path.open("a", encoding="utf-8") as debug_handle,
    ):
        for raw_line in raw_handle:
            line = raw_line.strip()
            if not line:
                continue
            summary["batch_error_lines_seen"] += 1
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                summary["batch_error_json_decode_error"] += 1
                debug_handle.write(json.dumps({"reason": "batch_error_json_decode_error", "raw_head": line[:500]}, ensure_ascii=False) + "\n")
                continue

            custom_id = str(item.get("custom_id") or "")
            request_meta = request_map.get(custom_id, {})
            debug_handle.write(
                json.dumps(
                    {
                        "row_number": request_meta.get("row_number"),
                        "doi": request_meta.get("doi"),
                        "reason": "batch_error_file_entry",
                        "detail": item,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    return summary


def clean_abstract(raw_abstract: Any) -> str:
    if not isinstance(raw_abstract, str):
        return ""
    text = html.unescape(raw_abstract)
    text = HTML_TAG_RE.sub(" ", text)
    text = SPACE_RE.sub(" ", text)
    return text.strip()


def _column_letters_to_index(cell_ref: str) -> int:
    match = CELL_REF_RE.match(cell_ref or "")
    if not match:
        return 0

    index = 0
    for char in match.group(1):
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index - 1


def _xlsx_shared_strings(archive: ZipFile) -> List[str]:
    path = "xl/sharedStrings.xml"
    if path not in archive.namelist():
        return []

    root = ET.fromstring(archive.read(path))
    strings: List[str] = []
    for item in root.findall("main:si", XML_NS):
        text = "".join(
            node.text or ""
            for node in item.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")
        )
        strings.append(text)
    return strings


def _resolve_sheet_path(archive: ZipFile) -> str:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    rel_map = {rel.attrib["Id"]: rel.attrib["Target"] for rel in relationships}
    sheets = workbook.find("main:sheets", XML_NS)
    if sheets is None or len(sheets) == 0:
        raise ValueError("Workbook has no sheets")

    first_sheet = next(iter(sheets))
    rel_id = first_sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
    target = rel_map[rel_id]
    if target.startswith("/"):
        return target.lstrip("/")
    if target.startswith("xl/"):
        return target
    return f"xl/{target}"


def iter_xlsx_rows(path: Path) -> Iterator[Tuple[int, Dict[str, str]]]:
    with ZipFile(path) as archive:
        shared_strings = _xlsx_shared_strings(archive)
        sheet_path = _resolve_sheet_path(archive)
        sheet = ET.fromstring(archive.read(sheet_path))
        sheet_data = sheet.find("main:sheetData", XML_NS)
        if sheet_data is None:
            return

        rows = sheet_data.findall("main:row", XML_NS)
        if not rows:
            return

        header_values = _extract_row_values(rows[0], shared_strings)
        headers = [value.strip() for value in header_values]
        if not any(headers):
            raise ValueError(f"No header row found in {path.name}")

        for row in rows[1:]:
            row_values = _extract_row_values(row, shared_strings)
            if not any(value.strip() for value in row_values):
                continue

            padded = row_values + [""] * max(0, len(headers) - len(row_values))
            payload = {headers[index]: padded[index] if index < len(padded) else "" for index in range(len(headers))}
            row_number = int(row.attrib.get("r", "0") or 0)
            yield row_number, payload


def _extract_row_values(row: ET.Element, shared_strings: Sequence[str]) -> List[str]:
    values: List[str] = []
    cursor = 0
    for cell in row.findall("main:c", XML_NS):
        ref = cell.attrib.get("r", "")
        column_index = _column_letters_to_index(ref)
        while cursor < column_index:
            values.append("")
            cursor += 1

        cell_type = cell.attrib.get("t")
        inline = cell.find("main:is", XML_NS)
        if inline is not None:
            text = "".join(
                node.text or ""
                for node in inline.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")
            )
        else:
            value_node = cell.find("main:v", XML_NS)
            if value_node is None:
                text = ""
            else:
                text = value_node.text or ""
                if cell_type == "s" and text.isdigit():
                    index = int(text)
                    text = shared_strings[index] if 0 <= index < len(shared_strings) else ""

        values.append(text)
        cursor += 1
    return values


def record_id_for_row(source_file: str, row_number: int, row: Dict[str, str]) -> str:
    for key in ("openalex_id", "doi", "title"):
        value = (row.get(key) or "").strip()
        if value:
            return value
    return f"{source_file}#{row_number}"


def load_processed_ids(output_path: Path) -> set:
    processed = set()
    if not output_path.exists():
        return processed

    with output_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            row_number = data.get("row_number")
            if row_number is not None:
                processed.add(str(row_number))
    return processed


def process_file(
    client: Any,
    schema: PropertySchema,
    input_path: Path,
    output_dir: Path,
    *,
    model: str,
    temperature: float,
    thinking_enabled: bool,
    max_retries: int,
    max_rows: Optional[int],
    keep_limit: Optional[int],
    resume: bool,
    request_interval: float,
    verbose: bool,
) -> Dict[str, Any]:
    file_output_dir = output_dir / schema.key
    file_output_dir.mkdir(parents=True, exist_ok=True)
    output_path = file_output_dir / "results.jsonl"
    debug_path = file_output_dir / "debug.jsonl"
    summary = Counter()

    processed_ids = load_processed_ids(output_path) if resume else set()
    output_mode = "a" if resume and output_path.exists() else "w"
    debug_mode = "a" if resume and debug_path.exists() else "w"

    with (
        output_path.open(output_mode, encoding="utf-8") as out_handle,
        debug_path.open(debug_mode, encoding="utf-8") as debug_handle,
    ):
        for row_index, row in tqdm(iter_xlsx_rows(input_path), desc=schema.key):
            if max_rows is not None and summary["rows_seen"] >= max_rows:
                break
            if keep_limit is not None and summary["kept"] >= keep_limit:
                break

            summary["rows_seen"] += 1
            record_id = record_id_for_row(input_path.name, row_index, row)
            row_id = str(row_index)

            if resume and row_id in processed_ids:
                summary["skipped_resume"] += 1
                continue

            abstract = clean_abstract(row.get("abstract", ""))
            if not abstract:
                summary["skipped_empty_abstract"] += 1
                continue

            doi = normalize_doi(row.get("doi"))
            if not doi:
                summary["skipped_missing_doi"] += 1
                debug_handle.write(
                    json.dumps(
                        {
                            "record_id": record_id,
                            "source_file": input_path.name,
                            "row_number": row_index,
                            "reason": "missing_doi",
                            "abstract_head": abstract[:500],
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                continue

            try:
                raw_response = call_model(
                    client,
                    schema,
                    abstract,
                    model=model,
                    temperature=temperature,
                    thinking_enabled=thinking_enabled,
                    max_retries=max_retries,
                )
            except Exception as exc:  # noqa: BLE001
                summary[f"api_error:{type(exc).__name__}"] += 1
                debug_handle.write(
                    json.dumps(
                        {
                            "record_id": record_id,
                            "source_file": input_path.name,
                            "row_number": row_index,
                            "reason": f"api_error:{type(exc).__name__}",
                            "error": str(exc),
                            "abstract_head": abstract[:500],
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                continue

            parsed, reason = parse_answer(raw_response, schema, return_reason=True)
            if not parsed:
                summary[reason] += 1
                debug_handle.write(
                    json.dumps(
                        {
                            "record_id": record_id,
                            "source_file": input_path.name,
                            "row_number": row_index,
                            "reason": reason,
                            "raw_head": raw_response[:800],
                            "abstract_head": abstract[:500],
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                continue

            out_record = {
                "row_number": row_index,
                "doi": doi,
                "metals": parsed["metals"],
                "application_name": parsed["property_type"],
                schema.metric_field: parsed[schema.metric_field],
            }
            out_handle.write(json.dumps(out_record, ensure_ascii=False) + "\n")
            summary["kept"] += 1
            processed_ids.add(row_id)

            if verbose and summary["kept"] % 10 == 0:
                print(f"[{schema.key}] kept={summary['kept']} seen={summary['rows_seen']}")

            if request_interval > 0:
                time.sleep(request_interval)

    summary_payload = {
        "schema": schema.key,
        "input_file": input_path.name,
        "output_file": str(output_path),
        "debug_file": str(debug_path),
        "summary": dict(summary),
    }
    summary_path = file_output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary_payload


def process_file_batch(
    client: Optional[Any],
    schema: PropertySchema,
    input_path: Path,
    output_dir: Path,
    *,
    model: str,
    temperature: float,
    thinking_enabled: bool,
    max_rows: Optional[int],
    request_limit: Optional[int],
    batch_prepare_only: bool,
    wait_batch: bool,
    batch_completion_window: str,
    batch_poll_interval: int,
    batch_max_requests: int,
) -> Dict[str, Any]:
    file_output_dir = output_dir / schema.key
    file_output_dir.mkdir(parents=True, exist_ok=True)
    results_path = file_output_dir / "results.jsonl"
    debug_path = file_output_dir / "debug.jsonl"
    batch_job_path = file_output_dir / "batch_job.json"
    batch_output_raw_path = file_output_dir / "batch_output_raw.jsonl"
    batch_error_raw_path = file_output_dir / "batch_error_raw.jsonl"

    if results_path.exists():
        results_path.unlink()
    if debug_path.exists():
        debug_path.unlink()

    prepared = prepare_batch_input_file(
        schema,
        input_path,
        output_dir,
        model=model,
        temperature=temperature,
        thinking_enabled=thinking_enabled,
        max_rows=max_rows,
        request_limit=request_limit,
    )
    summary = {
        "schema": schema.key,
        "mode": "batch",
        "model": model,
        **prepared,
        "results_file": str(results_path),
        "debug_file": str(debug_path),
    }
    batch_parts = split_batch_input_file(
        Path(prepared["batch_input_file"]),
        Path(prepared["request_map_file"]),
        file_output_dir,
        max_requests=batch_max_requests,
    )
    summary["batch_max_requests"] = batch_max_requests
    summary["batch_parts"] = batch_parts

    if prepared["requests_written"] == 0:
        summary["batch_status"] = "no_requests"
        batch_job_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        (file_output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        return summary

    if batch_prepare_only:
        summary["batch_status"] = "prepared_only"
        batch_job_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        (file_output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        return summary

    if client is None:
        raise ValueError("Batch mode submission requires an API client")

    chunk_summaries: List[Dict[str, Any]] = []
    aggregate_summary = Counter()
    wrote_results = False

    for batch_part in batch_parts:
        batch_input_path = Path(batch_part["batch_input_file"])
        request_map = json.loads(Path(batch_part["request_map_file"]).read_text(encoding="utf-8"))
        input_file = client.files.create(file=batch_input_path, purpose="batch")
        batch = client.batches.create(
            input_file_id=input_file.id,
            endpoint=CHAT_COMPLETIONS_ENDPOINT,
            completion_window=batch_completion_window,
        )

        chunk_summary = {
            "part_number": batch_part["part_number"],
            "request_count": batch_part["request_count"],
            "batch_input_file": str(batch_input_path),
            "request_map_file": batch_part["request_map_file"],
            "input_file_id": input_file.id,
            "batch_id": batch.id,
            "batch_status": getattr(batch, "status", None),
        }
        chunk_summaries.append(chunk_summary)
        summary["batch_jobs"] = chunk_summaries
        if len(chunk_summaries) == 1:
            summary["input_file_id"] = input_file.id
            summary["batch_id"] = batch.id
            summary["batch_status"] = getattr(batch, "status", None)
        else:
            summary["batch_status"] = "submitted"
        batch_job_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

        if not wait_batch:
            continue

        final_batch = wait_for_batch_completion(client, batch.id, batch_poll_interval)
        chunk_summary["batch_status"] = getattr(final_batch, "status", None)
        chunk_summary["output_file_id"] = getattr(final_batch, "output_file_id", None)
        chunk_summary["error_file_id"] = getattr(final_batch, "error_file_id", None)

        part_number = batch_part["part_number"]
        part_output_raw_path = file_output_dir / f"batch_output_raw.part{part_number:03d}.jsonl"
        part_error_raw_path = file_output_dir / f"batch_error_raw.part{part_number:03d}.jsonl"

        if chunk_summary["output_file_id"]:
            download_file(client, chunk_summary["output_file_id"], part_output_raw_path)
            part_summary = parse_batch_output_file(
                schema,
                part_output_raw_path,
                request_map,
                results_path,
                debug_path,
                results_mode="a" if wrote_results else "w",
            )
            aggregate_summary.update(part_summary)
            wrote_results = wrote_results or bool(part_summary.get("kept"))

        if chunk_summary["error_file_id"]:
            download_file(client, chunk_summary["error_file_id"], part_error_raw_path)
            aggregate_summary.update(append_batch_error_file(part_error_raw_path, request_map, debug_path))

        if chunk_summary["batch_status"] != "completed":
            aggregate_summary[f"batch_status:{chunk_summary['batch_status']}"] += 1

        summary["batch_jobs"] = chunk_summaries
        summary["batch_status"] = "completed" if all(
            part.get("batch_status") == "completed" for part in chunk_summaries
        ) else "partial"
        if len(chunk_summaries) == 1:
            summary["output_file_id"] = chunk_summary.get("output_file_id")
            summary["error_file_id"] = chunk_summary.get("error_file_id")
        summary.update(dict(aggregate_summary))
        batch_job_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    if wait_batch:
        summary["batch_status"] = "completed" if all(
            part.get("batch_status") == "completed" for part in chunk_summaries
        ) else "partial"
        summary.update(dict(aggregate_summary))

    (file_output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    batch_job_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def resolve_schemas(selected_keys: Sequence[str]) -> List[PropertySchema]:
    if not selected_keys:
        return list(SCHEMAS.values())

    resolved = []
    for key in selected_keys:
        schema = SCHEMAS.get(key)
        if schema is None:
            valid = ", ".join(sorted(SCHEMAS))
            raise ValueError(f'Unknown property "{key}". Valid values: {valid}')
        resolved.append(schema)
    return resolved


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract material-property metrics and metal elements from XLSX abstracts with Alibaba DashScope Qwen.",
    )
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR, help="Directory containing the XLSX files.")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR, help="Directory to write JSONL outputs.")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_ENV_FILE,
        help="Optional .env file that contains DASHSCOPE_API_KEY.",
    )
    parser.add_argument("--api-key", default=None, help="DashScope API key. Overrides DASHSCOPE_API_KEY.")
    parser.add_argument(
        "--api-key-env",
        default=DEFAULT_API_KEY_ENV,
        help="Environment variable name for the DashScope API key.",
    )
    parser.add_argument("--base-url", default=None, help="DashScope OpenAI-compatible base URL.")
    parser.add_argument(
        "--model",
        default=None,
        help=(
            "Model name. Common options: "
            f"{MODEL_OPTIONS[0]} or {MODEL_OPTIONS[1]}. "
            f"Defaults to {DEFAULT_MODEL_ENV} or {DEFAULT_MODEL}."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=("realtime", "batch"),
        default="realtime",
        help="Use direct online requests or DashScope batch jobs.",
    )
    parser.add_argument(
        "--property",
        action="append",
        default=[],
        help="Property key to process. Repeat this flag to select multiple properties.",
    )
    parser.add_argument("--max-rows", type=int, default=None, help="Maximum rows to scan per XLSX file.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum valid rows to keep per XLSX file.")
    parser.add_argument("--temperature", type=float, default=0.0, help="Sampling temperature.")
    parser.add_argument(
        "--thinking",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable or disable DashScope thinking mode. Default: disabled.",
    )
    parser.add_argument("--reasoning", dest="thinking", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--no-reasoning", dest="thinking", action="store_false", help=argparse.SUPPRESS)
    parser.add_argument("--max-retries", type=int, default=3, help="Max retries per API call.")
    parser.add_argument(
        "--request-interval",
        type=float,
        default=0.0,
        help="Sleep seconds between successful requests.",
    )
    parser.add_argument(
        "--batch-prepare-only",
        action="store_true",
        help="In batch mode, only create local batch request files and do not submit them.",
    )
    parser.add_argument(
        "--wait-batch",
        action="store_true",
        help="In batch mode, wait for the submitted job to finish and download/parse outputs.",
    )
    parser.add_argument(
        "--batch-completion-window",
        default=DEFAULT_BATCH_COMPLETION_WINDOW,
        help="DashScope batch completion window, for example 24h.",
    )
    parser.add_argument(
        "--batch-poll-interval",
        type=int,
        default=DEFAULT_BATCH_POLL_INTERVAL,
        help="Seconds between batch status polls when --wait-batch is enabled.",
    )
    parser.add_argument(
        "--batch-max-requests",
        type=int,
        default=DEFAULT_BATCH_MAX_REQUESTS,
        help="Maximum requests per DashScope batch file. Default: 50000.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Append to existing output files and skip record_id values already written.",
    )
    parser.add_argument("--verbose", action="store_true", help="Print extra progress information.")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    load_env_file(args.env_file)

    env_api_key = os.getenv(args.api_key_env)
    legacy_api_key = os.getenv(LEGACY_API_KEY_ENV)
    api_key = args.api_key or env_api_key or legacy_api_key
    base_url = args.base_url or os.getenv("DASHSCOPE_BASE_URL") or DEFAULT_BASE_URL
    model = args.model or os.getenv(DEFAULT_MODEL_ENV) or DEFAULT_MODEL
    if not args.api_key and not env_api_key and legacy_api_key:
        print(
            f"Warning: using legacy {LEGACY_API_KEY_ENV} as the DashScope API key source. "
            f"Please rename it to {args.api_key_env} in your .env file.",
            file=sys.stderr,
        )
    if args.mode != "batch" or not args.batch_prepare_only:
        if not api_key:
            print(
                f"Missing API key. Set {args.api_key_env} in the environment or pass --api-key.",
                file=sys.stderr,
            )
            return 2
    elif not api_key:
        print(
            "No API key found. Proceeding because --mode batch --batch-prepare-only only writes local files.",
            file=sys.stderr,
        )

    if args.mode == "batch" and args.resume:
        print(
            "Batch mode ignores --resume. Reuse the generated batch request files or batch job metadata instead.",
            file=sys.stderr,
        )

    data_dir = args.data_dir.resolve()
    output_dir = args.output_dir.resolve()

    if not data_dir.exists():
        print(f"Data directory does not exist: {data_dir}", file=sys.stderr)
        return 2

    try:
        schemas = resolve_schemas(args.property)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    client: Optional[Any] = None
    if api_key:
        client = get_client(api_key, base_url)
    all_summaries = []

    for schema in schemas:
        input_path = data_dir / schema.input_filename
        if not input_path.exists():
            print(f"Skipping missing file: {input_path}", file=sys.stderr)
            continue

        print(f"Processing {schema.key} from {input_path.name}")
        if args.mode == "batch":
            summary = process_file_batch(
                client,
                schema,
                input_path,
                output_dir,
                model=model,
                temperature=args.temperature,
                thinking_enabled=args.thinking,
                max_rows=args.max_rows,
                request_limit=args.limit,
                batch_prepare_only=args.batch_prepare_only,
                wait_batch=args.wait_batch,
                batch_completion_window=args.batch_completion_window,
                batch_poll_interval=args.batch_poll_interval,
                batch_max_requests=args.batch_max_requests,
            )
        else:
            assert client is not None
            summary = process_file(
                client,
                schema,
                input_path,
                output_dir,
                model=model,
                temperature=args.temperature,
                thinking_enabled=args.thinking,
                max_retries=args.max_retries,
                max_rows=args.max_rows,
                keep_limit=args.limit,
                resume=args.resume,
                request_interval=args.request_interval,
                verbose=args.verbose,
            )
        all_summaries.append(summary)

        if args.mode == "batch":
            print(
                f"  rows_seen={summary.get('rows_seen', 0)} requests_written={summary.get('requests_written', 0)} "
                f"batch_status={summary.get('batch_status')}"
            )
            if summary.get("batch_input_file"):
                print(f"  batch_input={summary['batch_input_file']}")
            if summary.get("request_map_file"):
                print(f"  request_map={summary['request_map_file']}")
            if summary.get("batch_id"):
                print(f"  batch_id={summary['batch_id']}")
            if summary.get("results_file"):
                print(f"  results={summary['results_file']}")
            if summary.get("debug_file"):
                print(f"  debug={summary['debug_file']}")
        else:
            counter = Counter(summary["summary"])
            print(
                f"  rows_seen={counter.get('rows_seen', 0)} kept={counter.get('kept', 0)} "
                f"empty_abstract={counter.get('skipped_empty_abstract', 0)}"
            )
            failure_items = [
                (key, value)
                for key, value in counter.items()
                if key not in {"rows_seen", "kept", "skipped_empty_abstract"}
            ]
            if failure_items:
                top_failures = ", ".join(f"{key}={value}" for key, value in sorted(failure_items))
                print(f"  other={top_failures}")
            print(f"  output={summary['output_file']}")
            print(f"  debug={summary['debug_file']}")

    if not all_summaries:
        print("No files were processed.", file=sys.stderr)
        return 1

    summary_path = output_dir / "run_summary.json"
    summary_path.write_text(json.dumps(all_summaries, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Run summary written to {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
