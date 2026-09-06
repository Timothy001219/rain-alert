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
            with st.spinner("AI 正在努力辨識圖片內容..."):
                try:
                    response = ai_client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=[
                            image,
                            "請幫我分析這張門牌或信件照片，提取出「姓名」與「地址」（包含路名與號碼）。"
                            "請嚴格使用以下 JSON 格式回傳，不要有其他 markdown 標籤或廢話："
                            '{"name": "辨識到的姓名或空字串", "address": "辨識到的完整地址或空字串"}'
                        ]
                    )
                    res_text = response.text.strip()
                    if res_text.startswith("```json"):
                        res_text = res_text[7:]
                    if res_text.endswith("
