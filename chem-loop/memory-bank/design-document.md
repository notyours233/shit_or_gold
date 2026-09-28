# 设计文档：ChemCouncil 闭环（推荐反应 + 实验数据回流更新经验库）

本设计文档描述 **ChemCouncil** 单仓库的闭环系统如何工作，以及我们在“格式保障 / 经验蒸馏 / 经验检索”上的关键决策。

核心原则（你已确认）：
1) **格式要求移出经验蒸馏目标**：格式/结构化输出是“静态 prompt + API/工具调用结构化 + 自动修复”的职责，不应主导经验库内容。
2) **经验蒸馏目标优先产出化学可复用经验**：经验库应该是“可迁移的化学启发/规律/边界条件/反例”，而不是大量“输出格式须知”。
3) **GRPO 与 MAD 职责分离**：GRPO 由单个预测智能体独立采样多个候选，再经真值 verify/reward 蒸馏经验；MAD 的提案、评审、反驳和共识只用于推荐端。

相关规范（细节以 spec 为准）：
- 数据契约：`spec-bank/chem_dataset_contract.md`、`spec-bank/experimental_csv_contract.md`
- 指标词表：`spec-bank/chem_metrics_keys.md`
- 数据处理规则：`spec-bank/data_processing_rules.md`
- verify 行为：`spec-bank/chem_verify_spec.md`
- 闭环工作流：`spec-bank/closed_loop_workflow.md`

---

## 1. 系统组成（Monorepo）

- `chemcouncil/`：Web 后端（aiohttp）+ 静态前端（实验同学使用）
  - 把“推荐反应（MAD rank）”与“经验回流（实验数据 -> GRPO 更新 experience.yaml）”封装为可取消 Job
- `MAD/`：多智能体排序/辩论（rank + debate traces），可选 Chroma 文献 RAG
- `youtu-chem-loop/`：单智能体 Training-Free GRPO + verify + 数据导入/处理；保留 MAD 外部适配器仅供历史评估兼容
- `state/`：Docker/Web 持久化目录（镜像里不包含 DB/Chroma）

---

## 2. 任务定义（材料性能，19 个方向）

每条当前样本只预测一个性能方向。输入以材料为中心：

- **唯一必填**：`material_name`。
- **可选实验人员字段**：材料类别、组分、结构关系、前驱体、投料比、制备方式、金属和非金属元素、元素含量、测试条件和 `custom_prompt`。
- **允许输入方式**：结构化字段、只填材料名加一段自定义提示词、或二者混用。
- **缺失处理**：只省略缺失字段，不能写 `unspecified`，也不能从材料名推断元素后冒充为用户填写的信息。

统一 `INPUT_JSON` 至少包含：

```json
{
  "material_name": "CuO",
  "material_description": "材料是CuO。",
  "task_type": "HER",
  "metrics_to_predict": [{"key": "overpotential_10mAcm-2", "unit_hint": "mV"}]
}
```

结构化字段存在时，`material_description` 按实验人员填写的内容组装；`custom_prompt` 作为额外材料数据保留在 JSON 中。它不可以覆盖系统提示词、检索规则、辩论协议或 JSON 输出合同。

19 个方向为：
`HER, OER, ORR, HOR, UOR, EOR, HZOR, O5H, CO2RR, photothermal_conversion_efficiency, conductivity, thermal_conductivity, ferromagnetism, ferrimagnetism, antiferromagnetism, photocatalytic_h2o2, antibacterial, thermoelectric, furfural_hydrogenation`。

模型输出仍为一个 JSON 对象：每个 `metrics_to_predict` key 对应一个不带单位的纯数字。CO2RR 在当前材料名合同中属于一个 `CO2RR` 方向；历史金属数据的旧产品/部分电流子任务只保留作兼容读取。

推荐阶段沿用旧的多智能体框架：一个 `task_type` 对应一场独立的 `PROPOSE -> REVIEW -> REBUTTAL -> 程序校验/共识` 辩论。选择全部方向时，外层运行 19 场独立辩论，再以各任务的规范化得分排序；不在同一场辩论中混合预测多个方向。

---

## 3. Ground Truth（GT）与 Verify 契约

GT 的存放与解析（核心约束）：
- GT 存在 `DatasetSample.answer` / `EvaluationSample.correct_answer`（JSON dict 字符串）
- GT 的 value 允许是“带单位的原始字符串”（verify 解析数值前缀）
- verify 计算 `reward ∈ [0, 1]`，并记录可选 `reasoning` 用于经验蒸馏

更细的对齐/缺失/额外 key 的规则见：
- `spec-bank/chem_verify_spec.md`

---

## 4. 模型输出契约（模型 -> 系统）与“格式保障”策略

你提出的要求是“内容里不强制 `<think>/<answer>` 标签，但必须结构化地有 `think` 与 `answer` 字段”，并且希望 80–90%+ 可解析率。

我们把“格式保障”拆成三层（静态 + API/工具调用 + 自动修复）：

### 4.1 静态 Prompt（hard rules）

目的：让模型在大多数情况下直接按正确结构输出。

实现位置（MAD 外部引擎路径）：
- `youtu-chem-loop/utu/external_engines/mad_runner.py`：
  - `_build_system_prompt(...)` 中定义了强约束规则
  - 明确要求：最终用 `conclude` 工具提交 **STRICT JSON**

### 4.2 API/工具调用层结构化输出（强制结构）

目的：尽可能让“最终答案”走 **工具调用参数** 这个结构化通道，而不是依赖自然语言内容解析。

契约（首选形态）：
```json
{
  "think": "short reasoning (string)",
  "answer": { "metric_key": 123.4 }
}
```

约束：
- `answer` 必须是 JSON dict：
  - 回归指标：value 必须是 **纯数字**
  - CO2RR Task 1（product + FE）：推荐形态是 `{"product": "<LABEL>", "faradaic_efficiency": <fraction>}`
    - 若该条历史 GT 只有 product，也允许只输出 `{"product": "<LABEL>"}`
- key 必须与 `metrics_to_predict` 完全一致（不缺不多）

在 MAD 路径中，这个结构化输出由 `conclude(conclusion=...)` 的工具参数承载。

### 4.3 自动修复（best-effort repair）

目的：当模型偏离格式时，尽量把“已经给出的结构化信息”救回来，避免全批次 reward=0。

实现位置：
- `youtu-chem-loop/utu/external_engines/mad_engine.py`：
  - `_normalize_structured_output(...)`：把结构化 JSON 转成 legacy `<think>/<answer>`（兼容历史 verify）
  - `_ensure_answer_block(...)`：缺 `<answer>` 时的保底修复（不凭空造数，只做包裹/抽取）
- `youtu-chem-loop/utu/practice/verify/chem_performance_lib/answer_parser.py`：
  - 同时支持解析 legacy tags 与结构化 JSON（见 verify spec）

说明：
- **verify 不再把“有没有 `<think>` 标签”当作 reward=0 的硬门槛**。
  格式应该主要由 “静态 prompt + 工具调用结构化 + 自动修复” 兜底。

---

## 5. 经验库策略：蒸馏目标（化学经验）与检索方式（工具检索）

### 5.1 我们要的经验是什么

经验库目标（优先级从高到低）：
1) **化学相关可复用经验**：合金化趋势、反应特异性规律、指标间关联、常见反例、适用边界。
2) 简短的 unit sanity checks（作为辅助，不应主导经验库）。
3) 工具使用纪律（经验检索 / 文献检索何时用、如何避免 off-target 证据）。

另外（你最新确认的方向）：经验要尽量做成**可检索的微经验卡（micro-card）**，避免“空泛大原则”。
- 每条经验采用可检索 `MaterialCard`：`TASK`、`MATERIAL`、`ELEMENTS`、`TARGET`、`ANCHOR`、`CONTEXT`、`TAKEAWAY`、`HOW_TO_USE`、`CAVEATS`、`APPLIES`。
  元素、条件和合成信息只有在源数据存在时才写入；缺失时直接省略，不写 `unspecified`，不编造边界。
- 我们允许经验库变大（几百条甚至更多），因为后续是通过 `search_experience` 做检索，而不是把全部经验塞进 prompt。

经验蒸馏实现注意（避免“吞卡/过度压缩”）：
- 当我们要求经验卡是 paragraph（多句、较长）时，若在 batch update 阶段再让 LLM “汇总/重写所有操作”，很容易因为 token 限制导致输出截断，最终经验条数反而变少。
- 因此我们默认用**确定性应用（deterministic apply）**：直接把 group update 产生的 ADD/UPDATE/DELETE 操作应用到经验池（只做保守去重），保证经验池能随数据增长。
- 如确需回到旧的 LLM consolidation（更激进的合并/改写），可通过环境变量切换：`UTU_EXPERIENCE_BATCH_UPDATE_MODE=llm`。
- 经验质量保底（清理碎片卡）：在个别 run 中，可能会混入“过短/空壳/跑偏”的 guideline（例如只有标题、只有 `APPLIES=...`，甚至出现非化学内容）。
  - 在把某次 run 产物 promote 为稳定 pack 前，建议执行一次 **最小长度清洗**（例如 `<200 chars` 直接删除）并保留报告，避免检索时“占坑但没信息”。
  - 脚本：`project/chem-loop/scripts/clean_agent_experiences.py`（只清理以行首 `^[G\\d+].` 开始的块，不会误删正文引用）。

对照实验支持（宽泛经验 vs 化学微经验卡）：
- 我们保留两套“经验蒸馏 prompt pack”，用于验证经验风格对闭环效果的影响：
  - `UTU_EXPERIENCE_PROMPT_PACK=chem`（默认）：化学 micro-card 风格（更具体、可检索、带锚点）
  - `UTU_EXPERIENCE_PROMPT_PACK=generic`：旧版宽泛经验（更抽象、更偏格式/方法）
  - 实现：`youtu-chem-loop/utu/practice/experience_updater.py` 根据 env 选择 `utu/prompts/practice/experience*.yaml`

格式/结构化输出注意事项：
- 只保留极少量“几乎总成立”的格式提醒，放在静态 prompt（或少量 guideline），不把它作为蒸馏主目标。
- 闭环导出稳定 experience pack 时，会对 guideline 做一次“去格式化”归一：
  - 自动剔除主要讲输出格式/标签/JSON 键对齐的 guideline（避免经验库被格式经验淹没）
  - 统一重写 `agent.instructions` 的头部为 chem-loop 的静态说明（输入字段 + 输出契约 + 化学经验列表）
  - 实现：`youtu-chem-loop/scripts/closed_loop/export_experience_yaml.py`（默认开启 `--normalize_chem_loop`）

### 5.2 GRPO 与推荐端如何使用经验

核心约束：**GRPO rollout 不运行多智能体辩论，也不把整份经验库塞进 prompt**。

- GRPO：单智能体从材料提示词预测一个性能方向；可选调用一次经过 DOI 遮蔽的文献检索。group reward 计算完成后，`ExperienceUpdater` 才读取候选轨迹和真值并更新经验库。
- 推荐端：MAD 在单个性能方向内进行提案、评审和反驳，并通过 `search_experience` 检索已经生成的稳定 guideline。

实现点：
- GRPO 侧不拼接经验到 prompt，也不调用 `search_experience`：
  - `youtu-chem-loop/utu/eval/processer/training_free_grpo_processor.py`
- MAD 侧经验检索：
  - `MAD` 的 `ExperienceStore` 提供 `search_experience`
  - `mad_runner.py` 会在 ACTION phase 里强制“先检索经验，再 conclude”（避免跳过检索）

### 5.3 经验 pack 的文件形态（稳定 pack + per-step pack）

1) 稳定 experience pack（闭环共用）：
- `youtu-chem-loop/configs/agents/practice/experience.yaml`
- `MAD/experience/experience.yaml`
- 旧版本归档：`MAD/experience/archive/<timestamp>_<tag>/experience.yaml`

补充（实验同学友好 / 防污染）：
- ChemCouncil Web 会把历史 pack 作为“可切换版本”暴露出来：
  - `GET /api/experience/history`：列出 `MAD/experience/archive/` 下的 pack
  - `POST /api/experience/activate/{archive_id}`：把某个 archive pack 激活为当前生效版本
- 激活操作是“可回退”的：在覆盖当前 pack 前，会先把当前版本再备份到 archive（`rollback_<ts>_before_<archive_id>`）
- 典型用途：用户回流时填错实验数据导致经验库被污染 → 先 rollback 到未污染版本 → 再重新回流正确数据

2) 旧的 GRPO per-step MAD pack 已停用：
- GRPO 不再写 `MAD_EXPERIENCE_PACK_PATH`，也不会在 rollout 中启动 MAD。
- 每批经验仍写入 DB cache；完整运行结束后再导出稳定 pack 并同步给推荐端。

### 5.4 经验检索算法：从“组件 Jaccard”升级到“材料语义向量相似度”

你确认了一个关键问题：仅靠元素或组分重叠做经验检索，会导致检索结果：
- **偏泛**：只要元素相同就会命中，但可能是完全不同的材料、方向或指标
- **偏格式**：query 里包含很多 “STRICT JSON / key matching” 等格式 token 时，会把“格式类经验”排到前面
- **偏不相关**：忽略 `material_name / material_description / task_type / metrics_to_predict / product` 后，经验很难精准对齐当前任务

因此我们在 MAD 的 `ExperienceStore` 中新增了向量检索模式：
- `search_mode: vector`：对 **query_text** 与经验条目（guideline + case）的文本 blob 做 embedding，并用 cosine similarity 排序。
- 仍保留旧模式 `search_mode: jaccard` 作为兜底（embedding 失败 / 无 key 时不会阻塞系统）。

配置位置：
- MAD 配置：`MAD/config/config.yaml` -> `experience.search_mode`
- embedding backend（支持 env override）：
  - `experience.embedding_provider`: `voyage | hash`
  - `experience.embedding_model`: e.g. `voyage-3-lite`
  - 缓存：`MAD_EXPERIENCE_EMBED_CACHE_PATH`（默认优先 `/state/experience_embed_cache.json`）

为了避免 embedding 被“格式 token”牵引，我们同时把 `search_experience` 工具的 query 构造改成：
- 优先从任务 prompt 的 `INPUT_JSON` 抽取 `material_name / material_description / task_type / metrics_to_predict / product`
- 只附加化学/指标相关 hint，不附加 “STRICT JSON” 类格式提示词

---

## 6. 实验数据回流：增量更新与 batch_size 策略

你已选择：**增量更新**。

含义：
- 原有性能数据（base dataset）不需要每次都重新跑一遍“从零开始”的 GRPO；
- 新实验数据作为一个新 dataset 上传到 DB 后，GRPO 以 `--seed_experience_yaml` 的经验 pack 为起点，
  在小数据上做 incremental update，产出更新后的 `experience.yaml`。
- 如果本次实验反馈关联到了之前的推荐记录，并且推荐时保存了 per-reaction debate traces，
  则会再做一个**误差对齐蒸馏**步骤：
  - 不是直接把原始推荐轨迹“原样蒸馏”；
  - 而是把 `预测轨迹 + 预测值 + 实验真值` 对齐起来，显式告诉蒸馏器这次预测偏高/偏低了多少；
  - 对 CO2RR，如果 recommendation summary / feedback row 中有 `product` 与 `faradaic_efficiency`，也会一并带入纠偏蒸馏；
- 这样第二阶段的目标就是“减少未来预测误差”，而不是只保留推荐时的辩论过程。

实验反馈 CSV 的新首选字段为 `material_name`、`material_input_json`、`task_type`、`value` 和 `unit`。
`elements` 可选，且仅保存实验人员或原始推荐输入显式提供的值。旧 `metals` CSV 仍可导入，但不是新回流合同的前提。

关于“实验数据条数不足/每次条数不一样”的影响（现阶段约束与解释）：
- 条数越少，经验蒸馏越不稳定（波动更大、更容易过拟合到偶然样本）。
- 因此我们现阶段把 `batch_size` 做成 **固定并硬检查**，避免随意改导致难以比较。
  - Web 后端通过 `CHEMCOUNCIL_EXPERIENCE_BATCH_SIZE` 固定 batch_size（当前 19 方向 held-out 测试选定值为 19）。
  - GRPO runner 本身支持“小于 batch_size 的数据也能跑完”（最后一批做 partial batch）。
- Web 反馈默认组合与当前测试对齐为 `epochs=1`、`batch_size=19`、`grpo_n=3`、`rollout_concurrency=4`、`RAG=1`；少量实验反馈仍允许以 partial batch 更新。

### 6.1 19 方向正式经验库生成门控

超参实验已经选择固定组合：`batch_size=19`、`grpo_n=3`、`epochs=1`、`RAG=1`、
`rollout_concurrency=4`。正式数据每个方向 50 条，共 950 个问题、2,850 条预测 rollout。运行入口另固定
单次 rollout attempt 的 `task_timeout=300` 秒；它不是超参，只用于把偶发长连接交给现有重试逻辑。

正式集不是从 11,291 条母数据直接截断得到。专用采样器会先排除现有 57 条超参验证集所涉及的
全部文章，再按稀缺方向优先分配，并在 19 个方向全局强制 `doc_id` 唯一。生成 manifest 必须证明：
19 个方向各 50 条、950 个唯一文献、与 held-out 的 sample/doc overlap 均为 0。

正式入口按以下门控执行：

1. `--prepare-only`：生成并按有序 sample ID 校验/上传独立数据集，不调用模型。
2. `--canary-only`：用 19 条数据、每方向 1 条、`grpo_n=3` 运行单智能体端到端 canary。
3. `--formal` / `--resume`：只有 canary audit 为 pass 才能首次启动或恢复 950 条正式运行。
4. `--promote`：只有正式 audit 为 pass 且经验卡覆盖 19/19 方向时，才归档旧 pack 并同步新 pack。

canary 和正式运行都从空经验种子开始；运行期间不修改推荐端稳定经验库。审计按 sample ID、rollout
数量、任务覆盖、输出解析、reward、单智能体轨迹、provider 错误、经验卡和稳定 pack 哈希逐项检查，
而不是只看进程退出码或数据库行数。

---

## 7. MAD 排序/辩论：单方向材料性能推荐 + 文献 RAG（可选）

推荐（rank）默认策略（面向实验同学）：
- 默认比较全部 19 个性能方向，也可由实验人员选择一个方向或一个方向子集。
- 外层调度字段保留为用户可控参数：`top_k_properties`（前端 Top-K 方向数）和
  `max_parallel_properties`（同时评估方向数）；两者都会写入推荐 Job payload，并在执行时按所选方向数
  做上限截断。旧的 `top_k_reactions` / `max_parallel_reactions` 仍作为兼容别名。
- 每个方向都启动独立的一场四智能体 `PROPOSE -> REVIEW -> REBUTTAL -> 共识` 辩论；这三个控件只控制
  外层有多少场独立辩论以及汇总多少结果，不会让一场辩论混合多个性能方向。
- 默认保存每个方向的完整辩论/轨迹（用于后续反馈误差对齐和经验蒸馏）。
- 跨方向汇总先将各任务原始指标按自己的单位、优劣方向和等级阈值映射为 unit-free
  `normalized_score`，再进行 `ranking`/`top_k` 排序；不同任务的原始数值不直接相互比较。

文献 RAG（Chroma）：
- 是否启用：`MAD_ENABLE_RAG=1/0`
- 内存模式（env-only switch）：
  - 测试/低内存：`MAD_RAG_MODE=shared`
  - 服务器/高内存：`MAD_RAG_MODE=per_agent`（或 unset）

重要提醒（避免后续遗忘）：
- 即使服务器内存大，提升并发也会乘法放大内存：
  - `CHEMCOUNCIL_JOB_CONCURRENCY` 每 +1，通常意味着多起一个 MAD 进程并加载 Chroma

---

## 8. 关键环境变量（运行时契约）

LLM（必须）：
- `UTU_LLM_API_KEY`
- `UTU_LLM_BASE_URL`
- `UTU_LLM_MODEL`
- 可选：`UTU_LLM_TYPE`（`chat.completions` / `responses`）

DB（必须）：
- `UTU_DB_URL`
  - docker 推荐：`sqlite:////state/test.db`

RAG（可选但常用）：
- `MAD_ENABLE_RAG=1`
- `MAD_RAG_MODE=shared|per_agent`
- `MAD_RAG_SHARED_COLLECTION=...`（shared 模式下使用）

Web 后端（资源/策略）：
- `CHEMCOUNCIL_JOB_CONCURRENCY`（并发 job 数；过大可能 OOM）
- `CHEMCOUNCIL_EXPERIENCE_BATCH_SIZE`（经验回流 batch_size 固定值）

---

## 11. 预测 vs 实验：误差统计与趋势图（效果评估）

为了验证“闭环是否真的让推荐越来越准”，我们加入了一个轻量的评估闭环（不影响 reward，本质是监控/可视化）：

目标：
- 对每次“推荐 -> 实验 -> 回流”的闭环，记录推荐预测与真实实验的差距
- 做单位一致化后，计算标准化误差并按回合统计趋势

实现方式（Web 后端 + file-based）：
1) 手动回流（UI）会要求先选择历史推荐记录（可多个块合并提交）
2) UI 在生成的 CSV 中为**每一行实验记录**写入 `recommendation_job_id=<rank_job_id>`（按行对齐推荐来源）
   - CO2RR 行会额外显式写入：
     - `product`
     - `faradaic_efficiency`
     - `partial_current_density`
   - 同时为了兼容现有 analytics，CO2RR 的 `partial_current_density` 也会镜像到通用 `value/unit`
   - 兼容模式：如果所有行都来自同一个推荐来源，也可以额外在提交 `/api/experience/update` 时带上单一字段 `recommendation_job_id=<rank_job_id>`
3) 后端把解析出的 `recommendation_job_id / recommendation_job_ids` 写入 experience_update job 的 `job.json.payload`
4) `/api/analytics` 端点会扫描所有可用的 completed experience_update jobs（CSV 上传）：
   - 读取 upload.csv（真实实验）
   - 按行的 `recommendation_job_id` 关联到对应 rank job 的 result.json（预测）
   - 做单位归一后计算：
     - `abs_error = |pred - actual|`
     - `rel_error = abs_error / (|actual| + floor)`（与 verify 的相对误差口径一致）
     - `score = exp(-rel_error)`（0~1，越大越好）
   - 对 CO2RR：
     - 旧版兼容：如果只有通用 `value/unit`，仍按 `partial_current_density` 统计
     - 新版完整三元组：原始解析仍保留 `faradaic_efficiency` 与 `partial_current_density` 两条原子误差记录，供纠偏蒸馏继续使用
     - 但在 `/api/analytics` 返回给前端之前，会把这两条原子记录合并成一条 `co2rr_combined`
     - 合并口径：`combined_rel_error = 0.5 * rel_error(FE) + 0.5 * rel_error(partial_current_density)`
     - 因此前端图表/均值里，完整 CO2RR 反馈按“一条实验记录”计数，同时仍展示 FE 与部分电流密度两个子值

UI 展示：
- 新增 “效果评估 / Analytics” 页面：
  - 趋势图：支持“按记录分组（每 N 条一个点）/按记录累积（1–N,1–2N…）/按回合（每次回流一个点）”
  - 回合表格：列出每次回流的统计，并支持删除/隐藏错误回合（soft-delete job，从评估中移除）
  - 记录明细：每条记录支持“忽略此条 / 恢复”：
    - 写入 experience_update job 的 ignore 列表（`job.json.payload.analytics_ignore_csv_rows`）
    - `/api/analytics` 聚合与图表会跳过被忽略的行（不修改原始 upload.csv，便于审计）
    - 注意：忽略只影响“效果评估”，不会回滚经验库；若经验库已被错误数据污染，请在“经验库历史版本”中回滚到未污染版本后重新提交反馈
  - 原始 JSON：可折叠查看 records/rounds 的原始数据（便于 debug）

---

## 9. 代码位置索引（你要看的“模型怎么被调用/契约怎么实现”）

### 9.1 “模型回答是怎么被调用的？”

两条主要路径：

1) **GRPO rollout（性能预测）使用单智能体 Runner**：
- 配置：`chem_performance_agent_single.yaml`，`type: simple`，不设置 `env.name: mad`。
- 执行：`youtu-chem-loop/utu/eval/benchmarks/base_benchmark.py` 构造 OpenAI Agents SDK 的 `Agent`，并调用 `Runner.run(...)`。
- 每个数据问题按 `grpo_n` 独立采样；同一候选内部没有 proposal/review/rebuttal。
- `TrainingFreeGRPO` 会拒绝 `env.name == "mad"`，避免误把推荐辩论接回 GRPO。

2) **经验蒸馏（总结/对比/提炼 guideline）调用 LLM**：
- `youtu-chem-loop/utu/practice/experience_updater.py`
  - `self.llm = SimplifiedAsyncOpenAI(...)`
  - `await self.llm.query_one(...)`
- client 实现：`youtu-chem-loop/utu/utils/openai_utils/simplified_client.py`

### 9.2 “结构化输出契约在哪里定义/兜底？”

- GRPO 的 `<think>/<answer>` 与数值 JSON 契约：
  - `youtu-chem-loop/configs/agents/practice/chem_performance_agent_single.yaml`
- “verify 解析支持结构化 JSON”：
  - `youtu-chem-loop/utu/practice/verify/chem_performance_lib/answer_parser.py`

### 9.3 “经验库如何从 GRPO 交给 MAD 推荐？”

- GRPO rollout 不拼接或检索经验：
  - `youtu-chem-loop/utu/eval/processer/training_free_grpo_processor.py`
- `ExperienceUpdater` 按 group reward 蒸馏并合并 guideline：
  - `youtu-chem-loop/utu/practice/experience_updater.py`
- 完整运行结束后导出/同步稳定 pack；推荐端 MAD 再通过 `ExperienceStore.search_experience` 检索。

---

## 10. 后续工作（我们确认问题都解决后再做）

- “格式成功率”度量与监控
  - 已提供离线统计脚本（基于 DB 的 `evaluation_data`）：`youtu-chem-loop/scripts/db/report_format_compliance.py`
  - 用法示例：
    - 先跑一个小的 GRPO rollout（会写入 `exp_id=<name>_epoch_0`）
    - 再统计（在 `youtu-chem-loop/` 下执行）：
      - `python3 scripts/db/report_format_compliance.py --db test.db --exp_id <name>_epoch_0 --stage judged`
  - 抽样检查“结构化工具调用通道”（conclude 的 JSON payload）：
    - `python3 scripts/db/inspect_conclude_payloads.py --db test.db --exp_id <name>_epoch_0 --stage judged --limit 5`
- 超参实验：`batch_size / grpo_n / epochs`（在 `spec-bank/hyperparam_experiments.md` 的纪律下做）
- 经验库检索策略优化（keyword vs embedding；不同 task_type 的过滤）
- 经验蒸馏 prompt 的化学指向性再加强（减少泛化格式要求，增加可复用化学规律）
