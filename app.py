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
# 請記得在此處填入你真正的 Discord Token 
TOKEN = os.environ.get("DISCORD_TOKEN")  

MY_SCHEDULED_TONES = {
    "2026-10-31": "242",  
    "2026-11-01": "124",    
    "2026-11-02": "311",   
}

STATS_FILE = "user_leaderboard.json"

intents = discord.Intents.default()
intents.message_content = True  
bot = commands.Bot(command_prefix="!", intents=intents)

# ─── 【核心升級】全域狀態：改為儲存「目前在哪個頻道工作」 ───
# 預設為 None（代表一上線時，還沒有導入任何頻道，保持完全安靜）
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
# 3. 每日 00:00 聲調笑話警報器 (自動發送到當前導入的頻道)
# ==============================================================================
@tasks.loop(hours=1)
async def midnight_alarm():
    global TARGET_CHANNEL_ID
    # 如果使用者還沒有輸入 !listen 導入任何頻道，定時器就先不發送警報
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
# 4. 指令專區：讓使用者隨時「導入」或「取消」頻道
# ==============================================================================
@bot.command(name="listen")
async def start_listening(ctx):
    global TARGET_CHANNEL_ID
    # 💡 自動抓取使用者「目前在哪個頻道輸入指令」的 ID
    current_channel_id = ctx.channel.id
    
    if TARGET_CHANNEL_ID == current_channel_id:
        await ctx.send("📢 機器人已經在這個頻道導入並偵測中囉！")
    else:
        TARGET_CHANNEL_ID = current_channel_id
        await ctx.send(f"✅ 成功導入頻道！機器人已鎖定此頻道進行聲調偵測與每日 00:00 警報！")

@bot.command(name="unlisten")
async def stop_listening(ctx):
    global TARGET_CHANNEL_ID
    if TARGET_CHANNEL_ID is None:
        await ctx.send("📴 機器人目前本來就沒有在任何頻道進行偵測。")
    else:
        TARGET_CHANNEL_ID = None
        await ctx.send("❌ 機器人已取消頻道導入！現在在任何頻道打字挑戰都不會觸發統計。")

# ==============================================================================
# 5. 監聽頻道訊息：只在被導入的特定頻道運作
# ==============================================================================
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # 確保 !listen 和 !unlisten 指令能被正常解析
    await bot.process_commands(message)

    # ─── 【核心修改】如果尚未導入頻道，或者「打字的頻道」不是被導入的頻道，直接不理它 ───
    if TARGET_CHANNEL_ID is None or message.channel.id != TARGET_CHANNEL_ID:
        return
    # ───────────────────────────────────────────────────────────────

    user_sentence = message.content.strip()
    if user_sentence.startswith("!"):
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
    else:
        pass

# ==============================================================================
# 6. 機器人啟動程序
# ==============================================================================
@bot.event
async def on_ready():
    print(f"🤖 機器人 {bot.user.name} 已成功上線！")
    if not midnight_alarm.is_running():
        midnight_alarm.start()

bot.run(TOKEN)
