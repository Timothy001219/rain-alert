from datetime import datetime, timedelta
import os
import sys
from threading import Thread
import pandas as pd
import requests
import urllib3
from flask import Flask, render_template_string, request

# 匯入你的氣象輪詢主程式
import rain

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)


# --- 股市分析相關函式 ---
def get_real_monthly_revenue(stock_id):
  """取得單月營收與 YoY"""
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
      'id': stock_id,
      'name': stock_name,
      'price': current_price,
      'eps': eps_str,
      'pe': pe_str,
      'dividend': dividend_str,
      'yield': yield_str,
      'payout': payout_str,
      'k': f'{latest_k:.2f} ({k_trend})',
      'd': f'{latest_d:.2f} ({d_trend})',
      'signal': signal,
      'revenue': revenue_summary,
  }


# --- 網頁介面模板 ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <title>氣象監控與台股分析儀表板</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="bg-light">
    <div class="container py-5">
        <h2 class="mb-2 text-center">🌦️ 氣象監控背景運行中</h2>
        <p class="text-center text-muted mb-4">Status: Weather Monitor is Running! | 同步提供台股財報與技術面快篩</p>
        
        <div class="card shadow-sm mb-4">
            <div class="card-body">
                <form method="POST">
                    <div class="mb-3">
                        <label for="stocks" class="form-label">輸入台股清單 (代碼 名稱，每行一檔)：</label>
                        <textarea class="form-control" id="stocks" name="stocks" rows="4">{{ stock_input }}</textarea>
                    </div>
                    <button type="submit" class="btn btn-primary">🚀 開始執行股市分析</button>
                </form>
            </div>
        </div>

        {% if results %}
            <h4 class="mb-3">📊 分析結果</h4>
            <div class="list-group">
                {% for r in results %}
                    <div class="list-group-item list-group-item-action mb-3 shadow-sm rounded">
                        <div class="d-flex w-100 justify-content-between">
                            <h5 class="mb-1 text-primary">{{ r.id }} {{ r.name }}</h5>
                            <small class="text-muted">現價: <strong>{{ r.price }}</strong></small>
                        </div>
                        <p class="mb-1">
                            💰 <strong>EPS:</strong> {{ r.eps }} | 
                            <strong>本益比:</strong> {{ r.pe }} | 
                            <strong>配息:</strong> {{ r.dividend }} | 
                            <strong>殖利率:</strong> <span class="text-success">{{ r.yield }}</span> | 
                            <strong>配息率:</strong> {{ r.payout }}
                        </p>
                        <p class="mb-1">
                            📊 <strong>K值:</strong> {{ r.k }} | 
                            <strong>D值:</strong> {{ r.d }} | 
                            <strong>狀態:</strong> <strong>{{ r.signal }}</strong>
                        </p>
                        <small class="text-secondary">📈 營收: {{ r.revenue }}</small>
                    </div>
                {% endfor %}
            </div>
        {% endif %}
    </div>
</body>
</html>
"""


@app.route('/', methods=['GET', 'POST'])
def home():
  results = []
  stock_input = '2330 台積電\n2317 鴻海\n2412 中華電\n5287 數字\n8422 可寧衛'

  if request.method == 'POST':
    stock_input = request.form.get('stocks', '')
    lines = stock_input.strip().split('\n')
    for line in lines:
      parts = line.replace(',', ' ').split()
      if len(parts) >= 2:
        res = analyze_stock(parts[0], parts[1])
        if res:
          results.append(res)
      elif len(parts) == 1:
        res = analyze_stock(parts[0], f'股票{parts[0]}')
        if res:
          results.append(res)

  return render_template_string(
      HTML_TEMPLATE, results=results, stock_input=stock_input
  )


def run_web():
  app.run(host='0.0.0.0', port=8080)


if __name__ == '__main__':
  # 1. 在背景啟動 Flask Web 服務 (維持雲端主機連線，並提供股市查詢網頁)
  t = Thread(target=run_web)
  t.start()

  # 2. 執行原本的天氣輪詢監控程式
  rain.main()
