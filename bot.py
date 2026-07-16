import os
import random
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

TOKEN = os.environ.get("BOT_TOKEN", "ضع_التوكن_هنا")
games = {}

ROLES = {"مافيا": "🔫", "مواطن": "👤", "دكتور": "💊", "محقق": "🔍"}

def new_game():
    return {
        "players": {},
        "phase": "joining",
        "day": 0,
        "votes": {},
        "healed": None,
        "investigated": None,
        "mafia_target": None,
        "mafia_votes": {},
        "night_step": None,  
        "timeout_task": None,
        "pinned_msg_id": None  # المتغير الجديد لحفظ رقم الرسالة المثبتة
    }

def assign_roles(players):
    ids = list(players.keys())
    random.shuffle(ids)
    n = len(ids)
    roles = ["مواطن"] * n
    
    if n >= 13:
        roles[0] = "مافيا"
        roles[1] = "مافيا"
        roles[2] = "مافيا"
    elif n >= 6:
        roles[0] = "مافيا"
        roles[1] = "مافيا"
    else:
        roles[0] = "مافيا"  
        
    if n >= 4: roles[-1] = "دكتور"
    if n >= 6: roles[-2] = "محقق"
    
    random.shuffle(roles)
    for i, uid in enumerate(ids):
        players[uid]["role"] = roles[i]
    return players

def get_alive(game):
    return {uid: p for uid, p in game["players"].items() if p["alive"]}

def check_winner(game):
    alive = get_alive(game)
    mafia = [p for p in alive.values() if p["role"] == "مافيا"]
    others = [p for p in alive.values() if p["role"] != "مافيا"]
    
    if not mafia: 
        return "مواطنون"
    if len(mafia) >= len(others): 
        return "مافيا"
    return None

def joining_keyboard():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✋ انضم للعبة", callback_data="join"),
        InlineKeyboardButton("🚪 خروج", callback_data="leave")
    ]])

# ── أوامر اللعبة ──────────────────────────────────────────

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("أضفني لمجموعة واستخدم /newgame هناك! 🎮")
        return
    
    chat_id = update.effective_chat.id
    
    if chat_id in games:
        game = games[chat_id]
        if game["phase"] == "joining":
            await update.message.reply_text("⚠️ *هناك لعبة بالفعل في مرحلة التسجيل!*\nاضغط على زر الانضمام للمشاركة.", parse_mode="Markdown")
        else:
            await update.message.reply_text("⚠️ *هناك لعبة مستمرة حالياً في المجموعة!*\nانتظر حتى تنتهي اللعبة الحالية.", parse_mode="Markdown")
        return

    games[chat_id] = new_game()
    
    # نرسل رسالة التسجيل ونحفظها في متغير
    sent_msg = await update.message.reply_text(
        "🎭 *لعبة المافيا*\n\nاضغط انضم للمشاركة!\nالحد الأدنى: 4 لاعبين\n\nعندما يكتمل اللاعبون اكتب /begin",
        reply_markup=joining_keyboard(), parse_mode="Markdown"
    )
    
    # محاولة تثبيت رسالة التسجيل
    try:
        await context.bot.pin_chat_message(chat_id, sent_msg.message_id)
        games[chat_id]["pinned_msg_id"] = sent_msg.message_id
    except Exception:
        pass # نتجاهل الخطأ لو البوت مو أدمن

async def newgame_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start_cmd(update, context)

async def join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat_id
    user = query.from_user
    
    if chat_id not in games or games[chat_id]["phase"] != "joining":
        await query.answer("اللعبة ليست في مرحلة التسجيل!", show_alert=True)
        return
    
    game = games[chat_id]
    if user.id in game["players"]:
        await query.answer("أنت مسجل بالفعل! ✅", show_alert=True)
        return
        
    safe_name = user.first_name.replace("_", "-").replace("*", "").replace("`", "").replace("[", "")
    game["players"][user.id] = {"name": safe_name, "role": None, "alive": True}
    
    names = [p["name"] for p in game["players"].values()]
    
    await query.edit_message_text(
        f"🎭 *لعبة المافيا*\n\n👥 اللاعبون ({len(names)}):\n" +
        "\n".join(f"• {n}" for n in names) +
        "\n\nاكتب /begin لبدء اللعبة (4 لاعبين على الأقل)",
        reply_markup=joining_keyboard(), parse_mode="Markdown"
    )
    await query.answer()

async def leave_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat_id
    uid = query.from_user.id
    
    if chat_id not in games or games[chat_id]["phase"] != "joining":
        await query.answer("لا يمكنك الخروج الآن!", show_alert=True)
        return
        
    game = games[chat_id]
    if uid not in game["players"]:
        await query.answer("أنت لست مسجلاً أصلاً!", show_alert=True)
        return
        
    del game["players"][uid]
    names = [p["name"] for p in game["players"].values()]
    text = (
        f"🎭 *لعبة المافيا*\n\n👥 اللاعبون ({len(names)}):\n" +
        "\n".join(f"• {n}" for n in names) +
        "\n\nاكتب /begin لبدء اللعبة (4 لاعبين على الأقل)"
    ) if names else "🎭 *لعبة المافيا*\n\nلا يوجد لاعبون. اضغط انضم للمشاركة!"
    
    await query.edit_message_text(text, reply_markup=joining_keyboard(), parse_mode="Markdown")
    await query.answer("خرجت من اللعبة 👋")

async def begin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in games:
        await update.message.reply_text("لا توجد لعبة! اكتب /newgame")
        return
        
    game = games[chat_id]
    if game["phase"] != "joining":
        await update.message.reply_text("اللعبة بدأت بالفعل!")
        return
        
    if len(game["players"]) < 4:
        await update.message.reply_text("تحتاج 4 لاعبين على الأقل! 😅")
        return
        
    game["players"] = assign_roles(game["players"])
    for uid, player in game["players"].items():
        role = player["role"]
        try:
            extra = ""
            if role == "مافيا":
                mafia_names = [p["name"] for p in game["players"].values() if p["role"] == "مافيا"]
                extra = f"\n\n🔫 زملاؤك في المافيا: {', '.join(mafia_names)}"
            desc = {"مافيا": "أنت من المافيا، اقتل المواطنين ليلاً!", "مواطن": "أنت مواطن شريف، اكشف المافيا!", "دكتور": "أنت الدكتور، اشفِ لاعباً كل ليلة!", "محقق": "أنت المحقق، تحقق من هوية لاعب كل ليلة!"}.get(role, "")
            await context.bot.send_message(uid, f"🎭 دورك:\n\n{ROLES.get(role,'')} *{role}*{extra}\n\n{desc}", parse_mode="Markdown")
        except Exception:
            pass
            
    # فك تثبيت رسالة التسجيل عند بدء اللعبة
    if game.get("pinned_msg_id"):
        try:
            await context.bot.unpin_chat_message(chat_id, game["pinned_msg_id"])
            game["pinned_msg_id"] = None
        except Exception:
            pass
            
    game["phase"] = "night"
    game["day"] = 1
    await update.message.reply_text(f"🌙 *الليلة {game['day']}*\n\nبدأت اللعبة! تم إرسال الأدوار بالخاص.", parse_mode="Markdown")
    await asyncio.sleep(2)
    await start_mafia_phase(chat_id, context)

# ── متحكمات الليل المحمية بالأقفال (State Locks) ─────────────────────────

async def start_mafia_phase(chat_id, context):
    if chat_id not in games: return
    game = games[chat_id]
    
    winner = check_winner(game)
    if winner:
        await end_game(chat_id, context, winner)
        return

    game["night_step"] = "mafia"
    game["mafia_votes"] = {}
    
    alive = get_alive(game)
    mafia_uids = [uid for uid, p in alive.items() if p["role"] == "مافيا"]
    targets = {uid: p for uid, p in alive.items() if p["role"] != "مافيا"}
    
    if mafia_uids and targets:
        await context.bot.send_message(chat_id, "🌑 *حلّ الظلام على المدينة...*\n\n🔫 همسات المافيا تتردد في الأزقة وهم يتآمرون لاختيار ضحيتهم...", parse_mode="Markdown")
        kb = [[InlineKeyboardButton(f"🎯 {p['name']}", callback_data=f"mafia_{uid}")] for uid, p in targets.items()]
        for uid in mafia_uids:
            try: await context.bot.send_message(uid, "🔫 *اختر من تغتال الليلة:*", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
            except Exception: pass
        
        game["timeout_task"] = asyncio.create_task(mafia_timeout(chat_id, context, targets, mafia_uids))
    else:
        await start_doctor_phase(chat_id, context)

async def mafia_timeout(chat_id, context, targets, mafia_uids):
    try:
        await asyncio.sleep(180)
        if chat_id in games and games[chat_id]["night_step"] == "mafia":
            game = games[chat_id]
            game["night_step"] = "locked" 
            
            if game["mafia_votes"]:
                vc = {}
                for t in game["mafia_votes"].values(): vc[t] = vc.get(t, 0) + 1
                max_v = max(vc.values())
                candidates = [t for t, v in vc.items() if v == max_v]
                game["mafia_target"] = random.choice(candidates)
            else:
                if targets:
                    game["mafia_target"] = random.choice(list(targets.keys()))
                    
            for uid in mafia_uids:
                try: await context.bot.send_message(uid, "⏱️ *انتهى الوقت! تم اعتماد اختيار المافيا.*", parse_mode="Markdown")
                except Exception: pass
            await start_doctor_phase(chat_id, context)
    except asyncio.CancelledError:
        pass
    except Exception:
        if chat_id in games and games[chat_id]["night_step"] == "mafia":
            games[chat_id]["night_step"] = "locked"
            await start_doctor_phase(chat_id, context)

async def start_doctor_phase(chat_id, context):
    if chat_id not in games: return
    game = games[chat_id]
    
    if game["timeout_task"] and game["timeout_task"] != asyncio.current_task() and not game["timeout_task"].done(): 
        game["timeout_task"].cancel()
    
    has_doctor_in_game = any(p["role"] == "دكتور" for p in game["players"].values())
    if not has_doctor_in_game:
        game["healed"] = None
        await start_detective_phase(chat_id, context)
        return

    await context.bot.send_message(chat_id, "💊 *الدكتور استيقظ على صوت خطوات مريبة...*\n\nيسارع ليقرر من يحميه بدوائه قبل فوات الأوان...", parse_mode="Markdown")
    
    alive = get_alive(game)
    doctor_uids = [uid for uid, p in alive.items() if p["role"] == "دكتور"]
    
    if doctor_uids:
        game["night_step"] = "doctor"
        kb = [[InlineKeyboardButton(f"💊 {p['name']}", callback_data=f"heal_{uid}")] for uid, p in alive.items()]
        for uid in doctor_uids:
            try: await context.bot.send_message(uid, "💊 *اختر من تشفي الليلة:*", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
            except Exception: pass
        game["timeout_task"] = asyncio.create_task(doctor_timeout(chat_id, context, alive, doctor_uids))
    else:
        game["night_step"] = "doctor_fake"
        game["healed"] = None
        game["timeout_task"] = asyncio.create_task(fake_doctor_timeout(chat_id, context))

async def doctor_timeout(chat_id, context, alive, doctor_uids):
    try:
        await asyncio.sleep(90)
        if chat_id in games and games[chat_id]["night_step"] == "doctor":
            game = games[chat_id]
            game["night_step"] = "locked" 
            if alive:
                game["healed"] = random.choice(list(alive.keys()))
            for uid in doctor_uids:
                try: await context.bot.send_message(uid, "⏱️ *انتهى الوقت! تم اختيار شخص عشوائي لحمايته.*", parse_mode="Markdown")
                except Exception: pass
            await start_detective_phase(chat_id, context)
    except asyncio.CancelledError:
        pass
    except Exception:
        if chat_id in games and games[chat_id]["night_step"] == "doctor":
            games[chat_id]["night_step"] = "locked"
            await start_detective_phase(chat_id, context)

async def fake_doctor_timeout(chat_id, context):
    try:
        await asyncio.sleep(20)
        if chat_id in games and games[chat_id]["night_step"] == "doctor_fake":
            games[chat_id]["night_step"] = "locked"
            await start_detective_phase(chat_id, context)
    except asyncio.CancelledError:
        pass
    except Exception:
        if chat_id in games and games[chat_id]["night_step"] == "doctor_fake":
            games[chat_id]["night_step"] = "locked"
            await start_detective_phase(chat_id, context)

async def start_detective_phase(chat_id, context):
    if chat_id not in games: return
    game = games[chat_id]
    
    if game["timeout_task"] and game["timeout_task"] != asyncio.current_task() and not game["timeout_task"].done(): 
        game["timeout_task"].cancel()
    
    has_detective_in_game = any(p["role"] == "محقق" for p in game["players"].values())
    if not has_detective_in_game:
        game["investigated"] = None
        await end_night_phase(chat_id, context)
        return

    await context.bot.send_message(chat_id, "🔍 *المحقق يتسلل في ظلام الليل...*\n\nعيناه تراقبان كل تفصيلة وهو يستعد للكشف عن أحد المشتبه بهم...", parse_mode="Markdown")
    
    alive = get_alive(game)
    detect_uids = [uid for uid, p in alive.items() if p["role"] == "محقق"]
    det_targets = {uid: p for uid, p in alive.items() if uid not in detect_uids}
    
    if detect_uids and det_targets:
        game["night_step"] = "detective"
        kb = [[InlineKeyboardButton(f"🔍 {p['name']}", callback_data=f"invest_{uid}")] for uid, p in det_targets.items()]
        for uid in detect_uids:
            try: await context.bot.send_message(uid, "🔍 *اختر من تحقق معه الليلة:*", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
            except Exception: pass
        game["timeout_task"] = asyncio.create_task(detective_timeout(chat_id, context, det_targets, detect_uids))
    else:
        game["night_step"] = "detective_fake"
        game["investigated"] = None
        game["timeout_task"] = asyncio.create_task(fake_detective_timeout(chat_id, context))

async def detective_timeout(chat_id, context, det_targets, detect_uids):
    try:
        await asyncio.sleep(90)
        if chat_id in games and games[chat_id]["night_step"] == "detective":
            game = games[chat_id]
            game["night_step"] = "locked" 
            t_rand = None
            if det_targets:
                t_rand = random.choice(list(det_targets.keys()))
                game["investigated"] = t_rand
            
            if t_rand:
                is_mafia_rand = game["players"][t_rand]["role"] == "مافيا"
                for uid in detect_uids:
                    try:
                        await context.bot.send_message(uid, f"⏱️ *انتهى الوقت! تم التحقيق عشوائياً مع:*\n*{game['players'][t_rand]['name']}* وهو {'🔴 مافيا!' if is_mafia_rand else '🟢 بريء!'}", parse_mode="Markdown")
                    except Exception: pass
            await end_night_phase(chat_id, context)
    except asyncio.CancelledError:
        pass
    except Exception:
        if chat_id in games and games[chat_id]["night_step"] == "detective":
            games[chat_id]["night_step"] = "locked"
            await end_night_phase(chat_id, context)

async def fake_detective_timeout(chat_id, context):
    try:
        await asyncio.sleep(20)
        if chat_id in games and games[chat_id]["night_step"] == "detective_fake":
            games[chat_id]["night_step"] = "locked"
            await end_night_phase(chat_id, context)
    except asyncio.CancelledError:
        pass
    except Exception:
        if chat_id in games and games[chat_id]["night_step"] == "detective_fake":
            games[chat_id]["night_step"] = "locked"
            await end_night_phase(chat_id, context)

async def end_night_phase(chat_id, context):
    if chat_id not in games: return
    game = games[chat_id]
    
    if game["timeout_task"] and game["timeout_task"] != asyncio.current_task() and not game["timeout_task"].done(): 
        game["timeout_task"].cancel()
        
    game["night_step"] = None
    await resolve_night(chat_id, context)

# ── callback الليل المُؤمن ضد الاستهبال وتكرار الضغط ──────────────────

async def night_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data  = query.data
    uid   = query.from_user.id

    game = None
    chat_id = None
    for cid, g in games.items():
        if uid in g["players"]:
            game = g
            chat_id = cid
            break

    if not game or game["phase"] != "night":
        await query.answer("ليس وقت هذا الإجراء!", show_alert=True)
        return

    if uid not in game["players"] or not game["players"][uid]["alive"]:
        await query.answer("أنت خارج اللعبة!", show_alert=True)
        return

    step = game.get("night_step")
    parts = data.split("_")
    action = parts[0]
    target_id = int(parts[1])

    if action == "mafia" and step == "mafia":
        if game["players"][uid]["role"] != "مافيا":
            await query.answer("هذا ليس دورك!", show_alert=True)
            return
        
        await query.answer("✅ تم تسجيل صوتك!")
        await query.edit_message_text(f"✅ اخترت *{game['players'][target_id]['name']}* هدفاً!", reply_markup=None, parse_mode="Markdown")
        
        game["mafia_votes"][uid] = target_id
        alive = get_alive(game)
        mafia_uids = [u for u, p in alive.items() if p["role"] == "مافيا"]
        
        if len(game["mafia_votes"]) >= len(mafia_uids):
            game["night_step"] = "locked" 
            if game["timeout_task"] and not game["timeout_task"].done():
                game["timeout_task"].cancel()
            
            vc = {}
            for t in game["mafia_votes"].values(): vc[t] = vc.get(t, 0) + 1
            max_v = max(vc.values())
            candidates = [t for t, v in vc.items() if v == max_v]
            game["mafia_target"] = random.choice(candidates)
            
            await start_doctor_phase(chat_id, context)
        else:
            for other in mafia_uids:
                if other != uid:
                    try: await context.bot.send_message(other, f"⚠️ زميلك اختار *{game['players'][target_id]['name']}*، اختر أنت أيضاً!", parse_mode="Markdown")
                    except Exception: pass

    elif action == "heal" and step == "doctor":
        if game["players"][uid]["role"] != "دكتور":
            await query.answer("هذا ليس دورك!", show_alert=True)
            return
        
        await query.answer("✅ تم الشفاء!")
        await query.edit_message_text(f"✅ ستشفي *{game['players'][target_id]['name']}* الليلة!", reply_markup=None, parse_mode="Markdown")
        
        game["healed"] = target_id
        game["night_step"] = "locked" 
        if game["timeout_task"] and not game["timeout_task"].done():
            game["timeout_task"].cancel()
        await start_detective_phase(chat_id, context)

    elif action == "invest" and step == "detective":
        if game["players"][uid]["role"] != "محقق":
            await query.answer("هذا ليس دورك!", show_alert=True)
            return
        
        await query.answer("✅ تم التحقيق!")
        is_mafia = game["players"][target_id]["role"] == "مافيا"
        await query.edit_message_text(f"🔍 نتيجة التحقيق:\n*{game['players'][target_id]['name']}* هو {'🔴 مافيا!' if is_mafia else '🟢 بريء!'}", reply_markup=None, parse_mode="Markdown")
        
        game["investigated"] = target_id
        game["night_step"] = "locked" 
        if game["timeout_task"] and not game["timeout_task"].done():
            game["timeout_task"].cancel()
        await end_night_phase(chat_id, context)
    else:
        await query.answer("ليس وقت هذا الإجراء حالياً!", show_alert=True)

# ── نهاية الليل والشروق بمؤقت النهار ──────────────────

async def resolve_night(chat_id, context):
    if chat_id not in games: return
    game = games[chat_id]
    target_id = game["mafia_target"]
    healed_id  = game["healed"]

    if target_id:
        role = game["players"][target_id]["role"]
        label = "مافيا 🔫" if role == "مافيا" else "مواطن 👤" 
        if target_id == healed_id:
            msg = f"🌅 *أشرقت شمس الصباح*\n\n✨ الدكتور أنقذ *{game['players'][target_id]['name']}* في اللحظة الأخيرة!\nلم يمت أحد الليلة! 🎉"
        else:
            game["players"][target_id]["alive"] = False
            msg = f"🌅 *أشرقت شمس الصباح*\n\n⚰️ اغتيل *{game['players'][target_id]['name']}* الليلة... وكان {label}"
    else:
        msg = "🌅 *أشرقت شمس الصباح*\n\nمرّت ليلة هادئة، لم يحدث شيء!"

    game["mafia_target"] = None
    game["healed"] = None
    game["investigated"] = None

    winner = check_winner(game)
    if winner:
        await context.bot.send_message(chat_id, msg, parse_mode="Markdown")
        await end_game(chat_id, context, winner)
        return

    game["phase"] = "day"
    game["votes"] = {} 
    
    alive = get_alive(game)
    alive_list = "\n".join(f"• {p['name']}" for p in alive.values())
    kb = [[InlineKeyboardButton(f"🗳️ {p['name']}", callback_data=f"vote_{uid}")] for uid, p in alive.items()]
    kb.append([InlineKeyboardButton("⏭️ تخطي التصويت", callback_data="skip_vote")])
    
    # نرسل رسالة التصويت ونحفظها لتثبيتها
    sent_msg = await context.bot.send_message(chat_id,
        f"{msg}\n\n👥 *اللاعبون الأحياء:*\n{alive_list}\n\n☀️ *بدأ النقاش والتصويت! (المهلة: 5 دقائق) ⏱️*\nمن تظنونه المافيا؟",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown"
    )
    
    # محاولة تثبيت رسالة التصويت
    try:
        await context.bot.pin_chat_message(chat_id, sent_msg.message_id)
        game["pinned_msg_id"] = sent_msg.message_id
    except Exception:
        pass
    
    game["timeout_task"] = asyncio.create_task(day_timeout(chat_id, context))

async def day_timeout(chat_id, context):
    try:
        await asyncio.sleep(120)
        if chat_id in games and games[chat_id]["phase"] == "day":
            try: await context.bot.send_message(chat_id, "⏳ *تذكير: تبقى 3 دقائق على نهاية التصويت!*", parse_mode="Markdown")
            except Exception: pass

        await asyncio.sleep(120)
        if chat_id in games and games[chat_id]["phase"] == "day":
            try: await context.bot.send_message(chat_id, "⏳ *تذكير: تبقى دقيقة واحدة فقط! احسموا أمركم!*", parse_mode="Markdown")
            except Exception: pass

        await asyncio.sleep(60)
        if chat_id in games and games[chat_id]["phase"] == "day":
            try: await context.bot.send_message(chat_id, "⏱️ *انتهى وقت التصويت النهاري! سيتم إغلاق الصندوق وفرز الأصوات الحالية...*", parse_mode="Markdown")
            except Exception: pass
            await resolve_vote(chat_id, context)

    except asyncio.CancelledError:
        pass
    except Exception:
        if chat_id in games and games[chat_id]["phase"] == "day":
            await resolve_vote(chat_id, context)

# ── التصويت الصباحي (المحمي ضد تكرار الفرز) ────────────────

async def vote_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    chat_id = query.message.chat_id
    uid     = query.from_user.id

    if chat_id not in games:
        await query.answer("لا توجد لعبة نشطة!", show_alert=True)
        return

    game = games[chat_id]

    if game["phase"] != "day":
        await query.answer("ليس وقت التصويت حالياً!", show_alert=True)
        return
    if uid not in game["players"]:
        await query.answer("أنت لست لاعباً في هذه اللعبة!", show_alert=True)
        return
    if not game["players"][uid]["alive"]:
        await query.answer("الأموات لا يصوتون! 💀", show_alert=True)
        return

    already = uid in game["votes"]

    if query.data == "skip_vote":
        game["votes"][uid] = "skip"
        await query.answer(f"{'✅ غيّرت صوتك إلى' if already else '✅ صوّتت على'} تخطي التصويت")
    else:
        try: target_id = int(query.data.split("_")[1])
        except Exception: return

        if not game["players"].get(target_id, {}).get("alive"):
            await query.answer("هذا لاعب خارج اللعبة!", show_alert=True)
            return

        game["votes"][uid] = target_id
        name = game["players"][target_id]['name']
        await query.answer(f"{'✅ غيّرت صوتك إلى' if already else '✅ صوّتت على'} {name}")

    alive = get_alive(game)
    if len(game["votes"]) >= len(alive):
        if game["timeout_task"] and not game["timeout_task"].done():
            game["timeout_task"].cancel()
        try: await query.edit_message_reply_markup(reply_markup=None)
        except Exception: pass
        await resolve_vote(chat_id, context)

async def resolve_vote(chat_id, context):
    if chat_id not in games: return
    game = games[chat_id]

    if game["phase"] != "day": return 
    game["phase"] = "resolving_day" 

    # فك تثبيت رسالة التصويت بمجرد انتهاء النهار
    if game.get("pinned_msg_id"):
        try:
            await context.bot.unpin_chat_message(chat_id, game["pinned_msg_id"])
            game["pinned_msg_id"] = None
        except Exception:
            pass

    if game["timeout_task"] and game["timeout_task"] != asyncio.current_task() and not game["timeout_task"].done(): 
        game["timeout_task"].cancel()

    if not game["votes"]:
        game["phase"] = "night"
        game["day"] += 1
        await context.bot.send_message(chat_id, "⏭️ *انتهى الوقت ولم يصوت أحد!*\n\nلم يُعدم أحد اليوم.\n\n🌙 يحل الليل...", parse_mode="Markdown")
        await asyncio.sleep(2)
        await start_mafia_phase(chat_id, context)
        return

    vc = {}
    for t in game["votes"].values(): vc[t] = vc.get(t, 0) + 1
    max_v = max(vc.values())
    candidates = [uid for uid, v in vc.items() if v == max_v]

    if len(candidates) > 1:
        game["phase"] = "night"
        game["day"] += 1
        names = []
        for u in candidates:
            if u == "skip": names.append("تخطي التصويت")
            else: names.append(game["players"][u]["name"])
            
        await context.bot.send_message(chat_id, f"⚖️ *تعادل الأصوات!*\n\nتعادل بين: {', '.join(names)}\nلم يُعدم أحد!\n\n🌙 يحل الليل...", parse_mode="Markdown")
        await asyncio.sleep(2)
        await start_mafia_phase(chat_id, context)
        return

    winner_option = candidates[0]

    if winner_option == "skip":
        game["phase"] = "night"
        game["day"] += 1
        await context.bot.send_message(chat_id, "⏭️ *أغلبية الأصوات اختارت تخطي التصويت!*\n\nلم يُعدم أحد اليوم.\n\n🌙 يحل الليل...", parse_mode="Markdown")
        await asyncio.sleep(2)
        await start_mafia_phase(chat_id, context)
        return

    executed = winner_option
    game["players"][executed]["alive"] = False
    name  = game["players"][executed]["name"]
    role  = game["players"][executed]["role"]
    label = "مافيا 🔫" if role == "مافيا" else "مواطن 👤"
    msg   = f"🗳️ *نتيجة التصويت:*\n\n⚰️ اغتيل *{name}* بـ {max_v} أصوات... وكان {label}"

    winner = check_winner(game)
    if winner:
        await context.bot.send_message(chat_id, msg, parse_mode="Markdown")
        await end_game(chat_id, context, winner)
        return

    game["phase"] = "night"
    game["day"] += 1
    await context.bot.send_message(chat_id, f"{msg}\n\n🌙 يحل الليل مجدداً...", parse_mode="Markdown")
    await asyncio.sleep(2)
    await start_mafia_phase(chat_id, context)

async def end_game(chat_id, context, winner):
    game = games[chat_id]
    if game["timeout_task"] and game["timeout_task"] != asyncio.current_task() and not game["timeout_task"].done(): 
        game["timeout_task"].cancel()
        
    reveal = "\n".join(f"{'💀' if not p['alive'] else '✅'} {p['name']}: {ROLES.get(p['role'],'')} {p['role']}" for p in game["players"].values())
    msg = f"🎉 *انتهت اللعبة!*\n\n{'🏆 فاز المواطنون! قضوا على المافيا!' if winner == 'مواطنون' else '🔫 فازت المافيا! سيطروا على المدينة!'}\n\n📋 *الأدوار:*\n{reveal}"
    await context.bot.send_message(chat_id, msg, parse_mode="Markdown")
    del games[chat_id]

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎭 *أوامر لعبة المافيا:*\n\n/newgame - بدء لعبة\n/begin - بدء اللعبة\n/help - المساعدة\n\n"
        "📌 *كيف تلعب:*\n1. أضف البوت كـ Admin\n2. /newgame\n3. انضم (4 لاعبين+)\n4. /begin\n5. راجع رسائلك الخاصة!",
        parse_mode="Markdown"
    )

async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in games:
        await update.message.reply_text("لا توجد لعبة نشطة حالياً!")
        return
    game = games[chat_id]
    
    # فك التثبيت لو تم إيقاف اللعبة قسرياً وفي رسالة معلقة
    if game.get("pinned_msg_id"):
        try:
            await context.bot.unpin_chat_message(chat_id, game["pinned_msg_id"])
        except Exception:
            pass
            
    if game["timeout_task"] and game["timeout_task"] != asyncio.current_task() and not game["timeout_task"].done(): 
        game["timeout_task"].cancel()
    del games[chat_id]
    await update.message.reply_text("🛑 *تم إيقاف اللعبة!*\n\nيمكنكم بدء لعبة جديدة بكتابة /newgame", parse_mode="Markdown")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start",   start_cmd))
    app.add_handler(CommandHandler("newgame", newgame_cmd))
    app.add_handler(CommandHandler("begin",   begin_cmd))
    app.add_handler(CommandHandler("help",    help_cmd))
    app.add_handler(CommandHandler("stop",    stop_cmd))
    app.add_handler(CallbackQueryHandler(join_callback,   pattern="^join$"))
    app.add_handler(CallbackQueryHandler(leave_callback,  pattern="^leave$"))
    
    app.add_handler(CallbackQueryHandler(night_callback,  pattern="^(mafia|heal|invest)_.*"))
    app.add_handler(CallbackQueryHandler(vote_callback,   pattern="^(vote_.*|skip_vote)"))

    # ── إعدادات الـ Webhook ──────────────────────────────────
    port = int(os.environ.get("PORT", "8080"))
    webhook_url = os.environ.get("WEBHOOK_URL", "").rstrip("/")

    if not webhook_url:
        print("⚠️ لم يتم تحديد WEBHOOK_URL، سيتم التشغيل بوضع polling للتجربة المحلية فقط.")
        app.run_polling()
        return

    print(f"✅ البوت يعمل بوضع webhook على المنفذ {port}...")
    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=TOKEN,                       
        webhook_url=f"{webhook_url}/{TOKEN}",  
    )

if __name__ == "__main__":
    main()
