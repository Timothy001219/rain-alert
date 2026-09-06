from datetime import datetime
import io
import json
import re
from PIL import Image
import streamlit as st
from supabase import create_client, Client
from google import genai

# 從 Streamlit 雲端的安全設定中讀取憑證
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]

# 初始化 Supabase 與 Gemini 客戶端
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
ai_client = genai.Client(api_key=GEMINI_API_KEY)

st.title("雲端版地址姓名記錄系統")

menu = ["現場拍照登錄", "歷史記錄查詢"]
choice = st.sidebar.selectbox("功能選單", menu)

# 定義區段與路名的對應字典
district_roads = {
    "8區": ["中正路二段", "民族路"],
    "13區": ["彰新路一段", "彰和路一段", "水源路", "金馬路二段", "金馬路三段", "孝德街"],
    "48區": ["彰南路三段", "彰南路五段", "田中路", "河濱路"]
}

# 初始化 Session State 用於 AI 自動帶入
if "ai_name" not in st.session_state:
    st.session_state["ai_name"] = ""
if "ai_lane" not in st.session_state:
    st.session_state["ai_lane"] = ""

if choice == "現場拍照登錄":
    st.subheader("手機拍照與雲端建檔")
    
    camera_file = st.file_uploader("拍攝或上傳門牌、信件照片", type=["jpg", "png", "jpeg"])
    
    if camera_file is not None:
        image = Image.open(camera_file)
        st.image(image, caption="現場拍攝照片", use_container_width=True)
        
        # 🤖 AI 智慧辨識按鈕
        if st.button("✨ 使用 AI 自動辨識圖片中的文字"):
            with st.spinner("AI 正在努力辨識圖片內容（若遇伺服器忙碌將自動切換）..."):
                prompt_text = '請幫我分析這張門牌或信件照片，提取出「姓名」與「地址」（包含路名與號碼）。請嚴格使用以下 JSON 格式回傳，不要有其他 markdown 標籤或廢話：{"name": "辨識到的姓名或空字串", "address": "辨識到的完整地址或空字串"}'
                
                models_to_try = ['gemini-3.6-flash', 'gemini-1.5-flash']
                success = False
                res_text = ""
                
                for model_name in models_to_try:
                    try:
                        response = ai_client.models.generate_content(
                            model=model_name,
                            contents=[image, prompt_text]
                        )
                        res_text = response.text.strip()
                        success = True
                        break
                    except Exception as e:
                        continue # 如果這個模型忙線，自動嘗試下一個
                
                if success:
                    try:
                        if res_text.startswith("```json"):
                            res_text = res_text[7:]
                        if res_text.endswith("```"):
                            res_text = res_text[:-3]
                            
                        data_parsed = json.loads(res_text.strip())
                        st.session_state["ai_name"] = data_parsed.get("name", "")
                        ai_full_address = data_parsed.get("address", "")
                        st.session_state["ai_lane"] = ai_full_address
                        
                        st.success(f"AI 辨識成功！辨識結果 -> 姓名: {st.session_state['ai_name']} | 地址: {ai_full_address}")
                    except Exception as parse_err:
                        st.error(f"解析 AI 回傳格式失敗: {parse_err}")
                else:
                    st.error("目前 AI 伺服器流量較大（503 忙碌中），請稍候 3 至 5 秒後再點一次按鈕即可！")
        
        name = st.text_input("輸入姓名", value=st.session_state["ai_name"])
        selected_district = st.selectbox("選擇區段", ["請選擇區段"] + list(district_roads.keys()))
        
        if selected_district != "請選擇區段":
            available_roads = district_roads[selected_district]
            selected_road = st.selectbox("選擇路名", ["請選擇路名"] + available_roads)
        else:
            selected_road = st.selectbox("選擇路名", ["請先選擇區段"])
            
        lane_num = st.text_input("輸入巷/弄/號 (例如: 123號 3樓)", value=st.session_state["ai_lane"])
        
        if selected_district != "請選擇區段" and selected_road != "請選擇路名":
            address = selected_road + lane_num
        else:
            address = lane_num
            
        status = st.selectbox("狀態分類", ["無此人", "遷移"])
        
        if st.button("確認並上傳至雲端"):
            if name and selected_district != "請選擇區段" and selected_road != "請選擇路名":
                file_name = f"img_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                
                buf = io.BytesIO()
                image.save(buf, format="JPEG")
                byte_im = buf.getvalue()
                
                # 上傳圖片至 Supabase Storage
                supabase.storage.from_("photos").upload(file_name, byte_im, {"content-type": "image/jpeg"})
                img_url = supabase.storage.from_("photos").get_public_url(file_name)
                
                # 寫入 Supabase 資料表 records
                data = {
                    "name": name,
                    "address": address,
                    "status": status,
                    "image_url": img_url,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                supabase.table("records").insert(data).execute()
                
                st.success("成功上傳並儲存至雲端資料庫！")
            else:
                st.error("請填寫姓名並完整選擇區段與路名。")

elif choice == "歷史記錄查詢":
    st.subheader("雲端智慧比對查詢")
    
    search_type = st.radio("查詢方式", ["依區段與路名篩選", "自由輸入關鍵字"])
    
    keyword = ""
    if search_type == "依區段與路名篩選":
        search_dist = st.selectbox("選擇要查詢的區段", list(district_roads.keys()))
        search_road = st.selectbox("選擇要查詢的路名", district_roads[search_dist])
        keyword = search_road
    else:
        keyword = st.text_input("輸入要搜尋的姓名或地址關鍵字")
    
    response = supabase.table("records").select("*").execute()
    results = response.data
    
    if keyword:
        results = [r for r in results if keyword in r.get('name', '') or keyword in r.get('address', '')]
        
    if results:
        # 依地址數字大小進行智慧排序（1 -> 15 -> 105）
        def address_sort_key(row):
            addr = row.get('address', '')
            numbers = re.findall(r'\d+', addr)
            return [int(n) for n in numbers] if numbers else [0]

        results.sort(key=address_sort_key)
        
        st.warning(f"找到 {len(results)} 筆雲端紀錄（已依地址數字由小到大排序）！")
        
        for i, row in enumerate(results):
            record_id = row.get('id')
            st.markdown(f"### 👤 姓名: {row['name']}")
            st.write(f"**地址:** {row['address']} | **狀態:** {row['status']} | **時間:** {row['timestamp']}")
            
            if row.get('image_url'):
                st.image(row['image_url'], width=200, caption="雲端存檔照片")
                with st.expander("🔍 點擊展開看清晰大圖", expanded=False):
                    st.image(row['image_url'], width=450, caption="完整大圖檢視")
            
            # 刪除按鈕
            if st.button(f"🗑️ 刪除這筆紀錄 ({row['name']} - {row['address']})", key=f"del_{i}_{record_id}"):
                img_url = row.get('image_url', '')
                if img_url:
                    try:
                        file_name = img_url.split('/')[-1]
                        supabase.storage.from_("photos").remove([file_name])
                    except Exception as e:
                        pass
                
                target_id = int(record_id)
                supabase.table("records").delete().eq("id", target_id).execute()
                
                st.toast(f"已成功刪除 {row['name']} 的紀錄！", icon="✅")
                st.rerun()
            
            st.markdown("---")
    else:
        st.info("查無相關歷史紀錄。")
