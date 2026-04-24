import torch
ckpt = torch.load("research/Models/MTF_CNN_LSTM_VOL.pt")
print(list(ckpt['model'].keys())[:10])
