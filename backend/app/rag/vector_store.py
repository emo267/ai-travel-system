from langchain_chroma import Chroma
from app.rag.embedding import get_embedding_model

CHROMA_PATH = "./chroma_data"
COLLECTION_NAME = "travel_knowledge"


def get_vector_store():
    return Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=get_embedding_model(),
        persist_directory=CHROMA_PATH,
    )