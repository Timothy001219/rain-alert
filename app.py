from datetime import datetime, timedelta
import pandas as pd
import requests
import streamlit as st
import yfinance as yf

# 網頁基本設定
st.set_page_config(
    page_title='台股技術與基本面快篩儀表板', page_icon='📈', layout='wide'
)

st.title('📈 台股技術與基本面快篩儀表板 (網頁版精準實時數據)')
st.markdown(
    '結合 **yfinance 歷史股價與精準 EPS** 與 **FinMind (單月營收)**，確保財務數據乾淨正確！'
)
st.markdown('---')

# --- 預設股票清單 ---
default_stocks_text = (
    '8422 可寧衛\n6803 崑鼎\n8341 日友\n6951 青新\n1216 統一\n2912'
    ' 統一超\n8462 柏文\n2762 世界健身\n5287 數字\n3130 一零四\n9917'
    ' 中保科\n9925 新保\n2412 中華電\n3045 台灣大\n4904 遠傳\n5904 寶雅\n2330'
    ' 台積電\n1788 杏昌\n1232 大統益\n5902 德記\n1264 德麥\n6923 中台\n5903'
    ' 全家\n0050 台灣50\n6887 寶特綠\n9933 中鼎\n2317 鴻海\n2884 玉山金\n1802'
    ' 台玻\n8390 金益鼎\n2891 中信金'
)

# --- 側邊欄設定 ---
st.sidebar.header('⚙️ 查詢設定')

uploaded_file = st.sidebar.file_uploader(
    '📂 上傳自選股檔案 (格式: 代碼 空格 名稱)', type=['txt', 'csv']
)

if uploaded_file is not None:
  try:
    file_bytes = uploaded_file.getvalue()
    try:
      file_text = file_bytes.decode('utf-8')
    except:
      file_text = file_bytes.decode('big5')
    default_stocks_text = file_text
    st.sidebar.success('✅ 成功讀取您上傳的股票清單！')
  except Exception as e:
    st.sidebar.error(f'⚠️ 檔案讀取失敗: {e}')

stocks_input = st.sidebar.text_area(
    '股票清單預覽與編輯 (每行一檔)', default_stocks_text, height=250
)
st.sidebar.markdown(
    '_格式範例：代碼 空格 名稱，可直接在上方修改。_'
)

run_btn = st.sidebar.button('🚀 開始執行批量分析', type='primary')


@st.cache_data(ttl=3600)
def get_real_monthly_revenue(stock_id):
  """同時取得今年與去年同期的單月營收，並計算 YoY"""
  try:
    start_date = (datetime.now() - timedelta(days=730)).strftime('%Y-%m-%d')
    url = f'https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockMonthRevenue&data_id={stock_id}&start_date={start_date}'

    res = requests.get(url, timeout=5)
    if res.status_code == 200:
      data = res.json()
      if 'data' in data and len(data['data']) > 0:
        df_rev = pd.DataFrame(data['data'])
        df_rev['date'] = pd.to_datetime(df_rev['date'])
        df_rev = df_rev.sort_values('date', ascending=False)

        revenue_records = []
        recent_months = df_rev.head(3)  # 取最近 3 個月

        for _, row in recent_months.iterrows():
          curr_date = row['date']
          curr_revenue = row['revenue'] / 1e8  # 轉換為億元
          month_str = curr_date.strftime('%m月')

          last_year_date = curr_date - pd.DateOffset(years=1)
          match_ly = df_rev[df_rev['date'] == last_year_date]

          ly_str = 'N/A'
          yoy_str = 'N/A'

          if not match_ly.empty:
            ly_revenue = match_ly.iloc[0]['revenue'] / 1e8
            ly_str = f'{ly_revenue:.2f}億'
            if ly_revenue > 0:
              yoy = (
                  (row['revenue'] - match_ly.iloc[0]['revenue'])
                  / match_ly.iloc[0]['revenue']
                  * 100
              )
              yoy_str = f'{yoy:+.2f}%'

          revenue_records.append(
              f'&nbsp;&nbsp;&nbsp;&nbsp;{curr_date.strftime("%Y年")}{month_str}:'
              f' 今年 {curr_revenue:.2f}億 | 去年 {ly_str} | YoY: {yoy_str}'
          )

        if revenue_records:
          return '<br>'.join(revenue_records)

    return '查無近期單月營收資料'
  except:
    return '單月營收資料取得中略過'


def analyze_stock(stock_id, stock_name):
  stock_id = stock_id.strip()
  symbol = None
  df = pd.DataFrame()

  candidates = [f'{stock_id}.TW', f'{stock_id}.TWO']

  for cand in candidates:
    try:
      temp_df = yf.download(cand, period='6mo', interval='1d', progress=False)
      if not temp_df.empty:
        df = temp_df
        symbol = cand
        break
    except:
      continue

  if df.empty:
    return None

  if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.get_level_values(0)

  # --- 取得現價 ---
  current_price = 'N/A'
  price_val = None
  if not df.empty and 'Close' in df.columns:
    price_val = float(df['Close'].iloc[-1])
    current_price = f'{price_val:.2f}'

  eps_val = None
  div_val = 0.0
  pe_val = None

  # --- 透過 yfinance 抓取財務基本面 ---
  try:
    ticker = yf.Ticker(symbol)
    info = ticker.info

    # 1. 取得 EPS
    eps_val = info.get('trailingEps')
    if eps_val is None or eps_val == 0 or abs(eps_val) > 1000:
      financials = ticker.quarterly_financials
      if financials is not None and not financials.empty:
        # 嚴格過濾真實 EPS 欄位，排除淨利總額
        for col_name in ['Basic EPS', 'Diluted EPS']:
          if col_name in financials.index:
            eps_row = financials.loc[col_name]
            valid_eps = eps_row.dropna()
            if len(valid_eps) >= 4:
              val_sum = float(valid_eps.head(4).sum())
              # 確保加總後的 EPS 在合理範圍內 (例如 -50 到 200 之間)
              if -50 < val_sum < 300:
                eps_val = val_sum
                break

    # 若 EPS 異常大（超過合理範圍），直接歸零或設為 N/A
    if eps_val is not None and (eps_val > 500 or eps_val < -100):
      eps_val = None

    # 2. 取得本益比
    pe_val = info.get('trailingPE')

    # 3. 取得配息（直接從歷史股利加總過去一年）
    divs = ticker.dividends
    if divs is not None and not divs.empty:
      # 取最近一整年的股利
      one_year_ago = pd.Timestamp.now() - pd.DateOffset(years=1)
      recent_divs = divs[divs.index >= one_year_ago]
      if not recent_divs.empty:
        div_val = float(recent_divs.sum())

    if div_val == 0.0:
      div_val = info.get('dividendRate') or info.get('lastDividendValue') or 0.0

  except Exception:
    pass

  # 整理基本面字串
  eps_str = 'N/A'
  pe_str = 'N/A'
  dividend_str = 'N/A'
  yield_str = 'N/A'
  payout_str = 'N/A'

  if eps_val is not None and eps_val != 0:
    eps_str = f'{eps_val:.2f}'
    if pe_val is not None and pe_val > 0:
      pe_str = f'{pe_val:.2f}'
    elif price_val and price_val > 0 and eps_val > 0:
      calc_pe = price_val / eps_val
      pe_str = f'{calc_pe:.2f}'

  if div_val and div_val > 0:
    dividend_str = f'{div_val:.2f}元'
    if price_val and price_val > 0:
      calc_yield = (div_val / price_val) * 100
      yield_str = f'{calc_yield:.2f}%'

  if div_val and div_val > 0 and eps_val is not None and eps_val > 0:
    calc_payout = (div_val / eps_val) * 100
    payout_str = f'{calc_payout:.1f}%'

  # --- 1. 計算 KD 值 ---
  n = 9
  lowest_low = df['Low'].rolling(window=n).min()
  highest_high = df['High'].rolling(window=n).max()
  rsv = (df['Close'] - lowest_low) / (highest_high - lowest_low) * 100

  k_list, d_list = [50.0], [50.0]
  rsv_values = rsv.values

  for i in range(1, len(df)):
    curr_rsv = rsv_values[i]
    if pd.isna(curr_rsv):
      k_val, d_val = k_list[-1], d_list[-1]
    else:
      k_val = (2 / 3) * k_list[-1] + (1 / 3) * curr_rsv
      d_val = (2 / 3) * d_list[-1] + (1 / 3) * k_val
    k_list.append(k_val)
    d_list.append(d_val)

  df['K'], df['D'] = k_list, d_list
  latest_k, latest_d = df['K'].iloc[-1], df['D'].iloc[-1]
  prev_k, prev_d = df['K'].iloc[-2], df['D'].iloc[-2]

  k_trend = '📈 向上' if latest_k > prev_k else '📉 向下'
  d_trend = '📈 向上' if latest_d > prev_d else '📉 向下'

  if prev_k <= prev_d and latest_k > latest_d:
    signal = '🌟 黃金交叉'
  elif prev_k >= prev_d and latest_k < latest_d:
    signal = '⚠️ 死亡交叉'
  else:
    signal = '多頭' if latest_k > latest_d else '空頭'

  # --- 2. 取得單月營收（今年、去年、YoY） ---
  monthly_rev_str = get_real_monthly_revenue(stock_id)

  # --- 3. K值超賣區樣式處理 ---
  k_val_str = f'{latest_k:.2f} ({k_trend})'
  if latest_k <= 20:
    k_val_str = (
        f"<span style='color: #d9534f; font-weight:"
        f" bold;'>{latest_k:.2f} ({k_trend}) 🔥 [超賣區]</span>"
    )

  d_val_str = f'{latest_d:.2f} ({d_trend})'
  if latest_d <= 20:
    d_val_str = (
        f"<span style='color: #d9534f; font-weight:"
        f" bold;'>{latest_d:.2f} ({d_trend}) 🔥 [超賣區]</span>"
    )

  return {
      '代碼': stock_id,
      '名稱': stock_name,
      '現價': current_price,
      'EPS': eps_str,
      '本益比': pe_str,
      '配息': dividend_str,
      '殖利率': yield_str,
      '配息率': payout_str,
      'k': k_val_str,
      'd': d_val_str,
      '技術訊號': signal,
      '近期營收摘要': monthly_rev_str,
  }


if run_btn:
  lines = stocks_input.strip().split('\n')
  stock_list = []
  for line in lines:
    parts = line.replace(',', ' ').split()
    if len(parts) >= 2:
      stock_list.append((parts[0], parts[1]))
    elif len(parts) == 1:
      stock_list.append((parts[0], f'股票{parts[0]}'))

  st.info(f'正在為您分析共計 {len(stock_list)} 檔股票，請稍候...')

  results = []
  progress_bar = st.progress(0)
  for idx, (s_id, s_name) in enumerate(stock_list):
    res = analyze_stock(s_id, s_name)
    if res:
      results.append(res)
    progress_bar.progress((idx + 1) / len(stock_list))

  if results:
    st.success('✅ 分析完畢！')
    for r in results:
      with st.container():
        st.markdown(
            f"""
                #### {r['代碼']} {r['名稱']} (現價: {r['現價']})
                - **💰 財務指標**: EPS: `{r['EPS']}` | 本益比: `{r['本益比']}` | 配息: `{r['配息']}` | 殖利率: `{r['殖利率']}` | 配息率: `{r['配息率']}`
                - **📊 技術指標**: K值: {r['k']} | D值: {r['d']} | 狀態: **{r['技術訊號']}**
                - **📈 單月營收對比 (今年 vs 去年 YoY):**<br>{r['近期營收摘要']}
                """,
            unsafe_allow_html=True,
        )
        st.divider()
  else:
    st.warning('⚠️ 查無有效的股票資料，請檢查代碼是否正確。')
else:
  st.info(
      '👈 請從左側邊欄 **上傳檔案** 或直接點擊 **「開始執行批量分析」**'
      ' 來載入數據！'
  )
