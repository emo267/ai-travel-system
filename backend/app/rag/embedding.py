from functools import lru_cache

from langchain_huggingface import HuggingFaceEmbeddings


@lru_cache(maxsize=1)
def get_embedding_model() -> HuggingFaceEmbeddings:
    """进程内复用同一个模型实例。

    bge-m3 有 2.3GB，每次重新加载要花约 10 秒；不缓存的话每一次知识库检索
    （聊天、行程生成的 RAG 步骤）都会白等这段时间。
    """
    return HuggingFaceEmbeddings(
        model_name="BAAI/bge-m3",
        model_kwargs={"device": "cpu"},  # 如果有 GPU 可以改成 "cuda"
        encode_kwargs={"normalize_embeddings": True},
    )
