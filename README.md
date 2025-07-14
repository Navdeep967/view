# 📦 View Main – Proxy Management Panel with Telegram Bot

View Main is a Flask-based web application with Telegram bot integration for managing proxy sessions, user access, and dashboard analytics. Ideal for managing proxies and users via a web panel with admin controls.

---

## 🔧 Features

- User registration & login system
- Admin dashboard with user limits
- Proxy upload, listing, and session tracking
- Integrated Telegram bot for access requests and alerts
- HTML templates for all UI pages

---

## 🚀 Setup Instructions

### 1. 📁 Clone or Upload the Project

```bash
git clone https://github.com/yourusername/view-main.git
cd view-main
```

### 2. 📦 Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. ✏️ Required Configuration

#### 🔐 `main.py`

Open `main.py` and set your Flask secret key:

```python
app.config['SECRET_KEY'] = 'your-secret-key-change-this'
```

You can also change the SQLite DB location if needed:

```python
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///video_grid.db'
```

#### 🤖 `telegram_bot.py`

Open `telegram_bot.py` and configure:

```python
BOT_TOKEN = 'your-bot-token-here'          # From @BotFather
ADMIN_CHAT_ID = 'your-admin-chat-id-here'  # Use @userinfobot to get your ID
```

---

## 🧠 Project Structure

```
view-main/
├── main.py                 # Flask app
├── telegram_bot.py         # Telegram bot logic
├── proxy_manager.py        # Proxy storage handler
├── templates/              # HTML pages
├── requirements.txt
```

---

## 🛠️ How to Run

### Run the Web App

```bash
python main.py
```

- Visit: `http://127.0.0.1:5000`
- Register a user and log in

### Run the Telegram Bot (in a second terminal)

```bash
python telegram_bot.py
```

---

## 🧪 How It Works

1. **User Access**
   - Users register through the web app.
   - They request access, which is forwarded to the admin via the bot.
   - Admin approves/rejects using Telegram.

2. **Admin Panel**
   - Admin can log in to `/admin` (if implemented) and manage user limits, proxies, and sessions.

3. **Proxy Upload**
   - Upload and view active proxies in the dashboard (`proxy_management.html`).

4. **Templates**
   - Modify any HTML page in the `templates/` folder to customize the UI.

---

## 🧾 Important Notes

- ✅ Always start both `main.py` and `telegram_bot.py` for full functionality.
- ⚠️ Keep your bot token and secret keys secure.
- 🗂 The SQLite database (`video_grid.db`) is created automatically.

---

## 📬 Contact

- 👤 Owner: **nav**
- 🕹 Discord: `nav_here`
- ✈️ Telegram: [@ykmehhh](https://t.me/ykmehhh)

---

## 🪪 License

Free to use, modify, and redistribute for educational or personal use. For commercial use, please contact the owner.