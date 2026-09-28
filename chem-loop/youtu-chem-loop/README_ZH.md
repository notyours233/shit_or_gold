# Youtu Chem Loop（子项目说明）

本目录是 ChemCouncil monorepo 中负责 **training-free GRPO + 经验蒸馏** 的子项目。

统一文档入口（single source of truth）：

- 中文：`../README_ZH.md`
- English：`../README.md`

典型用法（从仓库根目录执行）：

```bash
cd ChemCouncil
cp .env.example .env
./scripts/setup_venv.sh
source .venv/bin/activate
./scripts/run_full_v5_500.sh
```

