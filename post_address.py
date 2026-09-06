from datetime import datetime
import io
import re
from PIL import Image
import streamlit as st
from supabase import create_client, Client

# 從 Streamlit 雲端的安全設定中讀取 Supabase 憑證
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

st.title("雲端版地址姓名記錄系統")

menu = ["現場拍照登錄", "歷史記錄查詢"]
choice = st.sidebar.selectbox("功能選單", menu)

# 定義區段與路名的對應字典
district_roads = {
    "8區": ["中正路二段", "民族路"],
    "13區": ["彰新路一段", "彰和路一段", "水源路", "金馬路二段", "金馬路三段", "孝德街"],
    "48區": ["彰南路三段", "彰南路五段", "田中路", "河濱路"]
}

if choice == "現場拍照登錄":
    st.subheader("手機拍照與雲端建檔")
    
    camera_file = st.file_uploader("拍攝或上傳門牌、信件照片", type=["jpg", "png", "jpeg"])
    
    if camera_file is not None:
        image = Image.open(camera_file)
        st.image(image, caption="現場拍攝照片", use_container_width=True)
        
        name = st.text_input("輸入姓名")
        selected_district = st.selectbox("選擇區段", ["請選擇區段"] + list(district_roads.keys()))
        
        if selected_district != "請選擇區段":
            available_roads = district_roads[selected_district]
            selected_road = st.selectbox("選擇路名", ["請選擇路名"] + available_roads)
        else:
            selected_road = st.selectbox("選擇路名", ["請先選擇區段"])
            
        lane_num = st.text_input("輸入巷/弄/號 (例如: 123號 3樓)")
        
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
    
    if search_type == "依區段與路名篩選":
        search_dist = st.selectbox("選擇要查詢的區段", list(district_roads.keys()))
        search_road = st.selectbox("選擇要查詢的路名", district_roads[search_dist])
        keyword = search_road
    else:
        keyword = st.text_input("輸入要搜尋的姓名或地址關鍵字")
    
    if st.button("開始查詢"):
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
            
            # 使用 enumerate 產生絕對不會重複的編號 i
            for i, row in enumerate(results):
                record_id = row.get('id')
                st.markdown(f"### 👤 姓名: {row['name']}")
                st.write(f"**地址:** {row['address']} | **狀態:** {row['status']} | **時間:** {row['timestamp']} | **ID:** {record_id}")
                
                if row.get('image_url'):
                    st.image(row['image_url'], width=200, caption="雲端存檔照片")
                    with st.expander("🔍 點擊展開看清晰大圖", expanded=False):
                        st.image(row['image_url'], width=450, caption="完整大圖檢視")
                
                # 結合編號 i 與 record_id，確保 key 絕對唯一，並加入型態轉型與除錯顯示
                if st.button(f"🗑️ 刪除這筆紀錄 ({row['name']} - {row['address']})", key=f"del_{i}_{record_id}"):
                    img_url = row.get('image_url', '')
                    if img_url:
                        try:
                            file_name = img_url.split('/')[-1]
                            supabase.storage.from_("photos").remove([file_name])
                        except Exception as e:
                            pass
                    
                    # 強制將 record_id 轉為整數 int，確保與資料庫 int8 欄位完美匹配
                    target_id = int(record_id)
                    res = supabase.table("records").delete().eq("id", target_id).execute()
                    
                    # 顯示刪除後的回應結果用來確認
                    st.write("刪除回應結果：", res)
                    
                    st.success(f"已成功刪除 {row['name']} 的紀錄！")
                    st.rerun()
                
                st.markdown("---")
        else:
            st.info("查無相關歷史紀錄。")
