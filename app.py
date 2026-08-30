from datetime import datetime, timedelta
from io import StringIO

import pandas as pd
import requests
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="台股技術與基本面快篩儀表板", page_icon="📈", layout="wide")
st.title("📈 台股技術與基本面快篩儀表板")
st.caption("資料來源：FinMind 與 Yahoo Finance。資料可能延遲或缺漏，僅供研究參考。")

DEFAULT_STOCKS = """8422 可寧衛
6803 崑鼎
8341 日友
6951 青新
1216 統一
2912 統一超
8462 柏文
2762 世界健身
5287 數字
3130 一零四
9917 中保科
9925 新保
2412 中華電
3045 台灣大
4904 遠傳
5904 寶雅
2330 台積電
1788 杏昌
1232 大統益
5902 德記
1264 德麥
6923 中台
5903 全家
0050 台灣50
6887 寶特綠
9933 中鼎
2317 鴻海
2884 玉山金
1802 台玻
8390 金益鼎
2891 中信金"""

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"


def clean_stock_id(value):
    value = str(value).strip().upper()
    return value.zfill(4) if value.isdigit() else value


def finmind_get(dataset, stock_id, token="", days=730):
    """以 params 傳送 FinMind 請求，避免手動串接 URL 造成 token/特殊字元錯誤。"""
    params = {
        "dataset": dataset,
        "data_id": clean_stock_id(stock_id),
        "start_date": (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d"),
    }
    if token and token.strip():
        params["token"] = token.strip()

    try:
        response = requests.get(FINMIND_URL, params=params, timeout=15)
        response.raise_for_status()
        payload = response.json()
        rows = payload.get("data", [])
        if not isinstance(rows, list):
            return pd.DataFrame(), f"FinMind 回傳格式不是清單：{payload}"
        if not rows:
            return pd.DataFrame(), payload.get("msg", "查無資料")
        return pd.DataFrame(rows), ""
    except requests.RequestException as exc:
        return pd.DataFrame(), f"網路/API 錯誤：{exc}"
    except ValueError as exc:
        return pd.DataFrame(), f"JSON 解析錯誤：{exc}"
    except Exception as exc:
        return pd.DataFrame(), f"未知錯誤：{exc}"


@st.cache_data(ttl=1800, show_spinner=False)
def get_finmind_fundamentals(stock_id, token):
    pe = dividend_yield = dividend = None
    errors = []

    df, err = finmind_get("TaiwanStockPER", stock_id, token, days=90)
    if not df.empty:
        df["date"] = pd.to_datetime(df.get("date"), errors="coerce")
        df = df.sort_values("date").dropna(subset=["date"])
        latest = df.iloc[-1]
        pe = pd.to_numeric(latest.get("PER"), errors="coerce")
        dividend_yield = pd.to_numeric(latest.get("dividend_yield"), errors="coerce")
        pe = float(pe) if pd.notna(pe) and pe > 0 else None
        dividend_yield = float(dividend_yield) if pd.notna(dividend_yield) and dividend_yield >= 0 else None
    elif err:
        errors.append(f"PER：{err}")

    # StockDividend 的現金股利欄位是 CashEarningsDistribution，不是 type/stock_dividend。
    df_div, err = finmind_get("StockDividend", stock_id, token, days=1095)
    if not df_div.empty:
        col = next((c for c in ["CashEarningsDistribution", "cash_earnings_distribution"] if c in df_div.columns), None)
        if col:
            values = pd.to_numeric(df_div[col], errors="coerce").dropna()
            values = values[values > 0]
            if not values.empty:
                # 取最新一個股利年度/公告資料，避免把多年股利全部相加。
                date_col = pd.to_datetime(df_div.get("date"), errors="coerce")
                latest_date = date_col.max()
                latest_rows = df_div[date_col.dt.year == latest_date.year] if pd.notna(latest_date) else df_div
                latest_values = pd.to_numeric(latest_rows[col], errors="coerce").dropna()
                latest_values = latest_values[latest_values > 0]
                if not latest_values.empty:
                    dividend = float(latest_values.iloc[-1])
        else:
            errors.append("股利：找不到 CashEarningsDistribution 欄位")
    elif err:
        errors.append(f"股利：{err}")

    return pe, dividend_yield, dividend, errors


@st.cache_data(ttl=1800, show_spinner=False)
def get_monthly_revenue(stock_id, token):
    df, err = finmind_get("TaiwanStockMonthRevenue", stock_id, token, days=1095)
    if df.empty:
        return "查無近期單月營收資料", err

    required = {"revenue", "revenue_month", "revenue_year"}
    if not required.issubset(df.columns):
        return f"營收欄位不完整：目前欄位 {', '.join(df.columns)}", ""

    df["revenue"] = pd.to_numeric(df["revenue"], errors="coerce")
    df["revenue_year"] = pd.to_numeric(df["revenue_year"], errors="coerce")
    df["revenue_month"] = pd.to_numeric(df["revenue_month"], errors="coerce")
    df = df.dropna(subset=["revenue", "revenue_year", "revenue_month"]).copy()
    df["year"] = df["revenue_year"].astype(int)
    df["month"] = df["revenue_month"].astype(int)
    df = df.sort_values(["year", "month"], ascending=False).drop_duplicates(["year", "month"])

    output = []
    for _, row in df.head(3).iterrows():
        year, month = int(row["year"]), int(row["month"])
        current = float(row["revenue"])
        previous = df[(df["year"] == year - 1) & (df["month"] == month)]
        if previous.empty:
            last_text, yoy_text = "N/A", "N/A"
        else:
            last = float(previous.iloc[0]["revenue"])
            last_text = f"{last / 1e8:.2f}億"
            yoy_text = f"{(current - last) / last * 100:+.2f}%" if last else "N/A"
        output.append(f"{year}年{month}月：今年 {current / 1e8:.2f}億 | 去年 {last_text} | YoY {yoy_text}")
    return "<br>".join(output) if output else "查無近期單月營收資料", ""


def get_price_history(stock_id, token):
    """Yahoo 失敗時改用 FinMind 日成交資料，避免整檔股票直接被丟掉。"""
    stock_id = clean_stock_id(stock_id)
    errors = []
    for suffix in ("TW", "TWO"):
        symbol = f"{stock_id}.{suffix}"
        try:
            history = yf.Ticker(symbol).history(period="1y", interval="1d", auto_adjust=False)
            if not history.empty:
                history = history.rename(columns=str.title)
                return history, yf.Ticker(symbol), errors
            errors.append(f"Yahoo {symbol} 無資料")
        except Exception as exc:
            errors.append(f"Yahoo {symbol}：{exc}")

    df, err = finmind_get("TaiwanStockPrice", stock_id, token, days=365)
    if not df.empty:
        rename = {"open": "Open", "max": "High", "min": "Low", "close": "Close"}
        df = df.rename(columns=rename)
        for col in ["Open", "High", "Low", "Close"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["Date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["Date", "High", "Low", "Close"]).set_index("Date").sort_index()
        return df, None, errors
    errors.append(f"FinMind 股價：{err}")
    return pd.DataFrame(), None, errors


def calculate_kd(df):
    low = df["Low"].rolling(9, min_periods=9).min()
    high = df["High"].rolling(9, min_periods=9).max()
    spread = (high - low).replace(0, pd.NA)
    rsv = ((df["Close"] - low) / spread * 100).fillna(50)
    k, d = 50.0, 50.0
    ks, ds = [], []
    for value in rsv:
        k = (2 / 3) * k + (1 / 3) * float(value)
        d = (2 / 3) * d + (1 / 3) * k
        ks.append(k)
        ds.append(d)
    return ks, ds


def analyze_stock(stock_id, stock_name, token):
    stock_id = clean_stock_id(stock_id)
    df, ticker, errors = get_price_history(stock_id, token)
    if df.empty or len(df) < 2:
        return None, "；".join(errors)

    close = pd.to_numeric(df["Close"], errors="coerce").dropna()
    if close.empty:
        return None, "股價資料沒有有效 Close 欄位"
    price = float(close.iloc[-1])

    pe, dividend_yield, dividend, fundamental_errors = get_finmind_fundamentals(stock_id, token)
    errors.extend(fundamental_errors)

    eps = None
    if ticker is not None:
        try:
            info = ticker.get_info()
            for key in ("trailingEps", "epsTrailingTwelveMonths", "forwardEps"):
                value = pd.to_numeric(info.get(key), errors="coerce")
                if pd.notna(value) and value > 0:
                    eps = float(value)
                    break
            if pe is None:
                value = pd.to_numeric(info.get("trailingPE"), errors="coerce")
                if pd.notna(value) and value > 0:
                    pe = float(value)
        except Exception as exc:
            errors.append(f"Yahoo 基本面：{exc}")

    if dividend_yield is None and dividend and price > 0:
        dividend_yield = dividend / price * 100
    if dividend is None and dividend_yield and price > 0:
        dividend = price * dividend_yield / 100
    if pe is None and eps and eps > 0:
        pe = price / eps
    if eps is None and pe and pe > 0:
        eps = price / pe

    df = df.copy()
    df["K"], df["D"] = calculate_kd(df)
    latest_k, latest_d = float(df["K"].iloc[-1]), float(df["D"].iloc[-1])
    prev_k, prev_d = float(df["K"].iloc[-2]), float(df["D"].iloc[-2])
    if prev_k <= prev_d and latest_k > latest_d:
        signal = "黃金交叉"
    elif prev_k >= prev_d and latest_k < latest_d:
        signal = "死亡交叉"
    else:
        signal = "多頭" if latest_k >= latest_d else "空頭"

    revenue_text, revenue_error = get_monthly_revenue(stock_id, token)
    if revenue_error:
        errors.append(f"營收：{revenue_error}")

    return {
        "代碼": stock_id,
        "名稱": stock_name,
        "現價": f"{price:.2f}",
        "EPS": f"{eps:.2f}" if eps is not None else "N/A",
        "本益比": f"{pe:.2f}" if pe is not None and pe > 0 else "N/A",
        "配息": f"{dividend:.2f}元" if dividend is not None and dividend > 0 else "N/A",
        "殖利率": f"{dividend_yield:.2f}%" if dividend_yield is not None else "N/A",
        "配息率": f"{dividend / eps * 100:.1f}%" if dividend and eps and eps > 0 else "N/A",
        "K值": f"{latest_k:.2f}",
        "D值": f"{latest_d:.2f}",
        "技術訊號": signal,
        "近期營收摘要": revenue_text,
        "錯誤訊息": "；".join(errors),
    }, ""


st.sidebar.header("⚙️ 查詢設定")
fm_token = st.sidebar.text_input(
    "FinMind API Token（可留白；請勿把 token 寫死在程式碼）", value="", type="password"
)
uploaded_file = st.sidebar.file_uploader("📂 上傳自選股檔案（每行：代碼 空格 名稱）", type=["txt", "csv"])
stocks_text = DEFAULT_STOCKS
if uploaded_file is not None:
    raw = uploaded_file.getvalue()
    for encoding in ("utf-8-sig", "utf-8", "big5", "cp950"):
        try:
            stocks_text = raw.decode(encoding)
            st.sidebar.success(f"✅ 已讀取檔案（{encoding}）")
            break
        except UnicodeDecodeError:
            continue
stocks_input = st.sidebar.text_area("股票清單預覽與編輯（每行一檔）", stocks_text, height=250)
run_btn = st.sidebar.button("🚀 開始執行批量分析", type="primary")

if run_btn:
    stock_list = []
    for line in stocks_input.splitlines():
        parts = line.replace(",", " ").split()
        if parts:
            stock_list.append((parts[0], parts[1] if len(parts) >= 2 else f"股票{parts[0]}"))
    if not stock_list:
        st.error("請至少輸入一檔股票代碼。")
    else:
        st.info(f"正在分析 {len(stock_list)} 檔股票；若 API 限流，請稍後再試。")
        progress = st.progress(0)
        results, failures = [], []
        for index, (stock_id, stock_name) in enumerate(stock_list):
            result, error = analyze_stock(stock_id, stock_name, fm_token)
            if result:
                results.append(result)
            else:
                failures.append(f"{stock_id} {stock_name}：{error}")
            progress.progress((index + 1) / len(stock_list))

        if results:
            st.success(f"✅ 完成 {len(results)} 檔分析。")
            for item in results:
                st.markdown(
                    f"""#### {item['代碼']} {item['名稱']}（現價：{item['現價']}）

**財務指標：** EPS `{item['EPS']}`｜本益比 `{item['本益比']}`｜配息 `{item['配息']}`｜殖利率 `{item['殖利率']}`｜配息率 `{item['配息率']}`

**技術指標：** K `{item['K值']}`｜D `{item['D值']}`｜狀態 **{item['技術訊號']}**

**近期營收：**  
{item['近期營收摘要']}
""",
                    unsafe_allow_html=True,
                )
                if item["錯誤訊息"]:
                    with st.expander("查看此檔的資料來源提示"):
                        st.caption(item["錯誤訊息"])
                st.divider()
        if failures:
            with st.expander(f"有 {len(failures)} 檔未取得股價資料，查看原因"):
                st.write("\n".join(failures))
else:
    st.info("請從左側輸入股票清單，或按下「開始執行批量分析」。")

st.caption("提示：FinMind 官方欄位中，PER 使用 `PER`、殖利率使用 `dividend_yield`，月營收使用 `revenue_year/revenue_month`；本版本已依此處理。")

