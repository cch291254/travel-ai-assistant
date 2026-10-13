from sentence_transformers import SentenceTransformer

def load_embedding_model():
    model=SentenceTransformer(
        "BAAI/bge-m3",
        device="cuda",
        local_files_only=True,
    )


    model.max_seq_length=512
    model.half()
    return model