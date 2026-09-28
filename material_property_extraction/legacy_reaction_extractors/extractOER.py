import os
import csv
import json
import re
from collections import Counter

try:
    from tqdm import tqdm
except ModuleNotFoundError:
    def tqdm(iterable, *args, **kwargs):
        return iterable


API_KEY = os.getenv("DASHSCOPE_API_KEY") or os.getenv("OPENROUTER_API_KEY") or ""

if not API_KEY:
    raise ValueError("API_KEY cannot be empty")

_CLIENT = None


def _get_client():
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT

    try:
        from openai import OpenAI
    except ModuleNotFoundError as e:
        raise ModuleNotFoundError(
            'Missing dependency "openai". Activate your venv or run: pip install openai'
        ) from e

    _CLIENT = OpenAI(
        api_key=API_KEY,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    return _CLIENT


PROMPT = """
You are an expert in electrochemical catalysis literature analysis.

Given the abstract of a scientific paper, extract ONLY the following JSON with EXACT format:

1) Metal element catalysts (chemical symbols).
   - Must be chemical metal element symbols (e.g. Fe, Ni, Co).
   - Sort by importance or emphasis in the abstract reaction.
   - Exactly different elements.

2) Reaction type: MUST be exactly "OER".
   - OER refers to the oxygen evolution reaction.
   - If the abstract is not about OER, output INVALID.

3) Performance metrics for OER:
   - Focus on overpotentials (η) at specific current densities.
   - Extract overpotentials at:
       * 10 mA cm-2  (η10)
       * 20 mA cm-2  (η20)
       * 100 mA cm-2 (η100)
   - Any ONE of (η10, η20, η100) is sufficient (extract whatever is explicitly reported).
   - Unit: V (normalized to x.xx V). The abstract may report in mV; convert to V in the output.
   - IMPORTANT: In the JSON output, each overpotential value MUST be a string like "0.31 V" (not a bare number).
   - The abstract may phrase as:
       * "overpotential of XX mV at 10 mA cm-2"
       * "η10 = XX mV"
        * "potential at 10 mA cm-2" (if clearly an overpotential for OER)
    - Ignore metrics of other reactions.

4) The experimental environment is alkaline (pH > 7).
   - If the abstract mentions ANY acidic conditions, sulfuric acid, or perchloric acid,
     output INVALID (do not extract anything).
   - Examples of acidic mentions include: acidic, H2SO4, sulfuric acid, HClO4, perchloric acid.

If ANY of the following is true, output exactly INVALID:
- the reaction is not OER,
- there are NO metal element catalysts,
- none of the overpotentials (η10/η20/η100) are reported for OER,
- the abstract mentions acidic conditions / sulfuric acid / perchloric acid.

Output exactly in JSON:
{{
  "metals": ["M1","M2"],
  "reaction_type": "OER",
  "overpotential_10mAcm-2": null,
  "overpotential_20mAcm-2": null,
  "overpotential_100mAcm-2": null
}}

Abstract:
\"\"\"{abstract}\"\"\"
"""


JSON_BLOCK_REGEX = re.compile(r"\{.*?\}", re.S)
METAL_SYMBOL_RE = re.compile(r"^[A-Z][a-z]?$")

def _normalize_units(value: str):
    if not isinstance(value, str):
        return value
    normalized = (
        value.replace("cm−2", "cm-2")
        .replace("cm–2", "cm-2")
        .replace("cm⁻2", "cm-2")
        .replace("mA·cm-2", "mA cm-2")
        .replace("mA/cm2", "mA cm-2")
        .replace("mA cm−2", "mA cm-2")
        .replace("mA cm–2", "mA cm-2")
        .replace("mA cm⁻2", "mA cm-2")
    )
    return normalized.strip()


V_RE = re.compile(r"^\d+(\.\d+)?\s*V$", re.IGNORECASE)
MV_RE = re.compile(r"^\d+(\.\d+)?\s*mV$", re.IGNORECASE)
NUMBER_ONLY_RE = re.compile(r"^\d+(\.\d+)?$", re.IGNORECASE)


def _format_v(value_v: float) -> str:
    if value_v != value_v:  # NaN guard
        return None
    if value_v < 0:
        return None
    return f"{value_v:.2f} V"


def _coerce_overpotential_to_v(value):
    if value is None:
        return None

    # Models sometimes return bare numbers (e.g., 0.31) instead of "0.31 V".
    # Heuristic:
    # - <= 10: treat as volts
    # - > 10: treat as millivolts
    if isinstance(value, (int, float)):
        number = float(value)
        if number < 0:
            return None
        if number > 10:
            return _format_v(number / 1000.0)
        return _format_v(number)

    value = _normalize_units(value)
    if not isinstance(value, str):
        return None

    if V_RE.match(value):
        number_v = float(value.lower().replace("v", "").strip())
        return _format_v(number_v)

    if MV_RE.match(value):
        number_mv = float(value.lower().replace("mv", "").strip())
        return _format_v(number_mv / 1000.0)

    if NUMBER_ONLY_RE.match(value.strip()):
        number = float(value.strip())
        if number < 0:
            return None
        if number > 10:
            return _format_v(number / 1000.0)
        return _format_v(number)

    return None


def parse_answer(text, *, return_reason=False):
    def _ret(value, reason):
        if return_reason:
            return value, reason
        return value

    if not text:
        return _ret(None, "empty_response")

    if text.strip() == "INVALID":
        return _ret(None, "model_returned_INVALID")

    m = JSON_BLOCK_REGEX.search(text)
    if not m:
        return _ret(None, "no_json_object_found")

    try:
        data = json.loads(m.group())
    except json.JSONDecodeError:
        return _ret(None, "json_decode_error")

    metals = data.get("metals")
    rxn = data.get("reaction_type")
    op10 = data.get("overpotential_10mAcm-2")
    op20 = data.get("overpotential_20mAcm-2")
    op100 = data.get("overpotential_100mAcm-2")

    # Backward-compatible keys (older variants, if any)
    if op10 is None:
        op10 = data.get("overpotential_10mAcm2")
    if op20 is None:
        op20 = data.get("overpotential_20mAcm2")
    if op100 is None:
        op100 = data.get("overpotential_100mAcm2")

    if not isinstance(metals, list) or len(metals) == 0:
        return _ret(None, "missing_or_empty_metals")
    if not all(isinstance(x, str) and METAL_SYMBOL_RE.match(x) for x in metals):
        return _ret(None, "invalid_metal_symbol")

    if rxn != "OER":
        return _ret(None, "reaction_type_not_OER")

    op10 = _coerce_overpotential_to_v(op10)
    op20 = _coerce_overpotential_to_v(op20)
    op100 = _coerce_overpotential_to_v(op100)

    if op10 is None and op20 is None and op100 is None:
        return _ret(None, "no_valid_OER_overpotential_found")

    return _ret(
        {
            "metals": metals,
            "reaction_type": "OER",
            "overpotential_10mAcm-2": op10,
            "overpotential_20mAcm-2": op20,
            "overpotential_100mAcm-2": op100,
        },
        "ok",
    )


def extract_info(abstract: str):
    prompt = PROMPT.format(abstract=abstract.strip())
    client = _get_client()
    response = client.chat.completions.create(
        model="qwen3-max",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )
    return response.choices[0].message.content


def process_tsv(tsv_file, out_file, debug_out_file="debug_oer_failures.jsonl", limit=1000, max_rows=None, verbose=False):
    kept = 0
    read_count = 0
    skipped = 0
    failure_counts = Counter()

    with (
        open(tsv_file, "r", encoding="utf-8", errors="ignore") as f_in,
        open(out_file, "w", encoding="utf-8") as f_out,
        open(debug_out_file, "w", encoding="utf-8") as f_debug,
    ):
        try:
            reader = csv.DictReader(f_in, delimiter="\t")
        except Exception as e:
            raise RuntimeError(f"Failed to parse TSV header: {e}")

        if "index" not in reader.fieldnames or "abstract" not in reader.fieldnames:
            raise ValueError('TSV must include "index" and "abstract" columns')

        for row in tqdm(reader):
            if max_rows is not None and read_count >= max_rows:
                break
            if kept >= limit:
                break

            read_count += 1

            try:
                paper_id = row.get("index", None)
                abstract = row.get("abstract", None)

                if paper_id is None or abstract is None:
                    skipped += 1
                    failure_counts["missing_index_or_abstract"] += 1
                    continue

                if not isinstance(abstract, str):
                    skipped += 1
                    failure_counts["abstract_not_string"] += 1
                    continue

                abstract = abstract.strip()
                if not abstract:
                    skipped += 1
                    failure_counts["empty_abstract"] += 1
                    continue

                try:
                    raw = extract_info(abstract)
                except Exception as e:
                    skipped += 1
                    reason = f"api_error:{type(e).__name__}"
                    failure_counts[reason] += 1
                    f_debug.write(
                        json.dumps(
                            {"id": paper_id, "reason": reason, "error": str(e), "abstract_head": abstract[:240]},
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                    if verbose:
                        print(f"WARN: id={paper_id} API error: {type(e).__name__}: {e}")
                    continue

                parsed, reason = parse_answer(raw, return_reason=True)
                if not parsed:
                    skipped += 1
                    failure_counts[reason] += 1
                    f_debug.write(
                        json.dumps(
                            {"id": paper_id, "reason": reason, "raw_head": (raw or "")[:400]},
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                    if verbose:
                        print(f"WARN: id={paper_id} parse failed, reason={reason}")
                    continue

                out = {
                    "id": paper_id,
                    "metals": parsed["metals"],
                    "reaction_type": parsed["reaction_type"],
                    "overpotential_10mAcm-2": parsed["overpotential_10mAcm-2"],
                    "overpotential_20mAcm-2": parsed["overpotential_20mAcm-2"],
                    "overpotential_100mAcm-2": parsed["overpotential_100mAcm-2"],
                }

                f_out.write(json.dumps(out, ensure_ascii=False) + "\n")
                kept += 1

            except Exception as e:
                skipped += 1
                reason = f"row_exception:{type(e).__name__}"
                failure_counts[reason] += 1
                if verbose:
                    print(f"WARN: row failed: {type(e).__name__}: {e}")
                continue

    print("Done")
    print(f"Read rows: {read_count}")
    print(f"Kept items: {kept}")
    print(f"Skipped rows: {skipped}")
    if skipped:
        print("Skip reasons (Top 15):")
        for reason, count in failure_counts.most_common(15):
            print(f"  - {reason}: {count}")
        print(f"Debug written to: {debug_out_file}")


if __name__ == "__main__":
    process_tsv(
        "2-cleaned-abstracts-about-OER.tsv",
        "results_oer.jsonl",
        limit=20,
        max_rows=None,
        verbose=False,
    )
