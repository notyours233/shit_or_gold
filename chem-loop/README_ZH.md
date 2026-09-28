# ChemCouncil（一体化工作区）

这是一个用于“材料性能经验库生成与推荐排序”的一体化工作区（monorepo）。当前主线是：

1) 用已抽取的材料性能数据库跑 **training-free GRPO**，蒸馏出可复用的 **经验库**（guidelines，形如 `[G0]`）  
2) 把经验库导出成稳定文件 `experience.yaml`，供多智能体辩论/排序项目在推理时检索借鉴  
3) 再输入材料名称与可选实验提示词，针对所选性能方向执行 MAD 推荐，此时同时使用经验库和文献向量库

目录结构：

- `youtu-chem-loop/`：training-free GRPO 生成/更新经验库 + 数据处理 + DB 工具 + 一键闭环脚本
- `MAD/`：只在推荐端使用的多智能体辩论/排序（rank 模式）项目

---

## 0) 一次性安装 + 单一 `.env`（强烈推荐的运行方式）

本工作区统一约定：**根目录只有一个 `.env`**（包含密钥），各子项目都通过 `python-dotenv`
向上查找 `.env` 来加载配置。

### 0.1 创建 `.env`

```bash
cd ChemCouncil
cp .env.example .env
# 然后编辑 .env，填写密钥
```

最少需要（用于 youtu-chem-loop 单智能体 GRPO）：

- `UTU_LLM_API_KEY`
- `UTU_LLM_BASE_URL`
- `UTU_LLM_MODEL`

如果你启用文献 RAG（Chroma + Voyage embeddings），还需要：

- `VOYAGE_API_KEY`

### 0.2 一次性安装依赖（整个工作区只用一个 venv）

```bash
cd ChemCouncil
./scripts/setup_venv.sh
source .venv/bin/activate
```

该脚本会创建 `chem-loop/.venv`，并一次性安装：

- `youtu-chem-loop` / `MAD` 运行所需的第三方依赖（来自根目录 `requirements.txt`）

说明：
- 这里不需要 `pip install -e` 子项目：我们运行脚本时会进入对应子目录执行，因此 `import` 会从当前目录解析。

---

## Web 前端 + 后端（给别人使用的入口）

本仓库提供了一个最小可用的 Web 应用（aiohttp 后端 + 静态前端），把现有 CLI 流程包装成 HTTP 接口：

- **生成材料性能经验库**：已抽取性能 JSONL → GRPO dataset → Training-Free GRPO → 同步 `experience.yaml`
- **材料性能推荐（rank 模式）**：调用 `MAD/main.py --rank-reactions`，返回 property ranking + Top-K
- **真实实验回流更新经验库**：上传 CSV/XLSX（或选择一条历史推荐记录）→ 构建 dataset → 增量 GRPO 更新 → 刷新并同步 `experience.yaml`
- **效果评估**：统计推荐预测 vs 真实实验的误差，并按回合展示趋势
- 面向实验同学的 UI：导航分页面（推荐/回流/经验库/效果评估），支持中英双语与明暗主题，经验库支持查看“当前 + 历史归档”

### 本机运行（开发/调试推荐）

```bash
cd ChemCouncil
./scripts/run_web.sh
```

然后访问：

- `http://localhost:8000`

### Docker 运行（给不想装依赖的人用）

```bash
cd ChemCouncil
./scripts/init_state.sh
docker compose up --build
```

说明：

- 先准备 `.env`（`cp .env.example .env` 并填写密钥），否则后端无法调用模型。
- 本仓库的 Docker 镜像 **只包含代码**；经验库与文献数据库等 **持久化数据不进入镜像层**。
- `docker-compose.yml` 会把宿主机的 `./state/` 挂载到容器的 `/state`，并通过 symlink 让代码继续使用原路径：
  - `test.db` → `/state/test.db`
  - `MAD/data/chroma_db` → `/state/chroma_db`
  - `experience.yaml`（两个位置）→ `/state/experience_*.yaml`
  - job 日志/上传/结果 → `/state/jobs`
- 同时，`docker-compose.yml` 会强制设置 `UTU_DB_URL=sqlite:////state/test.db`，保证不同工作目录的子进程都使用同一个 DB 文件。
- 另外，Docker 环境里不带 repo-local 的 `.venv`，所以 `docker-compose.yml` 会强制设置 `MAD_PYTHON_BIN=/usr/local/bin/python`（避免你看到 `../.venv/bin/python not found` 这类错误）。
- 如果你要启用文献 RAG，请确保宿主机的 `MAD/data/chroma_db/` 已经构建完整（`docker-compose.yml` 会把它挂载到容器的 `/state/chroma_db`）。
- **内存提醒（非常重要）**：大 Chroma DB + 并发会很容易 OOM
  - **服务器默认/较低内存**：`MAD_RAG_MODE=shared`（所有 agents 共享已验证的 Voyage `literature_agent2` collection）
  - **高内存可选模式**：只有在四套 embedding 链路都验证通过后，才设置 `MAD_RAG_MODE=per_agent`
  - 每个材料推荐 job 都会启动一个 MAD 进程并可能加载 Chroma；`CHEMCOUNCIL_RECOMMENDATION_CONCURRENCY` 调高会让内存和模型调用量近似按材料数放大
  - 推荐表单的“同时评估方向数”还会放大单个材料内部的方向级调用；例如 10 个材料 × 3 个方向并发，峰值可能接近 30 个方向任务
  - `CHEMCOUNCIL_JOB_CONCURRENCY` 只控制经验生成/反馈更新等通用后台任务，不控制推荐材料池
- GRPO 不启动 MAD 子进程；`rollout_concurrency` 控制单智能体模型调用并发，仍建议从 1 开始逐步增加以避免 API 限流和检索负载过高
- 可选鉴权：设置 `CHEMCOUNCIL_API_TOKEN`，调用 `/api/*` 时带 `Authorization: Bearer <token>`。
- 批量推荐最多填写 10 条材料。浏览器会用并行请求提交每张材料卡片并并行轮询结果；后端用独立的 `CHEMCOUNCIL_RECOMMENDATION_CONCURRENCY`（默认 10）控制实际同时运行的材料推荐任务，因此不会被经验更新任务的 `CHEMCOUNCIL_JOB_CONCURRENCY=1` 串行化。
- **停止任务（排队/运行中都支持）**：
  - Web 页面里每个流程都提供“停止任务”按钮（会对当前 job 发起取消请求）
  - 或直接调用：`POST /api/jobs/{job_id}/cancel`

## 1) 核心概念（先读这段能少踩坑）

### 1.1 Training-free GRPO 在做什么

`youtu-chem-loop` 的 Training-free GRPO 不是“训练模型参数”，而是：

- 对一批任务（从 `test.db` 里的 dataset 读取）由同一个预测智能体独立生成 `grpo_n` 个候选
- 对 rollout 的输出做 verify / reward
- 对同一问题的候选做 group 对比，再蒸馏出 **经验（guidelines）**，写回新的 agent YAML（经验库）

MAD 的 proposal/review/rebuttal/共识只出现在推荐端，不参与 GRPO。

所以这个系统的主要产物是：

- `configs/agents/practice/<exp_name>_agent.yaml`：完整经验库（可能很长）
- `configs/agents/practice/experience.yaml`：固定文件名的“稳定经验包”（用于对外同步）

### 1.2 Debate / Rank（rank 模式是什么）

在 `MAD/main.py` 里：

- **debate 模式**：给定 `--components` + `--reaction-type`，只对一个 reaction_type 辩论并输出预测
- **rank 模式**：给定 `--components --rank-reactions`，系统会对多个 reaction_type 分别跑一轮 debate，
  然后按 grade 排序，输出 Top-K 推荐（也会写 `outputs/rank_<timestamp>.json`）

rank 模式常用于“给定金属组成，让系统推荐最值得优先验证的材料性能方向”。

### 1.3 真实实验数据回流（CSV，旧电化学流程）

这一节描述的是旧电化学反馈导入链，保留给历史数据回流使用。当前材料性能主线应先使用“材料性能经验库生成”流程。

CSV 典型列：

- `reaction_type`（或中文列名“反应类型”；值可用 HER/OER/ORR/...）
- `metals`（如 `Co(57%),Ni(23%)`；脚本会抽取元素符号，同时保留原始字符串到 meta）
- `product`（**CO2RR 必填**：主要产物；建议使用固定标签：`CO`/`HCOOH`/`CH4`/`C2H5OH`/`C2H4`/`CH3COOH`；其它反应可留空）
- `value`（指标数值）
- `unit`（mV/V/mA cm-2/A mg-1/% 等）
- `condition`（如 `10 mA cm-2`；用于 eta10/potential10 规则检查）
- 可选：`metric`/`指标`（若你给了明确指标名，脚本会尝试映射到规范 key）
- 可选：`doi`、`title`、`id`

---

## 2) 材料性能经验库生成（推荐前置主线）

当前材料性能项目的正常顺序是：

1. 从已抽取的性能数据库生成 GRPO 数据集。
2. 按 6 个材料性能方向各抽取 50 条，得到 300 条平衡数据。
3. 在正式生成经验库前做一次参数测试，选择更合适的 `batch_size` / `grpo_n`。
4. 用 Training-Free GRPO 蒸馏/更新经验库。
5. 把稳定版 `experience.yaml` 同步到 `MAD/experience/`。
6. 再执行 MAD 推荐/排序，此时推荐会同时使用经验库和文献向量库。

只构建并上传材料性能数据集，不调用模型：

```bash
cd ChemCouncil
./scripts/run_material_property_experience.sh --prepare-only
```

默认会生成/上传：

```text
dataset_name = material_property_bal50_seed20260521
JSONL        = youtu-chem-loop/data/processed/material_property/material_property_bal50_seed20260521.jsonl
规模         = 6 个方向 * 50 条 = 300 条
```

正式跑之前先做参数测试。参数测试默认使用 6 个方向各 10 条（共 60 条）的平衡小样本，以控制模型调用成本；正式经验库仍然使用 6 个方向各 50 条（共 300 条）。第一次可先 dry-run 看命令，不调用模型：

```bash
cd ChemCouncil
./scripts/run_material_property_param_test.sh --dry-run
```

确认后运行两阶段参数测试：

```bash
cd ChemCouncil
./scripts/run_material_property_param_test.sh
```

参数测试会输出：

```text
state/reports/material_property_hp_test60_<timestamp>_A_summary.txt
state/reports/material_property_hp_test60_<timestamp>_B_summary.txt
state/reports/material_property_hp_test60_<timestamp>_recommended_params.txt
```

如果你确认预算/时间允许，并希望参数测试也使用完整 300 条，可以这样跑：

```bash
cd ChemCouncil
TEST_SAMPLES_PER_PROPERTY=50 ./scripts/run_material_property_param_test.sh
```

如果只想确认环境没问题，可以先做一个很小的 smoke：

```bash
cd ChemCouncil
CHEM_GRPO_RAG_ENABLED=0 TRUNCATE=2 BATCH_SIZE=2 GRPO_N=1 ROLLOUT_CONCURRENCY=1 \
  EXP_NAME=material_property_smoke_no_rag \
  ./scripts/run_material_property_experience.sh --fresh
```

默认材料性能经验库生成：

```bash
cd ChemCouncil
./scripts/run_material_property_experience.sh --fresh
```

默认数据集名是 `material_property_bal50_seed20260521`，来源文件是：

```text
../material_property_extraction/results/final_review_package_20260415/all_results.jsonl
```

默认文献向量库 collection 是：

```text
material_property_literature_agent2
```

## 3) 经验库生成（旧电化学流程说明）

### 2.1 最小 smoke（确认环境没问题）

```bash
cd ChemCouncil
./scripts/run_grpo_smoke.sh
```

它等价于在 `youtu-chem-loop/` 内跑一个很小的单智能体 GRPO rollout，不会调用 MAD。

### 2.2 生成 v5 的完整经验库（500 条，一键脚本）

如果这是一个**全新的 DB**（例如你刚 clone 仓库、`test.db` 还不存在或是空的），先把 v5_500 的 dataset 写入 DB：

```bash
cd ChemCouncil/youtu-chem-loop
python -m scripts.data.upload_dataset \
  --file_path data/processed/chem_performance/chem_performance_dataset_v5_500.jsonl \
  --dataset_name chem_performance_v5_500 \
  --data_format default
```

然后运行：

```bash
cd ChemCouncil
./scripts/run_full_v5_500.sh
```

该脚本会：

- 检查 DB 中 `chem_performance_v5_500` 的样本数量（防止重复上传导致数据量异常）
- 运行 Training-free GRPO（带 `tee` 日志）
- 失败时打印“如何重跑/如何 resume/如何降低并发”等提示

你也可以用：

```bash
./scripts/run_full_v5_500.sh --fresh      # 强制从头跑（restart_step=0）
./scripts/run_full_v5_500.sh --resume     # 尽量复用缓存（不传 restart_step）
./scripts/run_full_v5_500.sh --restart_step 10
```

### 2.3 自定义运行（直接调用 CLI）

```bash
cd ChemCouncil/youtu-chem-loop
python -m scripts.run_training_free_GRPO \
  --config_name chem_performance_single \
  --experiment_name single_agent_smoke \
  --practice_dataset_name chem_performance_v5_500 \
  --epochs 1 \
  --batch_size 20 \
  --grpo_n 6 \
  --rollout_data_truncate 40 \
  --rollout_concurrency 4 \
  --restart_step 0
```

#### `run_training_free_GRPO.py` 常用参数解释

- `--config_name`（必填）：加载 `youtu-chem-loop/configs/practice/<name>.yaml`；正式 GRPO 使用 `chem_performance_single`
- `--experiment_name`：实验名（会写入 DB 的 exp_id 前缀，并决定输出 agent YAML 的文件名）
- `--practice_dataset_name`：从 DB 里读取 dataset 的名字（例如 `chem_performance_v5_500`）
- `--epochs`：跑几轮 epoch（经验上先固定 1，确定流程稳定后再调）
- `--batch_size`：每步处理多少条 query（越大越“稳”，但每 step 更慢/更贵）
- `--grpo_n`：每条 query 生成多少个候选 rollout（越大越贵；同时影响 advantage/更新强度）
- `--rollout_data_truncate`：只取 dataset 的前 N 条做本次实验（用于超参/消融对比）
- `--rollout_concurrency`：rollout 并发数（同时跑多少条单智能体模型调用）
  - 并发越大越快，但更容易触发 API 限流/超时
  - 你之前选的 `concurrency=4` 是比较稳妥的默认值
- `--restart_step`：是否复用缓存
  - `0`：从头重跑（最干净，适合可比的超参实验）
  - 不传（None）：尽量复用缓存（适合失败后续跑或追加）

> 备注：GRPO 的 RAG 开关/阈值不在 CLI 参数里，而在 `CHEM_GRPO_RAG_ENABLED`、`CHEM_GRPO_RAG_LIMIT`、`CHEM_LITERATURE_CHROMA_MAX_DISTANCE` 等环境变量中。

---

## 3) 结果查看与对比（离线）

### 3.1 汇总实验（最常用）

```bash
cd ChemCouncil/youtu-chem-loop
python -m scripts.db.summarize_experiments --exp_prefix mad_hp_v5_ --order avg_reward_desc
```

常用参数：

- `--exp_prefix`：按前缀聚合（适合超参 sweep）
- `--exp_id`：只看某一个 exp（例如 `xxx_epoch_0`）
- `--order`：排序字段（常用 `avg_reward_desc` / `exp_id`）

### 3.2 更细的 rollout 检查

```bash
cd ChemCouncil/youtu-chem-loop
python -m scripts.db.inspect_rollouts --exp_id <YOUR_EXP_ID>
```

---

## 4) 同步 experience.yaml + 从辩论蒸馏经验（闭环一键）

闭环脚本在 `youtu-chem-loop/scripts/run_closed_loop.sh`，根目录也有 wrapper：`./scripts/run_closed_loop.sh`。

### 4.1 只同步 experience.yaml（不做辩论蒸馏）

```bash
cd ChemCouncil
./scripts/run_closed_loop.sh --skip_debate_update
```

它会：

- 从一个 seed agent YAML 导出稳定文件：`youtu-chem-loop/configs/agents/practice/experience.yaml`
- 同步到辩论项目：`MAD/experience/experience.yaml`
- 将辩论项目 `MAD/experience/` 里旧的 YAML pack 自动归档到 `experience/archive/`

### 4.2 从辩论 trace 蒸馏经验（需要你先跑过辩论/排序并保存 trace）

1) 在辩论项目跑 rank（一定要加 `--save-each-reaction`）：

```bash
cd ChemCouncil/MAD
python main.py \
  --components "Ni(69.00%), Co(19.07%), Fe(11.48%), Cu(0.40%), Zn(0.05%)" \
  --rank-reactions \
  --save-each-reaction \
  --max-parallel-reactions 3
```

2) 回到根目录执行闭环蒸馏：

```bash
cd ChemCouncil
./scripts/run_closed_loop.sh --debate_latest_n 10 --concurrency 4
```

说明：

- `--debate_latest_n`：取 `MAD/outputs/result_*.json` 最新 N 个文件
- `--concurrency`：蒸馏时 LLM 并发（和 rollout_concurrency 不一样）
- 脚本全程带 `tee` 日志，失败会打印重跑提示

---

## 5) 真实实验 CSV 回流（闭环的“回灌”）

### 5.1 命名规范（推荐）

为了避免“同名重复上传导致 DB 里数据翻倍”、以及方便你后续做对比/回溯，建议把一次实验回流视为一个**独立批次**，
每个批次都使用一个唯一的 `dataset_name`（写入 DB 的 dataset 标识），但命名规则保持统一。

推荐变量：

- `DATE`：`YYYYMMDD`（例如 `20260227`）
- `TAG`：本批次的短标识（例如 `labA` / `run01` / `hzor_fix`；只用字母数字下划线）
- `N`：本批次记录条数（整数，例如 `20`；如果你想加版本号，把版本信息放到 `TAG` 里，例如 `labA_v1`）

推荐命名：

- **DB dataset_name**（实验数据批次，唯一）：  
  `chem_performance_exp_${DATE}_${TAG}_${N}`  
  例：`chem_performance_exp_20260227_labA_20`
- **导入后的 processed JSONL 文件名**（落地到 repo）：  
  `${dataset_name}__processed.jsonl`
- **可上传的 dataset JSONL 文件名**（default format）：  
  `${dataset_name}__dataset.jsonl`
- **GRPO experiment_name**（写入 DB 的 exp_id 前缀，便于 summarize）：  
  `mad_update_exp_${DATE}_${TAG}_${N}_rag1_u1_t${N}_e1_b20_n6_c4`

重要提醒：

- 本项目的 GRPO 预处理会对 `dataset_name` 以 `chem_performance` 开头的数据集注入“单位规范提示”（见代码逻辑）。
  因此实验回流的数据集也建议以 `chem_performance_...` 命名（不要随便改成别的前缀）。
- `upload_dataset.py` **不会覆盖**同名 dataset，会直接继续写入（导致重复）。因此：
  - 最简单做法：每次回流都用新的 `dataset_name`（推荐）
  - 如果你确实要“重传同名 dataset”，就需要先手动清 DB 或换一个 dataset_name

### 5.2 CSV -> processed JSONL（导入实验记录）

假设实验记录在 `experimental_records.csv`，先导入为 processed JSONL（建议把输出文件名固定为上面的规范）：

```bash
cd ChemCouncil/youtu-chem-loop
DATE=20260227
TAG=labA
N=20
DS="chem_performance_exp_${DATE}_${TAG}_${N}"

python -m scripts.data.import_experimental_csv \
  --csv_path /path/to/experimental_records.csv \
  --output_dir data/processed/chem_performance_experimental \
  --output_name "${DS}__processed.jsonl" \
  --require_eta10_condition
```

常用可选项（按需）：
- `--encoding gbk`：如果你的 CSV 来自中文 Excel 导出，出现乱码可用
- `--dry_run`：只看统计不落盘

### 5.3 processed JSONL -> dataset JSONL（构建可上传数据集）

接着把 processed records 构建成可上传 dataset JSONL（default format；建议同样按规范命名）：

```bash
python -m scripts.data.build_chem_performance_dataset \
  --input_dir data/processed/chem_performance_experimental \
  --output_file "data/processed/chem_performance_experimental/${DS}__dataset.jsonl" \
  --include_unit_hint
```

### 5.4 上传到 DB（注意 data_format=default）

然后上传到 DB（注意 `--data_format default`，不要用默认的 llamafactory）：

```bash
python -m scripts.data.upload_dataset \
  --file_path "data/processed/chem_performance_experimental/${DS}__dataset.jsonl" \
  --dataset_name "${DS}" \
  --data_format default
```

### 5.5 用实验数据更新经验库：两种推荐跑法

#### 跑法 A（推荐默认）：只用“新实验批次”做增量更新

优点：便宜、快、闭环转得快；适合每次新来 10~50 条实验数据就更新一次。

注意：如果你的实验批次只有 `N=20` 条，那么 `--batch_size` 不能大于 20（否则会报数据量不足）。

```bash
EXP="single_update_exp_${DATE}_${TAG}_${N}_rag1_u1_t${N}_e1_b20_n6_c4"
python -m scripts.run_training_free_GRPO \
  --config_name chem_performance_single \
  --experiment_name "${EXP}" \
  --practice_dataset_name "${DS}" \
  --epochs 1 \
  --batch_size 20 \
  --grpo_n 6 \
  --rollout_data_truncate "${N}" \
  --rollout_concurrency 4 \
  --restart_step 0
```

#### 跑法 B（周期性）：合并后全量重跑（例如 300 + 20 -> 320）

当新实验数据累计到一定量（例如 100+），或你准备发布一个“稳定版本 experience.yaml”时，建议做一次全量重蒸馏：

1) 用一个新的合并 dataset_name（例如 `chem_performance_v5_plus_exp_20260227`）上传 320 条
2) `--practice_dataset_name` 指向这个合并后的 dataset，再干净重跑（`--restart_step 0`）

合并 dataset 的实现方式有很多（从 processed records 重建、或拼接两个 dataset JSONL 再 round-robin 重排），
你可以先按跑法 A 跑通闭环，之后我们再把“合并构建脚本”固化成一键命令。

### 5.6 回流之后的验证（强烈建议做）

回流更新后，至少做两件事：

1) 用 `summarize_experiments.py` 看本次 exp 的 reward/parse_err 是否异常：

```bash
python -m scripts.db.summarize_experiments --exp_prefix mad_update_exp_${DATE}_${TAG}_ --order avg_reward_desc
```

2) 用一个固定对比集（比如你一直用的 `truncate=40` 子集）做回归对比，确保经验库没有“漂移变坏”。

---

## 6) 环境变量速查（只维护根目录这一份）

根目录 `.env.full` 给出完整列表，这里只列最常用的：

### 6.1 LLM（用于 youtu-chem-loop 单智能体 GRPO）

- `UTU_LLM_API_KEY`：模型 API Key
- `UTU_LLM_BASE_URL`：OpenAI-compatible base url（当前默认 `https://dashscope.aliyuncs.com/compatible-mode/v1`）
- `UTU_LLM_MODEL`：模型名（当前默认 `deepseek-v4-pro`）
- `UTU_LLM_TYPE`：`chat.completions` / `responses`

### 6.2 文献 RAG（可选）

- `CHEM_LITERATURE_BACKEND=chroma`
- `CHEM_LITERATURE_CHROMA_DIR=../MAD/data/chroma_db`（相对 `youtu-chem-loop/` 目录；推荐复用 MAD 的文献向量库）
- `CHEM_LITERATURE_CHROMA_COLLECTION=literature_agent2`（Voyage embedding 对应的集合；MAD 通常按 agent 拆分 collection）
- `CHEM_LITERATURE_CHROMA_MAX_DISTANCE=0.35`（越小越严格）
- `VOYAGE_API_KEY`：用于 query embeddings

### 6.3 MAD（仅推荐端）

- `MAD_REPO_PATH=../MAD`
- `MAD_PYTHON_BIN=../.venv/bin/python`（单 venv 推荐）
- `MAD_ENABLE_RAG=1`
- `MAD_RAG_MODE=shared` / `per_agent`（Docker 服务器交付默认 `shared`；`per_agent` 需要更高内存和四套匹配的 embedding 链路）
- `MAD_RAG_SHARED_AGENT=agent2`（`MAD_RAG_MODE=shared` 时使用哪个 agent 的 embedding 配置）
- `MAD_RAG_SHARED_COLLECTION=literature_agent2`（`shared` 时使用的 collection）
- `MAD_RAG_LIMIT=5`
- `MAD_RAG_MAX_DISTANCE=0.35`
- `MAD_RAG_TIMEOUT_S=30`

---

## 7) 安全与开源注意事项

- `.env` 一定不要提交（包含密钥），已在 `.gitignore` 中默认忽略。
- 我们把历史的密钥备份移动到了：`chem-loop/.local/env_backups/`（同样被忽略）。
- 开源/分享前建议检查：是否还有任何 `*.local` / `*.backup*` 之类文件残留。
- 本工作区可能包含大体量数据（尤其是 `MAD/data/chroma_db/` 和 `youtu-chem-loop/test.db`）：
  - 为了让仓库可上传到 GitHub，这些大文件默认 **不纳入 git 跟踪**（见根目录 `.gitignore`）
  - 你本地仍然可以保留它们；如需共享，建议用 Git LFS 或提供下载脚本 / Release 资产

---

## 8) 附录：常用命令与参数速查

这一节不是“完整 manual”，而是把常用参数的语义写清楚，方便你在做超参/消融/闭环时快速改。

### 8.1 超参 sweep：`youtu-chem-loop/scripts/run_hyperparam_sweep.py`

用途：只调 `epochs / batch_size / grpo_n`，其它条件固定，从而保证可比性。

示例：

```bash
cd ChemCouncil/youtu-chem-loop
python -m scripts.run_hyperparam_sweep \
  --config_name chem_performance_single \
  --dataset chem_performance_v5_500 \
  --truncate 40 \
  --rollout_concurrency 4 \
  --epochs 1 \
  --batch_sizes 10,20 \
  --grpo_ns 2,3,4,5 \
  --exp_prefix single_hp_v5_ \
  --rag_limit 5 --rag_max_distance 0.35 --rag_timeout_s 30
```

关键参数：

- `--epochs / --batch_sizes / --grpo_ns`：逗号分隔列表（支持中文逗号 `，`）
- `--truncate`：固定 `rollout_data_truncate`，保证不同组合对同一子集可比
- `--rollout_concurrency`：rollout 并发（同 `run_training_free_GRPO.py --rollout_concurrency`）
- `--restart_step`：默认 `0`（不复用缓存；适合干净 sweep）
- `--skip_existing`：默认开启（如果 DB 里已存在 `*_epoch_0` 就跳过）
- `--dry_run`：只打印计划命令（大 sweep 时建议先 dry_run）
- RAG 固定参数：`--rag_limit / --rag_max_distance / --rag_timeout_s`
  - 这些会写到单智能体检索环境变量 `CHEM_GRPO_RAG_*` / `CHEM_LITERATURE_*`，确保对比公平

### 8.2 闭环同步/蒸馏：`./scripts/run_closed_loop.sh`

用途：

1) 导出稳定经验包 `experience.yaml`（带 `updated_at_utc` 时间戳）  
2) 同步到辩论项目 `MAD/experience/experience.yaml`，并归档旧 pack  
3)（可选）读取最新 `outputs/result_*.json` traces，蒸馏新的经验，再同步一次  

常用参数：

- `--skip_debate_update`：只同步 experience.yaml，不蒸馏辩论 trace
- `--debate_latest_n N`：取最新 N 个 `result_*.json` 作为输入
- `--concurrency N`：蒸馏（ExperienceUpdater）时的 LLM 并发  
  - 注意：这不是 rollout 的并发；rollout 并发在 GRPO 脚本里叫 `--rollout_concurrency`
- `--dry_run`：只解析 trace，统计/报告，不调用 LLM、不写更新 YAML
- `--seed_agent_yaml PATH`：从哪个 agent YAML 作为经验种子导出 experience.yaml

### 8.3 辩论/排序：`MAD/main.py`

两种模式：

- debate：`--components ... --reaction-type conductivity`
- rank：`--components ... --rank-reactions`（对多个 property_type 跑 debate 并排序）

关键参数：

- `--components`：金属组成字符串
  - 仅符号：`"Pt,Pd,Ru,Ir,Rh"`
  - 带比例：`"Co(57%),Ni(23%)"`（比例会进入 meta；推理时可用作背景）
- `--reaction-type`：单个 property/reaction 兼容字段（debate 模式用，例如 `conductivity`）
- `--rank-reactions`：开启 rank 模式（此时不能再传 `--reaction-type`）
- `--property-types "conductivity,thermal_conductivity"`：rank 模式只跑材料性能子集
- `--reaction-types "conductivity,thermal_conductivity"`：兼容旧参数名，材料性能任务优先用 `--property-types`
- `--top-k-reactions K`：rank 输出 Top-K（默认 2）
- `--max-parallel-reactions N`：rank 时 reaction-level 并发（默认 3）
- `--save-each-reaction`：rank 模式把每个 reaction 的 trace 也写成 `outputs/result_*.json`
  - 如果你要从 rank 结果蒸馏经验，这个开关是必须的（否则只有 rank_*.json，缺 debate_history）

### 8.4 实验 CSV 导入：`youtu-chem-loop/scripts/data/import_experimental_csv.py`

用途：把“实验记录表 CSV”转换成 processed JSONL（统一字段、统一单位/条件标记），便于后续 build+upload。

必填：

- `--csv_path PATH`

常用可选：

- `--output_dir DIR`：输出 processed JSONL 的目录（默认：`data/processed/chem_performance_experimental`）
- `--encoding`：默认 `utf-8-sig`；如果你从中文 Excel 导出遇到乱码可用 `gbk`
- `--require_eta10_condition`：如果该 reaction_type 的 metric 是 eta10/potential10，则要求 condition 列能解析到 10 mA cm-2（否则 drop）
- `--drop_explicit_non_eta10`：如果 condition 明确写了非 10 mA cm-2，则 drop
- `--dry_run`：只输出统计信息，不写文件

补充说明：
- **CO2RR**：为了匹配本项目的两任务设计（产物分类 + partial current density 回归），CO2RR 行必须提供 `product` 列（主要产物）。
  若缺失会被 drop，并在统计里提示 `dropped_co2rr_missing_product`。

### 8.5 构建 dataset：`youtu-chem-loop/scripts/data/build_chem_performance_dataset.py`

用途：把 processed records（JSONL）转换成可上传到 DB 的 dataset JSONL（default format）。

常用参数：

- `--input_dir`：processed JSONL 目录
- `--output_file`：输出 dataset JSONL 路径
- `--include_unit_hint`：在 question 的 INPUT_JSON 中把 `metrics_to_predict` 写成带 `unit_hint` 的结构，帮助模型遵守单位/格式
- `--add_meta_doc_id`：尝试把每条样本映射到 DOI（写入 meta.doc_id），用于 doc-level masking（防止 RAG 把标签文献检索回来导致泄漏）
- `--require_meta_doc_id`：配合上一条使用，如果有样本无法映射 DOI 就直接失败（更严格）

注意：

- CO2RR 会自动拆成两个任务写两行 sample：
  1) top-FE 产物分类（`{"product": "..."}"`）
  2) 该产物的 partial current density 回归（数值）

### 8.6 上传 dataset：`youtu-chem-loop/scripts/data/upload_dataset.py`

用途：把 dataset JSONL 写入 `test.db`（或你配置的其它 DB）。

关键参数：

- `--file_path`：dataset JSONL 路径
- `--dataset_name`：写入 DB 的 dataset 名字（后续 GRPO 用 `--practice_dataset_name` 引用）
- `--data_format default`：我们当前 chem loop 的 dataset 文件是 default format（不要用默认的 llamafactory）
