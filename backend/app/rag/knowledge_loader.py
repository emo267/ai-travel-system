from langchain_text_splitters import RecursiveCharacterTextSplitter
from app.rag.vector_store import get_vector_store


def load_knowledge(text: str, metadata: dict):
    """将文本分块并写入向量库"""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=100,
        separators=["\n\n", "\n", "。", "！", "？", " ", ""],
    )
    chunks = splitter.split_text(text)
    vector_store = get_vector_store()
    vector_store.add_texts(texts=chunks, metadatas=[metadata] * len(chunks))
    return len(chunks)