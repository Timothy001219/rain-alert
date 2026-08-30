from datetime import datetime, timedelta
import pandas as pd
import requests
import streamlit as st
import yfinance as yf

# 網頁基本設定
st.set_page_config(
    page_title='台股技術與基本面快篩儀表板', page_icon='📈', layout='wide'
)

st.title('📈 台股技術面與基本面快篩儀表板')
st.markdown(
    '結合 **yfinance (股價與技術指標)** 與 **Finmind (單月營收、累計營收 YoY、EPS與本益比)**'
    ' 的個人專屬工具！'
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
def get_finmind_fundamentals(stock_id):
  """從 FinMind 取得 EPS、本益比、殖利率等數據（強化版）"""
  pe_val, yield_val, eps_val = 'N/A', 'N/A', 'N/A'
  start_date = (datetime.now() - timedelta(days=180)).strftime('%Y-%m-%d')

  try:
    # 1. 取得本益比與殖利率
    url_per = f'https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockPER&data_id={stock_id}&start_date={start_date}'
    res = requests.get(url_per, timeout=5)
    if res.status_code == 200:
      data = res.json()
      if 'data' in data and len(data['data']) > 0:
        df_pe = pd.DataFrame(data['data'])
        latest = df_pe.iloc[-1]
        if 'PE' in latest and pd.notna(latest['PE']):
          pe_num = float(latest['PE'])
          if pe_num > 0:
            pe_val = f'{pe_num:.2f}'
        if 'DividendYield' in latest and pd.notna(
            latest['DividendYield']
        ):
          y_val = float(latest['DividendYield'])
          # FinMind 有時候殖利率是小數（例如 0.04）或百分比（例如 4.0）
          if y_val < 1:
            y_val = y_val * 100
          yield_val = f'{y_val:.2f}%'
  except:
    pass

  try:
    # 2. 取得 EPS (改抓 TaiwanStockFinancialStatements 並放寬篩選條件)
    url_eps = f'https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockFinancialStatements&data_id={stock_id}&start_date={start_date}'
    res_eps = requests.get(url_eps, timeout=5)
    if res_eps.status_code == 200:
      data_eps = res_eps.json()
      if 'data' in data_eps and len(data_eps['data']) > 0:
        df_fin = pd.DataFrame(data_eps['data'])
        # 尋找包含 EPS 或 BasicEarningsPerShare 的欄位
        eps_rows = df_fin[
            df_fin['type'].str.contains('EPS|EarningsPerShare', case=False, na=False)
        ]
        if not eps_rows.empty:
          latest_eps = eps_rows.iloc[-1]['value']
          if pd.notna(latest_eps):
            eps_val = f'{float(latest_eps):.2f}'
  except:
    pass

  return pe_val, yield_val, eps_val


@st.cache_data(ttl=3600)
def get_real_monthly_revenue(stock_id):
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
        recent_months = df_rev.head(3)

        rev_texts = []
        for _, row in recent_months.iterrows():
          curr_date = row['date']
          curr_rev = row['revenue'] / 1e8
          m_str = curr_date.strftime('%m月')
          ly_date = curr_date - pd.DateOffset(years=1)
          match_ly = df_rev[df_rev['date'] == ly_date]

          ly_str = 'N/A'
          yoy_str = 'N/A'
          if not match_ly.empty:
            ly_rev = match_ly.iloc[0]['revenue'] / 1e8
            ly_str = f'{ly_rev:.2f}億'
            if ly_rev > 0:
              yoy = (
                  (row['revenue'] - match_ly.iloc[0]['revenue'])
                  / match_ly.iloc[0]['revenue']
                  * 100
              )
              yoy_str = f'{yoy:+.2f}%'

          curr_year = curr_date.year
          this_year_mask = (df_rev['date'].dt.year == curr_year) & (
              df_rev['date'].dt.month <= curr_date.month
          )
          this_year_acc = df_rev[this_year_mask]['revenue'].sum() / 1e8

          last_year_mask = (df_rev['date'].dt.year == curr_year - 1) & (
              df_rev['date'].dt.month <= curr_date.month
          )
          last_year_acc = df_rev[last_year_mask]['revenue'].sum() / 1e8

          acc_yoy_str = 'N/A'
          if last_year_acc > 0:
            acc_yoy = (
                (this_year_acc - last_year_acc) / last_year_acc * 100
            )
            acc_yoy_str = f'{acc_yoy:+.2f}%'

          acc_str = (
              f' | 累計: 今年 {this_year_acc:.2f}億 (去年 {last_year_acc:.2f}億,'
              f' 累計YoY: {acc_yoy_str})'
          )

          rev_texts.append(
              f'&nbsp;&nbsp;&nbsp;&nbsp;{curr_date.strftime("%Y年")}{m_str}:'
              f' 單月 {curr_rev:.2f}億 (去年 {ly_str}, YoY: {yoy_str}){acc_str}'
          )
        return '<br>'.join(rev_texts)
    return '查無近期營收'
  except:
    return '營收取得略過'


def analyze_stock(stock_id, stock_name):
  stock_id = stock_id.strip()
  candidates = [f'{stock_id}.TW', f'{stock_id}.TWO']
  df = pd.DataFrame()

  for cand in candidates:
    try:
      temp_df = yf.download(cand, period='6mo', interval='1d', progress=False)
      if not temp_df.empty:
        df = temp_df
        break
    except:
      continue

  if df.empty:
    return None

  if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.get_level_values(0)

  # 1. 取得現價
  current_price = 'N/A'
  try:
    price_val = df['Close'].iloc[-1]
    if price_val:
      current_price = f'{price_val:.2f}'
  except:
    pass

  # 2. 取得基本面 (本益比、殖利率、EPS)
  pe_str, yield_str, eps_str = get_finmind_fundamentals(stock_id)
  dividend_str = 'N/A'
  payout_str = 'N/A'

  # 試算配息金額與配息率
  try:
    if yield_str != 'N/A' and current_price != 'N/A':
      y_num = float(yield_str.replace('%', ''))
      p_num = float(current_price)
      calc_div = (y_num / 100) * p_num
      dividend_str = f'{calc_div:.2f}元'

      if eps_str != 'N/A':
        e_num = float(eps_str)
        if e_num > 0:
          calc_payout = (calc_div / e_num) * 100
          payout_str = f'{calc_payout:.1f}%'
  except:
    pass

  # 3. 技術指標計算 (KD)
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

  if prev_k <= prev_d and latest_k > latest_d:
    signal = '🌟 黃金交叉'
  elif prev_k >= prev_d and latest_k < latest_d:
    signal = '⚠️ 死亡交叉'
  else:
    signal = '多頭' if latest_k > latest_d else '空頭'

  k_trend = '📈 向上' if latest_k > prev_k else '📉 向下'
  d_trend = '📈 向上' if latest_d > prev_d else '📉 向下'

  k_val_str = f'{latest_k:.2f} ({k_trend})'
  if latest_k < 20:
    k_val_str = f"<span style='font-size: 1.4em; color: #d9534f; font-weight: bold;'>{latest_k:.2f} ({k_trend}) 📉 [低檔超賣]</span>"

  d_val_str = f'{latest_d:.2f} ({d_trend})'
  if latest_d < 20:
    d_val_str = f"<span style='font-size: 1.4em; color: #d9534f; font-weight: bold;'>{latest_d:.2f} ({d_trend}) 📉 [低檔超賣]</span>"

  revenue_summary = get_real_monthly_revenue(stock_id)

  return {
      '代碼': stock_id,
      '名稱': stock_name,
      '現價': current_price,
      'EPS': eps_str,
      '本益比': pe_str,
      'dividend': dividend_str,
      '殖利率': yield_str,
      '配息率': payout_str,
      'k': k_val_str,
      'd': d_val_str,
      '技術訊號': signal,
      '近期營收摘要': revenue_summary,
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
                - **💰 財務指標**: EPS: `{r['EPS']}` | 本益比: `{r['本益比']}` | 配息: `{r['dividend']}` | 殖利率: `{r['殖利率']}` | 配息率: `{r['配息率']}`
                - **📊 技術指標**: K值: {r['k']} | D值: {r['d']} | 狀態: **{r['技術訊號']}**
                - **📈 營收數據 (單月與累計 YoY):**<br>{r['近期營收摘要']}
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
