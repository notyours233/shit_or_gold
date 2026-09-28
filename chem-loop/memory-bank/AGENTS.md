# Repository Guidelines

## Always Rules (Non-Negotiable)
- Before writing any code, fully read `memory-bank/architecture.md` (includes the complete database schema) and `memory-bank/design-document.md`.
- After completing any major feature or milestone, update `architecture.md` (keep DB schema + dataflow accurate).
- Prefer modular design (multiple small files/modules). Avoid "one giant file" (monolith) implementations.

## 重要提示（中文，等价于 Always Rules）
- 写任何代码前必须完整阅读 `memory-bank/architecture.md`（包含完整数据库结构）
- 写任何代码前必须完整阅读 `memory-bank/design-document.md`
- 每完成一个重大功能或里程碑后，必须更新 `memory-bank/architecture.md`
- 强调模块化（多文件），禁止单体巨文件（monolith）

## Documentation Layout (This Workspace)
- Canonical docs live in `project/chem-loop/memory-bank/` and are the only ones that must be kept up to date.
- Spec/contract docs (data processing rules, metric key lists, workflow contracts) live in `project/chem-loop/spec-bank/`.

## Project Structure & Module Organization
- `chemcouncil/` — aiohttp backend + static frontend (experimenter UX)
- `MAD/` — multi-agent debate + rank mode + (optional) Chroma literature RAG
- `youtu-chem-loop/` — Training-Free GRPO + verify + data processing + MAD external engine adapter
  - `youtu-chem-loop/utu/` — core Python package
  - `youtu-chem-loop/configs/` — Hydra YAML configs
  - `youtu-chem-loop/scripts/` — CLI entrypoints (GRPO runner, dataset import/upload, closed-loop helpers)
  - `youtu-chem-loop/tests/` — pytest suite mirroring package layout
- `scripts/` — monorepo-level helper scripts (docker/web/smoke runs)
- `state/` — host-persisted runtime state for docker/web (DB, jobs, chroma mount)

## Build, Test, and Development Commands
- Python env (local): `cd project/chem-loop && ./scripts/setup_venv.sh`
- Smoke tests:
  - `cd project/chem-loop && ./scripts/run_e2e_smoke.sh`
  - `cd project/chem-loop && ./scripts/run_grpo_smoke.sh`
- Web (local dev): `cd project/chem-loop && ./scripts/run_web.sh`
- Docker: `cd project/chem-loop && ./scripts/init_state.sh && docker compose up -d --build`

## Coding Style & Naming Conventions
- Python 3.12; line length 120 (ruff). Use Google-style docstrings.
- Naming: modules/files `snake_case.py`; functions/vars `snake_case`; classes `CamelCase`.
- Imports: first-party recognized as `utu` (ruff isort). Keep functions small and typed where practical (mypy enabled, strict base with selected relaxations).
- Run `pre-commit install` to enable ruff format/check on commit.

## Testing Guidelines
- Framework: `pytest` (async supported via `pytest-asyncio`).
- Location: mirror source tree under `tests/`; name files `test_*.py` and functions `test_*`.
- Coverage: add tests for new features and bug fixes; include edge cases and config loading paths.
- Quick example: `uv run pytest tests/test_config.py -q`.

## Commit & Pull Request Guidelines
- Link PRs to an issue; keep changes focused and documented.
- Commit style: prefer Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`) or scoped prefixes (e.g., `tool_auto_gen:`) observed in history.
- PRs must pass lint, format, and tests; include a clear description, rationale, and any screenshots/logs for UI or eval changes.

## Security & Configuration Tips
- Do not commit secrets. Copy `.env.example` to `.env` and set required keys (LLM/tool APIs). `.env` is git-ignored.
- Prefer `uv run ...` to ensure the virtual env and pinned deps are used.
