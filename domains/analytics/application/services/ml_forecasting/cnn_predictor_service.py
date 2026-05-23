"""
File Overview: Multi-Timeframe CNN-LSTM predictor for market volatility and trend forecasting. Loads a pre-trained PyTorch model and engineers technical features from yfinance data.

All Functions/Classes:
- MultiTimeframeCNN (class): PyTorch neural network architecture combining daily, weekly, and monthly temporal features.
- cnn_predictor (class): Orchestrator for loading the model, engineering features, and performing inference. Data: yfinance (Market/Macro) -> Trend Prediction.
- get_macro_features: Fetches VIX, TNX, and DXY indices. Data: yfinance -> Macro Feature Dataframe.
- engineer_features: Calculates RSI, MACD, Stochastics, and EMA distances. Data: OHLCV -> Technical Indicators.
- predict: Main entry point for inference. Data: Symbol -> Strategy/Prediction/Confidence JSON.

Endpoints/APIs:
- External: yfinance API (NSE indices and macro data).

Database Tables:
- None.
"""
import os
import logging


import torch
import torch.nn as nn
import numpy as np
import pandas as pd
import yfinance as yf
from typing import Dict, Any
import asyncio

from shared.utils.symbol_validator import SymbolValidator

# Replicated architecture from ModelTraining.txt (matching the saved weight keys)
class ResBlock1D(nn.Module):
    def __init__(self, ch):
        super().__init__()
        self.net = nn.Sequential(nn.BatchNorm1d(ch), nn.GELU(), nn.Conv1d(ch, ch, 3, padding=1), nn.BatchNorm1d(ch), nn.GELU(), nn.Conv1d(ch, ch, 3, padding=1))
    def forward(self, x): return x + self.net(x)

class TimeframeBranch(nn.Module):
    def __init__(self, n_feat, cnn_hidden=64, lstm_hidden=64, out_dim=96):
        super().__init__()
        c3, c5 = cnn_hidden // 3, cnn_hidden // 3
        c7 = cnn_hidden - c3 - c5
        self.conv3, self.conv5, self.conv7 = nn.Conv1d(n_feat, c3, 3, padding=1), nn.Conv1d(n_feat, c5, 5, padding=2), nn.Conv1d(n_feat, c7, 7, padding=3)
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

class CnnPredictorService:
    def __init__(self, model_path: str = "models/MTF_CNN_LSTM_VOL.pt"):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model_path = model_path
        self.feature_cols = [
            'RSI_14', 'MACD', 'MACD_Signal', 'MACD_Hist', 'Stoch_K', 'Stoch_D', 'Williams_R',
            'EMA9_Dist', 'EMA21_Dist', 'EMA50_Dist', 'ADX', 'BB_Width', 'BB_Position',
            'ATR_Norm', 'ret_1d', 'ret_5d', 'ret_10d', 'HL_Ratio', 'OC_Ratio', 'Gap',
            'vol_momentum', 'OBV_Norm'
        ]
        self.model = None
        self.scalers = None
        self.labels = ["VOL_CRUSH", "NEUTRAL", "VOL_EXPAND"]
        self._load_model()

    def _load_model(self):
        if not os.path.exists(self.model_path):
            alt_path = "research/Models/MTF_CNN_LSTM_VOL.pt"
            if os.path.exists(alt_path): self.model_path = alt_path
            else: raise FileNotFoundError(f"Model not found at {self.model_path}")
        
        checkpoint = torch.load(self.model_path, map_location=self.device, weights_only=False)
        self.model = MultiTimeframeCNN(len(self.feature_cols)).to(self.device)
        self.model.load_state_dict(checkpoint['model'])
        self.model.eval()
        self.scalers = checkpoint['scalers']

    def _normalize_index(self, obj):
        if obj.empty: return obj
        if hasattr(obj.index, 'tz') and obj.index.tz is not None:
            obj.index = obj.index.tz_localize(None)
        obj.index = pd.to_datetime(obj.index).normalize()
        obj.index = obj.index.astype('datetime64[ns]')
        obj.index.name = "Date"
        # If it's a series, we don't have columns but we return the object
        if isinstance(obj, pd.DataFrame):
            obj = obj.sort_index()
            obj = obj[~obj.index.duplicated(keep='last')]
        return obj

    async def get_macro_features(self, interval="1d", period="2y"):
        # Wrap blocking yfinance calls
        vix_task = asyncio.to_thread(lambda: yf.Ticker("^VIX").history(period=period, interval=interval)['Close'])
        tnx_task = asyncio.to_thread(lambda: yf.Ticker("^TNX").history(period=period, interval=interval)['Close'])
        dxy_task = asyncio.to_thread(lambda: yf.Ticker("DX-Y.NYB").history(period=period, interval=interval)['Close'])
        
        vix, tnx, dxy = await asyncio.gather(vix_task, tnx_task, dxy_task)
        
        vix, tnx, dxy = self._normalize_index(vix), self._normalize_index(tnx), self._normalize_index(dxy)
        m_df = pd.concat([vix, tnx, dxy], axis=1, keys=['VIX', 'TNX', 'DXY']).ffill()
        m_df['MACRO_VIX'] = m_df['VIX'] / 100.0
        m_df['MACRO_TNX_Mom'] = m_df['TNX'] / (m_df['TNX'].rolling(20).mean() + 1e-8)
        m_df['MACRO_DXY_Ret'] = m_df['DXY'].pct_change(5)
        return m_df[['MACRO_VIX', 'MACRO_TNX_Mom', 'MACRO_DXY_Ret']].dropna()

    def engineer_features(self, df: pd.DataFrame) -> pd.DataFrame:
        if len(df) < 60: return pd.DataFrame()
        df = df.copy()
        df.columns = [c.lower() for c in df.columns]
        c, h, l, o, v = df['close'], df['high'], df['low'], df['open'], df['volume']
        
        delta = c.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        df['RSI_14'] = (100 - 100 / (1 + gain / (loss + 1e-8))) / 100.0
        ema12, ema26 = c.ewm(span=12, adjust=False).mean(), c.ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        sig = macd.ewm(span=9, adjust=False).mean()
        df['MACD'], df['MACD_Signal'], df['MACD_Hist'] = macd/(c+1e-8), sig/(c+1e-8), (macd-sig)/(c+1e-8)
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
        dip, dim = 100*dmp.rolling(14).mean()/(atr+1e-8), 100*dmm.rolling(14).mean()/(atr+1e-8)
        dx = 100*(dip-dim).abs()/(dip+dim+1e-8)
        df['ADX'] = dx.rolling(14).mean()/100
        sma20, std20 = c.rolling(20).mean(), c.rolling(20).std()
        bbl, bbu = sma20 - 2*std20, sma20 + 2*std20
        df['BB_Width'], df['BB_Position'] = (bbu-bbl)/(sma20+1e-8), (c-bbl)/(bbu-bbl+1e-8)
        df['ret_1d'], df['ret_5d'], df['ret_10d'] = c.pct_change(1), c.pct_change(5), c.pct_change(10)
        df['HL_Ratio'], df['OC_Ratio'], df['Gap'] = (h-l)/(c+1e-8), (c-o)/(o+1e-8), (o-c.shift(1))/(c.shift(1)+1e-8)
        df['vol_momentum'] = v / (v.rolling(10).mean() + 1e-8)
        obv = (np.sign(c.diff()) * v).fillna(0).cumsum()
        df['OBV_Norm'] = (obv - obv.rolling(50).min()) / (obv.rolling(50).max() - obv.rolling(50).min() + 1e-8)
        return df.dropna()

    async def predict(self, symbol: str) -> Dict[str, Any]:
        try:
            clean_sym = SymbolValidator.get_clean_symbol(symbol)
            
            # Map canonical symbols to yfinance-specific tickers
            yf_mapping = {
                "NIFTY": "^NSEI",
                "BANKNIFTY": "^NSEBANK",
                "FINNIFTY": "^CNXFIN"
            }
            yf_sym = yf_mapping.get(clean_sym, clean_sym)
            
            tkr = yf.Ticker(yf_sym)
            
            # Parallel history fetching
            h_d_task = asyncio.to_thread(tkr.history, period="2y", interval="1d")
            h_w_task = asyncio.to_thread(tkr.history, period="5y", interval="1wk")
            h_m_task = asyncio.to_thread(tkr.history, period="10y", interval="1mo")
            
            df_d, df_w, df_m = await asyncio.gather(h_d_task, h_w_task, h_m_task)
            
            if df_d.empty: return {"error": f"No data for {symbol}"}

            macro_d_task = self.get_macro_features("1d", period="2y")
            macro_w_task = self.get_macro_features("1wk", period="5y")
            macro_m_task = self.get_macro_features("1mo", period="10y")
            
            macro_d, macro_w, macro_m = await asyncio.gather(macro_d_task, macro_w_task, macro_m_task)
            
            macro_w = macro_w.shift(1).dropna()
            macro_m = macro_m.shift(1).dropna()

            df_d = self.engineer_features(df_d)
            df_w = self.engineer_features(df_w).shift(1).dropna()
            df_m = self.engineer_features(df_m).shift(1).dropna()

            df_d = self._normalize_index(df_d)
            df_w = self._normalize_index(df_w)
            df_m = self._normalize_index(df_m)

            if df_d.empty or macro_d.empty or df_w.empty or macro_w.empty or df_m.empty or macro_m.empty:
                return {"error": "Indicators produced empty dataframe (check history length)"}

            df_d = pd.merge_asof(df_d, macro_d, left_index=True, right_index=True, direction='backward').dropna()
            df_w = pd.merge_asof(df_w, macro_w, left_index=True, right_index=True, direction='backward').dropna()
            df_m = pd.merge_asof(df_m, macro_m, left_index=True, right_index=True, direction='backward').dropna()

            if len(df_d) < 21 or len(df_w) < 12 or len(df_m) < 6:
                return {"error": "Insufficient history for full sequence"}

            def get_seq(df, sc, length):
                arr = df[self.feature_cols].values[-length:]
                flat = arr.reshape(-1, len(self.feature_cols))
                res = sc.transform(flat)
                return torch.FloatTensor(res.reshape(1, length, -1))

            xd = get_seq(df_d, self.scalers['daily'], 21).to(self.device)
            xw = get_seq(df_w, self.scalers['weekly'], 12).to(self.device)
            xm = get_seq(df_m, self.scalers['monthly'], 6).to(self.device)

            with torch.no_grad():
                logits = self.model(xd, xw, xm)
                probs = torch.softmax(logits, dim=1)
                pred_idx = torch.argmax(probs, dim=1).item()
                conf = probs[0][pred_idx].item()

            return {
                "symbol": symbol,
                "strategy": "MTF-CNN-LSTM-VOL",
                "prediction": self.labels[pred_idx],
                "confidence": conf,
                "confluence_status": "HIGH" if conf > 0.7 else "MODERATE" if conf > 0.5 else "LOW"
            }
        except Exception as e:
            logging.getLogger("cnn_predictor").exception("Prediction failed for %s", symbol)
            return {"error": str(e)}

    def predict_sync(self, symbol: str) -> Dict[str, Any]:
        """Synchronous wrapper for Celery workers (no running event loop)."""
        return asyncio.run(self.predict(symbol))
