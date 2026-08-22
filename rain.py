from datetime import datetime, timezone
import json
import os
import time
import requests
import urllib3

# 關閉 SSL 不安全請求警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 從環境變數讀取 API Key 與 Webhook
CWA_API_KEY = os.environ.get('CWA_API_KEY')
DISCORD_WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL')

TARGET_TOWNS = ['鹿港鎮', '福興鄉', '和美鎮']
CACHE_FILE = 'last_alert.json'
CHECK_INTERVAL_SECONDS = 30  # 檢查間隔時間 (秒)


def load_last_alert():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('content', '')
        except Exception as e:
            print(f'⚠️ 讀取快取失敗: {e}')
    return ''


def save_last_alert(content):
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump({'content': content}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f'⚠️ 寫入快取失敗: {e}')


def send_discord_message(title, description, color=0x3498DB):
    if not DISCORD_WEBHOOK_URL:
        print('⚠️ 未設定 DISCORD_WEBHOOK_URL，跳過發送')
        return False

    payload = {
        'embeds': [{
            'title': title,
            'description': description,
            'color': color,
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }]
    }
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5)
        if response.status_code in [200, 204]:
            print('📲 [Discord 訊息發送成功]')
            return True
        else:
            print(f'❌ Discord 發送失敗，狀態碼: {response.status_code}')
            return False
    except Exception as e:
        print(f'❌ Discord 發送錯誤: {e}')
        return False


def parse_rainfall_value(val):
    try:
        num = float(val)
        return num if num >= 0 else 0.0
    except (ValueError, TypeError):
        return 0.0


def check_rain_stations(api_key):
    url = f'https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0002-001?Authorization={api_key}'
    raining_stations = []

    try:
        response = requests.get(url, verify=False, timeout=15)
        if response.status_code == 200:
            data = response.json()
            stations = data.get('records', {}).get('Station', [])

            for st in stations:
                town = st.get('GeoInfo', {}).get('TownName', '')
                if town in TARGET_TOWNS:
                    st_name = st.get('StationName', '未知測站')
                    rainfall_elem = st.get('WeatherElement', {}) or st.get(
                        'RainfallElement', {}
                    )
                    raw_rain = rainfall_elem.get('Now', {}).get(
                        'Precipitation', 0.0
                    )

                    precipitation = parse_rainfall_value(raw_rain)
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
    url = f'https://opendata.cwa.gov.tw/api/v1/rest/datastore/W-C0033-001?Authorization={api_key}'
    warnings = set()

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
                phenomena = info.get('Phenomena', '特別天氣現象')

                for location in hazard.get('Location', []):
                    loc_name = location.get('LocationName', '')
                    if '彰化縣' in loc_name:
                        warnings.add(
                            f'⚠️ **氣象署發布【{phenomena}】警報**'
                            ' (涵蓋彰化縣)'
                        )
    except Exception as e:
        print(f'⚠️ 天氣特報查詢錯誤: {e}')

    return list(warnings)


def run_check():
    if not CWA_API_KEY:
        print('❌ 錯誤: 未設定 CWA_API_KEY')
        return

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f'[{now_str}] 正在掃描天氣狀態...')

    raining_stations = check_rain_stations(CWA_API_KEY)
    weather_warnings = check_weather_warnings(CWA_API_KEY)

    msg_lines = []
    if weather_warnings:
        msg_lines.extend(weather_warnings)

    if raining_stations:
        if msg_lines:
            msg_lines.append('')
        msg_lines.append('🚨 **【區域即時降雨回報】**')
        for s in raining_stations:
            msg_lines.append(
                f'• **{s["town"]}** ({s["name"]}) 即時雨量：**{s["rain"]} mm**'
            )

    if not msg_lines:
        print('☀️ 目前無雨量且無大雷雨特報')
        if load_last_alert() != '':
            save_last_alert('')
            print('🔄 已重置天氣狀態紀錄')
        return

    current_alert_content = '\n'.join(msg_lines)
    last_alert_content = load_last_alert()

    if current_alert_content == last_alert_content:
        print('⏭️ 天氣狀況與上次相同，跳過發送')
        return

    full_msg = msg_lines + ['\n請注意天氣變化與出門安全！']
    embed_color = 0xE74C3C if weather_warnings else 0x3498DB

    success = send_discord_message(
        title='☔ 區域即時天氣警報通知',
        description='\n'.join(full_msg),
        color=embed_color,
    )

    if success:
        save_last_alert(current_alert_content)


def main():
    print(
        f'🚀 Render 背景監控服務已啟動！每 {CHECK_INTERVAL_SECONDS} 秒執行一次...'
    )
    while True:
        try:
            run_check()
        except Exception as e:
            print(f'❌ 執行過程發生例外錯誤: {e}')

        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == '__main__':
    main()
