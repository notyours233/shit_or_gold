## 2026-01-20 — Step 1 Baseline Health Check (完成)

范围：仅执行实施计划 Step 1（建立可运行基线 + 明确 verify 加载路径与签名）。在确认测试通过前未开始 Step 2。

### 已完成内容

- 已完整阅读并对齐本仓库权威文档：
  - `project/youtu-agent/memory-bank/architecture.md`
  - `project/youtu-agent/memory-bank/design-document.md`
  - `project/youtu-agent/memory-bank/step.md`
  - `project/youtu-agent/spec-bank/README.md`
- Step 1.2（verify 加载路径与签名）走查完成：
  - verify 目录：`utu/practice/verify/`
  - 加载位置：`utu/eval/processer/training_free_grpo_processor.py`
  - 配置字段：`EvalConfig.verify_filename / EvalConfig.verify_func_name`
  - 调用方式：judge 阶段调用 `verify_func(sample=..., llm=...)`，支持 sync/async；返回 dict 至少含 `reward`，可选 `reasoning`

### Step 1.1 测试基线（用户执行）

- 运行命令：
  - `uv run pytest -q tests/test_config.py tests/db/test_db_service.py`
- 结果：
  - 首次运行：2 failed（均为 "配置加载/环境变量缺省" 导致的硬失败）
  - 修复后再次运行：通过（用户确认）

### 首次失败原因与修复（本次变更）

1) `tests/test_config.py::test_load_toolkit_config`：
- 原因：测试会加载 `generated/download_bilibili_video`，但 `configs/tools/generated/` 下缺少对应 YAML，Hydra 抛 `MissingConfigException`
- 修复：新增 "generated tool config stub"，使 Hydra 能加载该 config（不实现真实下载逻辑）
  - `project/youtu-agent/configs/tools/generated/download_bilibili_video.yaml`
  - `project/youtu-agent/configs/tools/generated/download_bilibili_video/`（stub 目录：`main.py` / `runner.py` / `manifest.json` / `requirements.txt`）

2) `tests/test_config.py::test_load_eval_config`：
- 原因：多个 eval 配置（例如 `ww` / `gaia`）的 `judge_model.model_provider.type` 使用 `${oc.env:JUDGE_LLM_TYPE}`，在未设置环境变量时会在 `OmegaConf.resolve` 阶段硬失败（`InterpolationResolutionError`）
- 修复：为 judge env 插值增加 fallback（优先 `JUDGE_*`，否则回落到 `UTU_*`，再不行用安全默认值），保证 "未配 judge env" 时也能正常加载：
  - `project/youtu-agent/configs/eval/ww.yaml`
  - `project/youtu-agent/configs/eval/gaia.yaml`
  - `project/youtu-agent/configs/eval/example.yaml`
  - `project/youtu-agent/configs/eval/web/web.yaml`
  - `project/youtu-agent/configs/eval/web/web_practice.yaml`

### 备注 / 风险提示

- 本仓库 tests 里存在大量需要外部依赖（网络 / API Key / Docker / MCP server / 交互输入）的用例；本次 Step 1 的 "基线" 选择了只验证 config loading + DBService graceful handling 的子集。
- `configs/tools/generated/download_bilibili_video*` 当前是为通过 config-loading baseline 追加的 stub；若后续真的要运行该工具，需要补齐 MCP 实现与依赖安装。

## 2026-01-20 — Step 2 Data Contract + Processing (完成)

范围：执行实施计划 Step 2（数据契约 + 指标 key 词表 + 数据处理程序），并在用户确认验证通过后记录与沉淀文档。

### Step 2.0 / 2.1 / 2.2 文档产出（spec-bank）

- 数据 raw/processed 布局约定：
  - `project/youtu-agent/spec-bank/data_layout.md`
- 化学性能数据契约（reaction_type/metals/metrics_gt/CO2RR product）：
  - `project/youtu-agent/spec-bank/chem_dataset_contract.md`
- 指标 key 词表（防止 verify 与数据字段不匹配）：
  - `project/youtu-agent/spec-bank/chem_metrics_keys.md`
- 数据处理规则说明（清洗/单位/过滤策略）：
  - `project/youtu-agent/spec-bank/data_processing_rules.md`

### Step 2.3 数据处理程序（模块化）

新增离线处理模块（不触 DB，输出到 `data/processed/chem_performance/`）：

- 包入口：
  - `project/youtu-agent/utu/data_processing/__init__.py`
  - `project/youtu-agent/utu/data_processing/chem_performance/__init__.py`
- 常量/枚举与非指标字段列表：
  - `project/youtu-agent/utu/data_processing/chem_performance/constants.py`
- metals 规范化（去重/大小写/排序）：
  - `project/youtu-agent/utu/data_processing/chem_performance/metals.py`
- metric key/values 规范化（O5H key 小写；key-aware 单位统一：overpotential->mV / potential->V / exchange_current_density->mA cm-2；%->0~1；"数值前缀" 可解析性判定）：
  - `project/youtu-agent/utu/data_processing/chem_performance/metrics.py`
- 单条 record 清洗 + jsonl 文件/目录批处理：
  - `project/youtu-agent/utu/data_processing/chem_performance/processor.py`
- CLI 脚本（手动运行并打印统计信息）：
  - `project/youtu-agent/scripts/data/process_chem_performance_data.py`

### Step 2.3 最小单测（pytest）

- 新增单测覆盖 metals/key/value/CO2RR product/空指标丢弃等关键边界：
  - `project/youtu-agent/tests/data_processing/test_chem_performance_processing.py`

### 验证/测试（用户执行）

- 用户确认 Step 2 验证通过：
  - `tests/data_processing/test_chem_performance_processing.py` 通过
  - 数据处理脚本可运行并生成 processed 输出（注意：本 repo 的 `data/` 目录被 gitignore；processed 输出属于本地运行产物）

### 补充：processed -> uploadable dataset JSONL

为后续入库（`upload_dataset.py --data_format default`）增加了一个转换脚本：

- `project/youtu-agent/scripts/data/build_chem_performance_dataset.py`
  - 输入：`data/processed/chem_performance/*.jsonl`（Step 2.3 的 processed records）
  - 输出：一个可 upload 的 DatasetSample JSONL（默认：`data/processed/chem_performance/chem_performance_dataset.jsonl`）
  - 每行包含：`source="training_free_grpo"` + `question`（含 INPUT_JSON 与输出格式约束）+ `answer`（metrics_gt JSON dict string）+ `meta`（保留 id/metals/reaction_type/product/units 等用于追溯）

运行结果（用户执行并确认）：
- 写入样本数：5797
- 分布：CO2RR 1654 / HER 3226 / OER 235 / ORR 264 / UOR 99 / EOR 81 / O5H 62 / HzOR 75 / HOR 101
- 与 raw 总行数 (5804) 的差异主要来自“处理阶段丢弃无可评测指标的记录”（例如 HOR 中部分记录所有指标为 null）

### Step 2.4 入库到本地 DB（用户执行）

- 上传命令：
  - `uv run python scripts/data/upload_dataset.py --file_path data/processed/chem_performance/chem_performance_dataset.jsonl --dataset_name chem_performance_v1 --data_format default`
- DB 校验（SQLite）：
  - `select dataset, count(*) from data group by dataset` → `chem_performance_v1: 5797`
- 备注：
  - 本仓库当前数据加载逻辑默认从 DB 表 `data` 读取（按 `dataset` 名过滤）。重复 upload 到同一个 `dataset_name` 会导致记录累加，后续跑 eval/GRPO 会把旧数据也读出来；建议 dataset_name 带版本号（例如 `chem_performance_v1` / `chem_performance_2026_01_21`）。

## 2026-01-21 — Step 3 Prompt / Agent Guidance (进行中)

### Step 3.1 化学性能预测专用 Agent 配置（已新增）

- 新增 chem-performance 专用 agent config（用于 rollout 时强约束输出格式）：
  - `project/youtu-agent/configs/agents/practice/chem_performance_agent.yaml`
- 关键约束：
  - 只输出 `<think>...</think>` 与 `<answer>...</answer>`
  - `<answer>` 必须是 JSON dict；keys 必须严格匹配 `metrics_to_predict`；values 必须是纯数字（无单位）
- LLM 设置（按用户偏好调整）：
  - 默认模型：`deepseek-reasoner`（DeepSeek “thinking mode” 常用的 reasoning 模型名）
  - `temperature=1`
  - `top_p=0.95`
- 备注：
  - Training-Free GRPO 在 rollout 阶段会用 `practice.rollout_temperature` 覆盖 agent config 的 `model_settings.temperature`；若希望 rollout 真正用 `temperature=1`，需要在 practice config 中把 `rollout_temperature` 设为 1。

### Step 3.1 交互式烟测（用户执行）

- 命令：
  - `uv run python scripts/cli_chat.py --config_name practice/chem_performance_agent`
- 结果：
  - DeepSeek “thinking mode” 下可以稳定输出 `<think>` 与 `<answer>` 块
  - `<answer>` 为 JSON dict 且 values 为纯数字（无单位），满足 verify 的最小输入要求

## 2026-01-21 — Step 4 Chem Verify (完成)

范围：执行实施计划 Step 4（verify 模块拆分实现 + 最小单测），并在用户确认测试通过后记录。

### 产物（模块化拆分）

- verify 行为规格（对照实现用）：
  - `project/youtu-agent/spec-bank/chem_verify_spec.md`
- verify 入口文件（供 Training-Free GRPO processor 动态加载）：
  - `project/youtu-agent/utu/practice/verify/chem_performance_verify.py`
- 解析/对齐/奖励子模块（避免单体文件）：
  - `project/youtu-agent/utu/practice/verify/chem_performance_lib/answer_parser.py`（提取 `<answer>` + JSON + 数值校验；`<think>` 存在性检查）
  - `project/youtu-agent/utu/practice/verify/chem_performance_lib/gt_parser.py`（解析 `correct_answer` JSON dict；提取数值前缀）
  - `project/youtu-agent/utu/practice/verify/chem_performance_lib/key_alignment.py`（缺失/多余 keys 差异）
  - `project/youtu-agent/utu/practice/verify/chem_performance_lib/reward.py`（占位 reward：按指标取平均的平滑误差得分）

### 重要修复：避免同名模块/包冲突

- 由于 verify 入口曾与同名 package 产生 Python import shadowing（`chem_performance.py` vs `chem_performance/`），改为：
  - 入口文件：`chem_performance_verify.py`
  - helper 包：`chem_performance_lib/`
- 入口文件使用绝对 import（因为 processor 动态加载模块名为 `verify_module`，相对 import 会失败）。

### 验证/测试（用户执行）

- 命令：
  - `pytest -q tests/practice/test_chem_performance_verify.py`
- 结果：
  - 7 passed（用户确认）

## 2026-01-21 — Step 5 Config Wiring (完成)

### Step 5.1 Eval 配置（已新增）

- 新增 eval config：
  - `project/youtu-agent/configs/eval/chem/chem_performance.yaml`
- 关键字段：
  - `data.dataset = chem_performance_v1`
  - `verify_filename = chem_performance_verify.py`
  - `verify_func_name = verify_func`
  - agent 使用 `configs/agents/practice/chem_performance_agent.yaml`

### Step 5.2 Practice 配置（已新增）

- 新增 practice config：
  - `project/youtu-agent/configs/practice/chem_performance.yaml`
- 默认超参：
  - `epochs=1`, `batch_size=50`, `grpo_n=3`
  - `rollout_temperature=1`（匹配用户偏好的 temperature）

### Step 5.3 配置加载与 verify 动态加载（用户执行）

- Dry load（仅验证“配置可解析 + verify 可动态加载”，不跑 LLM）：
  - `ConfigLoader.load_eval_config("chem/chem_performance")` 成功
  - `TrainingFreeGRPOProcesser(cfg).verify_func` 成功加载（无 "Failed to load verification function" 警告）

## 2026-01-21 — Step 7 End-to-End GRPO Smoke (完成)

### Step 7.1 最小规模试跑（用户执行）

- 运行命令（20 条数据，epochs=1，batch_size=4，grpo_n=2）：
  - `python scripts/run_training_free_GRPO.py --config_name chem_performance --experiment_name chem_perf_smoke_01 --epochs 1 --batch_size 4 --grpo_n 2 --rollout_data_truncate 20`
- 结果：
  - 训练流程正常结束
  - 生成新的 agent config（含 experiences）：
    - `project/youtu-agent/configs/agents/practice/chem_perf_smoke_01_agent.yaml`

### Step 7.2 Experiences 抽查（未通过；已定位偏航原因）

- 抽查文件：
  - `project/youtu-agent/configs/agents/practice/chem_perf_smoke_01_agent.yaml`
- 发现偏航（与任务/工具配置不匹配）：
  - `[G2]` / `[G3]` 等经验建议 “prioritize using external tools / literature values …”
  - 但当前 chem-performance agent 默认 `toolkits: {}`，也没有 web/tool 检索能力；这类经验对 rollout 不可执行，且会引导模型在 `<think>` 中偏向“应该去查数据/用工具”而不是学会合理估计与范围校验。
- 处理策略（用户要求先不改既有产物）：
  - 不直接修改该次生成的 `chem_perf_smoke_01_agent.yaml`（保持 smoke run 产物可复现）。
  - 按实施计划回到 Step 3：收紧 practice 的目标描述，使经验蒸馏“禁止建议外部工具/文献检索”。
  - 后续需重新跑一次 GRPO（同样的 smoke 配置即可）生成新的 agent config，再复查 Step 7.2 是否通过。

已做的收紧（用于下一次跑 GRPO）：
- 更新 practice 配置的 `agent_objective/learning_objective`，明确“无外部工具/检索能力，经验不得建议工具”：
  - `project/youtu-agent/configs/practice/chem_performance.yaml`

## 2026-03-14 — ChemCouncil Web 前端体验完善（完成）

目标：让实验同学在 “推荐 → 填写实验 → 回流更新 → 效果评估 → 经验库回滚” 的闭环里更少踩坑、更可控。

### 经验回流（Manual feedback）改进

- 支持 **多个“推荐回流块”同时展示**：可在同一页分别选择推荐 A/B，并在各自块下填写实验数据（避免写错到别的推荐下面）。
- 草稿按 `recommendation_job_id` **自动保存/恢复**（localStorage），切换推荐或刷新页面不丢数据。
- 支持勾选多个块一次提交：前端会把多个块**合并为 1 个** `experience_update` 任务，并在 CSV 中为**每一行**写入 `recommendation_job_id`，保证效果评估按行对齐到对应推荐来源（即使一个更新里混合了多个推荐来源也不失真）。
- 交互优化：通过 `focusin/click` 同步 active block（避免 `mousedown` 干扰原生 `<select>` 打开导致“选不了 B 块”一类问题）。
- UI 明确提示 `batch_size=4`：少于 4 条训练样本时给出建议（CO2RR 一行实验记录通常会拆成 2 条训练样本，所以“行数”与“样本数”不一定相同）。
- 新增废液混合物上下文：支持记录 `metals_scope / metals_other`（top-5 主成分 vs 额外痕量金属/杂质），并把该上下文写入训练样本与经验蒸馏提示，减少“误以为只有这五种金属”的过度结论。

### 经验库（Experience library）浏览改进

- 经验条目渲染从“代码风格的 raw YAML”升级为 **更像 Markdown 的卡片阅读模式**：
  - `CaseCard` 自动拆字段（RT/METALS/TARGET/ANCHOR/TAKEAWAY/APPLIES），字段区固定行高 + 垂直对齐，长值自动省略。
  - 非 CaseCard（段落经验）使用 **预览（省略号）→ 展开后变长** 的方式：展开后不重复全文，只显示剩余段落，阅读更连贯。
- 增加 **经验搜索框**：按关键词过滤（支持多个词，用空格/逗号分隔），便于在 500+ 条经验里快速定位。
- 支持浏览经验库归档与一键激活（rollback）：填错实验数据导致经验被污染时，可先切回未污染版本再重新回流。

### 历史推荐（Recommendation history）改进

- 历史推荐列表展示更完整（时间/状态/金属组成/操作），并支持筛选。
- 新增 “查看推荐值” 的 **懒加载展开**：点击后抓取 `/api/jobs/<job_id>/result`，在表格内展示 top_k 的反应类型与预测值（并保留下载 JSON 的入口）。

### 效果评估（Analytics）改进

- 用点 + 折线展示 score 趋势，并支持聚合方式切换：
  - `records_bucket`：每 N 条记录一个点（默认 N=4 对齐 batch_size）
  - `records_cumulative`：1–N、1–2N… 的累计均值趋势
  - `rounds`：每次回流更新一个点
- 支持在 UI 中 **隐藏/删除某次回流回合**（对应该次 `experience_update` job 的 soft-delete），从而把错误数据从效果评估视图里移除。


## 2026-02-10 — Closed Loop Integration: Debate + Experimental CSV (完成/可用)

目标：把“经验库（GRPO）→ 多智能体辩论 → 真实实验 → 回灌 GRPO 更新经验库”的闭环跑通到“文件可交换 + 脚本可执行”的状态（reward 保持不变）。

### 新增/更新能力

- 实验 CSV 导入（lab record → processed records）：
  - 解析 `reaction_type/metals/value/unit/condition` 等常见列，支持 metals 写法 `Co(57%),Ni(23%)`
  - 脚本：`project/youtu-agent/scripts/data/import_experimental_csv.py`
  - 解析模块：`project/youtu-agent/utu/data_processing/chem_performance/experimental_csv.py`
- Dataset builder meta 扩展：保留实验 provenance（不影响旧数据）：
  - `project/youtu-agent/scripts/data/build_chem_performance_dataset.py`
- Debate trace 兼容外部辩论仓库输出：
  - `project/youtu-agent/utu/debate/langgraph_trace.py` 支持外部 `experiment_id/timestamp` schema，并能从 claim/query 推断 `reaction_type`
  - 单测：`project/youtu-agent/tests/debate/test_langgraph_trace.py`
- 文档更新：
  - `project/youtu-agent/memory-bank/architecture.md` 增加与 `project/reaction_recommendation` 的互操作说明
  - `project/youtu-agent/memory-bank/design-document.md` 增加闭环数据流与工件（artifacts）说明
  - `project/youtu-agent/memory-bank/step.md` 增加 Step 11（跨仓库闭环集成）

### 验证/测试

- `pytest -q tests/data_processing`：通过（CSV 解析/单位规范化/CO2RR 处理稳定）
- `pytest -q tests/debate`：通过（外部辩论输出 schema 可解析）

## 2026-01-26 — 工程隐患记录（先记录，不在本次修复）

以下属于“存在风险但用户要求先不动”的状态，后续在准备提交/协作前应处理：

- `project/youtu-agent/.env.full`：
  - 该文件是 git tracked；当前包含看起来像真实的 `UTU_LLM_API_KEY` 等敏感配置（有泄露/误提交风险）。
  - 建议后续：把真实密钥移到未跟踪的 `.env`（git ignored）中，并对泄露风险进行 key 轮换。
- `project/youtu-agent/AGENTS.md`：
  - 根目录的 `AGENTS.md` 当前处于删除状态（`git status` 显示 `D AGENTS.md`），可能是误删或与本 workspace 的 `memory-bank/AGENTS.md` 混淆。
  - 风险：丢失仓库贡献/开发约定，影响后续协作一致性。
- `project/youtu-agent/uv.lock`：
  - 当前 lockfile 的 registry 指向发生变化（例如从 `pypi.org` 改为镜像源），可能影响跨环境复现一致性。
  - 备注：本环境网络受限时，`uv run pytest ...` 可能触发依赖下载失败；已知可用替代是直接运行 `pytest ...`（使用已装依赖的 venv）。
- `project/youtu-agent/utu/practice/verify/chem_performance/`：
  - 该目录目前只残留 `__pycache__`（无源代码），是早期同名 shadowing 修复后的遗留物；不影响运行但可能造成目录结构困惑。
  - 建议后续清理（删除 pycache / 空目录）以减少误导，但本次先不动。

## 2026-01-26 — Step 7.3 外部文献数据库接入（完成）

背景：用户希望 chem-performance agent 在推理过程中可以使用“外部文献数据库”，以降低纯猜测并让经验蒸馏中的“查证据/用数据”类建议变得可执行（但仍禁止泛化到 web 搜索引擎）。

### 产物（spec-bank）

- 文献 DB 工具契约（tool contract + 外部 DB 最小 schema + 配置方式）：
  - `project/youtu-agent/spec-bank/chem_literature_db_tool.md`

### 产物（代码：模块化）

- SQLite 只读文献 store（stdlib-only；可配置表/列名以适配外部 DB schema）：
  - `project/youtu-agent/utu/literature/sqlite_store.py`
  - `project/youtu-agent/utu/literature/__init__.py`
- builtin toolkit（agent 可调用的 tools：healthcheck/search/get）：
  - `project/youtu-agent/utu/tools/chem_literature_db_toolkit.py`
  - 接线：`project/youtu-agent/utu/tools/__init__.py`（注册到 `TOOLKIT_MAP["chem_literature_db"]`）

### 配置接线

- 新增 toolkit config（可选引用；默认通过 env `CHEM_LITERATURE_DB_PATH` 指定外部 sqlite 路径）：
  - `project/youtu-agent/configs/tools/chem_literature_db.yaml`
- chem-performance agent 启用 `chem_literature_db` toolkit，并在 instructions 中说明推荐调用方式：
  - `project/youtu-agent/configs/agents/practice/chem_performance_agent.yaml`
- practice 目标描述调整：
  - 允许使用 `chem_literature_db`（若 DB 配置缺失则工具返回结构化 error，不抛异常）
  - 明确禁止泛化到 web 搜索/搜索引擎（只允许文献 DB 工具）
  - `project/youtu-agent/configs/practice/chem_performance.yaml`

### 测试（本地 venv 执行）

- 工具单测（临时 sqlite fixture；覆盖缺 DB / search / get）：
  - `project/youtu-agent/tests/tools/test_chem_literature_db_toolkit.py`
  - `pytest -q tests/tools/test_chem_literature_db_toolkit.py` → 通过
- 配置加载回归（确保新增 config 不破坏 Hydra/OmegaConf resolve）：
  - `pytest -q tests/test_config.py::test_load_toolkit_config tests/test_config.py::test_load_agent_config` → 通过

### 备注 / 风险提示

- 当前默认 `CHEM_LITERATURE_DB_PATH` 为空字符串；工具会返回 error payload（而不是抛异常）。要让 agent 真正用上文献检索，需要用户提供外部 sqlite DB 路径并保证表/列名与 config 对齐。
- 如果未来希望把“性能样本 id -> 文献”的映射打通，需要额外定义映射表/字段，并让 agent 在 prompt 中可获得 record_id（目前 question 里不包含 id）。

## 2026-01-26 — Chroma DB 现状盘点（完成）

背景：用户反馈其“文献数据库”实际是 Chroma（本地持久化目录：`project/youtu-agent/chroma_db/`），需要先搞清楚当前 DB 中已有的数据与可用字段。

### 盘点产物（spec-bank）

- Chroma DB 目录与数据结构盘点（包含 collection 名称、规模、metadata key、已知风险）：
  - `project/youtu-agent/spec-bank/chroma_db_inventory.md`

### 当前 Chroma DB 内容要点（来自直接 SQLite 检查）

- DB 路径：
  - `project/youtu-agent/chroma_db/chroma.sqlite3`
  - `project/youtu-agent/chroma_db/<segment_uuid>/`（HNSW 索引文件）
- 可见的 active collection（`collections` 表）：
  - `chemical_reactions_recommendation_agent2`（dimension=1024；cosine space）
- 以 chunk 为粒度存储文献内容：
  - `embedding_metadata` 中每个 chunk 包含 `reaction_type` / `doc_id` / `chunk_id` / `total_chunks` / `chroma:document`
  - 当前 reaction_type 覆盖：ORR/OER/EOR/UOR/HOR/HZOR/O5H（不含 HER/CO2RR）
- 异常/风险：
  - `segments` / `collection_metadata` 中出现一个 collection_id（`afa6f5e3-...`）但在 `collections` 表中缺失，疑似旧数据残留（orphaned segments）。

### 现有代码状态（仓库内）

- `project/youtu-agent/chroma_db/vector_store.py` 提供了一个 `VectorStore` 管理类（add/update/delete/query/similarity_search 等）。
- 但它当前不满足“可直接在本 repo 跑”的条件：
  - 代码引用 `utils.logger.Logger`（本仓库未提供该模块），疑似外部代码片段迁入。
  - `add_documents()` 在 `embeddings is None` 时不会真正调用 `collection.add(...)`（逻辑不完整）。

## 2026-01-26 — Step 7.4 Chroma + Voyage 文献检索接线（完成）

目标：把现有本地 Chroma 向量库（`project/youtu-agent/chroma_db/`）接入到 chem-performance 任务中，使 agent 能在推理过程中检索文献 chunk，并且在“未命中/低置信度”时明确返回，而不是强行给不相关 chunk 误导模型。

### 产物（代码：模块化）

- Voyage embedding wrapper（读取 env/config；用于 query embedding）：
  - `project/youtu-agent/utu/literature/voyage_embedder.py`
- Chroma 只读检索 store（PersistentClient + get_collection + query；包含 SQLite tmpdir 兼容处理）：
  - `project/youtu-agent/utu/literature/chroma_store.py`
- `chem_literature_db` toolkit 扩展为“多后端”（sqlite/chroma）：
  - `project/youtu-agent/utu/tools/chem_literature_db_toolkit.py`
  - Chroma backend 支持：
    - `reaction_type` metadata filter
    - `max_distance` 阈值过滤（cosine distance；越小越相似）
    - 若过滤后无结果，返回显式 payload：`hit=false` + `"No results (or all candidates are low-confidence)."`

### 配置接线（chem-performance 默认走 Chroma）

- chem-performance agent 默认启用 Chroma backend（collection 指向 `chemical_reactions_recommendation_agent2`）：
  - `project/youtu-agent/configs/agents/practice/chem_performance_agent.yaml`
- tool config 文件同步扩展（便于后续 generator / 其它 agent 复用）：
  - `project/youtu-agent/configs/tools/chem_literature_db.yaml`
- `.env`/`.env.example`/`.env.full` 增加 Voyage/Chroma 相关 env 变量占位：
  - `VOYAGE_API_KEY` / `VOYAGE_EMBED_MODEL=voyage-3-large` / `CHEM_LITERATURE_CHROMA_*`

### 测试（离线、无网络）

- Chroma backend 单测（本地临时 persistent chroma dir + 手工 embeddings；mock Voyage embed_query）：
  - `project/youtu-agent/tests/tools/test_chem_literature_db_toolkit_chroma.py`
  - `pytest -q tests/tools/test_chem_literature_db_toolkit_chroma.py` → 通过

### 关键工程注意事项

- Chroma client settings 一致性：
  - Chroma 的 SharedSystemClient 会按 `(path, settings)` 复用全局实例；若同一路径用不同 settings（例如 allow_reset True/False）会报错：
    - `"An instance of Chroma already exists ... with different settings"`
  - 因此 store 默认 `allow_reset=True`（但我们不调用 reset），避免与其它代码冲突。
- SQLite temp dir：
  - 部分环境下 Chroma/SQLite 会报 `unable to open database file`；store 初始化时会默认设置：
    - `SQLITE_TMPDIR=/tmp`, `TMPDIR=/tmp`
- 线程调用：
  - Chroma Rust backend 在后台线程里调用可能会 hang；保持 Chroma 调用在主线程。
- CLI/RunHooks 工具输出类型：
  - openai-agents 的 FunctionTool 结果可能是 `list/dict`（而非 string）。
  - 早期 `PrintUtils.truncate_text()` 只支持 `str/dict`，导致工具调用后在 `BaseRunHooks.on_tool_end()` 崩溃：
    - `AttributeError: 'list' object has no attribute 'splitlines'`
  - 已修复：`PrintUtils.truncate_text()` 支持任意 JSON-serializable 对象；`on_tool_end` 也按 Any 处理并做安全日志截断。

## 2026-01-27 — Step 7.5 文献遮蔽（label leakage 防护；完成）

背景：在 chem-performance 的某些样本中，Chroma 文献库会直接命中包含 ground-truth 数值的论文 chunk（例如摘要中直接写出 “overpotential = 288 mV”）。
这会导致：
- rollout 变成“查到答案就复制”，而不是推理预测（label leakage）
- 经验蒸馏也会偏向“优先查文献拿数值”，破坏后续泛化能力与评测可信度

用户决策：
- 遮蔽范围：仅在训练/评测跑数据集时启用（Training-Free GRPO practice + eval），**不影响 CLI** 的真实检索体验
- 遮蔽粒度：doc-level（按 DOI/doc_id 整篇文献遮蔽）
- 映射来源：`project/youtu-agent/rawdata/2-cleaned-abstracts-about-<REACTION_TYPE>.tsv`，其中 `index` 对应样本 `meta.id`，`doi` 对应 Chroma 的 `doc_id`

实现方式（避免并发污染；不通过 prompt 传递“黑名单”）：
- 在数据集 rollout 路径（`BaseBenchmark.rollout_one`）对每个 sample：
  - 解析 sample.meta 的 `reaction_type` + `id`
  - 解析该样本对应的 DOI/doc_id（详见下方；v1 用 TSV 映射，v2 直接用 meta.doc_id）
  - 深拷贝 agent config 并注入 `toolkits.chem_literature_db.config.masked_doc_ids=[doc_id]`（per-sample、非全局 env）
- `chem_literature_db` toolkit 在 Chroma backend 中强制过滤被遮蔽的 doc_id：
  - 搜索结果如果全部被过滤/或阈值过滤后为空：返回显式 `hit=false` 的 “No results …” payload（防止误导）
  - 工具输出不回显 masked_doc_ids（避免泄露答案来源）

代码产物：
- TSV 映射解析与缓存（只扫描需要的 id；避免加载整个 TSV 到内存）：
  - `project/youtu-agent/utu/literature/chem_performance_masking.py`
- rollout 注入点（train/eval only；CLI 不走此路径）：
  - `project/youtu-agent/utu/eval/benchmarks/base_benchmark.py`
- 工具侧过滤（masked_doc_ids 生效；无命中时显式 hit=false）：
  - `project/youtu-agent/utu/tools/chem_literature_db_toolkit.py`

测试：
- `project/youtu-agent/tests/literature/test_chem_performance_masking.py`
- `project/youtu-agent/tests/tools/test_chem_literature_db_toolkit_chroma.py`（包含 masked_doc_ids 过滤用例）

## 2026-01-27 — Step 7.6 chem_performance_v2 数据集（meta.doc_id；完成代码接线，待生成/上传）

背景：用户确认“训练时动态 TSV 映射过重”，希望把 `id -> DOI/doc_id` 直接写入性能数据集，避免训练/评测时再做映射扫描。

用户决策：
- meta 键名：`meta.doc_id`（与 Chroma metadata 字段 `doc_id` 一致）
- 新 dataset 名：`chem_performance_v2`

实现：
- dataset build 脚本支持一次性 join：
  - `project/youtu-agent/scripts/data/build_chem_performance_dataset.py`
  - 新增参数：`--add_meta_doc_id` / `--require_meta_doc_id` / `--rawdata_dir` / `--rawdata_file_template`
- rollout 注入逻辑更新为“优先读 meta.doc_id；缺失再 fallback 到 TSV resolver”（兼容 v1）：
  - `project/youtu-agent/utu/eval/benchmarks/base_benchmark.py`
- 配置默认切换到 v2（前提是用户已把 v2 upload 到 DB）：
  - `project/youtu-agent/configs/eval/chem/chem_performance.yaml`
  - `project/youtu-agent/configs/practice/chem_performance.yaml`

待用户执行（数据生成/上传属于一次性操作）：
- 生成 uploadable JSONL（推荐输出到新文件名，避免覆盖 v1 文件）：
  - `python3 scripts/data/build_chem_performance_dataset.py --add_meta_doc_id --require_meta_doc_id --output_file data/processed/chem_performance/chem_performance_dataset_v2.jsonl`
- 上传到 DB（注意：同 dataset_name 重复上传会累加；建议确认 DB 中无旧 v2 再 upload）：
  - `python3 scripts/data/upload_dataset.py --file_path data/processed/chem_performance/chem_performance_dataset_v2.jsonl --dataset_name chem_performance_v2 --data_format default`

## 2026-01-27 — Step 7.7 平衡抽样数据集（9 反应 * 50 = 450；完成）

背景：用户计划生成“真正的经验库”时，覆盖 9 个 reaction_type，但控制成本：
- 每个 reaction_type 抽 50 条
- 合计 450 条用于一次完整的 experience generation（Training-Free GRPO）

实现：
- 新增 stdlib-only 抽样脚本（从 uploadable dataset JSONL 中抽样，不依赖 DB）：
  - `project/youtu-agent/scripts/data/sample_chem_performance_balanced_dataset.py`
- 典型用法（从 v2 dataset JSONL 抽 450 条）：
  - `python3 scripts/data/sample_chem_performance_balanced_dataset.py --input_file data/processed/chem_performance/chem_performance_dataset_v2.jsonl --output_file data/processed/chem_performance/chem_performance_dataset_v2_450.jsonl --per_reaction 50 --shuffle_output`

后续（用户执行：上传并用于 practice）：
- 上传为独立 dataset（避免污染全量 v2）：
  - `python3 scripts/data/upload_dataset.py --file_path data/processed/chem_performance/chem_performance_dataset_v2_450.jsonl --dataset_name chem_performance_v2_450 --data_format default`
- practice run 时用 CLI override 指定 dataset（无需改 config 文件）：
  - `python3 scripts/run_training_free_GRPO.py --config_name chem_performance --practice_dataset_name chem_performance_v2_450 ...`

补充：由于当前 Chroma 文献库仅覆盖 7 种 reaction_type（不含 HER/CO2RR），后续“测试/超参实验”阶段先不使用 HER 与 CO2RR 数据：
- Chroma 覆盖的 reaction_type：ORR/OER/EOR/UOR/HOR/HZOR/O5H
- 缺失：HER、CO2RR
- 已生成对应的 7 反应平衡子集（7 * 50 = 350）：
  - `project/youtu-agent/data/processed/chem_performance/chem_performance_dataset_v2_350_noher_co2rr.jsonl`
  - 建议 upload 为 `chem_performance_v2_350_noher_co2rr`，并在测试/超参实验时用 `--practice_dataset_name` 覆盖。

## 2026-01-27 — Step 7.8 工具调用循环防护（DeepSeek thinking 多次重复 toolcall；完成）

问题：即使把 `max_turns` 从 6 提到 10，DeepSeek thinking 模式仍可能反复调用 `literature_search` 来“确认答案”，最终触发 `MaxTurnsExceeded`。

修复策略（硬约束，不靠 prompt）：
- RunHooks 在每次工具调用时统计 per-run 的 tool call 次数：
  - `project/youtu-agent/utu/hooks/base_hooks.py`
- Toolkit 层支持 `tool_call_limits` / `max_calls_per_run`，并在 run 内动态禁用超预算工具：
  - `project/youtu-agent/utu/tools/base.py`
- chem-performance agent 默认限制 `literature_search` 每个问题最多 1 次（防止循环）：
  - `project/youtu-agent/configs/agents/practice/chem_performance_agent.yaml`
  - `project/youtu-agent/configs/agents/practice/chem_performance_agent_aliyun_thinking.yaml`

## 2026-01-27 — Step 7.9 Training-Free GRPO Smoke（Test C）可用性修复：模型配置与空结果处理（完成）

背景：CLI 测试 B 通过，但在 Training-Free GRPO（Test C）阶段出现两类问题：
- Rollout 端报 404：`deepseek-reasoner` 不存在/无权限（实际是 provider 不支持该 model name）。
- Rollout 全失败后，`rollout_manager` 在取 `stat[0]` 时触发 `IndexError: list index out of range`，掩盖真实根因。

修复：
- Training-Free GRPO 支持用 `--agent_config` 覆盖 agent 配置（Hydra config name 或 configs/agents 下的 YAML 路径）：
  - `project/youtu-agent/utu/practice/utils.py`
  - 典型用法（Aliyun DashScope thinking）：`--agent_config practice/chem_performance_agent_aliyun_thinking`
- 让 practice 配置中的 rollout 参数真正生效：
  - `practice.rollout_concurrency` -> `evaluation.concurrency`
  - `practice.task_timeout` -> `RolloutManager(task_timeout=...)`
  - `project/youtu-agent/utu/practice/training_free_grpo.py`
- 当 batch 内没有任何样本进入 judged（通常意味着 rollout 全失败）时，抛出带计数信息的 `RuntimeError`，不再是 `IndexError`：
  - `project/youtu-agent/utu/practice/rollout_manager.py`

补充：为了避免每次跑 Training-Free GRPO 都要手写 `--agent_config practice/chem_performance_agent_aliyun_thinking`，
新增了一个专用 practice config：
- `project/youtu-agent/configs/practice/chem_performance_aliyun_thinking.yaml`
  - 绑定 eval config：`project/youtu-agent/configs/eval/chem/chem_performance_aliyun_thinking.yaml`

## 2026-01-28 — Step 7.10 Training-Free GRPO reward 全为 0（Aliyun thinking 推理字段不在 content；保持 verify 严格并 stitch `<think>`；完成）

现象（用户 hp_check baseline）：
- `chem_performance_aliyun_thinking` 跑完后 `evaluation_data.reward` 全为 0
- `Top reasoning` 全是：`Missing <think>...</think> block.`

根因（与 Step 4.1/chem_verify_spec 的“必须有 `<think>`”不冲突）：
- Aliyun DashScope compatible-mode 的 “thinking mode” 通常把推理放在独立字段（例如 `reasoning_content`），而 assistant 的 `content` 只包含最终输出（例如 `<answer>...</answer>`）
- 观测：在部分请求里，provider 甚至会把 `<answer>` 也放进 `reasoning_content`，导致 `content=""`；若不处理会出现 `final_output` 为空/缺 `<answer>` 的情况
- openai-agents SDK 会把该字段转换成 Responses-style 的 output item：`type=="reasoning"`，但我们之前只把 `final_output`（assistant content）写入 `EvaluationSample.response`，导致 verify 看不到字面上的 `<think>` 标签，从而奖励全为 0

修复策略（严格遵循 Step 4.1：缺 `<think>` 必须 reward=0；因此不改 verify 规则，而是让 rollout 产物满足规则）：
- 新增 reasoning 提取工具（从 RunResult.raw_responses 的 `type=="reasoning"` item 中提取 summary 文本）：
  - `project/youtu-agent/utu/utils/reasoning_extractor.py`
- Dataset rollout（train/eval 路径）写入 DB 前，把 provider 的 reasoning 字段 stitch 成 `<think>...</think>` 并拼接到最终输出前：
  - `project/youtu-agent/utu/eval/benchmarks/base_benchmark.py`
- 同时把 reasoning 作为 side-channel 存入 `trajectories`（便于后续 experience 蒸馏直接利用显式推理，而不是完全靠“推断”）：
  - `project/youtu-agent/utu/utils/agents_utils.py`

验证/测试：
- 单测覆盖 reasoning 抽取与 stitch 行为：
  - `project/youtu-agent/tests/utils/test_reasoning_extractor.py`

## 2026-01-31 — Step 8.0 MAD 外部引擎接入（rollout 调外部 repo；稳定优先；完成）

目标：把同事项目 `MAD` 作为“外部 Python 引擎”，在 **rollout 阶段**调用它生成预测，但保持 youtu-agent 现有：
- dataset/DB/batching
- chem verify / reward
- Training-Free GRPO experience distillation
完全不变。

实现（代码）：
- 新增外部引擎适配层（subprocess 调用，隔离依赖）：
  - `project/youtu-agent/utu/external_engines/mad_engine.py`
  - `project/youtu-agent/utu/external_engines/mad_runner.py`
- rollout 接入点（当 `agent.env.name == "mad"` 时走 MAD；否则走原 SimpleAgent/openai-agents Runner）：
  - `project/youtu-agent/utu/eval/benchmarks/base_benchmark.py`
- 配套配置文件：
  - agent: `project/youtu-agent/configs/agents/practice/chem_performance_agent_mad.yaml`
  - eval: `project/youtu-agent/configs/eval/chem/chem_performance_mad.yaml`
  - practice: `project/youtu-agent/configs/practice/chem_performance_mad.yaml`

关键稳定性修复（保证 chem_verify 可评分）：
- 问题 A：MAD 的 reasoning/trajectory summary 里会包含原始 prompt，而 prompt 模板含 `<answer>...</answer>` 示例，
  造成 verify 解析到“错误的第一个 answer block”，reward=0。
  - 修复：adapter 在 stitch `<think>` 前清理 reasoning 中的 `<answer>` block 与裸 `<answer>` 标签：
    - `project/youtu-agent/utu/external_engines/mad_engine.py`
- 问题 B：MAD 有时不会在最终输出包含 `<answer>...</answer>`，导致 verify 报 `Missing <answer>...</answer> block`。
  - 修复（稳定优先）：adapter 做 best-effort auto-fix：
    - 如果输出里已有 JSON dict：自动包一层 `<answer>...</answer>`
    - 若是单指标且没有 JSON：提取最后一个数字并构造 JSON dict
    - 多指标时：尝试按 `metric_key: number` 形式抽取
    - 代码：`project/youtu-agent/utu/external_engines/mad_engine.py`

验证（实测）：
- `mad_smoke_v3_epoch_0`：4 条样本均 `reasoning=NULL`（表示 verify 未产生错误信息，think/answer 解析通过），且经验生成正常。

调试/观测：如何查看 rollout 实际输出（<think>/<answer>）
- 从 `test.db` 查询 `evaluation_data.response` 并提取 tag 内容：
  - 示例脚本：打印每条的 `<think>` 前 600 字与完整 `<answer>`
- 如需看更细粒度的“步骤/工具调用过程”，查看 `evaluation_data.trajectories`（消息列表包含 tool calls 与观测）。

补充（便于人工检查、避免截断）：
- 新增 stdlib-only inspection 脚本，可将指定 exp_id 的 `<think>`/`<answer>` 原文导出为 markdown：
  - `project/youtu-agent/scripts/db/inspect_rollouts.py`
  - 用法示例（导出 reward 最高的 5 条）：
    - `SQLITE_TMPDIR=/tmp TMPDIR=/tmp .venv/bin/python scripts/db/inspect_rollouts.py --exp_id mad_baseline_n3_epoch_0 --stage judged --order reward_desc --limit 5 --include_question --out_file /tmp/mad_baseline_top5.md`

## 2026-02-02 — Step 8.1 MAD 超参实验准备（只调三参；加入实验汇总脚本；进行中）

背景：
- 用户确认 MAD rollout 的输出格式（单个 `<think>` + 单个 `<answer>`）满足现阶段经验蒸馏需求，无需再改模板。
- 下一步进入 Step 8：超参实验（仅调 `epochs / batch_size / grpo_n`）。

Baseline（用户已跑通）：
- 命令（示例）：
  - `SQLITE_TMPDIR=/tmp TMPDIR=/tmp .venv/bin/python scripts/run_training_free_GRPO.py --config_name chem_performance_mad --experiment_name mad_baseline_n3 --practice_dataset_name chem_performance_v2_350_noher_co2rr --epochs 1 --batch_size 10 --grpo_n 3 --rollout_data_truncate 30 --rollout_concurrency 1 --restart_step 0`
- DB 统计（`exp_id=mad_baseline_n3_epoch_0`，`30 samples * grpo_n=3 => 90 judged rows`）：
  - `n_judged=90`, `avg_reward≈0.4802`, `min=0`, `max=1`, `parse_err=0`
- 经验产物：
  - 生成的 agent config：`project/youtu-agent/configs/agents/practice/mad_baseline_n3_agent.yaml`
  - cache：`cache_experience`（`experiment_name=mad_baseline_n3`）

文献遮蔽（label leakage）状态说明：
- youtu-agent 的“文献遮蔽”实现点在 dataset rollout 路径（注入 `masked_doc_ids`）+ toolkit 侧强制过滤：
  - 注入（生成并传递 `masked_doc_ids`）：`project/youtu-agent/utu/eval/benchmarks/base_benchmark.py`
    - youtu-agent 内置 rollout：注入到 `chem_literature_db` toolkit config
    - MAD 外部引擎 rollout：通过 adapter 参数传给 MAD runner
  - 过滤：`project/youtu-agent/utu/tools/chem_literature_db_toolkit.py`（Chroma/SQLite backend 都支持按 `masked_doc_ids` 过滤）
- MAD 外部引擎现在也支持文献检索辅助推理，并且仍然执行 doc-level 遮蔽：
  - MAD runner 侧启用 RAG（默认开启，可用 `MAD_ENABLE_RAG=0` 关闭）：
    - `project/youtu-agent/utu/external_engines/mad_runner.py`
  - 依赖隔离：MAD venv 不直接依赖 chroma/voyage；而是通过 subprocess 调用 youtu-agent venv 的 runner：
    - runner：`project/youtu-agent/utu/external_engines/chem_literature_runner.py`
    - proxy（stdlib-only）：`project/youtu-agent/utu/external_engines/chem_literature_proxy.py`
    - 重要坑位：MAD repo 自带 `agents/` 包名会 shadow openai-agents 的 `agents` 包，
      导致在 MAD venv 内不能直接 `import utu`（`utu/__init__.py` 会 import `agents.run`）。
      因此 MAD runner 通过 file-based import 加载 proxy（避免触发 `utu/__init__.py`）。
  - 遮蔽注入点：`BaseBenchmark.rollout_one()` 解析 sample 的 `doc_id` 并通过 `masked_doc_ids` 传入 MAD adapter：
    - `project/youtu-agent/utu/eval/benchmarks/base_benchmark.py`
    - `project/youtu-agent/utu/external_engines/mad_engine.py`
  - 遮蔽执行点：`chem_literature_db` toolkit 在 Chroma backend 过滤 `metadata.doc_id in masked_doc_ids`，
    且 tool 输出不会泄露 masked 列表：
    - `project/youtu-agent/utu/tools/chem_literature_db_toolkit.py`

为超参 sweep 增加的对比工具（stdlib-only；避免 pandas/uv 依赖）：
- 新增 DB 汇总脚本：`project/youtu-agent/scripts/db/summarize_experiments.py`
  - 用法示例：
    - `SQLITE_TMPDIR=/tmp TMPDIR=/tmp .venv/bin/python scripts/db/summarize_experiments.py --exp_id mad_baseline_n3_epoch_0`
    - 或按前缀列出：`... --exp_prefix mad_hp_ --order avg_reward_desc`

下一步（实验纪律；参见 `spec-bank/hyperparam_experiments.md`）：
- 在同一轮 sweep 内固定：
  - dataset（建议先用 `chem_performance_v2_350_noher_co2rr` + `rollout_data_truncate=30/60`）
  - `rollout_concurrency=1`（稳定优先）
  - temperature/top_p/timeout/verify/reward 逻辑
- 只调整三参：`epochs`, `batch_size`, `grpo_n`，并把三参编码进 `experiment_name`（便于 DB 汇总）。

RAG + masking 验证（MAD 外部引擎）：
- 目标：在进入超参 sweep 前，确认：
  - MAD rollout 能稳定调用文献检索（`search_rag`）
  - 遮蔽 doc_id 不会泄露进 trajectory/tool 输出（label leakage prevention）
- 验证 1（单样本 smoke）：
  - `experiment_name=mad_rag_mask_smoke_v2`，`truncate=1`
  - `search_rag in traj = True`
  - `has 'RAG System is not configured' = False`
  - `masked doc_id leaked = False`
- 验证 2（10 样本稳定性）：
  - `experiment_name=mad_rag_mask_t10`，`truncate=10`, `batch_size=5`, `grpo_n=1`
  - `n_judged=10`, `rows containing search_rag=10`
  - `leak_count=0`（masked doc_id 未出现在 trajectories JSON）

RAG ablation（rag on/off；truncate=30）结果（用户已跑完）：
- 汇总（`scripts/db/summarize_experiments.py --exp_prefix mad_ablate_rag_ --order avg_reward_desc`）：
  - `mad_ablate_rag_off_t30_epoch_0`: `n_judged=30`, `avg_reward=0.4925`, `pass>0=96.7%`, `parse_err=0`, `guidelines=11`
  - `mad_ablate_rag_on_t30_epoch_0`:  `n_judged=30`, `avg_reward=0.4386`, `pass>0=86.7%`, `parse_err=0`, `guidelines=18`
- 现象：RAG on 平均奖励更低（而且 `reward==0` 的样本更多）。

根因分析（稳定优先；先修“单位/尺度”问题）：
- 注：本段分析对应当时的数据处理口径（overpotential 以 `V` 存储/评测）。2026-02-04 起已切换为 overpotential=`mV`（见文末新条目），因此旧实验与新实验不再可直接对比。
- 两组都有“单位/尺度错位”导致 reward 接近 0 的案例（典型表现：把 `mV` 当成 `V`、把 `%` 当成 0~1 小数、把 `mA mg^-1` 当成 `A mg^-1`）。
- 该错位在 RAG on 更常见：因为检索返回的文献片段经常以 `mV/%/mA` 表达，MAD 会把这些数字直接抄进 `<answer>`，但我们的 dataset 预处理已统一为：
  - 电位/过电位：`mV -> V`（`spec-bank/data_processing_rules.md`）
  - 百分数：`% -> 0~1`（`spec-bank/data_processing_rules.md`）
  - EOR mass_activity：GT 多为 `A mg^-1`（DB 实测范围约 `0.045~25.67`）
- 结论：在不显式提示单位规范时，“加 RAG”会把模型拉向 paper 常见单位，从而更容易 100~1000x 量级错误，奖励反而下降。

修复（已落地；不改输出格式；只补充输入侧单位约束）：
- 在 Training-Free GRPO preprocess 阶段，对 `dataset.startswith("chem_performance")` 的样本自动追加“单位/尺度规范”提示：
  - potentials/overpotentials：统一输出 `V`（看到 `mV` 需要 /1000）
  - mass_activity：统一输出 `A mg^-1`（看到 `mA mg^-1` 需要 /1000）
  - faradaic_efficiency：统一输出 `0~1` 小数（看到 `%` 需要 /100）
  - 代码：`project/youtu-agent/utu/eval/processer/training_free_grpo_processor.py`
  - 单测：`project/youtu-agent/tests/eval/test_training_free_grpo_processor_units.py`

遮蔽有效性复核（针对“检索结果里的数值像是 ground truth”这一疑虑）：
- 结论：目前实现的 **doc-level masking** 生效；“数值碰巧一致/被其它文献引用到”不等价于遮蔽失效。
- 在现有实验里做了自动审计（从 `evaluation_data.trajectories` 解析 tool obs）：
  - `exp_id=mad_rag_mask_t10_epoch_0`: `doc_id substring hits=0`, `doi:... exact hits=0`
  - `exp_id=mad_ablate_rag_on_t30_epoch_0`: `doc_id substring hits=0`, `doi:... exact hits=0`
  - 说明：tool observation 中未出现样本 `meta.doc_id`（大小写不敏感也未出现），因此不存在“把被遮蔽 DOI 的 chunk 直接检索回来”的证据。
- Chroma 侧重复 doc_id 检查（SQLite 直查 `embedding_metadata.key='doc_id'`）：
  - `10.1002/ente.202000949` / `10.1002/smll.202411043` / `10.1007/s40820-024-01493-3` 均只存在单一 doc_id 变体（无 `doi:` / `https://doi.org/` 等重复键），因此不存在“同一篇论文以不同 doc_id 存两份导致遮蔽漏掉”的迹象。

下一步：
- 用新 `experiment_name`（避免覆盖旧 exp_id）重跑一轮 rag on/off（truncate=30）对比：
  - 目标：确认“单位/尺度错位导致的 0 分”显著减少后，RAG on 是否仍然低于 rag off。
- 通过后再进入 Step 8 超参 sweep（只调三参：`epochs/batch_size/grpo_n`；其余固定）。

RAG ablation（加入“单位/尺度规范”提示后重跑；truncate=30；用户已跑完）：
- `mad_ablate_rag_on_units_t30_epoch_0`: `n_judged=30`, `avg_reward=0.7364`, `min=0.1179`, `max=0.9802`, `pass>0=100%`, `parse_err=0`, `guidelines=42`
- `mad_ablate_rag_off_units_t30_epoch_0`: `n_judged=30`, `avg_reward=0.7271`, `min=0.0006`, `max=0.9919`, `pass>0=100%`, `parse_err=0`, `guidelines=10`
- 现象：两组都显著提升（对比旧的 rag_on/off 基线），且 RAG on 略高于 RAG off（差异很小，但方向正确）。
- 观测：两组均未出现“明显单位错位”的异常值（例如 FE>1 / overpotential>1.5V / mass_activity>200A mg^-1 的预测）；说明输入侧单位规范提示起效。

结论（用户决策）：
- Step 8 超参实验阶段 **固定启用 RAG**（`MAD_ENABLE_RAG=1`），并保持：
  - 文献遮蔽（masked_doc_ids）仍开启
  - `MAD_RAG_MAX_DISTANCE`、`MAD_RAG_LIMIT`、`MAD_RAG_TIMEOUT_S` 保持固定以保证可比性

超参 sweep 执行规范（新增）：
- 实验命名规范（编码固定项 + 三参，便于 DB 汇总；仅使用文件名安全字符）：
  - `mad_hp_rag{0|1}_u{0|1}_{ds}_t{truncate}_e{epochs}_b{batch_size}_n{grpo_n}`
  - 示例：`mad_hp_rag1_u1_ds350_t30_e1_b30_n3`
- 自动化脚本（stdlib-only）：
  - `project/youtu-agent/scripts/run_hyperparam_sweep.py`
  - 用途：按网格批量跑 `epochs/batch_size/grpo_n`，每个组合自动生成 `experiment_name` 并在每次运行后打印该 exp 的汇总表。

超参 sweep（阶段 1：先定 batch_size；epoch=1 固定；grpo_n=3 固定；truncate=40；RAG=on）
- 运行（用户实测）：
  - `mad_hp_bs1_rag1_u1_ds350_t40_e1_b10_n3_epoch_0`:
    - `n_judged=120`, `avg_reward=0.6487`, `min=0`, `max=0.9931`, `pass>0=100%`, `parse_err=0`, `guidelines=24`
  - `mad_hp_bs1_rag1_u1_ds350_t40_e1_b20_n3_epoch_0`:
    - `n_judged=120`, `avg_reward=0.6558`, `min=0`, `max=1.0`, `pass>0=100%`, `parse_err=0`, `guidelines=33`
- 结论：`batch_size=20` 略优（差异不大），后续阶段固定 `batch_size=20` 扫 `grpo_n`（2/3/4），`epochs` 暂固定 1。

## 2026-02-04 — Reward Redesign (Per-Reaction Single Metric + Unit Conventions)

背景：用户决定在本项目阶段“收敛每个反应只关注一个核心指标”（O5H/CO2RR 例外），并且把单位约定改成更贴近论文写法（特别是 overpotential 用 mV）。

### 用户最终口径（本阶段）

- HER / OER / HzOR：仅关注 `overpotential_10mAcm-2`，并按 **η@10 mA cm−2** 口径理解（即使原始 record 未显式写明 10 mA cm−2）
  - 对应的 metric key 统一为 `overpotential_10mAcm-2`
  - overpotential_10mAcm-2 的 canonical unit 改为 **mV**
- ORR：仅 `half_wave_potential`（canonical unit: V）
- HOR：仅 `exchange_current_density`（canonical unit: **mA cm−2**）
  - 丢弃“times greater / fold improvement”等不可换算的相对描述
- UOR：仅 `potential_10mAcm-2`（canonical unit: V；本阶段把 potential / overpotential 抽取统一到同一 key）
- EOR：仅 `mass_activity`（单位保持现有抽取：A mgX⁻1）
- O5H：仅关注 `faradaic_efficiency`（0~1 小数）
- CO2RR：多指标情况下等权；当前 raw 数据通常只有 faradaic_efficiency

### 代码落地（关键变更点）

数据处理（raw -> processed）：
- reaction_type 级别的指标范围过滤（只保留本阶段关注的 metric keys）：
  - `project/youtu-agent/utu/data_processing/chem_performance/constants.py`
  - `REACTION_ALLOWED_METRICS`
- key-aware 单位归一化（最重要变化：overpotential_10mAcm-2 -> mV；potential/half_wave_potential -> V；exchange_current_density -> mA cm−2）：
  - `project/youtu-agent/utu/data_processing/chem_performance/metrics.py`
- processor 侧应用 “allowed metrics + key-aware normalization”，并在 HOR 上丢弃不可换算单位：
  - `project/youtu-agent/utu/data_processing/chem_performance/processor.py`

Training-Free GRPO 输入侧单位提示（防止 RAG 把 V/mV/% 直接抄进 `<answer>` 造成量级错位）：
- 更新 unit conventions 注入文案：
  - `project/youtu-agent/utu/eval/processer/training_free_grpo_processor.py`

verify/reward：
- 当前阶段：CO2RR 等权；其它 reaction 默认等权（且多数为单指标；O5H 也已收敛为单指标 FE）：
  - `project/youtu-agent/utu/practice/verify/chem_performance_lib/reward.py`
- verify 入口从 `sample.meta.reaction_type` 透传 reaction_type 给 reward：
  - `project/youtu-agent/utu/practice/verify/chem_performance_verify.py`

### 单测更新（确保行为稳定）

- 数据处理：`project/youtu-agent/tests/data_processing/test_chem_performance_processing.py`
- verify/reward：`project/youtu-agent/tests/practice/test_chem_performance_verify.py`
- unit conventions 注入：`project/youtu-agent/tests/eval/test_training_free_grpo_processor_units.py`

### 备注（对实验可比性的影响）

- 由于单位口径与 reward 聚合逻辑发生变化，旧的超参 sweep（基于 overpotential=V 的老口径）与新实验结果不再可直接对比。
- 建议在 DB 中使用新的 dataset_name / exp_prefix 以避免混淆。
# 进展记录（ChemCouncil）

说明（迁移提示）：
- 本文件包含从早期 `youtu-agent` 阶段迁移来的进展记录，因此会出现历史路径（如 `project/youtu-agent/...`）。
- 在 ChemCouncil 单仓库中，对应路径一般为：`project/chem-loop/youtu-chem-loop/...`（如需精确定位，请以仓库实际目录为准）。
- 当前权威设计以：
  - `memory-bank/architecture.md`
  - `memory-bank/design-document.md`
  为准；闭环操作流程以 `spec-bank/closed_loop_workflow.md` 与仓库 README 为准。

## 2026-03-13 — 经验库段落化（micro-card）+ 超参选择（b=4,n=2）+ 清洗与前端验收计划

背景：我们在 balanced smoke / full v5_500 经验蒸馏过程中确认：
- “结构化输出（format/parse）”可以稳定达到高通过率，但经验内容如果过于宽泛，会降低化学任务的可用性。
- 化学任务更适合“可检索的微经验卡”：每条针对一个具体 `reaction_type + metals + target`，并包含量化锚点（GT/range）与适用边界。

### 经验蒸馏（最关键）从“口号”升级到“段落”

目标：每条经验是 **one-line、multi-sentence paragraph**（便于后端 JSON 处理，同时保证信息密度）。

改动位置（prompt + 训练目标）：
- 经验抽取 prompt：要求每条是 paragraph（至少 3 句），并显式包含 context/anchor/how-to-use/caveat：
  - `project/chem-loop/youtu-chem-loop/utu/prompts/practice/experience.yaml`
- 经验合并/更新 prompt：强调“单行但多句”，禁止把卡片压缩成一句标题：
  - `project/chem-loop/youtu-chem-loop/utu/prompts/practice/experience.yaml`
- learning_objective 补充：写明 “multi-sentence paragraph style”：
  - `project/chem-loop/youtu-chem-loop/configs/practice/chem_performance_mad.yaml`

### 超参实验（先定 batch_size，再定 grpo_n）

实验约束（考虑 WSL/本地环境可用性）：
- 并发在高负载时可能触发 MAD 子进程被 kill（`returncode=-9`）或网络/DNS 抖动；因此建议默认 `rollout_concurrency=4`，必要时再上调。
- `batch_size` 在实验同学“每次只有少量新数据”场景下更偏好小值（更便于频繁更新），即便 reward 差异不大。

阶段 A：固定 `grpo_n=3`，扫 `batch_size`（3,4,5,6,10,15,20）。
- 观测：`batch_size=15` 与 `batch_size=4` 平均 reward 差距很小（同量级），但 `b=4` 更适合增量回流频繁更新。
- 决策：后续阶段 B 使用 `batch_size=4`。

阶段 B：固定 `batch_size=4`，扫 `grpo_n`（2,3,4,5,6,7）。
- 结果：`grpo_n=2` 在本次 sweep 中平均 reward 最好且 parse_err 低。
- 决策：全量经验库生成优先采用 `batch_size=4, grpo_n=2`（并发按资源从 4 起步）。
- Web 经验回流默认参数同步：
  - 后端默认 `grpo_n=2`（可用 env 覆盖）：`CHEMCOUNCIL_EXPERIENCE_GRPO_N=2`
  - `.env.example`/`.env.full` 增加对应字段，避免前后端默认值不一致。

### Web UI 测试数据（用于验收前端）

为前端验收提供两类数据：
1) 直接上传的 CSV fixture（覆盖 9 种 reaction_type，含 CO2RR product）：
   - `project/chem-loop/fixtures/web_ui/experimental_records_demo.csv`
   - `project/chem-loop/fixtures/web_ui/experimental_records_demo_cn_headers.csv`（中文表头）
2) 预置 job 历史（让“手动回流/效果评估”页面有数据可看，不必真的跑大作业）：
   - `project/chem-loop/scripts/seed_web_demo_jobs.py`

### 经验库质量保底：清洗“过短/空壳”经验

问题：少量卡片可能只剩标题或缺少关键信息（<200 chars），会污染检索结果（占坑但信息量低）。

落地：
- 新增清洗脚本（删除长度 <200 的 `[G..]` guideline blocks，并输出报告）：
  - `project/chem-loop/scripts/clean_agent_experiences.py`
- 本次清洗产物示例（full v5_500 run 的 agent YAML）：
  - 输入：`project/chem-loop/state/experience_runs/mad_full_v5_500_rag1_u1_t500_e1_b4_n2_c4_20260312_130332_agent.yaml`
  - 输出：`project/chem-loop/state/experience_runs_local/mad_full_v5_500_rag1_u1_t500_e1_b4_n2_c4_20260312_130332_agent.min200.cleaned.yaml`
  - 报告：`project/chem-loop/state/experience_runs_local/mad_full_v5_500_rag1_u1_t500_e1_b4_n2_c4_20260312_130332_agent.min200.clean_report.txt`

### 下一步：前端（Web UI）验收 checklist（看改动是否符合预期）

目标：验证 UI 能正确展示/下载经验库与历史归档，并且更新链路（job）可用。

建议最小验收步骤：
- 启动（Docker）：`docker compose up -d --build`，打开 `http://localhost:8000`
- API 快速检查（无需 token 时）：
  - 一键 smoke 脚本：`project/chem-loop/scripts/smoke_web_api.sh`
  - `GET /api/health`：服务与路径 OK
  - `GET /api/experience/meta`：能读到当前 `experience.yaml` 的 `updated_at_utc/source_agent_yaml`
  - `GET /api/experience/pack`：经验 pack 可下载
  - `GET /api/experience/history`：能列出归档（如果已存在）

注意：Docker 部署下 `youtu-chem-loop/configs/agents/practice/experience.yaml` 是到 `/state/experience_youtu.yaml` 的 symlink。
若要让 UI 展示“本次新生成”的经验库，需要先把目标 pack promote 到 `/state/experience_youtu.yaml`（闭环脚本支持 promote；也可手动替换后重启容器）。
为方便 promote（不依赖容器内操作），提供脚本：
- `project/chem-loop/scripts/promote_experience_pack_to_state.sh`

### 效果评估（Analytics）文案优化

前端页面文案已改为更通俗的解释（强调 score 的 0~1 范围与“越高越好”），避免用户直接看到 `mean_score/mean_rel_error` 这种工程名词：
- `project/chem-loop/chemcouncil/static/app.js`

## 2026-03-14 — 手动回流小样本提示（建议攒到 batch_size=4）

现象：手动回流即使只填 2 行实验记录（例如 HER + CO2RR），也可能在构造训练数据时变成 3 条训练样本（CO2RR 通常会拆成 2 条任务）。小于 `batch_size=4` 仍可更新，但更慢/性价比更低，也更容易在本地环境（WSL2/Docker）触发不稳定。

落地：前端增加说明，并在“手动回流”提交时对 `estimated_samples < 4` 弹出确认提示，避免误触发重更新。
- `project/chem-loop/chemcouncil/static/app.js`

## 2026-03-14 — Web UX：历史推荐 + 删除错误回合 + 经验库版本切换 + 按记录聚合

用户痛点（实验流程）：
- 回流数据需要严格绑定到“对应的推荐记录”，避免 A/B 混写。
- 如果填错数据/跑半截，需要能把错误回合从效果评估里移除，并能把经验库切回未污染版本。
- 效果评估希望按 batch_size=4 的节奏看趋势（每 4 条记录一个点），同时允许切换成累积/按回合视图。
- 需要一个独立的“历史推荐”页面，便于查看/复用/隐藏推荐任务。

落地（前端）：
- 手动回流草稿按 `recommendation_job_id` 分开存储（localStorage），切换推荐不会混在一起。
- “效果评估 / Analytics”：
  - 支持按记录分桶（每 N 条=1点）、按记录累积（1–N,1–2N…）、按回合（每次回流=1点）三种视图
  - 回合表格支持删除/隐藏错误回合（从评估中移除）
- 新增“历史推荐”页面：
  - 列出 MAD rank job，支持筛选、跳转到手动回流、隐藏/恢复 job

落地（后端）：
- Job 增加 `deleted_at_utc` 字段，用于软删除（隐藏 job，不删除文件）。
- 新增经验库版本切换接口：`POST /api/experience/activate/{archive_id}`（激活历史 pack；覆盖前会自动备份当前版本到 archive，便于回滚）。

代码位置：
- 前端：`project/chem-loop/chemcouncil/static/index.html`、`project/chem-loop/chemcouncil/static/app.js`
- 后端：`project/chem-loop/chemcouncil/server.py`、`project/chem-loop/chemcouncil/jobs.py`

## 2026-03-16 — Web UX：历史推荐结果/日志友好展示 + 经验反馈搜索候选 + 效果评估合并展示

用户诉求（前端可用性）：
- 历史推荐里“隐藏键”语义不清晰：需要明确这是软删除（可恢复），不是物理删除。
- 历史推荐里的结果与日志要能在网页里“好读”地展示，而不是只能点 raw JSON/纯文本。
- “经验反馈”页的搜索框需要支持候选下拉：输入关键字 -> 下面弹出匹配项 -> 点击即可新增反馈块并加载该推荐。
- “效果评估 / Analytics”里不希望“记录区间”和“记录明细”分成两个块，想合并展示，减少滚动与重复。

落地（前端）：
- 历史推荐（History）：
  - “隐藏”按钮改为 `隐藏（可恢复）`，并在说明文案里明确：隐藏是软删除，不会删除结果/日志文件，可恢复。
  - 新增两个按钮：
    - `查看结果`：在表格下方展开并以更易读的方式展示 top_k 卡片 + 完整 9 反应排序表（仍保留“下载结果 JSON”）。
    - `查看日志`：在表格下方展开并展示“关键行（错误/警告/异常）”+“完整日志 tail”（仍保留“下载日志”）。
- 经验反馈（Feedback）：
  - 搜索框支持候选下拉：输入关键字会触发 `/api/recommendations?q=...`，下方展示候选按钮列表。
  - 点击候选：自动创建并加载一个新的“推荐反馈块”；如果该 job 已被某个块使用，则自动跳转并激活该块（避免重复）。
  - 交互细节：支持 `Esc` 关闭候选；点击页面其他区域自动收起候选。
- 效果评估（Analytics）：
  - 移除“区间表格 + 明细表格”两个卡片的拆分，统一在一个卡片内按分组（bucket/cumulative/round）用 `<details>` 展示：
    - summary 行包含区间/均值/误差棒/记录数/更新时间
    - 展开后展示逐条记录（reaction/metric/pred/actual/abs/rel/reco_id/update_id）
  - round 模式下的“删除此回合”（soft-delete update job）按钮保留，放到每个 round 的展开区域内。

代码位置：
- 前端：`project/chem-loop/chemcouncil/static/index.html`、`project/chem-loop/chemcouncil/static/app.js`、`project/chem-loop/chemcouncil/static/styles.css`

运行提示（Docker）：
- 修改前端后需要重新构建镜像：`cd project/chem-loop && docker compose up -d --build`

## 2026-03-16 — Web UX：历史推荐展示辩论过程与轨迹（TopK 可追溯）

用户诉求：
- 在“历史推荐”里希望能看到最终 top_k 反应的证据与决定过程（辩论过程 + 轨迹），而不是只有最终排序结果。

现状与约束：
- Rank job 的 `result.json` 是稳定接口（来自 `rank_*.json`），只包含排序摘要，不包含每个反应的完整辩论过程。
- 当推荐时启用了 `--save-each-reaction`（Web 默认开启），MAD 会在该 job 的 `artifacts/mad_outputs/` 下保存每个反应的 `result_*.json`（包含 `debate_history` / `reasoning_trajectory` 等）。

落地（后端 API）：
- 新增 per-reaction 轨迹接口（从 job artifacts 读取，不改 DB）：
  - `GET /api/jobs/{job_id}/mad_traces`：列出该 job 保存的各反应轨迹（reaction_type -> url / mtime / 是否含 debate_history）
  - `GET /api/jobs/{job_id}/mad_traces/{reaction_type}`：返回该反应的完整 `result_*.json`（包含 debate_history / reasoning_trajectory / proposals / reviews 等）

落地（前端 History UI）：
- “查看结果”里的每个 top_k 反应卡片新增：
  - “查看辩论过程与轨迹”折叠块：打开后自动加载对应反应的轨迹 JSON，并以“阅读版摘要 + 预览 + 可下载原始 JSON”的方式展示：
    - 决策摘要：winner 提案、辩论轮数、事件统计、proposal 状态（surviving/defeated/withdrawn）
    - 关键证据：winner.evidence（若存在）
    - 评价摘要：针对 winner 的 review（截断预览）
    - reasoning_trajectory（全文，折叠）
    - debate_history（compact 预览，折叠）
- 若某次推荐未保存轨迹（没开 `--save-each-reaction`），UI 会提示“找不到轨迹”并给出如何开启的说明。

代码位置：
- 后端：`project/chem-loop/chemcouncil/server.py`
- 前端：`project/chem-loop/chemcouncil/static/app.js`

## 2026-03-17 — Analytics：记录明细逐条忽略/恢复（不改原始 CSV）

用户诉求：
- “效果评估”的记录明细里，如果某条实验数据填错，希望能 **忽略此条**，让统计/图表跳过它，同时不破坏原始上传文件（便于审计）。
- 需要明确：忽略不会回滚经验库；若错误数据已用于更新经验库，应回滚到未污染版本并重新提交反馈。

落地（后端）：
- 在 experience_update job 的 `job.json.payload` 中存储 ignore 列表：
  - `analytics_ignore_csv_rows: list[int]`（1-based CSV 行号）
- 新增两个 API（幂等）：
  - `POST /api/jobs/{job_id}/analytics_ignore`：添加 ignore 行号（支持 `csv_row_index` 或 `csv_row_indices`）
  - `POST /api/jobs/{job_id}/analytics_unignore`：移除 ignore 行号
- `/api/analytics` 输出中为每条 record 增加 `ignored: bool`，并在聚合统计时跳过 ignored 行：
  - round summary 的 `num_records/mean_rel_error/std` 基于未忽略记录
  - overall 统计同理，并额外返回 ignored 计数方便 UI 展示

落地（前端 Analytics UI）：
- “记录明细”表格每行新增操作列：
  - 未忽略：按钮 `忽略此条`
  - 已忽略：标记 `已忽略` + 按钮 `恢复`
- 图表与分组统计使用未忽略记录计算，但分桶区间仍按原始顺序（忽略不会导致桶边界漂移）。
- UI 额外提示：忽略只影响效果评估；需要回滚经验库请到 `经验库 → 历史版本` 激活旧包，然后在 `经验反馈` 重新提交。

代码位置：
- 后端：`project/chem-loop/chemcouncil/server.py`、`project/chem-loop/chemcouncil/analytics_ignore.py`
- 分析：`project/chem-loop/chemcouncil/analytics.py`
- 前端：`project/chem-loop/chemcouncil/static/app.js`、`project/chem-loop/chemcouncil/static/styles.css`
