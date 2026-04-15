import os
from supabase import create_client, Client
from dotenv import load_dotenv
import httpx

# Load .env to get Supabase URL and Anon Key
load_dotenv()
url: str = "https://pirxrfkrjgskjjacrnkr.supabase.co"
key: str = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBpcnhyZmtyamdza2pqYWNybmtyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjkzODc0NTgsImV4cCI6MjA4NDk2MzQ1OH0.0G-EA2HB4Vb3xc1W-0N5qh94YUmo3AuIs5FT2scYo2c"

if not url or not key:
    print("❌ Cannot find SUPABASE_URL or SUPABASE_ANON_KEY in .env")
    exit(1)

supabase: Client = create_client(url, key)

print("\n=== Supabase Auth & Local API Test ===")
print("Let's test if our JWKS-based JWT validation works!\n")

print("Please provide a test user's email and password created in your Supabase Auth:")
email = input("Email: ")
password = input("Password: ")

try:
    print(f"\n1. ⏳ Attempting to log into Supabase as {email}...")
    auth_response = supabase.auth.sign_in_with_password({"email": email, "password": password})
    access_token = auth_response.session.access_token
    print("✅ Successfully logged in! Received JWT token from Supabase.")
    
except Exception as e:
    print(f"❌ Failed to log in via Supabase: {e}")
    exit(1)

print("\n2. ⏳ Testing local API without token (Should be blocked)...")
try:
    res = httpx.get("http://localhost:8000/api/v1/auth/me")
    if res.status_code == 401:
         print(f"✅ Success! Local API correctly blocked anonymous request (Status: {res.status_code})")
    else:
         print(f"⚠️ Unexpected status: {res.status_code}. Response: {res.text}")
except Exception as e:
    print(f"❌ Error hitting local API: Is your FastAPI server running? Make sure to run `uvicorn app.main:app --reload`\nError Details: {e}")
    exit(1)


print("\n3. ⏳ Testing local API WITH token (Should allow)...")
try:
    # Notice we pass the 'Bearer ' header 
    headers = {"Authorization": f"Bearer {access_token}"}
    res = httpx.get("http://localhost:8000/api/v1/auth/me", headers=headers)
    
    if res.status_code == 200:
         print(f"✅ Success! Local API verified your JWT via JWKS and returned your user info:")
         print(f"   => {res.json()}")
    else:
         print(f"❌ API Rejected Token! Status: {res.status_code}. Response: {res.text}")
except Exception as e:
    print(f"❌ Error hitting local API: {e}")
    exit(1)

print("\n✨ All tests complete!")
