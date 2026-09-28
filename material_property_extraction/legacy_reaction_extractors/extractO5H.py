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

2) Reaction type: MUST be exactly "O5H".
   - O5H refers to electrochemical oxidation of
     5-hydroxymethylfurfural (HMF), typically to FDCA.
   - If the abstract is not about HMF oxidation, output INVALID.

3) Performance metrics:
   - Extract the Faradaic efficiency (%) specifically reported
     for the O5H (HMF oxidation) reaction.
     * May be described as "Faradaic efficiency" or "FE".
   - Ignore Faradaic efficiency or performance metrics
     of ALL other reactions.

4) The experimental environment is alkaline (pH > 7).
   - If the abstract mentions ANY acidic conditions, sulfuric acid, or perchloric acid,
     output INVALID (do not extract anything).
   - Examples of acidic mentions include: acidic, H2SO4, sulfuric acid, HClO4, perchloric acid, 酸性, 硫酸, 高氯酸.

5) Optional metrics (ONLY if explicitly reported for O5H):
   - HMF conversion (%).
   - FDCA yield (%).

If ANY of the following cannot be determined:
- the reaction is not O5H,
- there are NO metal element catalysts,
- Faradaic efficiency (%) for the O5H reaction is NOT reported,
- the experimental environment is acidic (or mentions sulfuric/perchloric acid),

output exactly:
INVALID

Output exactly in JSON:
{{
  "metals": ["M1","M2"],
  "reaction_type": "O5H",
  "Faradaic_efficiency": "xx%",
  "HMF_conversion": null,
  "FDCA_yield": null
}}

Abstract:
\"\"\"{abstract}\"\"\"
"""

# —— Response 解析正则
JSON_BLOCK_REGEX = re.compile(r"\{.*?\}", re.S)
PERCENT_RE = re.compile(r"^\d+(\.\d+)?\s*%$")
METAL_SYMBOL_RE = re.compile(r"^[A-Z][a-z]?$")

# —— Acidic-condition prefilter
# Skip papers explicitly mentioning acidic conditions/electrolytes, sulfuric acid, or perchloric acid.
# Note: avoid matching the generic word "acid" because many O5H papers mention FDCA ("furandicarboxylic acid").
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
    fe = data.get("Faradaic_efficiency")
    hmf_conv = data.get("HMF_conversion")
    fdca_yield = data.get("FDCA_yield")

    # —— 1️⃣ 金属元素必须存在（硬条件）
    if not isinstance(metals, list) or len(metals) == 0:
        return _ret(None, "missing_or_empty_metals")
    if not all(isinstance(x, str) and METAL_SYMBOL_RE.match(x) for x in metals):
        return _ret(None, "invalid_metal_symbol")

    # —— 2️⃣ 反应类型必须是 O5H
    if rxn != "O5H":
        return _ret(None, "reaction_type_not_O5H")

    # —— 3️⃣ FE 必须存在，且是百分数（硬条件）
    if not isinstance(fe, str) or not PERCENT_RE.match(fe):
        return _ret(None, "missing_or_invalid_Faradaic_efficiency")

    # —— 4️⃣ OPTIONAL 指标：只在存在时校验
    if hmf_conv is not None:
        if not isinstance(hmf_conv, str) or not PERCENT_RE.match(hmf_conv):
            hmf_conv = None

    if fdca_yield is not None:
        if not isinstance(fdca_yield, str) or not PERCENT_RE.match(fdca_yield):
            fdca_yield = None

    return _ret({
        "metals": metals,
        "reaction_type": "O5H",
        "Faradaic_efficiency": fe,
        "HMF_conversion": hmf_conv,
        "FDCA_yield": fdca_yield
    }, "ok")

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

def process_tsv(
    tsv_file,
    out_file,
    limit=1000,
    verbose=False,
    debug_out_file="debug_o5h_failures.jsonl",
    max_rows=None,
):
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
                        print("WARN: 缺失 index 或 abstract，跳过")
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
                        print(f"WARN: 第{id}条 API 调用失败: {type(e).__name__}: {e}")
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
                        print(f"WARN: 第{id}条 解析失败, reason={reason}")
                    continue

                # —— 写入结果
                out = {
                    "id": row["index"],
                    "metals": parsed["metals"],
                    "reaction_type": parsed["reaction_type"],
                    "Faradaic_efficiency": parsed["Faradaic_efficiency"],
                    "HMF_conversion": parsed["HMF_conversion"],
                    "FDCA_yield": parsed["FDCA_yield"]
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

    print("处理完成")
    print(f"读取行数: {read_count}")
    print(f"保留样本: {kept}")
    print(f"跳过行数: {skipped}")
    if skipped:
        print("跳过原因统计（Top 15）:")
        for reason, count in failure_counts.most_common(15):
            print(f"  - {reason}: {count}")
        print(f"失败样本已写入: {debug_out_file}")

if __name__ == "__main__":
    # Debug-friendly defaults:
    # - limit: how many valid items to keep
    # - max_rows: how many rows to scan at most (optional)
    process_tsv(
        "2-cleaned-abstracts-about-O5H.tsv",
        "results_o5h.jsonl",
        limit=20,
        max_rows=None,
        verbose=False,
    )
