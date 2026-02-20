import os
from typing import Dict, Tuple


def resolve_llm_config() -> Tuple[Dict, str]:
    """Resolve Mem0 LLM config with local-first and env-driven fallbacks."""
    if os.getenv("OPENROUTER_API_KEY"):
        return (
            {
                "provider": "openai",
                "config": {
                    "model": os.getenv("TB05_OPENROUTER_MODEL", "meta-llama/llama-3.1-8b-instruct"),
                },
            },
            "openrouter",
        )

    # Mem0 xAI provider currently breaks due config bug in 1.0.4.
    # Route through OpenAI-compatible provider using xAI endpoint.
    if os.getenv("XAI_API_KEY"):
        os.environ.setdefault("OPENAI_API_KEY", os.environ["XAI_API_KEY"])
        os.environ.setdefault("OPENAI_BASE_URL", "https://api.x.ai/v1")
        return (
            {
                "provider": "openai",
                "config": {
                    "model": os.getenv("TB05_XAI_MODEL", "grok-3-mini"),
                },
            },
            "xai-via-openai-compatible",
        )

    raise RuntimeError(
        "No supported LLM credentials found. Set OPENROUTER_API_KEY (preferred) "
        "or XAI_API_KEY to run TB5 extraction with Mem0."
    )


def build_mem0_config(base_dir: str) -> Tuple[Dict, str]:
    llm_config, llm_backend = resolve_llm_config()

    work_dir = os.path.join(base_dir, ".tb05_mem0")
    os.makedirs(work_dir, exist_ok=True)

    config = {
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "collection_name": "tb05_mem0_eval",
                "path": os.path.join(work_dir, "qdrant"),
                "embedding_model_dims": 384,
            },
        },
        "embedder": {
            "provider": "fastembed",
            "config": {
                "model": "BAAI/bge-small-en-v1.5",
            },
        },
        "llm": llm_config,
        "history_db_path": os.path.join(work_dir, "history.db"),
    }

    return config, llm_backend
