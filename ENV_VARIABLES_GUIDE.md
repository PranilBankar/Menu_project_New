# 🔧 Environment Variables Guide

## Quick Setup

```bash
cd backend
copy .env.example .env
# Edit .env with your actual values
```

---

## 📋 Required Variables

### **DATABASE_URL** (Required)
Your Supabase PostgreSQL connection string.

**How to get it:**
1. Go to https://supabase.com/dashboard
2. Select your project
3. Settings → Database
4. Copy "URI" connection string
5. **Add `?sslmode=require` at the end!**

**Format:**
```
postgresql://postgres:[PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres?sslmode=require
```

**Example:**
```
DATABASE_URL=postgresql://postgres:MyPass123@db.abcdefg.supabase.co:5432/postgres?sslmode=require
```

---

## 🎯 Recommended Variables

### **OPENAI_API_KEY** (Highly Recommended)
For LLM-powered menu structuring (much better than rule-based).

**How to get it:**
1. Go to https://platform.openai.com/api-keys
2. Create new secret key
3. Copy and paste into .env

**Example:**
```
OPENAI_API_KEY=sk-proj-abc123xyz789...
```

**Without it:** System falls back to basic rule-based parsing (less accurate)

---

## ⚙️ Optional Variables

### **SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_KEY**
For future features (authentication, real-time, storage).

**How to get them:**
1. Supabase Dashboard → Settings → API
2. Copy Project URL
3. Copy anon public key
4. Copy service_role key (keep secret!)

**Example:**
```
SUPABASE_URL=https://abcdefg.supabase.co
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### **REDIS_URL**
For caching (Phase 4). Leave as default for now.

**Default:**
```
REDIS_URL=redis://localhost:6379/0
```

### **SECRET_KEY**
For JWT tokens and security. Generate a secure one:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

**Example:**
```
SECRET_KEY=xK9mP2nQ5rT8wZ1aB4cD7eF0gH3iJ6kL9mN2oP5qR8sT
```

### **OCR_ENGINE**
Choose OCR engine: `paddleocr` (free, local) or `google_vision` (paid, cloud)

**Default (recommended):**
```
OCR_ENGINE=paddleocr
```

### **LLM_MODEL**
Choose OpenAI model for menu structuring.

**Options:**
- `gpt-4-turbo-preview` - Best accuracy, higher cost
- `gpt-3.5-turbo` - Good accuracy, lower cost

**Default:**
```
LLM_MODEL=gpt-4-turbo-preview
```

### **EMBEDDING_MODEL**
Model for generating embeddings (Phase 2).

**Default (recommended):**
```
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_DIMENSION=384
```

### **UPLOAD_DIR**
Directory for storing uploaded menu images.

**Default:**
```
UPLOAD_DIR=data/raw
```

### **CORS_ORIGINS**
Allowed frontend URLs (comma-separated).

**Default:**
```
CORS_ORIGINS=http://localhost:3000,http://localhost:5173,http://localhost:8080
```

---

## 📝 Complete Example .env File

```env
# Application
APP_NAME="Menu Intelligence System"
APP_VERSION="1.0.0"
DEBUG=True

# Database (REQUIRED)
DATABASE_URL=postgresql://postgres:MyPass123@db.abcdefg.supabase.co:5432/postgres?sslmode=require
DB_ECHO=False

# Supabase (Optional)
SUPABASE_URL=https://abcdefg.supabase.co
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# Redis (Optional)
REDIS_URL=redis://localhost:6379/0
CACHE_TTL=3600

# Security
SECRET_KEY=xK9mP2nQ5rT8wZ1aB4cD7eF0gH3iJ6kL9mN2oP5qR8sT
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# OCR
OCR_ENGINE=paddleocr
GOOGLE_VISION_API_KEY=

# LLM (RECOMMENDED)
OPENAI_API_KEY=sk-proj-abc123xyz789...
LLM_MODEL=gpt-4-turbo-preview
LLM_TEMPERATURE=0.3

# Embeddings
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_DIMENSION=384

# File Upload
UPLOAD_DIR=data/raw
MAX_UPLOAD_SIZE=10485760
ALLOWED_EXTENSIONS=.jpg,.jpeg,.png,.pdf

# CORS
CORS_ORIGINS=http://localhost:3000,http://localhost:5173,http://localhost:8080
```

---

## ✅ Minimum Configuration (To Get Started)

You only **need** these two:

```env
DATABASE_URL=postgresql://postgres:YourPass@db.xxxxx.supabase.co:5432/postgres?sslmode=require
OPENAI_API_KEY=sk-proj-your-key-here
```

All other variables have sensible defaults!

---

## 🔒 Security Best Practices

1. **Never commit .env file** - Already in `.gitignore`
2. **Use strong passwords** - For Supabase database
3. **Keep API keys secret** - Never share or expose
4. **Rotate keys regularly** - Change passwords/keys periodically
5. **Use different keys** - Dev vs Production environments

---

## 🧪 Testing Your Configuration

After creating `.env`, test it:

```bash
cd backend
python test_connection.py
```

**Expected output:**
```
✅ Connection successful!
✅ pgvector extension enabled
✅ All expected tables exist!
```

---

## 🆘 Troubleshooting

### Connection Failed?
- ✅ Check DATABASE_URL is correct
- ✅ Ensure `?sslmode=require` is at the end
- ✅ Verify Supabase project is active
- ✅ Check password has no special characters that need escaping

### LLM Not Working?
- ✅ Check OPENAI_API_KEY is valid
- ✅ Ensure you have API credits
- ✅ System will fallback to rule-based if key is missing

### File Upload Errors?
- ✅ Ensure UPLOAD_DIR exists or will be created
- ✅ Check file permissions
- ✅ Verify MAX_UPLOAD_SIZE is reasonable

---

## 📚 Related Documentation

- **QUICKSTART.md** - Quick setup guide
- **FILES_RECREATED.md** - What was recreated
- **backend/supabase_schema.sql** - Database schema
- **README.md** - Project overview

---

## 🎉 You're All Set!

Once you have:
1. ✅ Created `.env` from `.env.example`
2. ✅ Added your DATABASE_URL
3. ✅ Added your OPENAI_API_KEY (optional)
4. ✅ Tested with `python test_connection.py`

You're ready to start the server! 🚀

```bash
uvicorn app.main:app --reload
```
