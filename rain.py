from datetime import datetime
import math
import os
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 從 GitHub Secrets 讀取機密資料（避免把密碼公開）
CWA_API_KEY = os.environ.get('CWA_API_KEY')
DISCORD_WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL')

TARGET_COUNTY = '彰化縣'
TARGET_TOWN = '鹿港鎮'


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

      target_lat = 24.058
      target_lon = 120.435

      closest_station = None
      min_distance = float('inf')

      for st in stations:
        county = st['GeoInfo']['CountyName']
        if county == TARGET_COUNTY:
          lat = float(st['GeoInfo']['Coordinates'][1]['StationLatitude'])
          lon = float(st['GeoInfo']['Coordinates'][0]['StationLongitude'])
          dist = math.sqrt((lat - target_lat) ** 2 + (lon - target_lon) ** 2)
          if dist < min_distance:
            min_distance = dist
            closest_station = st

      if closest_station:
        precipitation = float(
            closest_station['WeatherElement']['Now']['Precipitation']
        )
        current_time = datetime.now().strftime('%H:%M:%S')
        print(
            f'[{current_time}] 即時雨量: {precipitation} mm'
        )

        # 如果雨量大於 0，發送 Discord 通知
        if precipitation > 0:
          msg = (
              f'🚨 **【降雨警報】**\n'
              f'**{TARGET_COUNTY}{TARGET_TOWN}** 測站觀測到降雨！\n'
              f'即時雨量：**{precipitation} mm**\n'
              f'請注意出門安全！'
          )
          send_discord_message(msg)
  except Exception as e:
    print(f'⚠️ 查詢發生錯誤: {e}')


if __name__ == '__main__':
  main()
