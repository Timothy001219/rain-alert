from datetime import datetime
import json
import os
import time

# 匯入你主程式裡的核心分析函式
from main import analyze_stock, DEFAULT_STOCKS_TEXT, normalize_stock_id

def generate_cache():
    lines = DEFAULT_STOCKS_TEXT.strip().splitlines()
    stock_list = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 2:
            s_id = normalize_stock_id(parts[0])
            s_name = parts[1]
            stock_list.append((s_id, s_name))

    results = []
    token = os.getenv("FINMIND_TOKEN", "").strip()

    print(f"開始背景更新 {len(stock_list)} 檔股票資料...")
    for idx, (s_id, s_name) in enumerate(stock_list):
        print(f"[{idx+1}/{len(stock_list)}] 處理 {s_id} {s_name}...")
        try:
            result, error = analyze_stock(s_id, s_name, token)
            if result is not None:
                results.append(result)
            else:
                print(f"  -> 失敗: {error}")
        except Exception as e:
            print(f"  -> 發生例外: {e}")
        time.sleep(0.5) # 避免對 API 請求過快

    cache_payload = {
        "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "results": results
    }

    with open("daily_cache.json", "w", encoding="utf-8") as f:
        json.dump(cache_payload, f, ensure_ascii=False, indent=4)
    print("✅ 每日快取更新完成，已儲存至 daily_cache.json")

if __name__ == "__main__":
    generate_cache()
