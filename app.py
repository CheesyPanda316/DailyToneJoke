import json
import os
import re
from datetime import datetime
import threading
import discord
from discord.ext import commands, tasks
from pypinyin import pinyin, Style
from flask import Flask
import pytz

# ==============================================================================
# 0. 背景流暢網頁埠
# ==============================================================================
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive!"

def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

threading.Thread(target=run_dummy_server, daemon=True).start()

# ==============================================================================
# 1. 核心宣告（強制全權限）
# ==============================================================================
TOKEN = os.environ.get("DISCORD_TOKEN")  

MY_SCHEDULED_TONES = {
    "2026-10-30": "242",
    "2026-10-31": "242",  # 今日密碼：242
    "2026-11-01": "124",    
    "2026-11-02": "311",   
}

STATS_FILE = "user_leaderboard.json"

# 強制開啟全部特權
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

TARGET_CHANNEL_ID = None  

# ==============================================================================
# 2. 輔助函式
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

    tz = pytz.timezone('Asia/Taipei')
    now = datetime.now(tz)
    
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
# 4. 斜線指令專區：/listen 與 /unlisten
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
# 5. 獨立常規訊息監聽：不綁定任何前置條件
# ==============================================================================
@bot.listen("on_message") # 💡 使用獨立事件監聽器，防止被常規事件核心卡死吞掉
async def handle_user_msg(message):
    try:
        # 排除自己的機器人
        if message.author.bot:
            return

        user_sentence = message.content.strip()
        # 排除指令字串
        if user_sentence.startswith("/") or user_sentence.startswith("!"):
            return

        # 🚨 【最底層防禦測試】只要能拿到字，立刻回覆！
        test_tone = convert_chinese_to_tone_code(user_sentence)
        await message.channel.send(
            f"📢 **【測試核心連通】**\n"
            f"• 聽到內容：`{user_sentence}`\n"
            f"• 解析聲調：`{test_tone}`"
        )

        # 檢查頻道鎖定
        if TARGET_CHANNEL_ID is None or message.channel.id != TARGET_CHANNEL_ID:
            return

        # 台北時間日期比對
        tz = pytz.timezone('Asia/Taipei')
        today_str = datetime.now(tz).strftime("%Y-%m-%d")
        
        if today_str not in MY_SCHEDULED_TONES:
            return

        target_tone = MY_SCHEDULED_TONES[today_str]

        if len(test_tone) != len(target_tone) or len(test_tone) == 0:
            return

        if test_tone == target_tone:
            user_id = str(message.author.id)
            stats = load_stats()

            if user_id not in stats:
                stats[user_id] = {"name": message.author.name, "correct": 0}

            stats[user_id]["correct"] += 1
            save_stats(stats)
            
            times = stats[user_id]["correct"]
            await message.channel.send(f"🎉 **成功觸發！** {message.author.mention} 你已經講了 {times} 次每日聲調笑話。")
    except Exception as e:
        print(f"❌ 錯誤攔截: {e}")

# ==============================================================================
# 6. 機器人啟動程序
# ==============================================================================
@bot.event
async def on_ready():
    print(f"🤖 機器人 {bot.user.name} 已成功滿血上線！")
    try:
        # 💡 非同步同步斜線指令，不阻塞監聽核心
        await bot.tree.sync()
        print("✨ 斜線指令同步完成！")
    except Exception as e:
        print(f"❌ 同步斜線指令錯誤: {e}")
        
    if not midnight_alarm.is_running():
        midnight_alarm.start()

bot.run(TOKEN)
