# 🏨 Astana Hotel — AI Call Center — Setup Guide

This document is a step-by-step guide to running the project **from scratch on another computer**.

---

## 📋 Requirements

Before you start, make sure the following are installed:

| Software | Version | Download |
|----------|---------|----------|
| **Python** | 3.11+ | https://www.python.org/downloads/ |
| **Docker Desktop** | Latest | https://www.docker.com/products/docker-desktop/ |
| **Git** *(optional)* | Latest | https://git-scm.com/ |

> ⚠️ **Windows users:** When installing Python, check the **"Add Python to PATH"** option!

---

## 🔑 API Keys — Get These First

The system needs two API keys. Both are **free**:

### 1. Groq API Key (Speech-to-Text)
1. Go to [console.groq.com](https://console.groq.com)
2. Sign up (a Google account works)
3. Click **API Keys** → **Create API Key**
4. Copy and save the key (it starts with `gsk_...`)

### 2. Gemini API Key (Language Model)
1. Go to [aistudio.google.com](https://aistudio.google.com)
2. Click **Get API key** → **Create API key**
3. Copy and save the key (it starts with `AIza...`)

---

## ⚙️ Setup Steps

### Step 1 — Open the project

Extract the provided folder somewhere on your computer (e.g. `C:\Projects\Astana\`).

Open a terminal (PowerShell or CMD) and go to the folder:
```
cd C:\Projects\Astana
```

---

### Step 2 — Create the `.env` file

There is a file named `.env.example` in the folder. Create your `.env` from it:

**Windows PowerShell:**
```powershell
Copy-Item .env.example .env
```

**CMD:**
```cmd
copy .env.example .env
```

Now open the `.env` file in Notepad (or VS Code) and fill in the following lines:

```env
STT_PROVIDER=groq
GROQ_API_KEY=gsk_paste_your_groq_key_here

LLM_PROVIDER=gemini
GEMINI_API_KEY=AIza_paste_your_gemini_key_here
```

**Save** and close the file.

---

### Step 3 — Create a virtual environment and install packages

**Run these commands in the terminal, one after another:**

```powershell
# Create the virtual environment
python -m venv .venv

# Activate the virtual environment
.venv\Scripts\activate

# Install the required packages (may take 5-10 min)
pip install -r requirements.txt
```

> 💡 **Note:** During installation the `torch` package (~2.5 GB) will be downloaded — depending on your internet connection, this can take a while.

---

### Step 4 — Start Docker (Database)

**Open Docker Desktop** (double-click the Docker icon in the system tray and wait for it to start).

Then run this command in the terminal:

```powershell
docker compose up -d
```

This command automatically:
- ✅ Creates the PostgreSQL database
- ✅ Seeds it with hotel rooms, services, prices, etc.
- ✅ Builds a one-year room availability schedule

To check that everything is running:
```powershell
docker compose ps
```
You should see the service (`hotel_db`) in a **"healthy"** state.

---

### Step 5 — Start the server

```powershell
.venv\Scripts\python -m uvicorn web.server:app --app-dir src --port 8000
```

The server is ready when you see these lines in the terminal:
```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000
```

> 🕐 **On the first run**, the AI models (bge-m3 ~600MB) will be downloaded — wait 1-2 minutes.

---

### Step 6 — Open the browser

Open your browser (Chrome, Edge, Firefox) and go to:

```
http://localhost:8000
```

🎉 İbrahim's interface will open!

---

## 🔁 Running It Next Time

Each time you want to use it, you only need:

```powershell
# 1. Start Docker (every time)
docker compose up -d

# 2. Start the server
.venv\Scripts\python -m uvicorn web.server:app --app-dir src --port 8000
```

---

## 🛑 Stopping

```powershell
# Stop the server: Ctrl + C (in the terminal)

# Stop Docker:
docker compose down
```

---

## ❓ Common Problems

### "Port 8000 is already in use"
```powershell
# Use a different port:
.venv\Scripts\python -m uvicorn web.server:app --app-dir src --port 8001
# Then: http://localhost:8001
```

### "Docker daemon is not running"
Open Docker Desktop and wait for it to fully start (until the icon stabilizes).

### "Microphone permission denied"
Click the lock icon in the browser address bar → allow microphone access.

### "pip install failed"
```powershell
# Upgrade pip:
python -m pip install --upgrade pip
# Then try again:
pip install -r requirements.txt
```

---

## 📞 Support

If any problem occurs, save the error message from the terminal output — it will be needed to solve the issue.
