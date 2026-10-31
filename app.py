import json
import os
import re
import asyncio
from datetime import datetime, timedelta
import discord
from discord.ext import commands, tasks
from pypinyin import pinyin, Style
from flask import Flask
import threading

# ==============================================================================
# 0. 關鍵防禦：使用 Flask 在背景提供流暢不卡死的網頁埠，徹底騙過 Render
# ==============================================================================
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive!"

def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

threading.Thread(target=run_dummy_server, daemon=True).start()

# ==============================================================================
# 1. 設定與大老闆排程專區
# ==============================================================================
TOKEN = os.environ.get("DISCORD_TOKEN")  

MY_SCHEDULED_TONES = {
    "2026-10-30": "242",  
    "2026-10-31": "242",  # 今日密碼：242
    "2026-11-01": "3",    
    "2026-11-02": "23",   
    "2026-11-03": "123",   
    "2026-11-04": "1123",   
    "2026-11-05": "31123",   
    "2026-11-06": "231123",   
    "2026-11-07": "4231123",   
    "2026-11-08": "44231123",   
    "2026-11-09": "144231123",   
    "2026-11-10": "3144231123",   
}

intents = discord.Intents.default()
intents.message_content = True  
intents.members = True  # 排行榜撈暱稱核心，請確保 Developer Portal 已開啟 Server Members Intent

bot = commands.Bot(command_prefix="!", intents=intents)

# 💡 固底防呆：固定文字頻道 ID（對應你的指定文字頻道）
TARGET_CHANNEL_ID = 1564653924169023489  

# ==============================================================================
# 2. 核心技術與【Discord 頻道簡介雲端資料庫】讀寫邏輯
# ==============================================================================
def convert_chinese_to_tone_code(text):
    clean_text = "".join(re.findall(r"[\u4e00-\u9fa5]", text))
    pinyin_list = pinyin(clean_text, style=Style.TONE3, neutral_tone_with_five=True)
    
    tone_code = ""
    for item in pinyin_list:
        main_pronunciation = item if isinstance(item, list) and len(item) > 0 else str(item)
        match = re.search(r"\d$", main_pronunciation)
        tone_code += match.group() if match else "5"
        
    return tone_code

# 從頻道的簡介中讀取資料
async def load_stats_from_channel():
    try:
        channel = bot.get_channel(TARGET_CHANNEL_ID)
        if not channel or not channel.topic:
            return {}
        
        match = re.search(r"DATA_START({.*})DATA_END", channel.topic)
        if match:
            return json.loads(match.group(1))
    except Exception as e:
        print(f"❌ 解析簡介資料失敗: {e}")
    return {}

# 將資料寫回頻道的簡介中保存
async def save_stats_to_channel(data):
    try:
        channel = bot.get_channel(TARGET_CHANNEL_ID)
        if not channel:
            return
        
        json_str = json.dumps(data, ensure_ascii=False)
        new_topic = f"每日指定聲調挑戰頻道 ｜ 機器人紀錄專區 [請勿刪除後方資料]\nDATA_START{json_str}DATA_END"
        await channel.edit(topic=new_topic)
    except Exception as e:
        print(f"❌ 寫入頻道簡介失敗: {e}")

# ==============================================================================
# 3. 🚨 核心新功能：每日 00:00 結算昨夜排行榜 ＆ 重設並發布今日全新挑戰 🚨
# ==============================================================================
@tasks.loop(minutes=1)  # 縮短檢查頻率到每分鐘，配合 UptimeRobot 絕不漏掉 00:00
async def midnight_scheduler():
    now = datetime.now()
    
    # 💡 只有在精準 00:00 的這一分鐘才執行結算與重設
    if now.hour == 0 and now.minute == 0:
        channel = bot.get_channel(TARGET_CHANNEL_ID)
        if not channel:
            return

        # 1. 撈出昨天的紀錄並公佈最終排行榜
        stats = await load_stats_from_channel()
        yesterday_str = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        
        embed_end = discord.Embed(
            title=f"🏆 【{yesterday_str}】今日聲調造句挑戰 ｜ 最終榮譽榜 🏆",
            description="昨天的挑戰已經結束！以下是最終勝出的前 10 名大師：\n───────────────────",
            color=0xf1c40f
        )
        
        if stats:
            sorted_stats = sorted(stats.items(), key=lambda x: x[1]["correct"], reverse=True)
            leaderboard_text = ""
            for index, (user_id, info) in enumerate(sorted_stats[:10], start=1):
                leaderboard_text += f"🥇 第 {index} 名 ｜ {info['name']} ── 💥 成功觸發 **{info['correct']}** 次！\n"
            embed_end.description += f"\n{leaderboard_text}"
        else:
            embed_end.description += "\n😭 昨天竟然沒有人挑戰成功，大家都太害羞了！"
            
        await channel.send(embed=embed_end)
        
        # 2. 核心重設：清空頻道簡介裡的紀錄（新的一天歸零開始）
        await save_stats_to_channel({})
        print(f"[System] 跨日 00:00！昨日紀錄已結算，資料庫已成功歸零重置。")

        # 3. 發布今天全新的聲調密碼挑戰警報
        today_str = now.strftime("%Y-%m-%d")
        if today_str in MY_SCHEDULED_TONES:
            target_tone = MY_SCHEDULED_TONES[today_str]
            embed_start = discord.Embed(
                title="🚨 全新一日！今日指定聲調造句挑戰開始！",
                description=f"全新的一天開始了！今天的目標聲調密碼是：\n\n➡️ **【 {target_tone} 】**\n\n昨日分數已全面歸零，大家快來搶下今天的第一分吧！",
                color=0x27ae60
            )
            await channel.send(embed=embed_start)

# ==============================================================================
# 4. 常規維護與斜線指令
# ==============================================================================
@bot.command(name="sync")
async def sync_commands(ctx):
    await ctx.send("⏳ 正在向 Discord 伺服器同步斜線指令...")
    try:
        synced = await bot.tree.sync()
        await ctx.send(f"✨ 成功同步了 {len(synced)} 個斜線指令！請重整 Discord（F5）測試。")
    except Exception as e:
        await ctx.send(f"❌ 同步失敗: {e}")

@bot.tree.command(name="listen", description="檢查頻道鎖定狀態")
async def start_listening(interaction: discord.Interaction):
    await interaction.response.send_message("✅ 頻道已由後台自動固底鎖定，無需手動變更，即可直接開始挑戰！")

@bot.tree.command(name="check", description="檢查中文字在機器人眼中的聲調密碼")
@discord.app_commands.describe(text="想要查詢聲調的中文字或句子")
async def check_tone(interaction: discord.Interaction, text: str):
    tone = convert_chinese_to_tone_code(text)
    await interaction.response.send_message(f"🔍 「{text}」在機器人眼中的聲調密碼是：**【 {tone} 】**")

@bot.tree.command(name="leaderboard", description="查看今日即時挑戰排行榜")
async def leaderboard(interaction: discord.Interaction):
    stats = await load_stats_from_channel()
    if not stats:
        await interaction.response.send_message("📊 今天新一輪的挑戰還沒有人上榜喔！快來搶頭香！")
        return
    
    sorted_stats = sorted(stats.items(), key=lambda x: x[1]["correct"], reverse=True)
    
    leaderboard_text = "🏆 **【 今日即時聲調挑戰 ｜ 榮譽排行榜 】** 🏆\n"
    leaderboard_text += "（每天 00:00 將會結算並重設歸零）\n"
    leaderboard_text += "───────────────────\n"
    for index, (user_id, info) in enumerate(sorted_stats[:10], start=1):
        leaderboard_text += f"第 {index} 名 ｜ {info['name']} ── 💥 今日已觸發 **{info['correct']}** 次！\n"
    
    await interaction.response.send_message(leaderboard_text)

# ==============================================================================
# 5. 監聽頻道訊息
# ==============================================================================
@bot.event
async def on_message(message):
    try:
        if message.author.bot:
            return

        await bot.process_commands(message)

        if message.channel.id != TARGET_CHANNEL_ID:
            return

        user_sentence = message.content.strip()
        if user_sentence.startswith("/") or user_sentence.startswith("!"):
            return

        today_str = datetime.now().strftime("%Y-%m-%d")
        if today_str not in MY_SCHEDULED_TONES:
            return

        target_tone = MY_SCHEDULED_TONES[today_str]
        user_tone = convert_chinese_to_tone_code(user_sentence)

        print(f"[Debug] 收到挑戰: '{user_sentence}' | 解析聲調: {user_tone} | 目標聲調: {target_tone}")

        if len(user_tone) != len(target_tone) or len(user_tone) == 0:
            return

        if user_tone == target_tone:
            user_id = str(message.author.id)
            stats = await load_stats_from_channel()

            if user_id not in stats:
                stats[user_id] = {"name": message.author.name, "correct": 0}

            stats[user_id]["correct"] += 1
            await save_stats_to_channel(stats)
            
            times = stats[user_id]["correct"]
            await message.channel.send(f"🎉 {message.author.mention} 成功觸發！你今天已經講了 {times} 次每日聲調笑話。")
    except Exception as e:
        print(f"❌ 錯誤攔截: {e}")

# ==============================================================================
# 6. 機器人啟動程序
# ==============================================================================
@bot.event
async def on_ready():
    print(f"🤖 機器人 {bot.user.name} 已成功滿血上線！")
    if not midnight_scheduler.is_running():
        midnight_scheduler.start()

async def main():
    async with bot:
        await bot.start(TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
