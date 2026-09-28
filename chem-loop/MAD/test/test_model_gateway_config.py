from pathlib import Path

import yaml


CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "config.yaml"
SHARED_GATEWAY = "https://zenmux.dev/api/v1"
QWEN_EMBEDDING_GATEWAY = "https://agent-team-api.myrimate.cn/v1"


def test_all_chat_agents_use_shared_gateway() -> None:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))

    for agent_name in ("agent1", "agent2", "agent3", "agent4"):
        assert config["llm"][agent_name]["base_url"] == SHARED_GATEWAY


def test_gemini_uses_gateway_model_id_without_provider_prefix() -> None:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))

    assert config["llm"]["agent3"]["model"] == "gemini-3.5-flash"


def test_gpt_uses_gateway_model_id_without_provider_prefix() -> None:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))

    assert config["llm"]["agent1"]["model"] == "gpt-5.5"


def test_qwen_embedding_uses_shared_gateway() -> None:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))

    assert config["llm"]["agent4"]["emb_url"] == f"{QWEN_EMBEDDING_GATEWAY}/embeddings"


def test_openrouter_embeddings_use_a_dedicated_credential() -> None:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))

    for agent_name in ("agent1", "agent3"):
        agent = config["llm"][agent_name]
        assert agent["embedding_provider"] == "openrouter"
        assert agent["embedding_api_key"] == "${OPENROUTER_API_KEY}"
