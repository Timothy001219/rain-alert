from datetime import datetime
import math
import os
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 從 GitHub Secrets 讀取機密資料
CWA_API_KEY = os.environ.get('CWA_API_KEY')
DISCORD_WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL')

# 🎯 設定你要監控的多個鄉鎮清單
TARGET_TOWNS = ['鹿港鎮', '福興鄉', '和美鎮']


def send_discord_message(message):
  if not DISCORD_WEBHOOK_URL:
    return
  payload = {'content': message}
  try:
    requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5)
  except Exception as e:
    print(f'❌ Discord 發送錯誤: {e}')


def main():
  url = f'https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0001-001?Authorization={CWA_API_KEY}'
  try:
    response = requests.get(url, verify=False, timeout=10)
    if response.status_code == 200:
      data = response.json()
      stations = data['records']['Station']

      current_time = datetime.now().strftime('%H:%M:%S')
      raining_stations = []

      # 檢查所有測站
      for st in stations:
        town = st['GeoInfo'].get('TownName', '')

        # 如果該測站的鄉鎮名稱在我們的目標清單內
        if town in TARGET_TOWNS:
          st_name = st['StationName']
          raw_rain = st['WeatherElement']['Now']['Precipitation']

          try:
            precipitation = float(raw_rain)
          except (ValueError, TypeError):
            precipitation = 0.0

          print(f'[{current_time}] 測站 ({town} - {st_name}) 雨量: {precipitation} mm')

          # 如果該測站有雨
          if precipitation > 0:
            raining_stations.append({
                'town': town,
                'name': st_name,
                'rain': precipitation,
            })

      # 如果清單中有任何一個測站正在下雨，就發送 Discord 通知
      if raining_stations:
        msg_lines = ['🚨 **【鄰近區域降雨警報】**']
        for s in raining_stations:
          msg_lines.append(
              f'• **{s["town"]}** ({s["name"]}) 即時雨量：**{s["rain"]} mm**'
          )
        msg_lines.append('請注意出門安全！')

        full_msg = '\n'.join(msg_lines)
        send_discord_message(full_msg)
        print('📲 已發送多測站降雨通知到 Discord')
      else:
        print('☀️ 監控區域目前皆無降雨')

    else:
      print('⚠️ 無法取得氣象站資料')
  except Exception as e:
    print(f'⚠️ 查詢發生錯誤: {e}')


if __name__ == '__main__':
  main()
