# Deployment Guide — Render + Vercel

Complete this in order. Takes ~45 minutes total.

---

## 0. Before you start — get your Google token

Do this on your local machine (not on Render):

```bash
cd backend
pip install -r requirements.txt
# Put your credentials.json here (from Google Cloud Console)
python get_google_token.py
```

Browser opens → sign in with the Gmail account the bot will use → approve.
Copy the printed JSON — you'll paste it as `GOOGLE_TOKEN_JSON` in Render.

---

## 1. Push to GitHub

```bash
git init
git add .
git commit -m "initial commit"
# Create a NEW repo on github.com (do NOT tick "Add README")
git remote add origin https://github.com/YOUR_USERNAME/nexus-ai.git
git push -u origin main
```

**Double-check before pushing:**
```bash
git status   # .env must NOT appear in this list
cat .gitignore   # confirm .env is listed
```

---

## 2. Deploy Backend → Render

1. Go to [render.com](https://render.com) → **New** → **Web Service**
2. Connect your GitHub repo
3. Settings:
   - **Root Directory:** `backend`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Region:** Singapore (closest to India)
   - **Plan:** Free

4. **Environment Variables** — click "Add from .env" or add one by one:

| Key | Value |
|-----|-------|
| `GEMINI_API_KEY` | your key |
| `SUPABASE_URL` | `https://xxxx.supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY` | your service role key |
| `GOOGLE_CLIENT_ID` | from credentials.json |
| `GOOGLE_CLIENT_SECRET` | from credentials.json |
| `GOOGLE_TOKEN_JSON` | the JSON from step 0 (paste as single line) |
| `TWILIO_ACCOUNT_SID` | your SID |
| `TWILIO_AUTH_TOKEN` | your auth token |
| `TWILIO_WHATSAPP_NUMBER` | `whatsapp:+14155238886` |
| `WHATSAPP_DEV_NUMBER` | `+91XXXXXXXXXX` |
| `META_VERIFY_TOKEN` | `nexus_verify_123` |

5. Click **Create Web Service** → wait ~3 minutes for first deploy

6. Your backend URL will be: `https://nexus-ai-backend.onrender.com`

7. Test it:
```
https://nexus-ai-backend.onrender.com/health
→ {"status":"ok"}
```

---

## 3. Set up Supabase Schema

1. Go to [supabase.com](https://supabase.com) → your project → **SQL Editor**
2. Paste the entire contents of `backend/schema.sql`
3. Click **Run**
4. Go to **Authentication → Users → Add user** → create your dashboard login

---

## 4. Connect Twilio Webhook

1. Go to [console.twilio.com](https://console.twilio.com)
2. **Messaging → Try it out → Send a WhatsApp message**
3. Set **"When a message comes in":**
   ```
   https://nexus-ai-backend.onrender.com/webhook/whatsapp
   ```
4. **Join the sandbox** — from your phone, text the join code to `+14155238886`
5. **Join from your personal number too** (for the dev channel)

---

## 5. Deploy Dashboard → Vercel

```bash
cd dashboard
npm install
npm run build   # test build locally first
```

If build passes:

```bash
npm i -g vercel
vercel --prod
```

Or via GitHub:
1. [vercel.com](https://vercel.com) → **New Project** → Import your GitHub repo
2. **Root Directory:** `dashboard`
3. **Framework:** Vite
4. **Environment Variables:**

| Key | Value |
|-----|-------|
| `VITE_SUPABASE_URL` | `https://xxxx.supabase.co` |
| `VITE_SUPABASE_ANON_KEY` | your **anon** key (not service role) |

5. Click **Deploy**
6. Your dashboard URL: `https://nexus-ai-dashboard.vercel.app`

---

## 6. Keep Render Alive (free tier spins down after 15 min)

1. Go to [cron-job.org](https://cron-job.org) → create free account
2. **New cronjob:**
   - URL: `https://nexus-ai-backend.onrender.com/health`
   - Schedule: every 10 minutes
3. Save → enable

This prevents cold starts during the demo.

---

## 7. Final Test (all channels)

**WhatsApp:**
```
Send to sandbox number: "Hi I need a BI dashboard. Budget 1 lakh, I'm the CTO, 2 months."
Expected: bot replies, lead appears in dashboard instantly
```

**Email:**
```
Send an email to your connected Gmail inbox
Expected: appears in dashboard Email tab within 60 seconds
```

**Dashboard:**
```
Open https://nexus-ai-dashboard.vercel.app
Log in → see leads, conversations, meetings live
```

---

## 8. Environment Variable Summary

### Render (backend)
```
GEMINI_API_KEY
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET
GOOGLE_TOKEN_JSON          ← single-line JSON string
TWILIO_ACCOUNT_SID
TWILIO_AUTH_TOKEN
TWILIO_WHATSAPP_NUMBER     ← whatsapp:+14155238886
WHATSAPP_DEV_NUMBER        ← +91XXXXXXXXXX
META_VERIFY_TOKEN          ← nexus_verify_123
```

### Vercel (dashboard)
```
VITE_SUPABASE_URL
VITE_SUPABASE_ANON_KEY     ← anon key, NOT service role
```

---

## Common Issues

**Render deploy fails**
- Check Build Logs in Render dashboard
- Usually a missing package — add to requirements.txt

**Bot not replying on WhatsApp**
- Check Render logs for errors
- Verify webhook URL is set correctly in Twilio (must be https, not http)
- Make sure you joined the sandbox from your phone

**Dashboard shows blank / auth error**
- Make sure you used the ANON key (not service role) for Vercel
- Check Supabase → Authentication → Users — your login user must exist

**Gmail not polling**
- GOOGLE_TOKEN_JSON must be a valid single-line JSON string
- Refresh token expires if you don't use it — re-run get_google_token.py

**Render cold start (first request slow)**
- cron-job.org keeps it warm — make sure it's enabled
