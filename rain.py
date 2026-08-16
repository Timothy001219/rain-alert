from datetime import datetime
import os
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 從 GitHub Secrets 讀取 (不需要 config.txt)
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

def main():
    if not CWA_API_KEY:
        print("❌ 錯誤: 未設定 CWA_API_KEY")
        return

    url = f'https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0002-001?Authorization={CWA_API_KEY}'
    
    try:
        response = requests.get(url, verify=False, timeout=15)
        if response.status_code == 200:
            data = response.json()
            stations = data['records']['Station']
            current_time = datetime.now().strftime('%H:%M:%S')
            raining_stations = []

            for st in stations:
                town = st['GeoInfo'].get('TownName', '')
                if town in TARGET_TOWNS:
                    st_name = st['StationName']
                    # 讀取正確的 RainfallElement 路徑
                    rainfall_elem = st.get('RainfallElement', {})
                    raw_rain = rainfall_elem.get('Now', {}).get('Precipitation', 0.0)

                    try:
                        precipitation = float(raw_rain)
                    except (ValueError, TypeError):
                        precipitation = 0.0

                    if precipitation > 0:
                        raining_stations.append({'town': town, 'name': st_name, 'rain': precipitation})

            if raining_stations:
                msg_lines = ['🚨 **【鄰近區域降雨警報】**']
                for s in raining_stations:
                    msg_lines.append(f'• **{s["town"]}** ({s["name"]}) 即時雨量：**{s["rain"]} mm**')
                msg_lines.append('請注意出門安全！')
                send_discord_message('\n'.join(msg_lines))
                print('📲 已發送通知')
            else:
                print('☀️ 目前皆無降雨')
        else:
            print(f'⚠️ API 狀態碼錯誤: {response.status_code}')
    except Exception as e:
        print(f'⚠️ 發生錯誤: {e}')

if __name__ == '__main__':
    main()
