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
    '結合 **yfinance (股價/EPS/本益比/殖利率)** 與 **Finmind (單月營收 YoY)**'
    ' 的個人專屬工具！'
)
st.markdown('---')

# --- 側邊欄設定 ---
st.sidebar.header('⚙️ 查詢設定')

default_stocks = '2330 台積電\n2317 鴻海\n2412 中華電\n5287 數字\n8422 可寧衛'
stocks_input = st.sidebar.text_area(
    '輸入股票清單 (代碼 名稱)', default_stocks, height=150
)
st.sidebar.markdown(
    '_格式範例：代碼 空格 名稱，每行一檔股票。_'
)

run_btn = st.sidebar.button('🚀 開始執行批量分析', type='primary')


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
          rev_texts.append(
              f'{curr_date.strftime("%Y年")}{m_str}: 今年 {curr_rev:.2f}億 | 去年'
              f' {ly_str} | YoY: {yoy_str}'
          )
        return ' | '.join(rev_texts)
    return '查無近期營收'
  except:
    return '營收取得略過'


def analyze_stock(stock_id, stock_name):
  stock_id = stock_id.strip()
  candidates = [f'{stock_id}.TW', f'{stock_id}.TWO']
  df = pd.DataFrame()
  symbol = ''

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

  current_price, eps_str, pe_str, dividend_str, yield_str, payout_str = (
      'N/A',
      'N/A',
      'N/A',
      'N/A',
      'N/A',
      'N/A',
  )
  try:
    ticker = yf.Ticker(symbol)
    info = ticker.info
    price_val = (
        info.get('regularMarketPrice')
        or info.get('currentPrice')
        or df['Close'].iloc[-1]
    )
    if price_val:
      current_price = f'{price_val:.2f}'

    eps_val = info.get('trailingEps')
    if eps_val is not None:
      eps_str = f'{eps_val:.2f}'

    pe_val = info.get('trailingPE')
    if pe_val is not None:
      pe_str = f'{pe_val:.2f}'

    div_val = info.get('dividendRate') or info.get('lastDividendValue')
    if div_val is not None:
      dividend_str = f'{div_val:.2f}元'
    else:
      div_val = 0.0

    if div_val > 0 and price_val and price_val > 0:
      calc_yield = (div_val / price_val) * 100
      yield_str = f'{calc_yield:.2f}%'
    else:
      yield_str = 'N/A'

    if div_val > 0 and eps_val is not None and eps_val > 0:
      calc_payout = (div_val / eps_val) * 100
      payout_str = f'{calc_payout:.1f}%'
    else:
      payout_str = 'N/A'
  except:
    pass

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

  revenue_summary = get_real_monthly_revenue(stock_id)

  return {
      '代碼': stock_id,
      '名稱': stock_name,
      '現價': current_price,
      'EPS': eps_str,
      '本益比': pe_str,
      '配息': dividend_str,
      '殖利率': yield_str,
      '配息率': payout_str,
      'k': f'{latest_k:.2f} ({k_trend})',
      'd': f'{latest_d:.2f} ({d_trend})',
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
                - **💰 財務指標**: EPS: `{r['EPS']}` | 本益比: `{r['本益比']}` | 配息: `{r['配息']}` | 殖利率: `{r['殖利率']}` | 配息率: `{r['配息率']}`
                - **📊 技術指標**: K值: `{r['k']}` | D值: `{r['d']}` | 狀態: **{r['技術訊號']}**
                - **📈 營收趨勢**: {r['近期營收摘要']}
                """
        )
        st.divider()
  else:
    st.warning('⚠️ 查無有效的股票資料，請檢查代碼是否正確。')
else:
  st.info(
      '👈 請點擊左側邊欄的 **「開始執行批量分析」** 按鈕來載入數據！'
  )
