# %% Dependencies
import os
import logging
import pickle
import pymongo
import telegram
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    ConversationHandler,
    CallbackContext,
    PicklePersistence,
)
from telegram.utils import helpers
from bson.json_util import dumps
from multicolorcaptcha import CaptchaGenerator
from jokes import getJoke

# %% Constants and Globals
USERINFO = {}  # holds user information
CAPTCHA_DATA = {}
STATUS_PATH = "./conversationbot/botconfig.p"

# %% Load environment variables
COIN_SYMBOL = os.environ["COIN_SYMBOL"]
COIN_NAME = os.environ["COIN_NAME"]
AIRDROP_AMOUNT = "{:,.2f}".format(float(os.environ["AIRDROP_AMOUNT"]))
AIRDROP_DATE = os.environ["AIRDROP_DATE"]
BOT_TOKEN = os.environ["BOT_TOKEN"]
AIRDROP_NETWORK = os.environ["AIRDROP_NETWORK"]
REFERRAL_REWARD = float(os.environ["REFERRAL_REWARD"])
COIN_PRICE = os.environ["COIN_PRICE"]
WEBSITE_URL = os.environ["WEBSITE_URL"]
DB_URI = os.environ["DB_URI"]
EXPLORER_URL = os.environ["EXPLORER_URL"]
ADMIN_USERNAME = os.environ["ADMIN_USERNAME"]

# Social media links
TWITTER_LINKS = "\n".join(os.environ["TWITTER_LINKS"].split(","))
TELEGRAM_LINKS = "\n".join(os.environ["TELEGRAM_LINKS"].split(","))
DISCORD_LINKS = "\n".join(os.environ["DISCORD_LINKS"].split(","))

# Airdrop settings
MAX_USERS = int(os.environ["MAX_USERS"])
MAX_REFS = int(os.environ["MAX_REFS"])
CAPTCHA_ENABLED = os.environ["CAPTCHA_ENABLED"]

# %% MongoDB Connection
myclient = pymongo.MongoClient(DB_URI)
mydb = myclient["airdrop"]
users = mydb["users"]
users.create_index([('ref', pymongo.TEXT)], name='search_index', default_language='english')
users.create_index("userId")

# %% Bot status
if os.path.exists(STATUS_PATH):
    BOT_STATUS = pickle.load(open(STATUS_PATH, "rb"))
else:
    BOT_STATUS = {"status": "ON"}

# %% Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
print(BOT_TOKEN)

# %% Updater and Dispatcher
persistence = PicklePersistence(filename='conversationbot/conversationbot')
updater = Updater(token=BOT_TOKEN, use_context=True, persistence=persistence)
dispatcher = updater.dispatcher

# %% Message Strings
SYMBOL = f"\n⭐️ 1 {COIN_SYMBOL} = {COIN_PRICE}" if COIN_PRICE != "0" else ""
EXPLORER_URL = f"\nContract: {EXPLORER_URL}" if EXPLORER_URL else ""
WEBSITE_URL = f"\nWebsite: {WEBSITE_URL}" if WEBSITE_URL else ""

WELCOME_MESSAGE = f"""
Hello, NAME! I am your friendly {COIN_NAME} Airdrop bot
{SYMBOL}
⭐️ For Joining - Get {AIRDROP_AMOUNT} {COIN_SYMBOL}
⭐️ For each referral - Get {"{:,.2f}".format(REFERRAL_REWARD)} {COIN_SYMBOL}

📘By Participating you are agreeing to the {COIN_NAME} (Airdrop) Program Terms and Conditions. Please see pinned post for more information.
Click "🚀 Join Airdrop" to proceed"""

PROCEED_MESSAGE = f"""
🔹 Airdrop Reward = *{AIRDROP_AMOUNT} {COIN_SYMBOL}*
🔹 Extra reward per referral = *{"{:,.2f}".format(REFERRAL_REWARD)} {COIN_SYMBOL}* (max {MAX_REFS}){SYMBOL}

📢 Airdrop Rules

✏️ Mandatory Tasks:
- Join our Telegram group(s)
- Follow our Twitter page(s)
- Join our Discord server(s)

NOTE: Users found cheating would be disqualified & banned immediately.

Airdrop Date: *{AIRDROP_DATE}*{EXPLORER_URL}
{WEBSITE_URL}
"""

MAKE_SURE_TELEGRAM = f"""
🔹 Do not forget to join our Telegram group(s)
{TELEGRAM_LINKS}
"""

FOLLOW_TWITTER_TEXT = f"""
🔹 Follow our Twitter page(s)
{TWITTER_LINKS}
"""

JOIN_DISCORD_TEXT = f'''
🔹 Join our Discord server(s)
{DISCORD_LINKS}
'''

SUBMIT_BEP20_TEXT = f"""
Type in *your Wallet Address*

Please make sure your wallet supports the *{AIRDROP_NETWORK}*

Example:
0x3136D6e327018d4124C222E15f4aD7fA8621f16E

_Incorrect Details? Use_ /restart _command to start over._
"""

JOINED = f"""
Thank you!
Rewards would be sent out automatically to your {AIRDROP_NETWORK} address on the {AIRDROP_DATE}

Don't forget to:
🔸 Stay in the telegram channels
🔸 Follow all the social media channels for the updates

Your personal referral link (+{"{:,.2f}".format(REFERRAL_REWARD)} {COIN_SYMBOL} for each referral)
REPLACEME
"""

WITHDRAWAL_TEXT = f"""
Withdrawals would be sent out automatically to your {AIRDROP_NETWORK} address on the {AIRDROP_DATE}
NOTE: Users found cheating would be disqualified & banned immediately."""

BALANCE_TEXT = f"""
{COIN_NAME} Airdrop Balance: *IARTBALANCE*
Referral Balance: *REFERRALBALANCE*
"""

# %% Utility Functions
def setBotStatus(status):
    BOT_STATUS["status"] = status
    pickle.dump(BOT_STATUS, open(STATUS_PATH, "wb"))

def getUserInfo(id):
    user = users.find_one({"userId": id})
    if user:
        refs = users.find({"ref": str(id)})
        user["refCount"] = refs.count()
    return user

def maxNumberReached(update, context):
    update.message.reply_text("Hey! Thanks for your interest but it seems like the maximum amount of users has been reached.")
    return ConversationHandler.END

def botStopped(update, context):
    update.message.reply_text("The airdrop has been completed. Thanks for your interest.")
    return ConversationHandler.END

def botPaused(update, context):
    update.message.reply_text("The airdrop has been temporarily paused, please try again later", reply_markup=ReplyKeyboardMarkup([["/start"]]))
    return ConversationHandler.END

def checkCaptcha(update, context):
    user = update.message.from_user
    text = update.message.text
    if CAPTCHA_DATA[user.id] != text:
        update.message.reply_text("Invalid captcha!")
        return generateCaptcha(update, context)
    else:
        NAME = getName(user)
        update.message.reply_text(text="Correct!", parse_mode=telegram.ParseMode.MARKDOWN)
        update.message.reply_text(text=WELCOME_MESSAGE.replace("NAME", NAME), reply_markup=ReplyKeyboardMarkup([['🚀 Join Airdrop']]), parse_mode=telegram.ParseMode.MARKDOWN)
        CAPTCHA_DATA[user.id] = True
        return PROCEED

def start(update, context):
    user = update.message.from_user
    CAPTCHA_DATA[user.id] = False
    if user.id not in USERINFO:
        USERINFO[user.id] = {}

    refferal = update.message.text.replace("/start", "").strip()
    if refferal and refferal != str(user.id) and "ref" not in USERINFO[user.id]:
        USERINFO[user.id]["ref"] = refferal
    else:
        USERINFO[user.id]["ref"] = False

    NAME = getName(user)
    if getUserInfo(user.id):
        update.message.reply_text(text="It seems like you have already joined!", reply_markup=ReplyKeyboardMarkup(reply_keyboard))
        return LOOP

    count = users.count_documents({})
    if count >= MAX_USERS:
        return maxNumberReached(update, context)

    if BOT_STATUS["status"] == "STOPPED":
        return botStopped(update, context)

    if BOT_STATUS["status"] == "PAUSED":
        return botPaused(update, context)

    if CAPTCHA_ENABLED == "YES" and not CAPTCHA_DATA[user.id]:
        return generateCaptcha(update, context)
    else:
        update.message.reply_text(text=WELCOME_MESSAGE.replace("NAME", NAME), reply_markup=ReplyKeyboardMarkup([['🚀 Join Airdrop']]), parse_mode=telegram.ParseMode.MARKDOWN)
    return PROCEED

def generateCaptcha(update, context):
    user = update.message.from_user
    generator = CaptchaGenerator(2)
    captcha = generator.gen_captcha_image(difficult_level=3)
    image = captcha["image"]
    characters = captcha["characters"]
    CAPTCHA_DATA[user.id] = characters
    filename = f"{user.id}.png"
    image.save(filename, "png")
    photo = open(filename, "rb")
    update.message.reply_photo(photo)
    update.message.reply_text("Please type in the numbers on the image", reply_markup=ReplyKeyboardRemove())
    return CAPTCHASTATE

def submit_details(update, context):
    update.message.reply_text(text=PROCEED_MESSAGE, parse_mode=telegram.ParseMode.MARKDOWN)
    update.message.reply_text(text="Please click on \"Submit Details\" to proceed", parse_mode=telegram.ParseMode.MARKDOWN, reply_markup=ReplyKeyboardMarkup([['Submit Details']]))
    return SUBMITDETAILS

def joined_channels(update, context):
    update.message.reply_text(text=MAKE_SURE_TELEGRAM, parse_mode=telegram.ParseMode.MARKDOWN)
    update.message.reply_text(text=FOLLOW_TWITTER_TEXT, parse_mode=telegram.ParseMode.MARKDOWN)
    update.message.reply_text(text=JOIN_DISCORD_TEXT, parse_mode=telegram.ParseMode.MARKDOWN)
    update.message.reply_text(text=SUBMIT_BEP20_TEXT, parse_mode=telegram.ParseMode.MARKDOWN)
    return SUBMITBEP20

def submit_bep20(update, context):
    global users
    user = update.message.from_user
    bep20 = update.message.text.strip()
    ref = USERINFO[user.id]["ref"]
    update.message.reply_text(text="Thanks for submitting your details", reply_markup=ReplyKeyboardMarkup(reply_keyboard))
    update.message.reply_text(text=WITHDRAWAL_TEXT, parse_mode=telegram.ParseMode.MARKDOWN)
    link = helpers.create_deep_linked_url(context.bot.get_me().username, str(user.id))

    users.insert_one({
        "userId": user.id,
        "username": user.username,
        "ref": ref,
        "wallet": bep20,
    })

    update.message.reply_text(text=JOINED.replace("REPLACEME", link), parse_mode=telegram.ParseMode.MARKDOWN)
    return LOOP

def statistics(update, context):
    admin = update.message.from_user.username
    if admin != ADMIN_USERNAME:
        update.message.reply_text("Sorry you can't use this command")
        return

    count = users.count_documents({})
    text = f"*{COIN_NAME}* Airdrop stats\n"
    text += f"*Users:* {count} / {MAX_USERS}\n\n"

    cursor = users.find({})

    for doc in cursor:
        text += f"Name: @{doc['username']}  Wallet: {doc['wallet']}\n"

    if len(text) < 4000:
        update.message.reply_text(text, parse_mode=telegram.ParseMode.MARKDOWN)
    else:
        x = dumps(cursor)
        with open("/tmp/data.json", "w") as f:
            f.write(x)
        context.bot.send_document(update.message.chat_id, document=open("/tmp/data.json", "rb"))

def balance(update, context):
    user = update.message.from_user
    doc = getUserInfo(user.id)
    refs = doc["refCount"]
    balance = AIRDROP_AMOUNT
    refBalance = "{:,.2f}".format(refs * REFERRAL_REWARD)
    update.message.reply_text(text=BALANCE_TEXT.replace("IARTBALANCE", balance).replace("REFERRALBALANCE", refBalance), parse_mode=telegram.ParseMode.MARKDOWN)

def restart(update, context):
    del USERINFO[update.message.from_user.id]
    update.message.reply_text("Restarting process...", reply_markup=ReplyKeyboardRemove())
    start(update, context)

def getName(user):
    if user.username:
        NAME = f"@{user.username}"
    elif user.last_name:
        NAME = f"{user.first_name} {user.last_name}"
    else:
        NAME = f"{user.first_name}"
    return NAME

# %% Handlers
START, PROCEED, SUBMITDETAILS, JOINCHANNELS, SUBMITBEP20, LOOP, CAPTCHASTATE = range(7)
reply_keyboard = [["Statistics"], ["My Balance"], ["/start"], ["/restart"]]

start_handler = CommandHandler('start', start)
balance_handler = CommandHandler('balance', balance)
stat_handler = CommandHandler('stats', statistics)
restart_handler = CommandHandler('restart', restart)

conv_handler = ConversationHandler(
    entry_points=[start_handler],
    states={
        PROCEED: [MessageHandler(Filters.regex('^(🚀 Join Airdrop)$'), submit_details)],
        SUBMITDETAILS: [MessageHandler(Filters.regex('^(Submit Details)$'), joined_channels)],
        SUBMITBEP20: [MessageHandler(Filters.text, submit_bep20)],
        LOOP: [MessageHandler(Filters.regex('^(Statistics)$'), statistics),
               MessageHandler(Filters.regex('^(My Balance)$'), balance)],
        CAPTCHASTATE: [MessageHandler(Filters.text, checkCaptcha)],
    },
    fallbacks=[start_handler, restart_handler],
    persistent=True,
    name="my_conversation",
)

# %% Add Handlers
dispatcher.add_handler(conv_handler)
dispatcher.add_handler(balance_handler)
dispatcher.add_handler(stat_handler)
dispatcher.add_handler(restart_handler)

# %% Start Polling
updater.start_polling()
updater.idle()
