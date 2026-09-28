# ChemCouncil 服务器 Docker 部署说明

这个部署方式和 ChemLoop 一样：镜像里只放代码。持久数据放在服务器挂载目录，密钥放在服务器本地 `.env` 中，由 Docker Compose 在启动时注入容器。

真实 `.env` 不会写入镜像，也不属于两个数据挂载点。它是部署时必须单独准备的第三项运行时配置；缺少它时，`docker compose up` 会直接报 `env file .env not found`。即使绕过 Compose 直接启动容器，网页进程可能仍能打开，但推荐、GRPO、反馈更新和 Chroma 查询会因模型或 Voyage API key 缺失而失败。

## 1. 需要发给服务器使用者的文件

使用已上传到 Harbor 的镜像时，只需要准备：

```text
/opt/chemcouncil/
  docker-compose.yml
  .env
  state/
  chroma_db/
```

镜像地址：

```text
harbor.pic-aichem.online/wangzm/chemcouncil-material:20260902
```

当前发布标签为 `linux/amd64`，目标服务器应使用 x86_64/amd64 Docker 节点。

`.env.deploy.example` 是不含密钥的模板，可以发给服务器使用者。真实 `.env` 必须通过受控通道单独传到服务器，不能提交到 Git，也不能打进镜像或上传到 Harbor。

大文件不要打进镜像，单独放在服务器挂载点：

```text
./state/      # 小体积持久状态：SQLite、experience.yaml、job 日志、上传和结果
./chroma_db/  # 大体积文献向量库：chroma.sqlite3 + uuid 文件夹
```

## 2. 两个挂载点

`docker-compose.yml` 默认使用两个挂载点：

```yaml
volumes:
  - ${CHEMCOUNCIL_STATE_DIR:-./state}:/state
  - ${CHEMCOUNCIL_CHROMA_DIR:-./MAD/data/chroma_db}:/state/chroma_db
```

推荐服务器目录结构：

```text
/opt/chemcouncil/
  docker-compose.yml
  .env
  state/
    experience_youtu.yaml
    experience_mad.yaml
    test.db
    jobs/
    experience_archive/
  chroma_db/
    chroma.sqlite3
    <uuid-folder>/
    <uuid-folder>/
```

说明：

- `/state/test.db`：训练/反馈流程共用 SQLite。
- `/state/jobs`：网页任务日志、上传文件和结果。
- `/state/experience_youtu.yaml`：GRPO/反馈更新后的稳定经验库。
- `/state/experience_mad.yaml`：MAD 推荐时读取的经验库。
- `/state/chroma_db`：统一文献 Chroma 向量库。当前数据库包含 `literature_agent1` 到 `literature_agent4` 四个 collection。

## 3. 初始化服务器目录

在服务器上：

```bash
mkdir -p /opt/chemcouncil
cd /opt/chemcouncil
```

把 `docker-compose.yml` 和 `.env.deploy.example` 放进 `/opt/chemcouncil`。

准备 `.env`：

```bash
cp .env.deploy.example .env
nano .env
chmod 600 .env
```

至少填写：

```bash
UTU_LLM_API_KEY=...
UTU_LLM_BASE_URL=https://agent-team-api.myrimate.cn/v1
UTU_LLM_MODEL=deepseek-v4-pro
VOYAGE_API_KEY=...
```

如果 MAD 配置里用到其它供应商，也填写：

```bash
OPENAI_API_KEY=...
DEEPSEEK_API_KEY=...
GOOGLE_API_KEY=...
QWEN_API_KEY=...
```

当前服务器使用 `MAD_RAG_MODE=shared`，不需要配置 `OPENROUTER_API_KEY`。只有切换到
`per_agent` 并保留当前 agent1/agent3 embedding 配置时，才需要额外准备 OpenRouter 凭据。

如果你把两个挂载点放在推荐位置，`.env` 里设置：

```bash
CHEMCOUNCIL_STATE_DIR=./state
CHEMCOUNCIL_CHROMA_DIR=./chroma_db
```

## 4. 放置文献向量库

把下载好的 Chroma DB 放到：

```text
/opt/chemcouncil/chroma_db/
```

必须能看到：

```text
/opt/chemcouncil/chroma_db/chroma.sqlite3
/opt/chemcouncil/chroma_db/<uuid-folder>/data_level0.bin
/opt/chemcouncil/chroma_db/<uuid-folder>/header.bin
/opt/chemcouncil/chroma_db/<uuid-folder>/index_metadata.pickle
```

可以检查 collection：

```bash
sqlite3 /opt/chemcouncil/chroma_db/chroma.sqlite3 \
  "select name from collections order by name;"
```

当前统一向量库正常应看到：

```text
literature_agent1
literature_agent2
literature_agent3
literature_agent4
```

## 5. 初始化 state

如果代码目录完整，可以运行：

```bash
./scripts/init_state.sh
```

它会创建：

```text
state/jobs
state/experience_archive
state/experience_youtu.yaml
state/experience_mad.yaml
```

如果你已有正式经验库，也可以手动复制：

```bash
mkdir -p state/jobs state/experience_archive
cp youtu-chem-loop/configs/agents/practice/experience.yaml state/experience_youtu.yaml
cp MAD/experience/experience.yaml state/experience_mad.yaml
```

## 6. 启动服务

```bash
docker login harbor.pic-aichem.online
docker compose pull
docker compose up -d
```

查看日志：

```bash
docker compose logs -f --tail=200
```

健康检查：

```bash
curl http://127.0.0.1:8000/api/health
```

浏览器访问：

```text
http://服务器IP:8000
```

如果服务器已有反向代理，建议用 Nginx/Caddy 把域名转发到 `127.0.0.1:8000`，并只在内网暴露容器端口。

## 7. 内存建议

文献向量库约几十 GB，RAG 会占用明显内存。服务器交付配置默认使用：

```bash
MAD_RAG_MODE=shared
MAD_RAG_SHARED_AGENT=agent2
MAD_RAG_SHARED_COLLECTION=literature_agent2
CHEMCOUNCIL_JOB_CONCURRENCY=1
CHEMCOUNCIL_RECOMMENDATION_CONCURRENCY=10
```

在该模式下，四个对话 agent 仍然分别使用自己的聊天模型，但文献检索统一使用已经验证的 agent2/Voyage 链路：

```text
agent1, agent2, agent3, agent4
              |
              v
voyage-3-large -> literature_agent2
```

因此服务器不需要 `OPENROUTER_API_KEY`，也不需要同时加载四个 Chroma collection。

批量推荐的并发分为两层：

- `CHEMCOUNCIL_RECOMMENDATION_CONCURRENCY` 控制不同材料之间的并发。前端最多提交 10 个材料卡片，默认最多同时运行 10 个独立 MAD 推荐任务；设置为 2、4 或 5 可以在内存/API 限流较紧时降低压力。
- 推荐表单中的“同时评估方向数”（后端字段 `max_parallel_properties`）只控制一个材料内部的性能方向并发。例如 10 个材料、每个材料 3 个方向，理论上会同时产生约 30 个方向级任务/模型调用，因此应结合服务器资源设置这两个参数。

也就是说，10 条材料现在是“前端并行提交 + 后端并行执行”，不再因为通用 `CHEMCOUNCIL_JOB_CONCURRENCY=1` 而排成串行队列。`CHEMCOUNCIL_JOB_CONCURRENCY` 仍只限制经验库生成、经验反馈更新等通用后台任务。

如果后续服务器内存充足，并且已经为 agent1/agent3 准备好匹配的 embedding 服务，可以切换到：

```bash
MAD_RAG_MODE=per_agent
```

`per_agent` 会加载四个 collection，并且要求每个查询 embedding 模型与对应 collection 建库模型一致。当前服务器先保持：

```bash
CHEMCOUNCIL_JOB_CONCURRENCY=1
CHEMCOUNCIL_RECOMMENDATION_CONCURRENCY=10
```

确认稳定后再增加。

## 8. 更新镜像

发布新标签后，修改 `.env` 中的 `CHEMCOUNCIL_IMAGE`，然后：

```bash
docker compose pull
docker compose up -d
```

`state/` 和 `chroma_db/` 是宿主机挂载目录，不会因为重建镜像丢失。

## 9. 常见问题

端口被占用：

```bash
CHEMCOUNCIL_PUBLIC_PORT=18000
docker compose up -d
```

向量库 collection 找不到：

- 检查 `CHEMCOUNCIL_CHROMA_DIR` 指向的目录是不是包含 `chroma.sqlite3`。
- 检查 `.env` 中的 `MAD_RAG_SHARED_COLLECTION` 是否为 `literature_agent2`。

网页能打开但任务失败：

```bash
docker compose logs -f --tail=300
```

同时在网页的 job 日志里查看具体失败步骤。常见原因是 API key 缺失、模型 base URL 不对、`VOYAGE_API_KEY` 缺失、或服务器内存不足。
