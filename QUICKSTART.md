# 🚀 Quick Start Guide

## Setup (5 minutes)

### 1. Create Virtual Environment
```bash
cd backend
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Mac/Linux
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Setup Supabase Database

1. **Create Supabase Account**
   - Go to https://supabase.com
   - Sign up (free!)
   - Create new project
   - **Save your password!**

2. **Enable pgvector Extension**
   - Dashboard → Database → Extensions
   - Search "vector"
   - Click "Enable"

3. **Run SQL Schema**
   - Dashboard → SQL Editor
   - New query
   - Copy entire content from `backend/supabase_schema.sql`
   - Click "Run"

4. **Get Connection String**
   - Settings → Database
   - Copy "URI" connection string
   - Add `?sslmode=require` at the end

### 4. Configure Environment

```bash
# Copy template
copy .env.example .env

# Edit .env and add:
# 1. Your Supabase DATABASE_URL
# 2. Your OPENAI_API_KEY (optional but recommended)
```

### 5. Test Connection

```bash
python test_connection.py
```

Expected output:
```
✅ Connection successful!
✅ pgvector extension enabled
✅ All expected tables exist!
```

### 6. Start Server

```bash
uvicorn app.main:app --reload
```

Server runs at: http://localhost:8000

### 7. Test API

Open: http://localhost:8000/api/docs

Try these endpoints:
1. **POST /api/v1/areas/** - Create an area
2. **POST /api/v1/menus/upload** - Upload a menu image
3. **GET /api/v1/restaurants/** - List restaurants

---

## Example API Calls

### Create Area
```bash
curl -X POST "http://localhost:8000/api/v1/areas/" \
  -H "Content-Type: application/json" \
  -d '{
    "area_name": "Koramangala",
    "city": "Bangalore",
    "pincode": "560034",
    "state": "Karnataka"
  }'
```

### Upload Menu
```bash
curl -X POST "http://localhost:8000/api/v1/menus/upload" \
  -F "file=@menu_image.jpg" \
  -F "area_name=Koramangala" \
  -F "city=Bangalore" \
  -F "restaurant_name=Green Bowl"
```

---

## Troubleshooting

### Connection Failed?
- Check DATABASE_URL in `.env`
- Ensure `?sslmode=require` is at the end
- Verify Supabase project is active

### Tables Not Found?
- Run SQL schema from `backend/supabase_schema.sql`
- Check Supabase SQL Editor for errors

### Import Errors?
- Ensure virtual environment is activated
- Run `pip install -r requirements.txt`

---

## Project Structure

```
backend/
├── app/
│   ├── api/v1/endpoints/    # API endpoints
│   ├── core/                # Config & database
│   ├── models/              # SQLAlchemy models
│   └── services/            # Business logic
│       ├── ocr/            # OCR engine
│       ├── nlp/            # Menu structuring
│       └── health/         # Health scoring
├── requirements.txt         # Dependencies
├── test_connection.py      # Test script
└── supabase_schema.sql     # Database schema
```

---

## You're Ready! 🎉

Your Menu Intelligence System is now:
- ✅ Connected to Supabase
- ✅ Ready to process menus
- ✅ Calculating health scores
- ✅ Storing structured data

**Start uploading menus and building your database!**
