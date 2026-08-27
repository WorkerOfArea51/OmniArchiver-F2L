<div align="center"><h1>🌐 OmniArchiver-F2L</h1>
<b>An open-source Python Telegram bot to transmit Telegram files over HTTP (Stream & Direct Download).</b>
</div><br>

## **📑 INDEX**

* [**⚙️ Installation**](#installation)
  * [Python & Git](#i-1)
  * [Download](#i-2)
  * [Requirements](#i-3)
* [**📝 Variables**](#variables)
* [**🕹 Deployment**](#deployment)
  * [Locally](#d-1)
  * [Docker](#d-2)
  * [Alwaysdata](#d-3)
* [**❤️ Credits**](#credits)

<a name="installation"></a>

## ⚙️ Installation

<a name="i-1"></a>

**1. Install Python & Git:**

For Windows:
```
winget install Python.Python.3.11
winget install Git.Git
```
For Linux:
```
sudo apt-get update && sudo apt-get install -y python3.11 git python3-pip
```
For MacOS:
```
brew install python@3.11 git
```
For Termux:
```
pkg install python -y
pkg install git -y
```

<a name="i-2"></a>

**2. Download repository:**
```
git clone https://github.com/WorkerOfArea51/OmniArchiver-F2L.git
```

**3. Change Directory:**

```
cd OmniArchiver-F2L
```

<a name="i-3"></a>

**4. Install requirements:**

```
pip install -r requirements.txt
```

<a name="variables"></a>

## 📝 Variables
**The variables listed below should be defined either in [config.py](https://github.com/WorkerOfArea51/OmniArchiver-F2L/blob/main/bot/config.py) file or as environment variables, depending on your setup.**
* `API_ID` | `TELEGRAM_API_ID`: API ID of your Telegram account, can be obtained from [My Telegram](https://my.telegram.org). `int`
* `API_HASH` | `TELEGRAM_API_HASH`: API hash of your Telegram account, can be obtained from [My Telegram](https://my.telegram.org). `str`
* `OWNER_ID`: ID of your Telegram account, can be obtained by sending **/info** to [@DumpJsonBot](https://t.me/DumpJsonBot) or [@userinfobot](https://t.me/userinfobot). `int`
* `ALLOWED_USER_IDS`: A list of Telegram account IDs (separated by spaces) that are permitted to use the bot. Leave this field empty to allow anyone to use it. `str`
* `BOT_USERNAME` | `TELEGRAM_BOT_USERNAME`: Username of your Telegram bot, create one using [@BotFather](https://t.me/BotFather). `str`
* `BOT_TOKEN` | `TELEGRAM_BOT_TOKEN`: Telegram API token of your bot, can be obtained from [@BotFather](https://t.me/BotFather). `str`
* `CHANNEL_ID` | `TELEGRAM_CHANNEL_ID`: ID of the channel where bot will forward all files received from users, can be obtained by forwarding any message from channel to [@DumpJsonBot](https://t.me/DumpJsonBot) and looking for `forward_from_chat` key. `int`
* `SECRET_CODE_LENGTH`: Number of characters that file code should contain, by default `24`. `int`
* `BASE_URL`: Base URL that bot should use while generating file links, can be FQDN and by default `http://127.0.0.1:8080`. `str`
* `BIND_ADDRESS`: Bind address for web server, by default `0.0.0.0` to run on all possible addresses. `str`
* `PORT`: Port for web server to run on, by default `8080`. `int`

<a name="deployment"></a>

## 🕹 Deployment

> [!NOTE]
> This bot is designed for personal use or to share with friends and family.

<a name="d-1"></a>

**1. Running locally:**
```
python -m bot
```

<a name="d-2"></a>

**2. Using Docker:**
* Build Docker image:
```
docker build -t omniarchiver-f2l .
```
* Run the Docker container:
```
docker run -p 8080:8080 omniarchiver-f2l
```

<a name="d-3"></a>

**3. Alwaysdata Deployment:**
* Set up a **User program** site on Alwaysdata pointing to `python -m bot`.
* Set environment variables in Alwaysdata or through a `start.sh` script.

<a name="credits"></a>

## ❤️ Credits

- [**WorkerOfArea51**](https://github.com/WorkerOfArea51): Maintainer of OmniArchiver-F2L.
