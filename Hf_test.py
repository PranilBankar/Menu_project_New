# hf_test.py
import os, requests
from dotenv import load_dotenv
load_dotenv('backend/.env')
model = os.getenv('LLM_MODEL', 'mistralai/Mistral-7B-Instruct-v0.2')
key = os.getenv('HUGGINGFACE_API_KEY')
headers = {"Authorization": f"Bearer {key}"}
r = requests.post(f"https://router.huggingface.co/models/{model}", json={"inputs":"Say hello in one sentence."}, headers=headers, timeout=60)
print(r.status_code, r.text[:1000]) //