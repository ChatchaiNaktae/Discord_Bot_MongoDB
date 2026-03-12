import discord
from discord.ext import commands, tasks
import datetime
import pytz
import os
import aiohttp
import random
import certifi
from dotenv import load_dotenv

# นำเข้าเครื่องมือสำหรับเชื่อมต่อ MongoDB (แบบ Async)
from motor.motor_asyncio import AsyncIOMotorClient 

load_dotenv()

# ==========================================
# Database Configuration (MongoDB)
# ==========================================
MONGO_URI = os.getenv('MONGO_URI')

# เชื่อมต่อ Database
if MONGO_URI:
    db_client = AsyncIOMotorClient(MONGO_URI, tlsCAFile=certifi.where())
    db = db_client['MyScheduleBotDB']
    
    # สร้าง Collection แทนไฟล์ JSON เดิม
    hw_collection = db['homework']
    attendance_collection = db['attendance']
    reminder_collection = db['reminders']
else:
    print("⚠️ คำเตือน: ยังไม่ได้ใส่ MONGO_URI ในไฟล์ .env ระบบฐานข้อมูลจะไม่ทำงาน")

# ==========================================
# Helper Functions
# ==========================================
# Function to parse date & time and support Buddhist Era (B.E.)
def parse_datetime_support_be(date_str, time_str):
    try:
        d_parts = date_str.split('/')
        day = int(d_parts[0])
        month = int(d_parts[1])
        year = int(d_parts[2])
        if year > 2500:
            year = year - 543

        t_parts = time_str.split(':')
        hour = int(t_parts[0])
        minute = int(t_parts[1])

        return datetime.datetime(year, month, day, hour, minute)
    except Exception:
        return None

# ฟังก์ชันช่วยหา ID ล่าสุด เพื่อรันเลข Auto-Increment สำหรับ MongoDB
async def get_next_id(collection):
    latest = await collection.find_one(sort=[("id", -1)])
    return 1 if latest is None else latest["id"] + 1

# ==========================================
# Bot Class & Background Tasks
# ==========================================
class ScheduleBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=discord.Intents.default())

    async def setup_hook(self):
        await self.tree.sync()
        self.check_schedule.start()

    @tasks.loop(minutes=1)
    async def check_schedule(self):
        tz = pytz.timezone('Asia/Bangkok')
        now = datetime.datetime.now(tz)

        current_day = now.strftime('%A')
        current_time = now.strftime('%H:%M')

        channel_id = 1478673451681185816
        channel = self.get_channel(channel_id)

        if channel is None:
            return

        # 1. Schedule Notifications
        if current_day == 'Tuesday' and current_time == '07:50':
            await channel.send("🔔 **แจ้งเตือน!** 08:00 น. มีเรียน 'ท.การคิดเชิงระบบกับการวิเคราะห์ปัญหา' ตึกเรียนรวม SEC 01 ศร. 202 ครับ")
        elif current_day == 'Tuesday' and current_time == '12:50':
            await channel.send("🔔 **แจ้งเตือน!** 13:00 น. มีเรียน 'เทคโนโลยีสารสนเทศเพื่อการค้นคว้า' ตึกอธิการบดี ชั้น 3 SEC 01 ครับ")
        elif current_day == 'Wednesday' and current_time == '07:50':
            await channel.send("🔔 **แจ้งเตือน!** 08:00 น. มีเรียน 'ท.การโปรแกรมคอมพิวเตอร์' กับอ.สกุลชาย ห้อง SC208 เตรียมเปิดคอมรอได้เลย!")
        elif current_day == 'Wednesday' and current_time == '12:50':
            await channel.send("🔔 **แจ้งเตือน!** 13:00 น. มีเรียน 'การพัฒนาคุณภาพชีวิตและสังคม' ตึกเรียนรวม SEC 02 ศร. 211 ครับ")
        elif current_day == 'Thursday' and current_time == '12:50':
            await channel.send("🔔 **แจ้งเตือน!** 13:00 น. มีเรียน 'ท.คณิตศาสตร์ดิสครีตและทฤษฎีการคำนวณ' ตึกคณะ SEC 01 อ.ชานนท์ SC201 ครับ")
        elif current_day == 'Thursday' and current_time == '14:50':
            await channel.send("🔔 **แจ้งเตือน!** 15:00 น. มีเรียน 'ท./ป. ระบบปฏิบัติการ' ตึกคณะ SEC 01 อ.ชานนท์ SC201 ครับ")

        # 2. Reminder Notification & Auto-Delete System (MongoDB Version)
        if not MONGO_URI: return # ข้ามถ้าไม่ได้ต่อ DB

        current_dt = datetime.datetime(now.year, now.month, now.day, now.hour, now.minute)
        
        # ดึงการแจ้งเตือนทั้งหมดจาก MongoDB
        cursor = reminder_collection.find()
        reminders_data = await cursor.to_list(length=100)

        for rmd in reminders_data:
            s_time = rmd.get("start_time", "08:00")
            e_time = rmd.get("end_time", "08:00")

            start_dt = parse_datetime_support_be(rmd["start_date"], s_time)
            end_dt = parse_datetime_support_be(rmd["end_date"], e_time)

            if start_dt is None or end_dt is None:
                continue

            # ถ้าเวลาปัจจุบัน เลยเวลาที่กำหนดไว้ -> ลบทิ้งจาก Database ทันที
            if current_dt > end_dt:
                await reminder_collection.delete_one({"id": rmd["id"]})
                print(f"Auto-deleted expired reminder: {rmd['name']}")
                continue

            if current_dt == start_dt:
                msg = f"🔔 **ถึงเวลาแล้ว!** โปรเจกต์/กิจกรรม: **{rmd['name']}**\n(กำหนดสิ้นสุด: วันที่ {rmd['end_date']} เวลา {e_time} น.)"
                await channel.send(msg)

            elif current_dt == end_dt:
                msg = f"⚠️ **หมดเวลาแล้ว!** โปรเจกต์/กิจกรรม: **{rmd['name']}**\nเคลียร์ให้เสร็จนะครับ! (ระบบจะลบกิจกรรมนี้ออกอัตโนมัติ)"
                await channel.send(msg)

    @check_schedule.before_loop
    async def before_check_schedule(self):
        await self.wait_until_ready()

bot = ScheduleBot()

@bot.event
async def on_ready():
    print(f'Bot is online! Logged in as {bot.user}')

# ==========================================
# Slash Commands: Schedule
# ==========================================
@bot.tree.command(name="monday", description="Show schedule for Monday (Free day)")
async def monday(interaction: discord.Interaction):
    msg = "🎮 **วันจันทร์:** ว่างเต็มวัน! พักผ่อนอ่านมังงะ ดูอนิเมะ หรือเล่นเกมได้ยาวๆ เลยครับ"
    await interaction.response.send_message(msg)

@bot.tree.command(name="tuesday", description="Show schedule for Tuesday")
async def tuesday(interaction: discord.Interaction):
    msg = (
        "**ตารางเรียนวันอังคาร:**\n"
        "⏰ 08:00 - 10:00 น.\n"
        "📖 00-41-008 ท.การคิดเชิงระบบกับการวิเคราะห์ปัญหา\n"
        "🏢 ตึกเรียนรวม SEC 01 ศร. 202\n"
        "-------------------------------\n"
        "⏰ 10:00 - 12:00 น.\n"
        "📖 00-41-008 ป.การคิดเชิงระบบกับการวิเคราะห์ปัญหา\n"
        "🏢 ตึกเรียนรวม SEC 01 ศร. 202\n"
        "-------------------------------\n"
        "⏰ 13:00 - 17:00 น.\n"
        "📖 00-12-003 เทคโนโลยีสารสนเทศเพื่อการค้นคว้า\n"
        "🏢 ตึกอธิการบดี ชั้น 3 SEC 01"
    )
    await interaction.response.send_message(msg)

@bot.tree.command(name="wednesday", description="Show schedule for Wednesday")
async def wednesday(interaction: discord.Interaction):
    msg = (
        "**ตารางเรียนวันพุธ:**\n"
        "⏰ 08:00 - 10:00 น.\n"
        "📖 06-13-101 ท.การโปรแกรมคอมพิวเตอร์\n"
        "🏢 อ.สกุลชาย SC208\n"
        "-------------------------------\n"
        "⏰ 10:00 - 12:00 น.\n"
        "📖 06-13-101 ป.การโปรแกรมคอมพิวเตอร์\n"
        "🏢 อ.สกุลชาย SC208\n"
        "-------------------------------\n"
        "⏰ 13:00 - 17:00 น.\n"
        "📖 00-41-001 การพัฒนาคุณภาพชีวิตและสังคม\n"
        "🏢 ตึกเรียนรวม SEC 02 ศร. 211"
    )
    await interaction.response.send_message(msg)

@bot.tree.command(name="thursday", description="Show schedule for Thursday")
async def thursday(interaction: discord.Interaction):
    msg = (
        "**ตารางเรียนวันพฤหัสบดี:**\n"
        "⏰ 13:00 - 15:00 น.\n"
        "📖 06-01-313 ท.คณิตศาสตร์ดิสครีตและทฤษฎีการคำนวณ\n"
        "🏢 ตึกคณะ SEC 01 อ.ชานนท์ SC201\n"
        "-------------------------------\n"
        "⏰ 15:00 - 17:00 น.\n"
        "📖 06-14-102 ท./ป. ระบบปฏิบัติการ\n"
        "🏢 ตึกคณะ SEC 01 อ.ชานนท์ SC201"
    )
    await interaction.response.send_message(msg)

@bot.tree.command(name="friday", description="Show schedule for Friday (Free day)")
async def friday(interaction: discord.Interaction):
    msg = "🎮 **วันศุกร์:** ว่างเต็มวัน! ลุยโปรเจกต์เขียนโค้ดต่อ หรือพักผ่อนตามสบายเลยครับ"
    await interaction.response.send_message(msg)

@bot.tree.command(name="myweek", description="Show summary schedule for the entire week")
async def myweek(interaction: discord.Interaction):
    summary_msg = (
        "**สรุปตารางเรียนเทอม 2:**\n"
        "วันจันทร์: ว่างเต็มวัน! 🎮\n"
        "วันอังคาร: การคิดเชิงระบบฯ (เช้า) และ IT (บ่าย)\n"
        "วันพุธ: โปรแกรมคอมพิวเตอร์ (เช้า) และ พัฒนาคุณภาพชีวิตฯ (บ่าย)\n"
        "วันพฤหัสบดี: ดิสครีต (บ่าย) และ ระบบปฏิบัติการ (บ่าย)\n"
        "วันศุกร์: ว่างเต็มวัน! 🎮"
    )
    await interaction.response.send_message(summary_msg)

# ==========================================
# Slash Commands: Homework Manager (MongoDB)
# ==========================================
@bot.tree.command(name="hw_add", description="Add a new homework or project task")
async def hw_add(interaction: discord.Interaction, subject: str, task: str, due_date: str = "รอกำหนด (TBD) ⏳"):
    new_id = await get_next_id(hw_collection)

    new_hw = {"id": new_id, "subject": subject, "task": task, "due_date": due_date}
    
    # บันทึกลง Database
    await hw_collection.insert_one(new_hw)

    msg = f"✅ **บันทึกการบ้านเรียบร้อย!**\n📚 **วิชา:** {subject}\n📝 **งาน:** {task}\n📅 **ส่ง:** {due_date}\n*(รหัสงาน: {new_id})*"
    await interaction.response.send_message(msg)

@bot.tree.command(name="hw_list", description="Show all pending homework")
async def hw_list(interaction: discord.Interaction):
    cursor = hw_collection.find().sort("id", 1)
    tasks = await cursor.to_list(length=100)

    if not tasks:
        await interaction.response.send_message("🎉 **ไม่มีการบ้านค้างเลย!** ไปเล่นเกม ดูกันพลาได้สบายใจ!")
        return

    msg = "📋 **รายการการบ้านที่ต้องทำ:**\n"
    for task in tasks:
        msg += f"🔹 **[ID: {task['id']}]** วิชา {task['subject']} | 📝 {task['task']} | 📅 ส่ง: {task['due_date']}\n"
    await interaction.response.send_message(msg)

@bot.tree.command(name="hw_done", description="Mark homework as done and remove it")
async def hw_done(interaction: discord.Interaction, task_id: int):
    # ค้นหางานที่ต้องการจะลบก่อน เพื่อเอาชื่อวิชามาแสดงโชว์
    task_to_delete = await hw_collection.find_one({"id": task_id})
    
    if not task_to_delete:
        await interaction.response.send_message(f"❌ **หาไม่เจอ!** ไม่มีงานรหัส {task_id} ในสมุดจดครับ")
        return

    # สั่งลบออกจาก Database
    await hw_collection.delete_one({"id": task_id})
    await interaction.response.send_message(
        f"✅ **เย้! ลบงานรหัส {task_id} เรียบร้อย!**\n(ลบวิชา {task_to_delete['subject']} ออกจากสมุดจดแล้ว!)")

@bot.tree.command(name="hw_edit", description="Edit an existing homework task by ID")
async def hw_edit(interaction: discord.Interaction, task_id: int, subject: str = None, task: str = None, due_date: str = None):
    # เช็คก่อนว่ามีงานนี้ไหม
    target_task = await hw_collection.find_one({"id": task_id})
    
    if target_task is None:
        await interaction.response.send_message(f"❌ **หาไม่เจอ!** ไม่มีงานรหัส {task_id} ในสมุดจดครับ")
        return

    # รวบรวมข้อมูลที่จะอัปเดต
    update_data = {}
    if subject is not None: update_data["subject"] = subject
    if task is not None: update_data["task"] = task
    if due_date is not None: update_data["due_date"] = due_date
    
    if not update_data:
        await interaction.response.send_message("❌ ไม่มีการเปลี่ยนแปลงข้อมูลครับ")
        return

    # อัปเดตลง Database
    await hw_collection.update_one({"id": task_id}, {"$set": update_data})
    
    # โหลดข้อมูลใหม่ที่เพิ่งแก้เสร็จมาเพื่อเตรียมส่งข้อความ
    updated_task = await hw_collection.find_one({"id": task_id})

    msg = (
        f"✏️ **แก้ไขงานรหัส {task_id} เรียบร้อย!**\n"
        f"📚 **วิชา:** {updated_task['subject']}\n"
        f"📝 **งาน:** {updated_task['task']}\n"
        f"📅 **ส่ง:** {updated_task['due_date']}"
    )
    await interaction.response.send_message(msg)

# ==========================================
# Slash Commands: Attendance Tracker (MongoDB)
# ==========================================
@bot.tree.command(name="skip_add", description="Add 1 skip quota to a specific subject")
async def skip_add(interaction: discord.Interaction, subject: str):
    record = await attendance_collection.find_one({"subject": subject})
    
    if record:
        new_count = record["count"] + 1
        await attendance_collection.update_one({"subject": subject}, {"$set": {"count": new_count}})
    else:
        new_count = 1
        await attendance_collection.insert_one({"subject": subject, "count": new_count})

    warning = "\n🚨 **อันตราย!** ขาดเกิน 3 ครั้งระวังติด F!" if new_count >= 3 else ""
    await interaction.response.send_message(
        f"⚠️ บันทึกการขาดเรียนวิชา **{subject}**\nรวมขาดไปแล้ว: **{new_count} ครั้ง**{warning}")

@bot.tree.command(name="skip_check", description="Check your skip count for all subjects")
async def skip_check(interaction: discord.Interaction):
    cursor = attendance_collection.find()
    records = await cursor.to_list(length=100)

    if not records:
        await interaction.response.send_message("✅ **เยี่ยมมาก!** ยังไม่เคยขาดเรียนเลยสักวิชาครับ!")
        return

    msg = "📊 **สรุปโควต้าการขาดเรียน:**\n"
    for r in records:
        msg += f"🔹 วิชา {r['subject']}: ขาดไปแล้ว **{r['count']}** ครั้ง\n"
    await interaction.response.send_message(msg)

@bot.tree.command(name="skip_reset", description="Reset the skip count for a subject to 0")
async def skip_reset(interaction: discord.Interaction, subject: str):
    result = await attendance_collection.delete_one({"subject": subject})
    
    if result.deleted_count > 0:
        await interaction.response.send_message(f"🔄 **รีเซ็ต!** ลบประวัติการขาดเรียนวิชา **{subject}** เรียบร้อยครับ")
    else:
        await interaction.response.send_message(f"❌ **หาไม่เจอ!** ไม่พบประวัติการขาดเรียนวิชา **{subject}** ในระบบครับ")

# ==========================================
# Slash Commands: Event & Project Reminder (MongoDB)
# ==========================================
@bot.tree.command(name="reminder_add", description="Add an event (Date: DD/MM/YYYY, Time: HH:MM)")
async def reminder_add(interaction: discord.Interaction, name: str, start_date: str, end_date: str,
                       start_time: str = "08:00", end_time: str = "08:00"):
    if parse_datetime_support_be(start_date, start_time) is None or parse_datetime_support_be(end_date, end_time) is None:
        await interaction.response.send_message(
            "❌ **รูปแบบผิดพลาด!**\nวันที่ต้องเป็น วัน/เดือน/ปี\nเวลาต้องเป็น ชั่วโมง:นาที (เช่น 09:30)")
        return

    new_id = await get_next_id(reminder_collection)

    new_rmd = {
        "id": new_id, "name": name,
        "start_date": start_date, "end_date": end_date,
        "start_time": start_time, "end_time": end_time
    }
    
    await reminder_collection.insert_one(new_rmd)

    msg = (f"✅ **สร้างการแจ้งเตือนเรียบร้อย!**\n📌 **กิจกรรม:** {name}\n"
           f"🟢 **เริ่ม:** {start_date} เวลา {start_time} น.\n"
           f"🔴 **สิ้นสุด:** {end_date} เวลา {end_time} น.")
    await interaction.response.send_message(msg)

@bot.tree.command(name="reminder_list", description="Show all active reminders and events")
async def reminder_list(interaction: discord.Interaction):
    cursor = reminder_collection.find().sort("id", 1)
    reminders = await cursor.to_list(length=100)

    if not reminders:
        await interaction.response.send_message("✨ **ไม่มีกิจกรรมหรือการแจ้งเตือนค้างอยู่ครับ!**")
        return

    msg = "📅 **รายการแจ้งเตือน / กิจกรรมทั้งหมด:**\n"
    for rmd in reminders:
        s_time = rmd.get("start_time", "08:00")
        e_time = rmd.get("end_time", "08:00")
        msg += f"🔹 **[ID: {rmd['id']}]** {rmd['name']} | เริ่ม: {rmd['start_date']} ({s_time}) | สิ้นสุด: {rmd['end_date']} ({e_time})\n"
    await interaction.response.send_message(msg)

@bot.tree.command(name="reminder_del", description="Delete a reminder by ID")
async def reminder_del(interaction: discord.Interaction, rmd_id: int):
    target_rmd = await reminder_collection.find_one({"id": rmd_id})
    
    if not target_rmd:
        await interaction.response.send_message(f"❌ **หาไม่เจอ!** ไม่มีกิจกรรมรหัส {rmd_id} ในระบบครับ")
        return

    await reminder_collection.delete_one({"id": rmd_id})
    await interaction.response.send_message(f"🗑️ **ลบกิจกรรมรหัส {rmd_id} เรียบร้อย!**\n(ลบ '{target_rmd['name']}' ออกจากระบบแล้ว)")

@bot.tree.command(name="reminder_edit", description="Edit an existing reminder by ID")
async def reminder_edit(interaction: discord.Interaction, rmd_id: int, name: str = None, start_date: str = None, end_date: str = None, start_time: str = None, end_time: str = None):
    target_rmd = await reminder_collection.find_one({"id": rmd_id})

    if not target_rmd:
        await interaction.response.send_message(f"❌ **หาไม่เจอ!** ไม่มีกิจกรรมรหัส {rmd_id} ในระบบครับ")
        return

    update_data = {}
    if name is not None: update_data["name"] = name
    if start_date is not None: update_data["start_date"] = start_date
    if end_date is not None: update_data["end_date"] = end_date
    if start_time is not None: update_data["start_time"] = start_time
    if end_time is not None: update_data["end_time"] = end_time

    if not update_data:
        await interaction.response.send_message("❌ ไม่มีการเปลี่ยนแปลงข้อมูลครับ")
        return

    # ตรวจสอบรูปแบบเวลาที่แก้ไขใหม่ผสมกับของเดิม
    test_sd = update_data.get("start_date", target_rmd["start_date"])
    test_st = update_data.get("start_time", target_rmd["start_time"])
    test_ed = update_data.get("end_date", target_rmd["end_date"])
    test_et = update_data.get("end_time", target_rmd["end_time"])

    if parse_datetime_support_be(test_sd, test_st) is None or parse_datetime_support_be(test_ed, test_et) is None:
        await interaction.response.send_message("❌ **รูปแบบวันที่หรือเวลาผิดพลาด!** การแก้ไขถูกยกเลิกครับ (กรุณาใช้ วัน/เดือน/ปี และ ชั่วโมง:นาที)")
        return

    await reminder_collection.update_one({"id": rmd_id}, {"$set": update_data})
    updated_rmd = await reminder_collection.find_one({"id": rmd_id})

    msg = (
        f"✏️ **แก้ไขกิจกรรมรหัส {rmd_id} เรียบร้อย!**\n"
        f"📌 **กิจกรรม:** {updated_rmd['name']}\n"
        f"🟢 **เริ่ม:** {updated_rmd['start_date']} เวลา {updated_rmd['start_time']} น.\n"
        f"🔴 **สิ้นสุด:** {updated_rmd['end_date']} เวลา {updated_rmd['end_time']} น."
    )
    await interaction.response.send_message(msg)

# ==========================================
# Slash Commands: Utilities
# ==========================================
@bot.tree.command(name="weather", description="Check current weather in Bang Phra, Chon Buri")
async def weather(interaction: discord.Interaction):
    lat, lon = 13.2148, 100.9416
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
    await interaction.response.defer()
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                current = data.get("current_weather", {})
                temp = current.get("temperature", "-")
                wind_speed = current.get("windspeed", "-")
                weather_code = current.get("weathercode", 0)

                condition = "ท้องฟ้าแจ่มใส ☀️"
                if weather_code in [1, 2, 3]:
                    condition = "มีเมฆบางส่วน ⛅"
                elif weather_code in [45, 48]:
                    condition = "มีหมอก 🌫️"
                elif weather_code in [51, 53, 55, 61, 63, 65, 80, 81, 82]:
                    condition = "ฝนตก 🌧️ (อย่าลืมพกเสื้อกันฝน!)"
                elif weather_code in [71, 73, 75]:
                    condition = "หิมะตก ❄️"
                elif weather_code in [95, 96, 99]:
                    condition = "พายุฝนฟ้าคะนอง ⛈️ (อันตราย! งดแว้นเด็ดขาด)"

                msg = (f"🌤️ **รายงานสภาพอากาศ ณ บางพระ ชลบุรี** 🌤️\n"
                       f"🌡️ อุณหภูมิ: **{temp} °C**\n"
                       f"🌬️ ความเร็วลม: **{wind_speed} km/h**\n"
                       f"👀 สภาพอากาศ: **{condition}**")
                await interaction.followup.send(msg)
            else:
                await interaction.followup.send("❌ บอทติดต่อกรมอุตุฯ ไม่ได้ครับ")


@bot.tree.command(name="randomday", description="สุ่มกิจกรรมทำในวันว่าง (จันทร์/ศุกร์)")
async def randomday(interaction: discord.Interaction):
    activities = [
        "🤖 **ลุยงานโมเดล**: หยิบกันพลาหรือรถทามิย่าตัวใหม่มาต่อ พ่นสีแอร์บรัช ติดดีคอลให้ฉ่ำๆ ไปเลย!",
        "📖 **เสพมังงะ/อนิเมะ**: หยิบ Dr. Stone, Chainsaw Man, Sanda หรือเรื่องอื่นมาอ่านชิลๆ ต่อให้จบเล่ม!",
        "🧟 **Dev Roblox**: เปิด Studio ลุยเขียนโค้ด Lua อัปเกรดระบบเกมซอมบี้ของเราต่อให้เดือดๆ!",
        "⛏️ **อัปเดตม็อด Minecraft**: ลุยเขียน Java ปรับปรุงม็อด Heart Upgrade และม็อดอื่นๆ บน CurseForge!",
        "💻 **เล่น AI & เขียนโค้ด**: ลุยโปรเจกต์ Python สร้างแอปเจ๋งๆ หรือลองเล่นเจนรูปจาก Stable Diffusion!",
        "🎮 **เกมเมอร์โหมด**: ปิดโหมด Dev ทิ้งไป วันนี้ขอจับจอยลุยเล่นเกมให้หนำใจยาวๆ!"
    ]
    msg = f"🎲 **ตู้กาชาสุ่มกิจกรรมวันว่างทำงานแล้ว!** 🎲\n🎉 วันนี้บอทขอเสนอให้ชัย... \n\n👉 {random.choice(activities)}"
    await interaction.response.send_message(msg)

# ==========================================
# Execute Bot
# ==========================================
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
if DISCORD_TOKEN is None:
    print("Error: DISCORD_TOKEN not found! Please check your .env file.")
else:
    bot.run(DISCORD_TOKEN)