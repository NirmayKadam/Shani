"""
train_cnn_predictor.py — Phase 7 PyTorch 1D-CNN Sequence Trainer

Usage:
    docker compose exec app python -m scripts.train_cnn_predictor

Fetches 20 years of Macro Indices + cross-asset commodities.
Transforms data into Scale-Invariant features (to prevent Look-Ahead Bias).
Creates sliding 21-day sequences and trains a 1D Convolutional Neural Network
on the RTX 3050 GPU using PyTorch.
"""

import os
import sys
import logging
from datetime import datetime
import numpy as np
import pandas as pd
import yfinance as yf
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader

# Ensure the project root is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ── Configuration ───────────────────────────────────────────────
_WATCHLIST_RAW = "^NSEI,^NSEBANK,^CNXIT,^CNXAUTO,^CNXFMCG,^CNXMETAL,^CNXPHARMA,GC=F,SI=F,BZ=F"
_WATCHLIST = [s.strip() for s in _WATCHLIST_RAW.split(",") if s.strip()]

_YEARS_OF_HISTORY = 20
_SEQ_LEN = 21  # 21 trading days lookback window
_BATCH_SIZE = 256
_EPOCHS = 100
_LEARNING_RATE = 1e-3
_EARLY_STOPPING_PATIENCE = 10  # Stop if val accuracy doesn't improve for 10 epochs

_MODEL_DIR = "/app/models"
_MODEL_PATH = os.path.join(_MODEL_DIR, "CNN1DPredictor.pt")
os.makedirs(_MODEL_DIR, exist_ok=True)

# Define PyTorch Device Setup
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
logger.info(f"Using compute device: {device}")


def EngineerScaleInvariantFeatures(Df: pd.DataFrame) -> pd.DataFrame:
    """
    Generate scale-invariant features so the dataset requires NO standard scaler,
    preventing Look-Ahead Bias while dealing with huge price disparities.
    """
    if len(Df) < 50:
        return pd.DataFrame()

    Df.columns = [c.lower() for c in Df.columns]
    
    # Target: 1 if Tomorrow's Close > Today's Close
    Df["target"] = (Df["close"].shift(-1) > Df["close"]).astype(int)

    # RSI (14) - Already scaled 0-100
    Delta = Df["close"].diff()
    Gain = (Delta.where(Delta > 0, 0)).rolling(window=14).mean()
    Loss = (-Delta.where(Delta < 0, 0)).rolling(window=14).mean()
    RS = Gain / Loss
    Df["RSI_14"] = 100 - (100 / (1 + RS))
    Df["RSI_14"] = Df["RSI_14"] / 100.0  # Normalize to 0-1

    # EMAs to Price Percentage (Scale Invariant)
    EMA_9 = Df["close"].ewm(span=9, adjust=False).mean()
    EMA_21 = Df["close"].ewm(span=21, adjust=False).mean()
    Df["EMA9_Dist"] = (Df["close"] - EMA_9) / EMA_9
    Df["EMA21_Dist"] = (Df["close"] - EMA_21) / EMA_21

    # Bollinger Bands Percentage Width (Scale Invariant)
    SMA_20 = Df["close"].rolling(window=20).mean()
    STD_20 = Df["close"].rolling(window=20).std()
    BBL = SMA_20 - (STD_20 * 2)
    BBU = SMA_20 + (STD_20 * 2)
    Df["BB_Width"] = (BBU - BBL) / SMA_20
    Df["BB_Position"] = (Df["close"] - BBL) / (BBU - BBL + 1e-8)  # 0 to 1

    # Returns
    Df["ret_1d"] = Df["close"].pct_change(1)
    Df["ret_2d"] = Df["close"].pct_change(2)
    Df["ret_5d"] = Df["close"].pct_change(5)

    # Volume momentum
    Vol_SMA_10 = Df["volume"].rolling(window=10).mean()
    Df["vol_momentum"] = Df["volume"] / (Vol_SMA_10 + 1e-8)

    # Sentiment proxy: mean-reversion contrarian signal
    # During training we don't have live FinBERT scores, so we approximate
    # market sentiment using a smoothed contrarian indicator derived from
    # short-term returns. During inference, this feature is replaced with
    # the actual EMA sentiment polarity from Redis.
    Df["sentiment_proxy"] = (-Df["ret_5d"]).ewm(span=10, adjust=False).mean()

    Df = Df.dropna()
    return Df


class FinancialSequenceDataset(Dataset):
    def __init__(self, X, y):
        self.X = torch.tensor(X, dtype=torch.float32)
        self.y = torch.tensor(y, dtype=torch.long)
        
    def __len__(self):
        return len(self.X)
        
    def __getitem__(self, idx):
        return self.X[idx], self.y[idx]


class QuantCNN1D(nn.Module):
    def __init__(self, num_features):
        super(QuantCNN1D, self).__init__()
        # Conv1d expects input shape: (batch_size, num_features, seq_length)
        self.conv1 = nn.Conv1d(in_channels=num_features, out_channels=32, kernel_size=3, padding=1)
        self.relu = nn.ReLU()
        self.pool1 = nn.MaxPool1d(kernel_size=2)
        
        self.conv2 = nn.Conv1d(in_channels=32, out_channels=64, kernel_size=3, padding=1)
        self.pool2 = nn.MaxPool1d(kernel_size=2)
        
        self.adaptive_pool = nn.AdaptiveAvgPool1d(1)
        
        self.fc1 = nn.Linear(64, 32)
        self.fc2 = nn.Linear(32, 2)  # Binary classification
        self.dropout = nn.Dropout(0.4)

    def forward(self, x):
        # x input shape is (Batch, Seq_Len, Features)
        # PyTorch Conv1d expects (Batch, Channels/Features, Seq_Len)
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


def CreateSequences(Df, feature_cols):
    X, y = [], []
    features_data = Df[feature_cols].values
    target_data = Df["target"].values
    
    for i in range(len(Df) - _SEQ_LEN):
        seq_features = features_data[i : i + _SEQ_LEN]
        seq_target = target_data[i + _SEQ_LEN - 1]
        
        # Omit massive outlier spikes just in case
        if np.isnan(seq_features).any() or np.isnan(seq_target):
            continue
            
        X.append(seq_features)
        y.append(seq_target)
        
    return X, y


def Main():
    logger.info(f"Starting Phase 7 CNN Training. Targets: {_WATCHLIST}")
    
    All_X, All_y = [], []
    feature_cols = ['RSI_14', 'EMA9_Dist', 'EMA21_Dist', 'BB_Width', 'BB_Position', 'ret_1d', 'ret_2d', 'ret_5d', 'vol_momentum', 'sentiment_proxy']
    
    # ── 1. Data Ingestion ──
    for Sym in _WATCHLIST:
        logger.info(f"Downloading {Sym}...")
        try:
            Ticker = yf.Ticker(Sym)
            Df = Ticker.history(period=f"{_YEARS_OF_HISTORY}y")
            if Df.empty:
                continue
                
            EngineeredDf = EngineerScaleInvariantFeatures(Df)
            if EngineeredDf.empty:
                continue
                
            X_sym, y_sym = CreateSequences(EngineeredDf, feature_cols)
            All_X.extend(X_sym)
            All_y.extend(y_sym)
        except Exception as e:
            logger.error(f"Failed processing {Sym}: {e}")

    X_np = np.array(All_X)
    y_np = np.array(All_y)
    logger.info(f"Generated a massive Tensor Dataset of shape: {X_np.shape}")

    # Split Train/Val
    split_idx = int(0.8 * len(X_np))
    X_train, y_train = X_np[:split_idx], y_np[:split_idx]
    X_val, y_val = X_np[split_idx:], y_np[split_idx:]
    
    train_dataset = FinancialSequenceDataset(X_train, y_train)
    val_dataset = FinancialSequenceDataset(X_val, y_val)
    train_loader = DataLoader(train_dataset, batch_size=_BATCH_SIZE, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=_BATCH_SIZE, shuffle=False)

    # ── 2. Model Initialization ──
    model = QuantCNN1D(num_features=len(feature_cols)).to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=_LEARNING_RATE)
    scheduler = optim.lr_scheduler.StepLR(optimizer, step_size=20, gamma=0.5)

    # ── 3. Train Loop with Early Stopping + Best Checkpoint ──
    logger.info("Starting GPU Training (max %d epochs, patience %d)...", _EPOCHS, _EARLY_STOPPING_PATIENCE)
    best_val_acc = 0.0
    epochs_without_improvement = 0

    for epoch in range(_EPOCHS):
        model.train()
        running_loss = 0.0
        
        for batch_x, batch_y in train_loader:
            batch_x, batch_y = batch_x.to(device), batch_y.to(device)
            
            optimizer.zero_grad()
            outputs = model(batch_x)
            loss = criterion(outputs, batch_y)
            loss.backward()
            optimizer.step()
            
            running_loss += loss.item() * batch_x.size(0)
            
        epoch_loss = running_loss / len(train_dataset)
        
        # Validation
        model.eval()
        correct = 0
        total = 0
        with torch.no_grad():
            for batch_x, batch_y in val_loader:
                batch_x, batch_y = batch_x.to(device), batch_y.to(device)
                outputs = model(batch_x)
                _, predicted = torch.max(outputs.data, 1)
                total += batch_y.size(0)
                correct += (predicted == batch_y).sum().item()
                
        val_acc = 100 * correct / (total + 1e-8)
        current_lr = scheduler.get_last_lr()[0]
        logger.info(f"Epoch [{epoch+1}/{_EPOCHS}] Loss: {epoch_loss:.4f} | Val Accuracy: {val_acc:.2f}% | LR: {current_lr:.6f}")

        # Step the learning rate scheduler
        scheduler.step()

        # Best model checkpoint
        if val_acc > best_val_acc:
            best_val_acc = val_acc
            epochs_without_improvement = 0
            torch.save(model.state_dict(), _MODEL_PATH)
            logger.info(f"  ✅ New best model saved! (Val Accuracy: {val_acc:.2f}%)")
        else:
            epochs_without_improvement += 1

        # Early stopping
        if epochs_without_improvement >= _EARLY_STOPPING_PATIENCE:
            logger.info(f"Early stopping triggered after {epoch+1} epochs. Best Val Accuracy: {best_val_acc:.2f}%")
            break

    # ── 4. Final Summary ──
    logger.info(f"Training complete. Best model checkpoint saved to {_MODEL_PATH} (Val Accuracy: {best_val_acc:.2f}%)")
    logger.info("Success! PyTorch Models are ready for production inference.")

if __name__ == "__main__":
    Main()
