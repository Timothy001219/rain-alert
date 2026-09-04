from datetime import datetime
import json
import os
import time

# 匯入主程式的分析函式與預設清單
from main import DEFAULT_STOCKS_TEXT, analyze_stock, normalize_stock_id


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

    print(
        f"開始手動執行分析 {len(stock_list)} 檔股票資料（已加入安全緩衝）..."
    )
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

        # ⏳ 每次請求之間暫停 0.6 秒，避免瞬間流量過大被 FinMind 擋 402
        time.sleep(0.6)

    cache_payload = {
        "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "results": results,
    }

    with open("daily_cache.json", "w", encoding="utf-8") as f:
        json.dump(cache_payload, f, ensure_ascii=False, indent=4)
    print("✅ 快取更新完成，已儲存至 daily_cache.json")


if __name__ == "__main__":
    generate_cache()
