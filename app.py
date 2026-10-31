import json
import os
import re
import threading  # 💡 引入多執行緒
import http.server
import socketserver
from datetime import datetime
import discord
from discord import app_commands  
from discord.ext import tasks
from pypinyin import pinyin, Style

# ==============================================================================
# 0. 關鍵突破：在背景開一個假的網頁埠，徹底騙過 Render 的 Port 掃描
# ==============================================================================
def run_dummy_server():
    # Render 會自動提供一個變數叫 PORT，如果沒有就預設使用 10000
    port = int(os.environ.get("PORT", 10000))
    handler = http.server.SimpleHTTPRequestHandler
    # 允許地址快速重複使用，避免重啟時卡住
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", port), handler) as httpd:
        print(f"🌍 成功建立假的網頁伺服器，監聽埠：{port}")
        httpd.serve_forever()

# 讓網頁伺服器在背景偷偷跑，不卡住底下 Discord 機器人的執行
threading.Thread(target=run_dummy_server, daemon=True).start()

# ==============================================================================
# 1. 設定與大老闆排程專區
# ==============================================================================
TOKEN = os.environ.get("DISCORD_TOKEN")  

MY_SCHEDULED_TONES = {
    "2026-10-30": "242",  
    "2026-10-31": "242",  
    "2026-11-01": "124",    
    "2026-11-02": "311",   
}

STATS_FILE = "user_leaderboard.json"

intents = discord.Intents.default()
intents.message_content = True  
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

TARGET_CHANNEL_ID = None  

# ==============================================================================
# 2. 核心技術與資料庫讀寫
# ==============================================================================
def convert_chinese_to_tone_code(text):
    clean_text = "".join(re.findall(r"[\u4e00-\u9fa5]", text))
    pinyin_list = pinyin(clean_text, style=Style.TONE3, neutral_tone_with_five=True)
    tone_code = ""
    for item in pinyin_list:
        match = re.search(r"\d$", item)
        tone_code += match.group() if match else "5"
    return tone_code

def load_stats():
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_stats(data):
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# ==============================================================================
# 3. 每日 00:00 聲調笑話警報器
# ==============================================================================
@tasks.loop(hours=1)
async def midnight_alarm():
    global TARGET_CHANNEL_ID
    if TARGET_CHANNEL_ID is None:
        return

    now = datetime.now()
    if now.hour == 0:
        channel = client.get_channel(TARGET_CHANNEL_ID)
        if not channel:
            return
        today_str = now.strftime("%Y-%m-%d")
        if today_str in MY_SCHEDULED_TONES:
            target_tone = MY_SCHEDULED_TONES[today_str]
            embed = discord.Embed(
                title="🚨 每日聲調造句挑戰警報！",
                description=f"全新的一天開始了！今天的目標聲調密碼是：\n\n➡️ **【 {target_tone} 】**\n\n請直接在此頻道打字挑戰！",
                color=0x27ae60
            )
            await channel.send(embed=embed)

# ==============================================================================
# 4. 斜線指令專區：/listen 與 /unlisten
# ==============================================================================
@tree.command(name="listen", description="開始在此文字頻道偵測每日聲調笑話")
async def start_listening(interaction: discord.Interaction):
    global TARGET_CHANNEL_ID
    current_channel_id = interaction.channel_id
    
    if TARGET_CHANNEL_ID == current_channel_id:
        await interaction.response.send_message("📢 機器人已經在這個頻道導入並偵測中囉！")
    else:
        TARGET_CHANNEL_ID = current_channel_id
        await interaction.response.send_message("✅ 成功導入頻道！機器人已鎖定此頻道進行聲調偵測與每日 00:00 警報！")

@tree.command(name="unlisten", description="停止此文字頻道的聲調偵測功能")
async def stop_listening(interaction: discord.Interaction):
    global TARGET_CHANNEL_ID
    if TARGET_CHANNEL_ID is None:
        await interaction.response.send_message("📴 機器人目前本來就沒有在任何頻道進行偵測。")
    else:
        TARGET_CHANNEL_ID = None
        await interaction.response.send_message("❌ 機器人已取消頻道導入！現在在任何頻道打字挑戰都不會觸發統計。")

# ==============================================================================
# 5. 監聽頻道訊息：造句捕獲
# ==============================================================================
@client.event
async def on_message(message):
    if message.author.bot:
        return

    if TARGET_CHANNEL_ID is None or message.channel.id != TARGET_CHANNEL_ID:
        return

    user_sentence = message.content.strip()
    if user_sentence.startswith("/") or user_sentence.startswith("!"):
        return

    today_str = datetime.now().strftime("%Y-%m-%d")
    if today_str not in MY_SCHEDULED_TONES:
        return

    target_tone = MY_SCHEDULED_TONES[today_str]
    user_tone = convert_chinese_to_tone_code(user_sentence)
    
    if len(user_tone) != len(target_tone) or len(user_tone) == 0:
        return

    if user_tone == target_tone:
        user_id = str(message.author.id)
        stats = load_stats()

        if user_id not in stats:
            stats[user_id] = {"name": message.author.name, "correct": 0}

        stats[user_id]["correct"] += 1
        save_stats(stats)
        
        times = stats[user_id]["correct"]
        await message.channel.send(f"⚠️ {message.author.mention} 你已經講了 {times} 次每日聲調笑話。")

# ==============================================================================
# 6. 機器人啟動程序
# ==============================================================================
@client.event
async def on_ready():
    print(f"🤖 機器人 {client.user.name} 已成功上線！")
    try:
        synced = await tree.sync()
        print(f"✨ 成功同步了 {len(synced)} 個斜線指令！")
    except Exception as e:
        print(f"❌ 同步斜線指令時發生錯誤: {e}")
        
    if not midnight_alarm.is_running():
        midnight_alarm.start()

client.run(TOKEN)
