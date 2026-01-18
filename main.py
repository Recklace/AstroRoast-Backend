from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware  # <-- YENİ EKLENEN KISIM
from pydantic import BaseModel
import ephem
import math
import os
import httpx
from dotenv import load_dotenv

# --- AYARLAR ---
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

app = FastAPI(title="AstroRoast API")

# --- 🔥 CORS İZNİ (TARAYICI ENGELİNİ KALDIRIR) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Her yerden gelen isteği kabul et
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- VERİ MODELİ ---
class UserRequest(BaseModel):
    date: str
    time: str
    city_lat: str
    city_lon: str
    mode: str

# --- ASTROLOJİ MOTORU ---
def get_zodiac_sign(lon_rad):
    lon_deg = math.degrees(lon_rad)
    signs = ["Koç", "Boğa", "İkizler", "Yengeç", "Aslan", "Başak", 
             "Terazi", "Akrep", "Yay", "Oğlak", "Kova", "Balık"]
    index = int(lon_deg / 30)
    return signs[index % 12]

def calculate_chart_ephem(date, time, lat, lon):
    try:
        # Tarih formatını düzelt (1991/07/20 -> 1991/7/20) ephem bazen sıfırları sevmez
        date_parts = date.replace("-", "/").split("/")
        formatted_date = f"{int(date_parts[0])}/{int(date_parts[1])}/{int(date_parts[2])}"
        
        observer = ephem.Observer()
        observer.lat = lat
        observer.lon = lon
        observer.date = f"{formatted_date} {time}"
        
        sun = ephem.Sun(observer)
        moon = ephem.Moon(observer)
        mercury = ephem.Mercury(observer)
        mars = ephem.Mars(observer)
        saturn = ephem.Saturn(observer)

        return {
            "sun": get_zodiac_sign(ephem.Ecliptic(sun).lon),
            "moon": get_zodiac_sign(ephem.Ecliptic(moon).lon),
            "mercury": get_zodiac_sign(ephem.Ecliptic(mercury).lon),
            "mars": get_zodiac_sign(ephem.Ecliptic(mars).lon),
            "saturn": get_zodiac_sign(ephem.Ecliptic(saturn).lon),
        }
    except Exception as e:
        return {"error": str(e)}

# --- GEMINI MODEL SEÇİCİ ---
async def get_working_model(client):
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GOOGLE_API_KEY}"
    try:
        response = await client.get(url)
        data = response.json()
        for model in data.get("models", []):
            if "generateContent" in model.get("supportedGenerationMethods", []):
                return model['name'], None
        return "models/gemini-pro", None # Yedek
    except:
        return "models/gemini-pro", None

# --- API ENDPOINT ---
@app.post("/analyze")
async def analyze_user(request: UserRequest):
    chart_data = calculate_chart_ephem(request.date, request.time, request.city_lat, request.city_lon)
    
    if "error" in chart_data:
         # Hata olsa bile JSON dön ki uygulama çökmesin
        return {"roast_message": f"Hesaplama Hatası: {chart_data['error']}. Tarih formatını kontrol et."}

    async with httpx.AsyncClient() as client:
        model_name, _ = await get_working_model(client)
        url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:generateContent?key={GOOGLE_API_KEY}"
        
        prompt_text = f"""
        Rol: Acımasız, alaycı ve komik bir astrolog yapay zekasın.
        Kullanıcı Verileri: Güneş {chart_data['sun']}, Ay {chart_data['moon']}, Merkür {chart_data['mercury']}, Mars {chart_data['mars']}, Satürn {chart_data['saturn']}.
        Görev: Bu kişiyi burçlarına göre aşağıla (Roast et). Kısa ve vurucu olsun.
        """

        payload = {"contents": [{"parts": [{"text": prompt_text}]}]}
        
        try:
            response = await client.post(url, json=payload, timeout=60.0)
            data = response.json()
            if "candidates" in data:
                return {"roast_message": data["candidates"][0]["content"]["parts"][0]["text"]}
            else:
                return {"roast_message": "Yapay zeka sessiz kaldı. Tekrar dene."}
        except Exception as e:
            return {"roast_message": f"Bağlantı Hatası: {str(e)}"}
