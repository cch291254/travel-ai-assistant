import torch

#检查显卡，没有继续cpu
MODEL_DEVICE="cuda" if torch.cuda.is_available() else "cpu"