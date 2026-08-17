from datetime import datetime
import os
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CWA_API_KEY = os.environ.get('CWA_API_KEY')
DISCORD_WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL')

TARGET_TOWNS = ['鹿港鎮', '福興鄉', '和美鎮']


def send_discord_message(message):
  if not DISCORD_WEBHOOK_URL:
    return
  payload = {'content': message}
  try:
    requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5)
  except Exception as e:
    print(f'❌ Discord 發送錯誤: {e}')


def check_rain_stations(api_key):
  """檢查地面雨量站即時雨量"""
  url = f'https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0002-001?Authorization={api_key}'
  raining_stations = []

  try:
    response = requests.get(url, verify=False, timeout=15)
    if response.status_code == 200:
      data = response.json()
      stations = data['records']['Station']

      for st in stations:
        town = st['GeoInfo'].get('TownName', '')
        if town in TARGET_TOWNS:
          st_name = st['StationName']
          rainfall_elem = st.get('RainfallElement', {})
          raw_rain = rainfall_elem.get('Now', {}).get('Precipitation', 0.0)

          try:
            precipitation = float(raw_rain)
          except (ValueError, TypeError):
            precipitation = 0.0

          if precipitation > 0:
            raining_stations.append({
                'town': town,
                'name': st_name,
                'rain': precipitation,
            })
  except Exception as e:
    print(f'⚠️ 雨量站查詢錯誤: {e}')

  return raining_stations


def check_weather_warnings(api_key):
  """檢查氣象署即時大雷雨/豪大雨特報 (相當於雷達對流警戒)"""
  # 使用氣象署 W-C0033-001 豪雨特報 / 劇烈天氣資訊
  url = f'https://opendata.cwa.gov.tw/api/v1/rest/datastore/W-C0033-001?Authorization={api_key}'
  warnings = []

  try:
    response = requests.get(url, verify=False, timeout=15)
    if response.status_code == 200:
      data = response.json()
      hazards = (
          data.get('records', {})
          .get('SpecialPhenomena', {})
          .get('Hazards', [])
      )
      for hazard in hazards:
        info = hazard.get('Info', {})
        phenomena = info.get('Phenomena', '')  # 例如大雷雨、豪雨
        significance = info.get('Significance', '')

        # 檢查影響區域是否包含彰化縣
        for location in hazard.get('Location', []):
          loc_name = location.get('LocationName', '')
          if '彰化縣' in loc_name:
            warnings.append(f'⚠️ **氣象署發布【{phenomena}】警報** (影響範圍包含彰化縣)')
  except Exception as e:
    print(f'⚠️ 天氣特報查詢錯誤: {e}')

  return warnings


def main():
  if not CWA_API_KEY:
    print('❌ 錯誤: 未設定 CWA_API_KEY')
    return

  current_time = datetime.now().strftime('%H:%M:%S')
  print(f'[{current_time}] 正在執行全面天氣與雨量掃描...')

  # 1. 檢查雨量站
  raining_stations = check_rain_stations(CWA_API_KEY)

  # 2. 檢查大雷雨/豪雨特報 (對流雷達警戒)
  weather_warnings = check_weather_warnings(CWA_API_KEY)

  # 彙整發送訊息
  msg_lines = []

  if weather_warnings:
    msg_lines.extend(weather_warnings)

  if raining_stations:
    msg_lines.append('🚨 **【區域即時降雨回報】**')
    for s in raining_stations:
      msg_lines.append(
          f'• **{s["town"]}** ({s["name"]}) 即時雨量：**{s["rain"]} mm**'
      )

  if msg_lines:
    msg_lines.append('請注意天氣變化與出門安全！')
    send_discord_message('\n'.join(msg_lines))
    print('📲 已發送警報通知到 Discord')
  else:
    print('☀️ 監控區域目前無降雨且無大雷雨特報')


if __name__ == '__main__':
  main()
