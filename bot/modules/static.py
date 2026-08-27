import math

def get_human_size(size_bytes: int) -> str:
    if size_bytes == 0:
        return "0 B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"

WelcomeText = """\
👋 Hi **%(first_name)s**, welcome to **OmniArchiver-F2L**! 🌐

I can generate permanent direct download & high-speed streaming links for files directly from your Telegram channels without duplicating files!

**Commands:**
🎬 `/link <message_link>` - Index a single movie/file.
📺 `/batch anime <start_link> <end_link>` - Batch index Anime episodes.
🍿 `/batch series <start_link> <end_link>` - Batch index Web Series.
📊 `/stats` - View database statistics (Admins).
📜 `/privacy` - View Privacy Policy.
❓ `/help` - Show this help menu.
"""

PrivacyText = """
**Privacy Policy**

**1. Data Storage:** File links and message pointers are saved securely in MongoDB without duplicating files.

**2. Download Links:** Each link contains a cryptographically secure token.

**3. User Control:** You can revoke links anytime using the "Revoke" button or commands.

**4. Open Source:** The bot is [open source](https://github.com/WorkerOfArea51/OmniArchiver-F2L). Deploy your own instance for maximum privacy.

__By using this bot, you agree to this policy.__
"""

FileLinksText = """
📂 **File:** `%(file_name)s`
📦 **Size:** `%(file_size)s`
🏷️ **Category:** `%(category)s`

📥 **Download Link:**
`%(dl_link)s`
"""

MediaLinksText = """
🎬 **File:** `%(file_name)s`
📦 **Size:** `%(file_size)s`
🏷️ **Category:** `%(category)s`

📥 **Download Link:**
`%(dl_link)s`

▶️ **Stream Link:**
`%(stream_link)s`
"""

InvalidQueryText = "Query data mismatched."
MessageNotExist = "File does not exist or has been revoked."
LinkRevokedText = "The link has been revoked successfully from the database."
InvalidPayloadText = "Invalid payload."
UserNotInAllowedList = "You are not allowed to use this bot."
AdminOnlyText = "⚠️ This command is restricted to Bot Administrators."
InvalidLinkText = "❌ Invalid Telegram message link provided.\n\n**Usage:**\n`/link https://t.me/c/1234567890/42` or `/link https://t.me/channel_name/42`"
InvalidBatchUsageText = """❌ **Invalid Batch Command Usage!**

**Format:**
`/batch <category> <start_message_link> <end_message_link>`

**Examples:**
• `/batch anime https://t.me/c/1234567890/10 https://t.me/c/1234567890/25`
• `/batch series https://t.me/c/1234567890/50 https://t.me/c/1234567890/60`
"""
