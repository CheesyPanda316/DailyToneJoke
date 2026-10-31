import json
import os
import re
from datetime import datetime
import discord
from discord.ext import commands, tasks
from pypinyin import pinyin, Style
from flask import Flask # 💡 引入最輕量、不卡死非同步核心的網頁套件

# ==============================================================================
# 0. 關鍵防禦：使用 Flask 在背景提供流暢不卡死的網頁埠，徹底騙過 Render
# ==============================================================================
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive!"

def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    # 關閉除錯模式，以最省資源、不干擾 Discord 的方式在背景靈敏執行
    app.run(host='0.0.0.0', port=port)

import threading
threading.Thread(target=run_dummy_server, daemon=True).start()

# ==============================================================================
# 1. 設定與大老闆排程專區
# ==============================================================================
TOKEN = os.environ.get("DISCORD_TOKEN")  

MY_SCHEDULED_TONES = {
    "2026-10-30": "242",  # 徹底防禦海外伺服器時差
    "2026-10-31": "242",  # 今日密碼：242
    "2026-11-01": "124",    
    "2026-11-02": "311",   
}

STATS_FILE = "user_leaderboard.json"

intents = discord.Intents.default()
intents.message_content = True  

# 💡 換回專門處理訊息監聽的 commands.Bot 核心
bot = commands.Bot(command_prefix="!", intents=intents)

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
        channel = bot.get_channel(TARGET_CHANNEL_ID)
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
# 4. 斜線指令專區：/listen 與 /unlisten（完美相容架構）
# ==============================================================================
@bot.tree.command(name="listen", description="開始在此文字頻道偵測每日聲調笑話")
async def start_listening(interaction: discord.Interaction):
    global TARGET_CHANNEL_ID
    TARGET_CHANNEL_ID = interaction.channel_id
    await interaction.response.send_message("✅ 成功導入頻道！機器人已鎖定此頻道進行聲調偵測與每日 00:00 警報！")

@bot.tree.command(name="unlisten", description="停止此文字頻道的聲調偵測功能")
async def stop_listening(interaction: discord.Interaction):
    global TARGET_CHANNEL_ID
    TARGET_CHANNEL_ID = None
    await interaction.response.send_message("❌ 機器人已取消頻道導入！")

# ==============================================================================
# 5. 監聽頻道訊息：雙軌並行，完全解放耳朵
# ==============================================================================
@bot.event
async def on_message(message):
    try:
        if message.author.bot:
            return

        # 避免與常規指令衝突
        await bot.process_commands(message)

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
    except Exception as e:
        print(f"❌ 錯誤攔截: {e}")

# ==============================================================================
# 6. 機器人啟動程序
# ==============================================================================
@bot.event
async def on_ready():
    print(f"🤖 機器人 {bot.user.name} 已成功滿血上線！")
    try:
        synced = await bot.tree.sync()
        print(f"✨ 成功同步了 {len(synced)} 個斜線指令！")
    except Exception as e:
        print(f"❌ 同步斜線指令錯誤: {e}")
        
    if not midnight_alarm.is_running():
        midnight_alarm.start()

bot.run(TOKEN)
