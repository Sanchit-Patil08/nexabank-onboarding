# 🚀 Hosting NexaBank on Render

Follow these steps to deploy your NexaBank Onboarding System to [Render.com](https://render.com).

## 1. Prepare Your Repository
Ensure your code is pushed to a GitHub or GitLab repository.
- Your project should include the `requirements.txt` file I just created.
- Ensure `app.py` is in the root directory.

## 2. Create a New Web Service on Render
1.  Log in to your **Render Dashboard**.
2.  Click **New +** and select **Web Service**.
3.  Connect your GitHub/GitLab repository.
4.  Configure the following settings:
    - **Name**: `nexabank-onboarding` (or any name you prefer)
    - **Environment**: `Python 3`
    - **Build Command**: `pip install -r requirements.txt`
    - **Start Command**: `gunicorn app:app`

## 3. Configure Environment Variables
In the **Environment** tab of your Render service, add the following variables:
- `PYTHON_VERSION`: `3.11.0` (Recommended for stability)
- `GEMINI_API_KEY`: Your Google Gemini API Key.
- `OCR_API_KEY`: Your OCR.space API Key (if used).
- `FLASK_ENV`: `production`

## 4. Important: Handling the Database (SQLite)
Render's filesystem is **ephemeral**, meaning any data saved to `nexabank.db` (like new users or applications) will be **deleted** every time the server restarts or redeploys.

### Solutions:
- **Free Tier**: Data will reset on every deploy. Use this for demo purposes.
- **Persistent Disk (Paid)**: If you upgrade to a paid plan on Render, you can attach a "Persistent Disk" and move your `instance/nexabank.db` there.
- **External Database**: For a real production app, it is recommended to use **Supabase (PostgreSQL)** or **MongoDB** instead of SQLite.

## 5. System Dependencies (Tesseract OCR)
The `pytesseract` library requires the Tesseract engine to be installed on the server. On Render, you can add Tesseract by going to **Settings** -> **Build & Deploy** -> **Build Command** and changing it to:
```bash
pip install -r requirements.txt && apt-get update && apt-get install -y tesseract-ocr
```
*(Note: `apt-get` might require a custom Dockerfile if Render's default environment doesn't allow it. For a quick demo, OCR might fail but the app will fall back to manual values as I configured.)*

## 6. Deployment
Click **Create Web Service**. After a few minutes, your website will be live at `https://your-app-name.onrender.com`.
