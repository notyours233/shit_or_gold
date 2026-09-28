# Youtu Chem Loop

This directory is the **training-free GRPO + experience distillation** subproject inside the ChemCouncil monorepo.

Single source of truth:

- Chinese: `../README_ZH.md`
- English: `../README.md`

Typical flow (from monorepo root):

```bash
cd ChemCouncil
cp .env.example .env
./scripts/setup_venv.sh
source .venv/bin/activate
./scripts/run_full_v5_500.sh
```
