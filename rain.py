from datetime import datetime, timezone
import json
import os
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CWA_API_KEY = os.environ.get('CWA_API_KEY')
DISCORD_WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL')

TARGET_TOWNS = ['鹿港鎮', '福興鄉', '和美鎮']
CACHE_FILE = 'last_alert.json'


def load_last_alert():
    """讀取上一次發送的紀錄"""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('content', '')
        except Exception as e:
            print(f'⚠️ 讀取紀錄檔失敗: {e}')
    return ''


def save_last_alert(content):
    """更新上一次發送的紀錄"""
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump({'content': content}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f'⚠️ 寫入紀錄檔失敗: {e}')


def send_discord_message(title, description, color=0x3498DB):
    if not DISCORD_WEBHOOK_URL:
        print('⚠️ 未設定 DISCORD_WEBHOOK_URL，跳過發送 Discord 訊息')
        return

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
            print('📲 [Discord 訊息已成功發送]')
        else:
            print(f'❌ Discord 發送失敗，狀態碼: {response.status_code}')
    except Exception as e:
        print(f'❌ Discord 發送錯誤: {e}')


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
                    rainfall_elem = st.get('RainfallElement', {})
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
                            ' (影響範圍包含彰化縣)'
                        )
    except Exception as e:
        print(f'⚠️ 天氣特報查詢錯誤: {e}')

    return list(warnings)


def main():
    if not CWA_API_KEY:
        print('❌ 錯誤: 未設定 CWA_API_KEY')
        return

    current_time = datetime.now().strftime('%H:%M:%S')
    print(f'[{current_time}] 正在執行全面天氣與雨量掃描...')

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

    # 無降雨且無特報
    if not msg_lines:
        print('☀️ 監控區域目前無降雨且無大雷雨特報')
        if load_last_alert() != '':
            save_last_alert('')
            print('🔄 已重置天氣狀態紀錄（目前為晴朗/無雨）')
        return

    current_alert_content = '\n'.join(msg_lines)
    last_alert_content = load_last_alert()

    # 比對本次與上次是否相同
    if current_alert_content == last_alert_content:
        print('⏭️ 天氣狀況與上一次通知相同，跳過發送 Discord 訊息')
        return

    # 發送訊息並更新紀錄
    msg_lines.append('\n請注意天氣變化與出門安全！')
    embed_color = 0xE74C3C if weather_warnings else 0x3498DB

    send_discord_message(
        title='☔ 區域即時天氣警報通知',
        description='\n'.join(msg_lines),
        color=embed_color,
    )

    save_last_alert(current_alert_content)
    print('📲 已發送警報通知到 Discord，並已更新本地紀錄檔')


if __name__ == '__main__':
    main()
