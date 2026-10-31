import json
import os
import re
from datetime import datetime
import discord
from discord.ext import commands, tasks
from pypinyin import pinyin, Style

# ==============================================================================
# 1. 設定與大老闆排程專區
# ==============================================================================
# 請至 Discord Developer Portal 申請並貼上你的 Bot Token
TOKEN = "你的_DISCORD_BOT_TOKEN"  

# 請換成你要發布每日 00:00 警報的 Discord 頻道 ID (必須是純數字，不用加引號)
ANNOUNCE_CHANNEL_ID = 123456789012345678  

# 大老闆預排專區：每一天只給一串純 12345 組成的聲調亂碼字串
MY_SCHEDULED_TONES = {
    "2026-10-31": "242",  
    "2026-11-01": "124",    
    "2026-11-02": "311",   
    # 💡 依此類推，你可以在下方無限制地預先排定好幾個月的日期與聲調
}

STATS_FILE = "user_leaderboard.json"

# 初始化 Discord 機器人，並開啟讀取訊息內容的權限
intents = discord.Intents.default()
intents.message_content = True  
bot = commands.Bot(command_prefix="!", intents=intents)

# ==============================================================================
# 2. 核心技術：將使用者輸入的中文，自動轉為 12345 聲調字串
# ==============================================================================
def convert_chinese_to_tone_code(text):
    # 只保留中文字，過濾掉標點符號與空格
    clean_text = "".join(re.findall(r"[\u4e00-\u9fa5]", text))
    
    # 將中文字轉成帶有聲調數字的拼音 (輕聲標記為 5)
    pinyin_list = pinyin(clean_text, style=Style.TONE3, neutral_tone_with_five=True)
    
    tone_code = ""
    for item in pinyin_list:
        match = re.search(r"\d$", item)
        tone_code += match.group() if match else "5"
    return tone_code

# ==============================================================================
# 3. 資料庫讀寫：純統計成功次數
# ==============================================================================
def load_stats():
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_stats(data):
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# ==============================================================================
# 4. 每日 00:00 聲調笑話警報器排程 (每小時自動檢查一次是否跨日)
# ==============================================================================
@tasks.loop(hours=1)
async def midnight_alarm():
    now = datetime.now()
    # 當伺服器時間為半夜 00 點時觸發警報公告
    if now.hour == 0:
        channel = bot.get_channel(ANNOUNCE_CHANNEL_ID)
        if not channel:
            return
            
        today_str = now.strftime("%Y-%m-%d")
        if today_str in MY_SCHEDULED_TONES:
            target_tone = MY_SCHEDULED_TONES[today_str]
            embed = discord.Embed(
                title="🚨 每日聲調造句挑戰警報！",
                description=f"全新的一天開始了！今天的目標聲調密碼是：\n\n➡️ **【 {target_tone} 】**\n\n請直接在此頻道打字，創作出符合該聲調的句子來挑戰！",
                color=0x27ae60
            )
            await channel.send(embed=embed)

# ==============================================================================
# 5. 監聽頻道訊息：只統計成功次數，挑戰失敗默默忽略
# ==============================================================================
@bot.event
async def on_message(message):
    # 排除機器人自己的訊息
    if message.author.bot:
        return

    today_str = datetime.now().strftime("%Y-%m-%d")
    if today_str not in MY_SCHEDULED_TONES:
        return

    target_tone = MY_SCHEDULED_TONES[today_str]
    user_sentence = message.content.strip()
    
    # 分析使用者輸入的文字聲調
    user_tone = convert_chinese_to_tone_code(user_sentence)
    
    # 只要字數、聲調長度對不上，代表不是在玩遊戲，默默忽略
    if len(user_tone) != len(target_tone) or len(user_tone) == 0:
        return

    # 比對聲調是否完全正確
    if user_tone == target_tone:
        user_id = str(message.author.id)
        stats = load_stats()

        # 初始化新使用者資料（只存成功次數，不存嘗試次數）
        if user_id not in stats:
            stats[user_id] = {"name": message.author.name, "correct": 0}

        # 成功次數 +1 並儲存
        stats[user_id]["correct"] += 1
        save_stats(stats)
        
        # 取得目前累積成功挑戰的總次數
        times = stats[user_id]["correct"]
        
        # 🎯 跳出你指定格式的警告 Tag 訊息
        await message.channel.send(f"⚠️ {message.author.mention} 你已經講了 {times} 次每日聲調笑話。")
    else:
        # 聲調不對、挑戰失敗時：完全保持安靜、不做任何事
        pass

# ==============================================================================
# 6. 機器人啟動程序
# ==============================================================================
@bot.event
async def on_ready():
    print(f"🤖 機器人 {bot.user.name} 已成功上線！")
    # 確保定時排程器在機器人上線時立即啟動監聽
    if not midnight_alarm.is_running():
        midnight_alarm.start()

# 啟動並執行機器人
bot.run(TOKEN)