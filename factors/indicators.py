import pandas as pd
import pandas_ta as ta


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    out = df.copy()
    out["MA20"] = ta.sma(out["Close"], length=20)
    out["MA60"] = ta.sma(out["Close"], length=60)
    out["EMA12"] = ta.ema(out["Close"], length=12)
    out["EMA26"] = ta.ema(out["Close"], length=26)
    out["RSI14"] = ta.rsi(out["Close"], length=14)

    macd = ta.macd(out["Close"], fast=12, slow=26, signal=9)
    if macd is not None and not macd.empty:
        macd_line_col = next((c for c in macd.columns if c.startswith("MACD_")), None)
        macd_signal_col = next((c for c in macd.columns if c.startswith("MACDs_")), None)
        macd_hist_col = next((c for c in macd.columns if c.startswith("MACDh_")), None)
        if macd_line_col:
            out["MACD"] = macd[macd_line_col]
        if macd_signal_col:
            out["MACD_SIGNAL"] = macd[macd_signal_col]
        if macd_hist_col:
            out["MACD_HIST"] = macd[macd_hist_col]

    bbands = ta.bbands(out["Close"], length=20, std=2)
    if bbands is not None and not bbands.empty:
        bbl_col = next((c for c in bbands.columns if c.startswith("BBL_")), None)
        bbm_col = next((c for c in bbands.columns if c.startswith("BBM_")), None)
        bbu_col = next((c for c in bbands.columns if c.startswith("BBU_")), None)
        if bbl_col:
            out["BBL"] = bbands[bbl_col]
        if bbm_col:
            out["BBM"] = bbands[bbm_col]
        if bbu_col:
            out["BBU"] = bbands[bbu_col]

    return out
