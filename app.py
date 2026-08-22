from threading import Thread
from flask import Flask
import rain  # 匯入原本的輪詢主程式

app = Flask('')


@app.route('/')
def home():
    return 'Weather Monitor is Running!'


def run():
    app.run(host='0.0.0.0', port=8080)


# 在背景啟動 Flask Web 服務，同時執行天氣監控迴圈
if __name__ == '__main__':
    t = Thread(target=run)
    t.start()

    # 執行你原本的輪詢程式
    rain.main()
