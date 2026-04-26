"""
train_cnn_predictor.py — Phase 9 PyTorch 1D-CNN Sequence Trainer
Updated with volatility target engineering, CNN-LSTM hybrid architecture,
and robust cross-border timezone handling.
"""

import os
import sys
import logging
import numpy as np
import pandas as pd
import yfinance as yf
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report, confusion_matrix

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# -- Config
_WATCHLIST_RAW = "^NSEI,^NSEBANK,^CNXIT,^CNXAUTO,^CNXFMCG,^CNXMETAL,^CNXPHARMA,GC=F,SI=F,BZ=F"
_WATCHLIST     = [s.strip() for s in _WATCHLIST_RAW.split(",") if s.strip()]
_YEARS         = 20
_SEQ_D, _SEQ_W, _SEQ_M = 21, 12, 6
_BATCH, _EPOCHS = 256, 120
_LR, _PATIENCE = 1e-4, 15
_MODEL_DIR     = "./Models"
_MODEL_PATH    = os.path.join(_MODEL_DIR, "MTF_CNN_LSTM_VOL.pt")
_OFFICIAL_MODEL_DIR = "../models/MLForecast"
_OFFICIAL_MODEL_PATH = os.path.join(_OFFICIAL_MODEL_DIR, "MTF_CNN_LSTM_VOL.pt")
os.makedirs(_MODEL_DIR, exist_ok=True)
os.makedirs(_OFFICIAL_MODEL_DIR, exist_ok=True)

_VOL_THRESHOLD = 0.15  # 15% shift in volatility for target classes

FEATURE_COLS = [
    'RSI_14', 'MACD', 'MACD_Signal', 'MACD_Hist', 'Stoch_K', 'Stoch_D', 'Williams_R',
    'EMA9_Dist', 'EMA21_Dist', 'EMA50_Dist', 'ADX', 'BB_Width', 'BB_Position',
    'ATR_Norm', 'ret_1d', 'ret_5d', 'ret_10d', 'HL_Ratio', 'OC_Ratio', 'Gap',
    'vol_momentum', 'OBV_Norm'
]

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
if torch.cuda.is_available():
    torch.backends.cudnn.benchmark = True

def _normalize_index(df_or_series):
    if df_or_series.empty: return df_or_series
    if df_or_series.index.tz is not None:
        df_or_series.index = df_or_series.index.tz_localize(None)
    df_or_series.index = df_or_series.index.normalize()
    df_or_series.index = df_or_series.index.astype('datetime64[ns]')
    df_or_series = df_or_series.sort_index()
    df_or_series = df_or_series[~df_or_series.index.duplicated(keep='last')]
    return df_or_series

def get_macro_features(interval="1d"):
    vix = yf.Ticker("^VIX").history(period=f"{_YEARS}y", interval=interval)['Close']
    tnx = yf.Ticker("^TNX").history(period=f"{_YEARS}y", interval=interval)['Close']
    dxy = yf.Ticker("DX-Y.NYB").history(period=f"{_YEARS}y", interval=interval)['Close']
    vix, tnx, dxy = _normalize_index(vix), _normalize_index(tnx), _normalize_index(dxy)
    m_df = pd.concat([vix, tnx, dxy], axis=1, keys=['VIX', 'TNX', 'DXY']).ffill()
    m_df['MACRO_VIX'] = m_df['VIX'] / 100.0
    m_df['MACRO_TNX_Mom'] = m_df['TNX'] / (m_df['TNX'].rolling(20).mean() + 1e-8)
    m_df['MACRO_DXY_Ret'] = m_df['DXY'].pct_change(5)
    return m_df[['MACRO_VIX', 'MACRO_TNX_Mom', 'MACRO_DXY_Ret']].dropna()

def EngineerFeatures(df: pd.DataFrame) -> pd.DataFrame:
    if len(df) < 60: return pd.DataFrame()
    df = df.copy()
    df.columns = [c.lower() for c in df.columns]
    c, h, l, o, v = df['close'], df['high'], df['low'], df['open'], df['volume']
    
    # Volatility Target Engineering
    daily_ret = c.pct_change()
    rv_current = daily_ret.rolling(window=5).std()
    rv_future = rv_current.shift(-5)
    vol_change = (rv_future - rv_current) / (rv_current + 1e-8)
    df['target'] = np.where(vol_change > _VOL_THRESHOLD, 2, 
                   np.where(vol_change < -_VOL_THRESHOLD, 0, 1))

    delta = c.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['RSI_14'] = (100 - 100 / (1 + gain / (loss + 1e-8))) / 100.0
    ema12, ema26 = c.ewm(span=12, adjust=False).mean(), c.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    sig = macd.ewm(span=9, adjust=False).mean()
    df['MACD'], df['MACD_Signal'], df['MACD_Hist'] = macd/c, sig/c, (macd-sig)/c
    lo14, hi14 = l.rolling(14).min(), h.rolling(14).max()
    stk = 100 * (c - lo14) / (hi14 - lo14 + 1e-8)
    df['Stoch_K'], df['Stoch_D'], df['Williams_R'] = stk/100, stk.rolling(3).mean()/100, (hi14-c)/(hi14-lo14+1e-8)
    df['EMA9_Dist'] = (c - c.ewm(span=9, adjust=False).mean()) / (c.ewm(span=9, adjust=False).mean() + 1e-8)
    df['EMA21_Dist'] = (c - c.ewm(span=21, adjust=False).mean()) / (c.ewm(span=21, adjust=False).mean() + 1e-8)
    df['EMA50_Dist'] = (c - c.ewm(span=50, adjust=False).mean()) / (c.ewm(span=50, adjust=False).mean() + 1e-8)
    tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    df['ATR_Norm'] = atr / (c + 1e-8)
    dmp = h.diff().where((h.diff()>0) & (h.diff()>-l.diff()), 0)
    dmm = (-l.diff()).where((-l.diff()>0) & (-l.diff()>h.diff()), 0)
    dip, dim = 100*dmp.rolling(14).mean()/atr, 100*dmm.rolling(14).mean()/atr
    dx = 100*(dip-dim).abs()/(dip+dim+1e-8)
    df['ADX'] = dx.rolling(14).mean()/100
    sma20, std20 = c.rolling(20).mean(), c.rolling(20).std()
    bbl, bbu = sma20 - 2*std20, sma20 + 2*std20
    df['BB_Width'], df['BB_Position'] = (bbu-bbl)/sma20, (c-bbl)/(bbu-bbl+1e-8)
    df['ret_1d'], df['ret_5d'], df['ret_10d'] = c.pct_change(1), c.pct_change(5), c.pct_change(10)
    df['HL_Ratio'], df['OC_Ratio'], df['Gap'] = (h-l)/c, (c-o)/o, (o-c.shift(1))/c.shift(1)
    df['vol_momentum'] = v / (v.rolling(10).mean() + 1e-8)
    obv = (np.sign(c.diff()) * v).fillna(0).cumsum()
    df['OBV_Norm'] = (obv - obv.rolling(50).min()) / (obv.rolling(50).max() - obv.rolling(50).min() + 1e-8)
    return df.dropna()

def create_mtf_sequences(df_d, df_w, df_m):
    d_feats, w_feats, m_feats = df_d[FEATURE_COLS].values, df_w[FEATURE_COLS].values, df_m[FEATURE_COLS].values
    d_dates, w_dates, m_dates = df_d.index.values, df_w.index.values, df_m.index.values
    targets = df_d['target'].values
    Xd, Xw, Xm, y = [], [], [], []
    for i in range(_SEQ_D - 1, len(df_d) - 1):
        anchor = d_dates[i]
        d_seq = d_feats[i-_SEQ_D+1 : i+1]
        w_pos = np.searchsorted(w_dates, anchor, side='right') - 1
        if w_pos < _SEQ_W - 1: continue
        w_seq = w_feats[w_pos-_SEQ_W+1 : w_pos+1]
        m_pos = np.searchsorted(m_dates, anchor, side='right') - 1
        if m_pos < _SEQ_M - 1: continue
        m_seq = m_feats[m_pos-_SEQ_M+1 : m_pos+1]
        if d_seq.shape[0]==_SEQ_D and w_seq.shape[0]==_SEQ_W and m_seq.shape[0]==_SEQ_M:
            if not (np.isnan(d_seq).any() or np.isnan(w_seq).any() or np.isnan(m_seq).any()):
                Xd.append(d_seq); Xw.append(w_seq); Xm.append(m_seq); y.append(targets[i])
    return Xd, Xw, Xm, y

class MTFDataset(Dataset):
    def __init__(self, Xd, Xw, Xm, y):
        self.Xd, self.Xw, self.Xm, self.y = torch.FloatTensor(np.array(Xd)), torch.FloatTensor(np.array(Xw)), torch.FloatTensor(np.array(Xm)), torch.LongTensor(np.array(y))
    def __len__(self): return len(self.y)
    def __getitem__(self, i): return self.Xd[i], self.Xw[i], self.Xm[i], self.y[i]

class ResBlock1D(nn.Module):
    def __init__(self, ch):
        super().__init__()
        self.net = nn.Sequential(nn.BatchNorm1d(ch), nn.GELU(), nn.Conv1d(ch,ch,3,padding=1), nn.BatchNorm1d(ch), nn.GELU(), nn.Conv1d(ch,ch,3,padding=1))
    def forward(self, x): return x + self.net(x)

class TimeframeBranch(nn.Module):
    def __init__(self, n_feat, cnn_hidden=64, lstm_hidden=64, out_dim=96):
        super().__init__()
        c3, c5 = cnn_hidden//3, cnn_hidden//3
        c7 = cnn_hidden - c3 - c5
        self.conv3, self.conv5, self.conv7 = nn.Conv1d(n_feat,c3,3,padding=1), nn.Conv1d(n_feat,c5,5,padding=2), nn.Conv1d(n_feat,c7,7,padding=3)
        self.bn = nn.BatchNorm1d(cnn_hidden)
        self.res1 = ResBlock1D(cnn_hidden)
        self.lstm = nn.LSTM(input_size=cnn_hidden, hidden_size=lstm_hidden, num_layers=1, batch_first=True)
        self.dropout = nn.Dropout(0.4)
        self.proj = nn.Linear(lstm_hidden, out_dim)
    def forward(self, x):
        x = x.transpose(1, 2)
        c_out = torch.relu(self.bn(torch.cat([self.conv3(x), self.conv5(x), self.conv7(x)], 1)))
        c_out = self.res1(c_out).transpose(1, 2)
        lstm_out, _ = self.lstm(c_out)
        final = self.dropout(lstm_out[:, -1, :])
        return self.proj(final)

class MultiTimeframeCNN(nn.Module):
    def __init__(self, n_feat, branch_out=96):
        super().__init__()
        self.d = TimeframeBranch(n_feat, out_dim=branch_out)
        self.w = TimeframeBranch(n_feat, out_dim=branch_out)
        self.m = TimeframeBranch(n_feat, out_dim=branch_out)
        self.head = nn.Sequential(
            nn.Linear(branch_out*3, 128), nn.GELU(), nn.Dropout(0.6), 
            nn.Linear(128, 32), nn.GELU(), nn.Dropout(0.4),
            nn.Linear(32, 3)
        )
    def forward(self, xd, xw, xm): return self.head(torch.cat([self.d(xd), self.w(xw), self.m(xm)], 1))

def Main():
    logger.info("Fetching Macro indicators...")
    macro_d = get_macro_features("1d")
    macro_w = get_macro_features("1wk").shift(1).dropna()
    macro_m = get_macro_features("1mo").shift(1).dropna()

    Xd_tr_l, Xw_tr_l, Xm_tr_l, y_tr_l = [], [], [], []
    Xd_va_l, Xw_va_l, Xm_va_l, y_va_l = [], [], [], []
    
    logger.info(f"Downloading {len(_WATCHLIST)} symbols...")
    for sym in _WATCHLIST:
        try:
            tkr = yf.Ticker(sym)
            df_d = tkr.history(period=f"{_YEARS}y", interval="1d")
            df_w = tkr.history(period=f"{_YEARS}y", interval="1wk")
            df_m = tkr.history(period=f"{_YEARS}y", interval="1mo")
            if any(d.empty for d in [df_d, df_w, df_m]): continue

            df_d = EngineerFeatures(df_d)
            df_w = EngineerFeatures(df_w).shift(1).dropna()
            df_m = EngineerFeatures(df_m).shift(1).dropna()

            df_d, df_w, df_m = _normalize_index(df_d), _normalize_index(df_w), _normalize_index(df_m)

            df_d = pd.merge_asof(df_d, macro_d, left_index=True, right_index=True, direction='backward').dropna()
            df_w = pd.merge_asof(df_w, macro_w, left_index=True, right_index=True, direction='backward').dropna()
            df_m = pd.merge_asof(df_m, macro_m, left_index=True, right_index=True, direction='backward').dropna()

            xd, xw, xm, y = create_mtf_sequences(df_d, df_w, df_m)
            if not y: continue
            idx = int(0.8 * len(y))
            Xd_tr_l.extend(xd[:idx]); Xw_tr_l.extend(xw[:idx]); Xm_tr_l.extend(xm[:idx]); y_tr_l.extend(y[:idx])
            Xd_va_l.extend(xd[idx:]); Xw_va_l.extend(xw[idx:]); Xm_va_l.extend(xm[idx:]); y_va_l.extend(y[idx:])
        except Exception as e: logger.error(f"{sym} error: {e}")

    sc_d, sc_w, sc_m = StandardScaler(), StandardScaler(), StandardScaler()
    def process_x(l, sc, fit=False):
        arr = np.array(l); N,S,F = arr.shape
        flat = arr.reshape(-1, F)
        res = sc.fit_transform(flat) if fit else sc.transform(flat)
        return res.reshape(N,S,F)

    Xd_tr, Xw_tr, Xm_tr = process_x(Xd_tr_l, sc_d, True), process_x(Xw_tr_l, sc_w, True), process_x(Xm_tr_l, sc_m, True)
    Xd_va, Xw_va, Xm_va = process_x(Xd_va_l, sc_d), process_x(Xw_va_l, sc_w), process_x(Xm_va_l, sc_m)
    
    train_loader = DataLoader(MTFDataset(Xd_tr, Xw_tr, Xm_tr, y_tr_l), _BATCH, True, pin_memory=True)
    val_loader = DataLoader(MTFDataset(Xd_va, Xw_va, Xm_va, y_va_l), _BATCH, False, pin_memory=True)

    model = MultiTimeframeCNN(len(FEATURE_COLS)).to(device)
    class_counts = np.bincount(y_tr_l)
    w = torch.FloatTensor((1.0 / class_counts) / (1.0 / class_counts).sum() * len(class_counts)).to(device)
    crit = nn.CrossEntropyLoss(weight=w, label_smoothing=0.15)
    opt = optim.AdamW(model.parameters(), lr=_LR, weight_decay=1e-3)
    sched = optim.lr_scheduler.ReduceLROnPlateau(opt, mode='min', factor=0.5, patience=5)

    logger.info(f"Model params: {sum(p.numel() for p in model.parameters()):,}")
    best_acc, stale = 0, 0
    _NOISE_STD = 0.05
    for epoch in range(_EPOCHS):
        model.train(); running_loss = 0
        for xd, xw, xm, yb in train_loader:
            xd, xw, xm, yb = [t.to(device, non_blocking=True) for t in (xd, xw, xm, yb)]
            xd = xd + torch.randn_like(xd) * _NOISE_STD
            xw = xw + torch.randn_like(xw) * _NOISE_STD
            xm = xm + torch.randn_like(xm) * _NOISE_STD
            opt.zero_grad(); loss = crit(model(xd, xw, xm), yb); loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0); opt.step()
            running_loss += loss.item() * xd.size(0)
        
        model.eval(); correct, total, v_loss_sum = 0, 0, 0
        with torch.no_grad():
            for xd, xw, xm, yb in val_loader:
                xd, xw, xm, yb = [t.to(device, non_blocking=True) for t in (xd, xw, xm, yb)]
                out = model(xd, xw, xm); v_loss_sum += crit(out, yb).item() * xd.size(0)
                correct += (out.argmax(1) == yb).sum().item(); total += yb.size(0)
        
        acc = 100 * correct / (total + 1e-8); v_loss = v_loss_sum / len(val_loader.dataset)
        sched.step(v_loss)
        logger.info(f"[{epoch+1:03d}/{_EPOCHS}] loss: {running_loss/len(train_loader.dataset):.4f} v_loss: {v_loss:.4f} acc: {acc:.2f}%")
        if acc > best_acc:
            best_acc, stale = acc, 0
            ckpt = {'model': model.state_dict(), 'scalers': {'daily': sc_d, 'weekly': sc_w, 'monthly': sc_m}}
            torch.save(ckpt, _MODEL_PATH)
            torch.save(ckpt, _OFFICIAL_MODEL_PATH)
            logger.info(f"Model saved to {_OFFICIAL_MODEL_PATH}")
        else:
            stale += 1
            if stale >= _PATIENCE: break
    
    logger.info(f"Done. Best: {best_acc:.2f}%")
    
    # Final Eval
    checkpoint = torch.load(_MODEL_PATH)
    model.load_state_dict(checkpoint['model'])
    model.eval(); all_p, all_t = [], []
    with torch.no_grad():
        for xd, xw, xm, yb in val_loader:
            out = model(xd.to(device), xw.to(device), xm.to(device))
            all_p.extend(out.argmax(1).cpu().numpy())
            all_t.extend(yb.numpy())
    print("-" * 30)
    print(classification_report(all_t, all_p, target_names=["Crush", "Neutral", "Expand"]))

if __name__ == "__main__": Main()
