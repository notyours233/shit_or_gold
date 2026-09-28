import os
import csv
import re
import json
from collections import Counter
from tqdm import tqdm
from openai import OpenAI


# —— 从环境变量读取 API Key
API_KEY = os.getenv("DASHSCOPE_API_KEY") or os.getenv("OPENROUTER_API_KEY") or ""

if not API_KEY:
    raise ValueError("❌ API_KEY 不能为空")

# —— 设定 Qwen3 API 客户端
client = OpenAI(
    api_key=API_KEY,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"  
)

#2) Reaction type (like OER, HER, ORR, CO2RR, EOR, HOR, HZOR, O5H, UOR),and only ONE reaction type,
# —— Prompt 模板
PROMPT = """
You are an expert in electrochemical catalysis literature analysis.

Given the abstract of a scientific paper, extract ONLY the following JSON with EXACT format:

1) Metal element catalysts(chemical symbols).
   - Must be chemical metal element symbols (e.g. Fe, Ni, Co).
   - Sort by importance or emphasis in the abstract reaction.
   - Exactly different elements.
2) Reaction type: MUST be exactly "HOR".
   - HOR refers to the hydrogen oxidation reaction.
   - If the abstract is not about HOR, output INVALID.

3) Performance metrics (any ONE is sufficient; extract whatever is explicitly reported for HOR):
   3.1) Exchange current density (j0), unit mA cm-2.
        - Sometimes written as exchange current density, j0, or j₀.
        - Normalize to: "xx mA cm-2"
   3.2) Overpotential at 10 mA cm-2, unit V (normalized to x.xx V).
        - May be reported as "xx mV at 10 mA cm-2"; convert to V in the output.
   3.3) Overpotential at 50 mA cm-2, unit V (normalized to x.xx V).
        - May be reported as "xx mV at 50 mA cm-2"; convert to V in the output.
   - Ignore metrics of other reactions.

4) The experimental environment is alkaline (pH > 7).
   - If the abstract mentions ANY acidic conditions, sulfuric acid, or perchloric acid,
     output INVALID (do not extract anything).
   - Examples of acidic mentions include: acidic, H2SO4, sulfuric acid, HClO4, perchloric acid, 酸性, 硫酸, 高氯酸.

If ANY of the following is true, output exactly INVALID:
- the reaction is not HOR,
- there are NO metal element catalysts,
- none of the metrics (j0, overpotential@10, overpotential@50) are reported for HOR,
- the abstract mentions acidic conditions / sulfuric acid / perchloric acid.

Output exactly in JSON:
{{
  "metals": ["M1","M2"],
  "reaction_type": "HOR",
  "exchange_current_density": null,
  "overpotential_10mAcm-2": null,
  "overpotential_50mAcm-2": null
}}

Abstract:
\"\"\"{abstract}\"\"\"
"""

# —— Response 解析正则
JSON_BLOCK_REGEX = re.compile(r"\{.*?\}", re.S)
METAL_SYMBOL_RE = re.compile(r"^[A-Z][a-z]?$")

# —— Acidic-condition prefilter
# Skip papers explicitly mentioning acidic conditions/electrolytes, sulfuric acid, or perchloric acid.
# Note: avoid matching the generic word "acid" because many catalysis abstracts mention products like "acid".
ACIDIC_HINT_RE = re.compile(
    r"("
    r"\bacidic\b|"
    r"\bacidic\s+(?:conditions?|electrolyte|medium|environment)\b|"
    r"\bH2SO4\b|"
    r"\bHClO4\b|"
    r"\bsulfuric\s+acid\b|"
    r"\bperchloric\s+acid\b|"
    r"酸性|"
    r"硫酸|"
    r"高氯酸"
    r")",
    re.IGNORECASE,
)


def should_skip_acidic(abstract: str) -> bool:
    if not abstract:
        return False
    return ACIDIC_HINT_RE.search(abstract) is not None


def _normalize_units(value: str) -> str:
    if not isinstance(value, str):
        return value
    normalized = (
        value.replace("cm−2", "cm-2")
        .replace("cm⁻2", "cm-2")
        .replace("mA·cm-2", "mA cm-2")
        .replace("mA/cm2", "mA cm-2")
        .replace("mA cm−2", "mA cm-2")
    )
    return normalized.strip()


J0_RE = re.compile(r"^\d+(\.\d+)?\s*mA\s*cm-2$", re.IGNORECASE)
V_RE = re.compile(r"^\d+(\.\d+)?\s*V$", re.IGNORECASE)
MV_RE = re.compile(r"^\d+(\.\d+)?\s*mV$", re.IGNORECASE)

# —— 解析返回结构
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
    j0 = data.get("exchange_current_density")
    op10 = data.get("overpotential_10mAcm-2")
    op50 = data.get("overpotential_50mAcm-2")

    # Backward-compatible keys (older runs)
    if op10 is None:
        op10 = data.get("overpotential_10mAcm2")
    if op50 is None:
        op50 = data.get("overpotential_50mAcm2")

    if not isinstance(metals, list) or len(metals) == 0:
        return _ret(None, "missing_or_empty_metals")
    if not all(isinstance(x, str) and METAL_SYMBOL_RE.match(x) for x in metals):
        return _ret(None, "invalid_metal_symbol")

    if rxn != "HOR":
        return _ret(None, "reaction_type_not_HOR")

    if j0 is not None:
        j0 = _normalize_units(j0)
        if not isinstance(j0, str) or not J0_RE.match(j0):
            j0 = None

    if op10 is not None:
        op10 = _normalize_units(op10)
        if isinstance(op10, str) and MV_RE.match(op10):
            op10 = f"{float(op10.lower().replace('mv','').strip())/1000:.2f} V"
        if not isinstance(op10, str) or not V_RE.match(op10):
            op10 = None

    if op50 is not None:
        op50 = _normalize_units(op50)
        if isinstance(op50, str) and MV_RE.match(op50):
            op50 = f"{float(op50.lower().replace('mv','').strip())/1000:.2f} V"
        if not isinstance(op50, str) or not V_RE.match(op50):
            op50 = None

    if j0 is None and op10 is None and op50 is None:
        return _ret(None, "no_valid_HOR_metric_found")

    return _ret(
        {
            "metals": metals,
            "reaction_type": "HOR",
            "exchange_current_density": j0,
            "overpotential_10mAcm-2": op10,
            "overpotential_50mAcm-2": op50,
        },
        "ok",
    )

# —— 单次调用 Qwen3
def extract_info(abstract: str):
    prompt = PROMPT.format(abstract=abstract.strip())
    response = client.chat.completions.create(
        model="qwen3-max",  # 或者 qwen3-instruct / qwen3
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1
    )
    return response.choices[0].message.content

# —— 主处理流程
# def process_tsv(tsv_file, out_file, limit=1000):
#     kept = 0
#     count = 0
#     with open(tsv_file, "r", encoding="utf-8") as f_in, open(out_file, "w", encoding="utf-8") as f_out:
#         reader = csv.DictReader(f_in, delimiter="\t")
#         if "abstract" not in reader.fieldnames or "index" not in reader.fieldnames:
#             raise ValueError("TSV 文件需要包含 index 和 abstract 两列")

#         for row in tqdm(reader):
#             if kept >= limit:
#                 break

#             abstract = row["abstract"]
#             if not abstract.strip():
#                 continue

#             id = row["index"]
#             raw = extract_info(abstract)
#             parsed = parse_answer(raw)
#             if not parsed:
#                 print(f"第 {id} 条文献摘要没有信息")
#                 continue

#             kept += 1

#             out = {
#                 "id": row["index"],
#                 "metals": parsed["metals"],
#                 "reaction_type": parsed["reaction_type"],
#                 "overpotential": parsed["overpotential"]
#             }
#             f_out.write(json.dumps(out, ensure_ascii=False) + "\n")

#             count += 1

#     print(f"Finished! Kept {count} valid items.")

def process_tsv(tsv_file, out_file, limit=1000, verbose=False, debug_out_file="debug_hor_failures.jsonl", max_rows=None):
    kept = 0
    read_count = 0
    skipped = 0
    failure_counts = Counter()

    with open(tsv_file, "r", encoding="utf-8", errors="ignore") as f_in, \
         open(out_file, "w", encoding="utf-8") as f_out, \
         open(debug_out_file, "w", encoding="utf-8") as f_debug:

        try:
            reader = csv.DictReader(f_in, delimiter="\t")
        except Exception as e:
            raise RuntimeError(f"❌ 无法解析 TSV 表头: {e}")

        # 表头检查
        if "index" not in reader.fieldnames or "abstract" not in reader.fieldnames:
            raise ValueError("❌ TSV 文件必须包含 index 和 abstract 两列")

        for row in tqdm(reader):
            if max_rows is not None and read_count >= max_rows:
                break
            if kept >= limit:
                break

            read_count += 1

            try:
                # —— 字段存在性检查
                paper_id = row.get("index", None)
                abstract = row.get("abstract", None)

                if paper_id is None or abstract is None:
                    skipped += 1
                    failure_counts["missing_index_or_abstract"] += 1
                    if verbose:
                        print("⚠️ 缺失 index 或 abstract，跳过")
                    continue

                # —— abstract 类型与内容检查
                if not isinstance(abstract, str):
                    skipped += 1
                    failure_counts["abstract_not_string"] += 1
                    continue

                abstract = abstract.strip()
                if not abstract:
                    skipped += 1
                    failure_counts["empty_abstract"] += 1
                    continue

                if should_skip_acidic(abstract):
                    skipped += 1
                    failure_counts["acidic_condition_filtered"] += 1
                    f_debug.write(
                        json.dumps(
                            {"id": row["index"], "reason": "acidic_condition_filtered", "abstract_head": abstract[:240]},
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                    continue


                # —— 调用 Qwen3
                id = row["index"]
                try:
                    raw = extract_info(abstract)
                except Exception as e:
                    skipped += 1
                    reason = f"api_error:{type(e).__name__}"
                    failure_counts[reason] += 1
                    f_debug.write(
                        json.dumps(
                            {"id": id, "reason": reason, "error": str(e), "abstract_head": abstract[:240]},
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                    if verbose:
                        print(f"WARN: id={id} API error: {type(e).__name__}: {e}")
                    continue

                parsed, reason = parse_answer(raw, return_reason=True)

                if not parsed:
                    skipped += 1
                    failure_counts[reason] += 1
                    f_debug.write(
                        json.dumps(
                            {"id": id, "reason": reason, "raw_head": (raw or "")[:400]},
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                    if verbose:
                        print(f"WARN: id={id} parse failed, reason={reason}")
                    continue

                # —— 写入结果
                out = {
                    "id": row["index"],
                    "metals": parsed["metals"],
                    "reaction_type": parsed["reaction_type"],
                    "exchange_current_density": parsed["exchange_current_density"],
                    "overpotential_10mAcm-2": parsed["overpotential_10mAcm-2"],
                    "overpotential_50mAcm-2": parsed["overpotential_50mAcm-2"],
                }

                f_out.write(json.dumps(out, ensure_ascii=False) + "\n")
                kept += 1

            except Exception as e:
                # ⭐ 任何行级错误都在这里吞掉
                skipped += 1
                reason = f"row_exception:{type(e).__name__}"
                failure_counts[reason] += 1
                if verbose:
                    print(f"WARN: 行解析失败，已跳过: {type(e).__name__}: {e}")
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
        "2-cleaned-abstracts-about-HOR.tsv",
        "results_hor.jsonl",
        limit=20,
        verbose=False,
    )
