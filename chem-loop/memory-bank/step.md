# 实施计划（历史/归档）：Training‑Free GRPO 化学电催化“性能预测”经验库生成

说明（很重要）：
- 本文件最初来自早期 `youtu-agent` 阶段的 step-by-step 计划，保留用于追溯“当时如何把 GRPO/verify 跑通”。
- ChemCouncil 目前已经进入“闭环系统（推荐反应 + 实验回流 + 经验库）”阶段；**当前权威设计以**：
  - `memory-bank/architecture.md`
  - `memory-bank/design-document.md`
  为准；操作流程以 `spec-bank/closed_loop_workflow.md` 与仓库 README 为准。
- 本文件中若出现旧路径 `project/youtu-agent/...`，在本仓库应理解为：`project/chem-loop/youtu-chem-loop/...`。
- 本文件中关于“强制 `<think>/<answer>` 标签”的表述属于历史约束；当前策略是：
  - 静态 prompt + 工具调用结构化输出（`think`/`answer` 字段）+ 自动修复
  - verify 兼容 legacy tags 与结构化 JSON（见 `spec-bank/chem_verify_spec.md`）

面向对象：AI 开发者（含 Coding Agent）。  
目标：以**模块化（多文件）**方式跑通“金属元素 + 反应类型 → 多指标性能预测”的 Training‑Free GRPO 闭环，产出可导出的 experiences（G0/G1/…）。  
硬约束：**严禁单体巨文件（monolith）**；本计划**不包含任何代码**，只包含清晰可执行的指令；**每一步都必须包含验证正确性的测试**。  
说明：reward 细节（权重、尺度、聚合公式等）你已要求“后面再详细讨论”，因此本计划把 reward 部分拆成“接口与占位实现先跑通 + 后续替换为最终 reward”，避免阻塞主链路。  
文档约定：本项目的权威文档只更新 `project/chem-loop/memory-bank/*`；新增“规范/说明类文档”统一放到与 memory-bank 平级的 `project/chem-loop/spec-bank/`。

---

## 0) Always 规则（执行前必须确认）

### Step 0.1 — 阅读关键文档并做“理解确认”
- 指令：
  - 写任何代码前，完整阅读 `project/youtu-agent/memory-bank/architecture.md`（包含完整数据库结构）。
  - 写任何代码前，完整阅读 `project/youtu-agent/memory-bank/design-document.md`（任务定义/输出格式/verify 目标/超参限制等）。
  - 明确：任何新增功能必须拆分为多个小文件/模块；禁止把多个职责堆到一个“万能文件”里。
- 产出：
  - 一份“理解确认记录”（可放在 issue/PR 描述或临时 notes），至少写出 8 条硬约束（例如：输出必须含 `<think>` 和 `<answer>`；`<answer>` 必须是 JSON dict；一次性预测 record 中所有指标；只调 `grpo_n/epochs/batch_size` 等）。
- 验证/测试：
  - 走查记录是否覆盖 3 类信息：  
    1) 任务输入输出契约  
    2) 评测/verify 的目标与边界（不要求 reward 细节）  
    3) 工程约束（模块化/禁止 monolith/里程碑后更新 `project/youtu-agent/memory-bank/architecture.md`）  
  - 任一类缺失视为未完成。

---

## 1) 基线健康检查（先确保环境 OK）

### Step 1.1 — 跑通现有测试套件（建立可运行基线）
- 指令：
  - 在未改任何业务逻辑前运行项目现有测试套件，记录结果。
  - 若失败，先判断是否与本任务无关（例如环境变量、外部依赖），避免把“环境问题”误判为“业务设计问题”。
- 产出：
  - 测试结果记录（通过/失败；失败用例列表；失败原因摘要；是否阻塞本任务）。
- 验证/测试：
  - 期望：测试整体通过；若不通过，必须给出“是否阻塞本任务”的明确结论与理由。

### Step 1.2 — 确认 Training‑Free GRPO verify 的加载路径与签名
- 指令：
  - 阅读调用链：`scripts/run_training_free_GRPO.py` → `utu/practice/*` → `utu/eval/processer/training_free_grpo_processor.py`。
  - 明确 verify 文件放置目录、配置字段（verify_filename/verify_func_name）、verify 需返回的最小字段（至少 `reward`）。
- 产出：
  - 一段简短说明（不超过 15 行）：verify 文件必须位于哪里、配置怎么写、verify 返回值结构是什么。
- 验证/测试：
  - 手工校验说明是否覆盖：verify 目录拼接规则、函数名从配置读取、verify 支持同步/异步两种形式。

---

## 2) 数据契约（保证“可评测输入输出”先被锁死）

### Step 2.0 — 确认原始数据位置与“处理后数据”输出位置
- 指令：
  - 确认原始性能数据文件位于：`project/youtu-agent/data/*.jsonl`（当前已包含 9 种 reaction 的数据）。
  - 约定处理后文件输出到一个新目录（推荐）：`project/youtu-agent/data/processed/chem_performance/`，避免覆盖原始数据，便于回溯与复现。
- 产出：
  - 一条目录约定记录（写在 `project/youtu-agent/spec-bank/data_layout.md` 或同等短文档里）：raw/processed 分别在哪里。
- 验证/测试：
  - 人工检查：processed 目录为空或不存在时，不影响 raw 数据读取；processed 目录生成后，raw 数据不被修改（文件 hash 或行数对比均可）。

### Step 2.1 — 明确 ground truth 存储位置与格式
- 指令：
  - 明确：训练样本的 ground truth 来自 `DatasetSample.answer`，进入 `EvaluationSample.correct_answer`。
  - 明确：ground truth 必须是“可解析 JSON 字典字符串”，仅包含该 record 实际存在的指标（不包含 `id/metals/reaction_type/pos/block_index/product` 等元数据字段），且**至少 1 个指标**。
  - 明确：本阶段的 ground truth value **不是纯数值**，而是“原始字符串”（包含单位或 %），由 verify 负责解析成数值进行对比。
  - 明确：入库时每条样本 **必须包含** `meta.metals`、`meta.reaction_type`、`meta.metrics_gt`（其中 `meta.metrics_gt` 同样是“原始字符串 dict”，只包含非空指标）。
- 产出：
  - 数据契约清单（1 页以内）：  
    - `reaction_type` 枚举（9 类）  
    - `metals` 的表达（字符串数组）  
    - `correct_answer` 的格式约束（JSON dict；value 为“原始字符串”，由 verify 解析；字符串应以数值开头；单位在数据处理阶段统一）  
    - 缺失指标策略（缺失/空值不写入，也不要求预测）
- 验证/测试：
  - 从你的性能库随机抽查 20 条记录：确认每条都能生成至少 1 个指标的 JSON dict，并且每个值都能数值化。

### Step 2.2 — 建立“指标 key 词表”（防止 verify 与数据字段不匹配）
- 指令：
  - 从性能库做抽样统计（建议每个 reaction_type 抽 20 条），得到所有指标 key 的集合与分布。
  - 与 `project/youtu-agent/memory-bank/design-document.md` 中示例 key 做对齐；以数据真实 key 为准，避免“写死不存在的 key”。
- 产出：
  - 一份独立的“指标 key 词表”文档（建议新建 `project/youtu-agent/spec-bank/chem_metrics_keys.md`，保持短小），包含：
    - 全量指标 key 列表
    - 每个 reaction_type 常见指标集合（可选）
    - 明确哪些 key 暂不支持（如有）
- 验证/测试：
  - 覆盖率检查：抽样数据中出现的 key，至少 95% 在词表中有定义；低于阈值则必须先补齐词表或定义“忽略/兜底策略”。

### Step 2.3 — 数据处理（清洗字段 + 规范化 metals + 单位统一 + 过滤不可解析值）
- 指令：
  - 编写一个“数据处理程序”（模块化实现，避免 monolith），把 `project/youtu-agent/data/*.jsonl` 转成“处理后数据”：
    - 删除无用字段：`pos`、`block_index`（仅出现在 HOR/HzOR/O5H 中）。
    - 删除所有值为 `null` 的指标字段（你已选择策略 A：不保留 null 指标键）。
	    - 指标 key 规范化（避免大小写别名）：
	      - 将 O5H 中的 `Faradaic_efficiency` 统一为小写：`faradaic_efficiency`
    - 规范化 `metals`（你已确认必须做）：
      - 去重
      - 大小写统一（元素符号规范，例如 `pt` → `Pt`）
      - 排序（你已选择：按字母序排序）
	    - 单位统一（你已确认要在数据处理阶段做）：
	      - overpotential：统一到 `mV`（V→mV；mV 保持不变；本阶段按 η@10 mA cm−2 口径理解）
	      - potential / half_wave_potential：统一到 `V`（mV→V；V 保持不变）
	      - exchange_current_density：统一到 `mA cm-2`（A→mA；丢弃不可换算/相对描述）
	      - 百分数类（含 `%`）：统一为 **0~1 的小数**（你已选择 B：例如 `95%`→`0.95`）
	      - 其它单位若当前数据已一致，可先不转换，但必须保证数值可解析（后续再补充）
    - 过滤不可解析值：
      - 仅当一个指标值字符串“以数值开头”时才视为可解析（避免误把 `cm-2` 里的 `-2` 当作数值）
      - 若某条 record 的所有指标都不可解析/都被删掉，则丢弃该 record（保证每条 record 至少 1 个可评测指标）
    - CO2RR 特例：
      - `product` 作为输入条件保留（你已选择：CO2RR 输入包含 product）
      - `product` 不属于性能指标：不得进入 `metrics_gt` / `answer` / `metrics_to_predict`
- 产出：
  - 一份处理后的 jsonl（或多份分 reaction_type 的 jsonl），输出到 `project/youtu-agent/data/processed/chem_performance/`。
  - 一份处理规则说明（短文档）：`project/youtu-agent/spec-bank/data_processing_rules.md`。
- 验证/测试：
  - 基本一致性检查：
    - 原始文件行数 vs 处理后行数（允许减少，必须解释“被过滤的原因分布”）
    - 处理后每条记录：不存在 `pos/block_index`；不存在值为 null 的指标键
  - 可解析性检查：
    - 随机抽查 50 条处理后记录：每条至少 1 个指标值以数值开头；`%` 已转成 0~1 小数
  - CO2RR 检查：
    - 随机抽查 20 条 CO2RR：`product` 仍存在且未进入指标集合；`faradaic_efficiency` 已转为 0~1

---

## 3) Prompt / Agent 引导（先保证模型不会乱输出）

### Step 3.1 — 固化“模型输出规则”到新的 practice agent 配置
- 指令：
  - 将 `project/youtu-agent/memory-bank/design-document.md` 的 “3.1 模型引导规则”整理为一个可复用的 `agent.instructions`（越短越硬约束越好）。
  - 强制要求：只输出 `<think>` 与 `<answer>`；`<answer>` 必须为 JSON dict；keys 必须严格匹配 `metrics_to_predict`；values 必须是数值且无单位；不输出额外文本。
- 产出：
  - 新增一个专用 agent 配置（例如放在 `configs/agents/practice/` 下），只用于“化学性能预测”任务。
- 验证/测试：
  - 人工审查：该 instructions 中不得出现与任务无关的能力描述（如 web 搜索、推荐 Top‑k 反应、输出证据等）。

### Step 3.2 — 定义 question 模板规范（只给模型必需信息）
- 指令：
  - 采用 **方案 A（JSON 输入）** 作为唯一 question 规范：
    - question 中必须包含一个 JSON 输入块（字段固定，便于自动化与复现）：
      - `metals`：已规范化后的数组（排序/去重/大小写统一）
      - `reaction_type`
      - `metrics_to_predict`：字符串数组（每条 record 的非空指标 key 列表）
      - `unit_hint`（可选变体）：若你希望提示模型尺度，可把每个指标写成 `{key, unit_hint}` 对象
      - CO2RR 必须额外包含 `product`
    - question 必须包含输出格式要求（只能输出 `<think>` 与 `<answer>`；`<answer>` 为 JSON dict，numbers only）
  - 规定 question 不包含：ground truth 数值、文献证据、检索指令。
- 产出：
  - `question` 模板规范文档（可写入 `project/youtu-agent/memory-bank/design-document.md` 的补充小节，或独立短文档）。
- 验证/测试：
  - 抽样生成 10 条 question 文本，让另一位同学仅阅读题面后复述任务；若复述包含“推荐反应类型/输出证据”，则模板不合格需修正。
  - 结构校验（人工或自动均可）：question 中必须能定位到唯一的 `INPUT_JSON:` 块，且其中字段符合约定。

示例（非代码，仅展示 question 文本结构）：

```text
Task: Predict electrochemical performance metrics for the given catalyst and reaction.

INPUT_JSON:
{
  "metals": ["Pt", "Ru"],
	  "reaction_type": "HOR",
	  "metrics_to_predict": [
	    {"key": "exchange_current_density", "unit_hint": "mA cm-2"}
	  ]
	}

	Output format MUST be:
	<think>...</think>
	<answer>{"exchange_current_density": number}</answer>
	```

CO2RR 特例示例（必须包含 product）：

```text
Task: Predict electrochemical performance metrics for the given catalyst and reaction.

INPUT_JSON:
{
  "metals": ["Bi"],
  "reaction_type": "CO2RR",
  "product": "HCOOH",
  "metrics_to_predict": [
    {"key": "faradaic_efficiency", "unit_hint": "fraction_0_to_1"}
  ]
}
```

---

## 4) Verify 模块（先跑通解析与对齐；reward 先占位，后续替换）

> 本阶段强制模块化：至少拆成“输出解析”“GT 解析”“对齐校验”“verify 入口编排”四个职责文件；禁止把所有逻辑塞进一个 verify 文件。

### Step 4.1 — 写清 verify 行为规格（先写规范再实现）
- 指令：
  - 写出 verify 的行为清单（仅 bullets）：
    - 校验 `<think>` 是否存在（你已确认：缺 `<think>` 直接判失败）
    - 从 `sample.response` 提取 `<answer>` 内容
    - 将 `<answer>` 解析为 JSON dict（预测）
    - 将 `sample.correct_answer` 解析为 JSON dict（真实）
    - 校验 key 集合与 value 类型
    - 计算并返回 `reward`（占位实现即可，后续替换为最终 reward）
- 产出：
  - 一份短规格文档（例如 `project/youtu-agent/spec-bank/chem_verify_spec.md`），用于对照实现。
- 验证/测试：
  - 让另一位开发者只看该规格，能列出至少 6 个异常分支（缺 `<answer>`、JSON 无法解析、value 不是数值、缺 key、多 key、GT 为空等）。

### Step 4.2 — 实现“模型输出解析模块”（只负责提取 `<answer>` + JSON 解析）
- 指令：
  - 新建独立模块：只负责从文本提取 `<answer>` 区块并解析为 JSON dict，要求 value 全为数值。
  - 对解析失败给出可区分的失败原因（用于日志/debug）。
- 产出：
  - 一个独立解析模块文件（职责单一，可单测）。
- 验证/测试（自动化为主）：
  - 用例 A：合法 `<think>` + `<answer>`，`<answer>` 为合法 JSON dict → 解析成功  
  - 用例 B：无 `<answer>` → 解析失败且失败原因可区分  
  - 用例 C：`<answer>` 不是 JSON → 解析失败  
  - 用例 D：JSON value 为字符串（含单位）→ 解析失败

### Step 4.3 — 实现“GT 解析模块”（只负责 correct_answer JSON 解析与校验）
- 指令：
  - 新建独立模块：解析 `sample.correct_answer` 为 JSON dict，并校验：
    - 至少 1 个指标
    - value 为数值
  - 若 GT 非法，必须在日志中明确提示（这是数据问题）。
- 产出：
  - 一个独立 GT 解析模块文件。
- 验证/测试：
  - 用例 A：合法 JSON dict 且有 1 个指标 → 成功  
  - 用例 B：correct_answer 为空/None → 明确失败  
  - 用例 C：value 不是数值 → 明确失败

### Step 4.4 — 实现“key 对齐与完整性校验模块”（避免少报/多报）
- 指令：
  - 新建独立模块：对 `metrics_pred` 与 `metrics_gt` 做 key 对齐检查，并输出结构化结果（例如缺失 keys、额外 keys）。
  - 注意：惩罚策略（缺 key 是否直接 reward=0）先不在此阶段定死，只需能把差异信息提供给 verify。
- 产出：
  - 一个独立 key 对齐模块文件。
- 验证/测试：
  - 用例 A：key 完全一致 → 返回“无差异”  
  - 用例 B：缺 key → 能列出缺失列表  
  - 用例 C：多 key → 能列出额外列表

### Step 4.5 — 实现 verify 入口（只做编排：解析→对齐→reward 占位）
- 指令：
  - 新建 verify 入口文件放入 `utu/practice/verify/`：只负责调用 Step 4.2/4.3/4.4，并返回 `{reward: float, reasoning: ...}`。
  - reward 先用占位策略跑通闭环（例如：  
    - 解析失败 → reward=0  
    - key 不一致 → reward=0  
    - 缺少 `<think>` → reward=0  
    - key 一致且可解析 → reward 为一个稳定可复现的值（例如 1 或基于简单误差）  
    具体占位规则由实现者写在文档里，后续替换为最终 reward）。
- 产出：
  - 新增 verify 入口文件（短小、只做 orchestration）。
  - 一段“占位 reward 规则说明”（写入 Step 4.1 的规格文档）。
- 验证/测试：
  - 端到端单测：构造一个 EvaluationSample（response 含 `<answer>`；correct_answer 为 JSON dict）→ verify 返回 reward 在 [0,1]，且行为与占位规则一致  
  - 错误路径：response 无 `<answer>` → reward=0 且不抛未捕获异常

---

## 5) 配置接线（eval/practice 配置 + verify 可加载）

### Step 5.1 — 新建 eval 配置，接入 verify 与 agent
- 指令：
  - 新建一个 eval 配置文件：
    - 指向 Step 3.1 的 chem_performance agent
    - 指定 dataset 名称（你将上传的性能数据集名）
    - 指定 verify_filename 与 verify_func_name（对应 Step 4.5）
    - 设置 pass_k（用于重复采样/rollout）
- 产出：
  - 新增 eval 配置文件（放入 `configs/eval/` 的合理子目录）。
- 验证/测试：
  - 执行一次“只加载配置”的检查：必须能成功解析配置；并且运行 processor 初始化时不会出现“Failed to load verification function …”警告。

### Step 5.2 — 新建 practice 配置，引用 eval 配置（仅允许调 3 个超参）
- 指令：
  - 新建 practice 配置文件，defaults 引用 Step 5.1 的 eval 配置。
  - 设置默认的 `epochs / batch_size / grpo_n`（后续实验只允许改这三个；若代码本来支持 CLI 覆盖则不改代码）。
- 产出：
  - 新增 practice 配置文件（放入 `configs/practice/`）。
- 验证/测试：
  - 做一次 dry load：确认 practice 配置被正确解析；并确认 CLI 覆盖三参后确实生效（至少能从日志/行为看出变化）。

---

## 6) 数据入库与最小闭环（先小规模跑通）

### Step 6.1 — 制作最小 smoke 数据集（5–20 条）
- 指令：
  - 从性能库抽 5–20 条记录，覆盖至少 3 个 reaction_type（越多越好）。
  - 为每条记录生成：
    - question：包含 metals、reaction_type、metrics_to_predict 与输出格式要求
    - answer：JSON dict（真实指标值，数值、无单位）
- 产出：
  - 一个 smoke JSONL 文件（用于 upload_dataset）。
- 验证/测试：
  - 静态检查：每条样本 answer 都能被 JSON 解析、至少 1 个指标、value 全为数值。

### Step 6.2 — 上传 smoke 数据集到 DB
- 指令：
  - 使用项目提供的上传脚本将 smoke JSONL 入库为一个新的 dataset 名称。
- 产出：
  - DB 中存在该 dataset 的记录。
- 验证/测试：
  - 以脚本输出为准：确认“Uploaded N datapoints”中的 N 与 JSONL 行数一致；不一致必须停止并查因。

### Step 6.3 — 在不跑 GRPO 的情况下先手动抽检 verify
- 指令：
  - 手动构造 3 组模型 response 文本（包含 `<think>` 与 `<answer>`）覆盖：
    - keys 与数值都合法
    - keys 合法但数值有偏差
    - keys 缺失或多出
  - 将其喂给 verify（通过单测/最小调用方式即可）。
- 产出：
  - 抽检结果记录：每种情况的 reward 与占位规则是否一致。
- 验证/测试：
  - 三种情况必须与占位规则一致；若不一致先修 verify，再进入下一步。

---

## 7) 端到端跑通 Training‑Free GRPO（低成本试跑）

### Step 7.1 — 最小规模 Training‑Free GRPO 试跑（epochs=1，truncate 小数据）
- 指令：
  - 用 smoke 数据集运行一次最小配置：
    - epochs=1
    - batch_size 小
    - grpo_n 小
    - 启用数据 truncate（避免成本过高）
- 产出：
  - 生成的新 agent config 文件（包含 experiences）。
- 验证/测试：
  - 必须同时满足：
    - 进程正常结束（无异常退出）
    - 输出提示包含“New agent config file with experiences saved at: …”
    - 生成文件中至少出现 1 条 `[G0].` 形式的 experience（允许很少，但不能为 0）

### Step 7.2 — 抽查 experiences 是否与任务相关
- 指令：
  - 打开生成的 agent config，抽查前 3 条 experiences，确认内容聚焦于：
    - 如何预测指标
    - 如何保持输出格式可解析
    - 如何一次性覆盖所有指标
  - 若出现“推荐反应类型/输出证据/去检索文献”等偏航内容，回到 Step 3.1/3.2 修正。
- 产出：
  - 抽查结论（通过/不通过 + 1 句理由）。
- 验证/测试：
  - 通过标准：抽查的 experiences 不包含偏航指令；且至少有 1 条对“格式/完整性”的明确约束建议。

---

## 7.3) 接入外部文献数据库（新增：在超参实验前完成）

目标：让 chem-performance agent 在推理过程中可以调用一个“文献数据库”工具，从外部 DB 中检索相关论文/摘要/证据，从而提升数值预测质量与经验蒸馏的可执行性。

### Step 7.3.1 — 明确 tool contract 与 DB 最小 schema
- 指令：
  - 在 `project/youtu-agent/spec-bank/` 新增一份短文档，定义：
    - toolkit 名称（agent config 里如何启用）
    - tool 函数签名（search/get/healthcheck 至少）
    - 外部 DB 的最小字段（例如 paper_id/title/abstract；可配置列名）
    - 错误路径（DB 缺失/不可读时不抛异常，而是返回结构化 error）
- 产出：
  - `project/youtu-agent/spec-bank/chem_literature_db_tool.md`
- 验证/测试：
  - 让另一位开发者仅看该 spec，能在 10 分钟内写出一段伪代码说明如何在 agent 中调用这些工具。

### Step 7.3.2 — 实现 builtin toolkit（SQLite 后端优先）
- 指令：
  - 新增 `utu/literature/`（或同等职责拆分目录），实现一个“只读 SQLite 文献 store”
  - 新增 `utu/tools/chem_literature_db_toolkit.py`，暴露工具函数：
    - `literature_healthcheck()`
    - `literature_search(query, limit)`
    - `literature_get(paper_id)`
- 产出：
  - 代码模块（保持依赖轻量；尽量只用 stdlib）
- 验证/测试：
  - 新增 pytest：用临时 SQLite 文件建一个小表，验证 search/get 逻辑与错误路径（缺 DB 返回 error）。

### Step 7.3.3 — 配置接线到 chem agent
- 指令：
  - 新增 tool config（可选，但推荐）：`configs/tools/chem_literature_db.yaml`
  - 在 `configs/agents/practice/chem_performance_agent.yaml` 中启用该 toolkit，并在 instructions 中提示可用工具与使用策略
  - 对 practice 的 `agent_objective/learning_objective` 做更新：允许使用 `chem_literature_db`，但禁止泛化到 web 搜索
- 验证/测试：
  - `ConfigLoader.load_toolkit_config("chem_literature_db")` 能通过
  - `ConfigLoader.load_agent_config("practice/chem_performance_agent")` 能通过

---

## 7.4) 用现成 Chroma 向量库替换/补齐文献 DB 后端（新增：在超参实验前完成）

背景：用户的“外部文献数据库”实际是本仓库自带的本地持久化 Chroma 目录 `project/youtu-agent/chroma_db/`，其中已有 collection `chemical_reactions_recommendation_agent2`，embedding 由 Voyage 写入（模型名 `voyage-3-large`）。

目标：让 `chem_literature_db` toolkit 支持 `backend=chroma`：
- 用 Voyage 对 query 做 embedding
- 用 Chroma 的向量检索返回 chunk-level 证据
- **未命中/低置信度时明确返回“无结果/置信度低”**，避免误导模型

### Step 7.4.1 — 明确 Chroma collection 与 metadata contract
- 指令：
  - 盘点 `chroma_db/chroma.sqlite3` 里的 collection 名称、dimension、hnsw space、metadata keys。
  - 明确：agent 查询时可用哪些字段做过滤（例如 `reaction_type`）。
- 产出：
  - `project/youtu-agent/spec-bank/chroma_db_inventory.md` 更新（或新增补充文档）。
- 验证/测试：
  - 人工检查：collection 名称与 metadata keys 在文档中可复述且可用于实现过滤。

### Step 7.4.2 — 实现 Chroma store + Voyage embedder（模块化）
- 指令：
  - 在 `utu/literature/` 新增：
    - `chroma_store.py`：只读检索（PersistentClient + get_collection + query）
    - `voyage_embedder.py`：Voyage embedding wrapper（从 env/config 读取 model/api_key）
  - 在 `utu/tools/chem_literature_db_toolkit.py` 中增加 `backend=chroma` 分支：
    - `literature_search(query, limit, reaction_type?, max_distance?)`
    - 默认启用 `max_distance` 阈值过滤；无结果时返回显式 payload（hit=false）
  - 注意工程细节：
    - Chroma/SQLite 可能因 temp dir 报 `unable to open database file`：默认设置 `SQLITE_TMPDIR=/tmp` 与 `TMPDIR=/tmp`
    - Chroma Rust backend 可能在后台线程调用时 hang：保持 Chroma 调用在主线程
- 产出：
  - 模块化实现（至少 2 个新文件 + toolkit 修改；禁止把所有逻辑塞进单文件）
- 验证/测试：
  - 新增 pytest：
    - 临时 persistent chroma 目录 + 手写 embeddings
    - mock Voyage 的 embed_query（避免网络）
    - 覆盖：命中/阈值过滤/无结果 payload

### Step 7.4.3 — 配置接线 + env 占位
- 指令：
  - 更新 agent 配置，让 chem-performance 默认用 Chroma backend：
    - collection: `chemical_reactions_recommendation_agent2`
    - Voyage embed model: `voyage-3-large`
  - 在 `.env.example` 中新增 env 变量占位：
    - `VOYAGE_API_KEY` / `VOYAGE_EMBED_MODEL` / `CHEM_LITERATURE_CHROMA_*`
- 验证/测试：
  - `ConfigLoader.load_agent_config("practice/chem_performance_agent")` 能 resolve（无 env 时也不 hard fail）。

---

## 7.5) 文献遮蔽（防止 label leakage；新增：在超参实验前完成）

背景：chem-performance 的 ground-truth 数值往往来自某一篇特定论文。如果 agent 能直接用 `chem_literature_db`
查到那篇论文的 chunk，就会“抄答案”而不是推理/泛化，导致训练与评测指标失真（label leakage）。

目标：在 **训练/评测跑数据集时**（Training-Free GRPO practice + eval）对文献库做 **doc-level** 遮蔽：
- 对于当前样本对应的 DOI/doc_id，`literature_search` 不能返回该 doc 的任何 chunk。
- 遮蔽信息必须在代码侧强制执行，不能依赖模型自觉。
- 工具输出不能把被遮蔽的 doc_id 泄露给模型。

### Step 7.5.1 — 明确 sample id -> doc_id 的来源与字段
- 指令：
  - 明确样本 `meta.id` 与 `meta.reaction_type` 的来源（来自 `data/*.jsonl` / processed records）。
  - 明确 DOI/doc_id 的映射来自：
    - `project/youtu-agent/rawdata/2-cleaned-abstracts-about-<REACTION_TYPE>.tsv`
    - TSV 关键列：`index`（样本 id）与 `doi`（doc_id）
- 产出：
  - 在 `spec-bank/chem_literature_db_tool.md` 增补 “Leakage Masking” 小节（mask 规则与 scope）。
- 验证/测试：
  - 用一个已知样本（例如 OER id=108 -> doi=10.3390/nano13233076）人工验证映射可复述。

### Step 7.5.2 — 训练/评测 pipeline 注入 masked_doc_ids（不影响 CLI）
- 指令：
  - 仅在数据集 rollout 代码路径（`BaseBenchmark.rollout_one`）中：
    - 从 sample.meta 解析 `id` + `reaction_type`
    - 查映射得到 `doc_id`（DOI）
    - 深拷贝 agent config 并注入 `toolkits.chem_literature_db.config.masked_doc_ids=[doc_id]`
  - CLI (`scripts/cli_chat.py`) 不注入 masked_doc_ids（保持真实检索体验）。
- 验证/测试：
  - rollout 轨迹中出现 `literature_search` 调用时，该 doc_id 不应出现在 tool 输出。

### Step 7.5.3 — toolkit 侧强制过滤 + “无结果”显式返回
- 指令：
  - `chem_literature_db` toolkit 在 `backend=chroma` 分支中：
    - 过滤掉 `doc_id in masked_doc_ids` 的候选
    - 若全部候选被过滤/或阈值过滤后为空：返回 `hit=false` 的 no-results payload（避免误导模型）
  - 不在 tool 输出中返回 `masked_doc_ids` 本身（避免泄露）。
- 验证/测试：
  - pytest：构造一个小 chroma collection，mask 掉唯一命中文档后应返回 hit=false。

---

## 8) 超参实验框架（仅调 grpo_n / epochs / batch_size）

### Step 8.1 — 固化“只调三参”的实验纪律
- 指令：
  - 记录默认三参值与计划搜索空间；并明确其它参数保持固定（保证可比性）。
- 产出：
  - 一张小表：默认值 + 搜索空间 + 每次实验的控制变量说明。
- 验证/测试：
  - 任取一个参数做一次覆盖试跑（仍用 truncate 小数据）：确认实验记录中的参数值与实际运行一致（可通过日志/输出信息核对）。

### Step 8.2 — 建立 train/validation 数据集划分并固定可复现性
- 指令：
  - （后续真正训练阶段再做）将性能数据划分为 train/validation 两个 dataset（分别入库成两个 dataset 名称），保证验证集不参与经验蒸馏选择。
  - （后续真正训练阶段再做）固定随机性（至少保证：同一配置多次运行具备可比较性）。
- 产出：
  - 两个 dataset 名称与划分规则说明（记录在文档里）。
- 验证/测试：
  - 随机抽查：验证集中任意 10 条样本不应出现在训练集中（按原始来源 id 或其它唯一标识核对）。

---

## 9) 经验库导出与交付（你要带走整合到其它项目）


### Step 9.1 — 规范导出 experiences 的格式与版本信息
- 指令：
  - 定义 experiences 导出规范（文档即可，不写代码）：
    - exp_id / 时间戳
    - 三参（grpo_n/epochs/batch_size）
    - experience 列表（G0/G1/…）
    - 对应生成的 agent config 路径
- 产出：
  - `project/youtu-agent/spec-bank/experience_export.md`（短文档）。
- 验证/测试：
  - 用一次已完成实验的 agent config 做手工导出演练：确认能完整拿到所有 `[G*].` 条目，顺序与内容不丢失。

---

## 10) 文档与架构更新（每个里程碑后必须做）

### Step 10.1 — 里程碑后更新 architecture.md
- 指令：
  - 在完成以下任一里程碑后，更新 `project/youtu-agent/memory-bank/architecture.md`：
    - 新增 chem_performance verify 并接线到 processor
    - 新增 eval/practice 配置并能跑通最小闭环
    - 引入新的数据契约/目录结构
- 产出：
  - 更新后的 `project/youtu-agent/memory-bank/architecture.md`（只更新相关小节，保持简洁）。
- 验证/测试：
  - 文档审查：`project/youtu-agent/memory-bank/architecture.md` 中能找到以下信息且表述正确：
    - verify 文件位置与加载方式
    - 新增配置文件名与用途
    - 若 DB schema 未变更，明确写出“DB schema unchanged”

### Step 10.2 — 若实现与 design-document.md 有偏差则同步更新
- 指令：
  - 若实现过程中改变了关键行为（例如输出模板、数据契约、verify 接口约束等），必须同步更新 `project/youtu-agent/memory-bank/design-document.md`，避免后续维护偏差。
- 产出：
  - 更新后的 `project/youtu-agent/memory-bank/design-document.md`（仅改动与偏差相关的段落）。
- 验证/测试：
  - 走查：`project/youtu-agent/memory-bank/design-document.md` 的“任务定义/输出格式/verify 设计”与实际行为一致；不一致视为未完成。

---

## 11) 闭环集成（跨仓库）：Debate + Real Experiments

目标：把 `project/youtu-agent`（Training-Free GRPO 经验库）与外部多智能体辩论仓库
`project/reaction_recommendation` 串成可复现的闭环。

### Step 11.1 — Experience Pack 同步（Youtu-Agent → Debate Repo）
- 指令：
  - 选择一个 GRPO 产出的 agent YAML（含 `[G*].` experiences），例如：
    - `configs/agents/practice/<exp>_agent.yaml`
  - 将该 YAML 复制到辩论仓库的 pack 目录：
    - `project/reaction_recommendation/experience/`
  - 确保辩论仓库配置启用 `experience.packs_path: ./experience`（默认已启用）。
  - 若希望“固定文件名 + 自动更新时间戳”，推荐直接使用一键脚本：
    - `project/youtu-agent/scripts/run_closed_loop.sh`
    - 它会生成并同步：`project/reaction_recommendation/experience/experience.yaml`
- 产出：
  - 一个“当前使用的经验库 pack 文件名”的记录（写在文档里，避免多人协作时漂移）。
- 验证/测试：
  - 在 `project/reaction_recommendation` 运行一次 system status（或一次 debate），确认日志里显示 ExperienceStore 总量 > 0。

### Step 11.2 — Debate Trace 吸收（Debate Repo → Youtu-Agent）
- 指令：
  - 在辩论仓库完成一次 debate，会生成：
    - `project/reaction_recommendation/outputs/result_*.json`
    - 若你用的是 `--rank-reactions`（反应排序模式），默认只保存 `rank_*.json`（无 debate_history）；
      需要加 `--save-each-reaction` 才会落盘每个反应的 `result_*.json`（用于经验蒸馏）。
  - 用 Youtu-Agent 的脚本把 debate trace 蒸馏为经验（网络可用时运行）：
    - `scripts/debate/update_experiences_from_debate.py --debate_json <result.json> --seed_agent_yaml <seed.yaml>`
- 产出：
  - 一个新的 agent YAML（含追加/更新后的 experiences），保存到：
    - `configs/agents/practice/debate_update_<ts>_agent.yaml`
- 验证/测试（无需网络的 dry-run）：
  - `--dry_run` 能正确解析出 proposals + critiques 数量并输出状态分布。

### Step 11.3 — 实验记录 CSV 吸收（Lab CSV → Youtu-Agent Dataset）
- 指令：
  - 实验记录先暂定 CSV（列名可中文/英文），至少包含：
    - reaction_type、metals、value（指标值），可选 unit/condition/metric_name
  - 导入为 processed records：
    - `scripts/data/import_experimental_csv.py --csv_path <file.csv>`
  - 再用 `scripts/data/build_chem_performance_dataset.py` 构建可 upload 的 DatasetSample JSONL 并入库。
- 产出：
  - processed records JSONL + dataset JSONL + 新 dataset 名称（用于后续 GRPO）。
- 验证/测试：
  - 抽查 10 条输出记录：`metals` 已解析、metric key 与 v5 scope 一致、单位被规范化（例如 overpotential→mV）。

### Step 11.4 — 用真实实验数据更新经验库（Training-Free GRPO）
- 指令：
  - 用真实实验数据 dataset 跑一次 Training-Free GRPO，生成新经验库 YAML（reward 仍沿用当前实现）。
  - 之后重复 Step 11.1 把最新 YAML 同步回辩论仓库。
- 产出：
  - 最新经验库 agent YAML（闭环完成一轮）。
- 验证/测试：
  - 对比闭环前后：经验条目数变化、关键单位/格式经验是否被加强，且辩论仓库检索能命中最新 pack。
