from sentence_transformers import SentenceTransformer
from app.device import MODEL_DEVICE


#配置向量模型
def load_embedding_model():
    model=SentenceTransformer(
        "BAAI/bge-m3",
        device=MODEL_DEVICE,
        local_files_only=True,
    )


    model.max_seq_length=512
    if MODEL_DEVICE=="cuda":
        model.half()
    return model