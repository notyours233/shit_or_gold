# shit_or_gold / ChemCouncil

材料性能推荐与实验反馈闭环的源码仓库。推荐端采用 MAD 多智能体辩论；Training-Free GRPO 使用单智能体采样、真值校验和经验蒸馏，两条流程相互独立。

## 目录

- `chem-loop/chemcouncil/`：Web 后端、前端和后台任务。
- `chem-loop/MAD/`：单性能方向的多智能体推荐、评分和检索。
- `chem-loop/youtu-chem-loop/`：单智能体 GRPO、数据处理、校验和经验生成。
- `material_property_extraction/`：文献性能抽取脚本。
- `chem-loop/fixtures/`：代码自带的演示输入；不是正式训练数据。

详细说明见 [中文项目说明](chem-loop/README_ZH.md)、[部署说明](chem-loop/DEPLOY_ZH.md) 和 [源码发布边界](SOURCE_RELEASE.md)。

## 源码与运行数据分离

本仓库不包含真实 API key、Chroma 向量数据库、SQLite、历史任务、原始性能数据或训练后的经验库。`.env.example` 和 `.env.deploy.example` 中的密钥字段均为空，需要在运行机器上填写。

训练后的经验库不等于向量数据库；两者均作为独立运行资产提供。本源码副本没有修改或删除原工作区中的任何数据，也没有继承原仓库的提交历史。

## 本地配置

```bash
cd chem-loop
cp .env.example .env
# 在本机编辑 .env，填写自己有权使用的模型地址、模型名和 API key。
./scripts/setup_venv.sh
./scripts/init_state.sh
./scripts/run_web.sh
```

注意：`init_state.sh` 在没有正式经验库时只创建占位经验文件，不能视为已训练经验库。缺少向量库时不要启用文献 RAG；启用后必须提供与 collection 相匹配的 embedding 模型和凭据。正式 GRPO 还需要另行准备、校验并导入性能真值数据。

## Docker 部署

Dockerfile、Compose 和部署模板位于 `chem-loop/`。默认 Compose 镜像地址是原部署配置，并不代表拉取者拥有 Harbor 权限；如需从本源码构建，可按部署文档使用本地构建方式。

运行时需分别准备 `.env`、持久状态目录和 Chroma 目录。不要把包含密钥或用户实验数据的完整运行目录提交到 GitHub。

## 安全与验证

- 推送前审核 `git diff --cached`，尤其是 YAML、日志、自动生成配置及环境模板。
- `.gitignore` 不能清除旧提交中的秘密；历史密钥泄漏应撤销或轮换凭据并单独处理历史。
- 保留各子项目原有许可证；本次源码整理不替第三方组件重新授权。
- 离线测试不证明真实模型调用、正式 GRPO、完整推荐或服务器部署成功。
