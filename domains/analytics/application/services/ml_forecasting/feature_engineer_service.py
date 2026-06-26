"""
File Overview: Calculates technical indicators (RSI, MACD, Bollinger Bands, ATR, Obv, returns) from historical stock price dataframes.
"""
import numpy as np
import pandas as pd

class FeatureEngineerService:
    def engineer_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate 22 technical indicators for CNN-LSTM prediction.
        Input dataframe must contain Open, High, Low, Close, Volume.
        """
        if len(df) < 60:
            return pd.DataFrame()
            
        df = df.copy()
        # Ensure lowercase columns
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
