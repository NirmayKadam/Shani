import torch
import torch.nn as nn

class QuantCNN1D(nn.Module):
    """
    1D CNN architecture matched exactly to `train_cnn_predictor.py`.
    Used exclusively for inference in the live FastAPI endpoint.
    """
    def __init__(self, num_features):
        super(QuantCNN1D, self).__init__()
        self.conv1 = nn.Conv1d(in_channels=num_features, out_channels=32, kernel_size=3, padding=1)
        self.relu = nn.ReLU()
        self.pool1 = nn.MaxPool1d(kernel_size=2)
        
        self.conv2 = nn.Conv1d(in_channels=32, out_channels=64, kernel_size=3, padding=1)
        self.pool2 = nn.MaxPool1d(kernel_size=2)
        
        self.adaptive_pool = nn.AdaptiveAvgPool1d(1)
        
        self.fc1 = nn.Linear(64, 32)
        self.fc2 = nn.Linear(32, 2)  # Output: 2 logits (Bearish, Bullish)
        self.dropout = nn.Dropout(0.4)

    def forward(self, x):
        # x input shape is (Batch, Seq_Len, Features)
        # Transpose for Conv1D: (Batch, Features, Seq_Len)
        x = x.transpose(1, 2)
        
        x = self.conv1(x)
        x = self.relu(x)
        x = self.pool1(x)
        
        x = self.conv2(x)
        x = self.relu(x)
        x = self.pool2(x)
        
        x = self.adaptive_pool(x)
        x = x.view(x.size(0), -1)  # Flatten
        
        x = self.fc1(x)
        x = self.relu(x)
        x = self.dropout(x)
        x = self.fc2(x)
        return x
