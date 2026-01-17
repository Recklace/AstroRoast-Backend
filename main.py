from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import ephem
import math
import os
import httpx
from dotenv import load_dotenv
from pathlib import Path

# --- 1. AYARLAR ---
current_dir = Path(__file__).parent
env_path = current_dir / ".env"
load_dotenv(dotenv_path=env_path)

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

if not GOOGLE_API_KEY:
    raise ValueError("KRİTİK HATA: .env dosyası okunamadı!")

app = FastAPI(title="AstroRoast API", description="Auto-Model Detection Edition")

# --- 2. VERİ MODELİ ---
class UserRequest(BaseModel):
    date: str
    time: str
    city_lat: str
    city_lon: str
    mode: str

# --- 3. ASTROLOJİ MOTORU ---
def get_zodiac_sign(lon_rad):
    lon_deg = math.degrees(lon_rad)
    signs = ["Koç", "Boğa", "İkizler", "Yengeç", "Aslan", "Başak", 
             "Terazi", "Akrep", "Yay", "Oğlak", "Kova", "Balık"]
    index = int(lon_deg / 30)
    return signs[index % 12]

def calculate_chart_ephem(date, time, lat, lon):
    try:
        observer = ephem.Observer()
        observer.lat = lat
        observer.lon = lon
        observer.date = f"{date} {time}"
        
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

# --- 4. AKILLI MODEL SEÇİCİ (YENİ ÖZELLİK) ---
async def get_working_model(client):
    """Google'a sorar: Hangi modellerim açık? İlk çalışanı seçer."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GOOGLE_API_KEY}"
    try:
        response = await client.get(url)
        data = response.json()
        
        if "error" in data:
            return None, f"Liste Hatası: {data['error']['message']}"
            
        # Modelleri tara, 'generateContent' yapabilen ilkini bul
        for model in data.get("models", []):
            if "generateContent" in model.get("supportedGenerationMethods", []):
                # Genellikle 'models/gemini-pro' veya 'models/gemini-1.5-flash' döner
                print(f"✅ ÇALIŞAN MODEL BULUNDU: {model['name']}") # Terminalde görelim
                return model['name'], None
                
        return None, "Hiçbir uygun model bulunamadı."
    except Exception as e:
        return None, str(e)

# --- 5. GEMINI İSTEĞİ ---
async def generate_roast_direct(astro_data, mode):
    
    async with httpx.AsyncClient() as client:
        # Önce çalışan modeli bul
        model_name, error = await get_working_model(client)
        if error:
            return f"Model Bulunamadı: {error}"

        # Bulunan modeli kullan
        url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:generateContent?key={GOOGLE_API_KEY}"
        
        if mode == "fake_nice":
            prompt_text = f"""
            Rol: 90'ların aşırı kurumsal ama bozuk 'Müşteri Hizmetleri' botusun.
            Ton: Vıcık vıcık kibar ama parantez (...) içinde iğneleyici gerçekler söylüyorsun.
            Kullanıcı Verileri: Güneş {astro_data['sun']}, Ay {astro_data['moon']}, Merkür {astro_data['mercury']}, Mars {astro_data['mars']}, Satürn {astro_data['saturn']}.
            Görev: Bu kişiye 2-3 cümlelik astrolojik yorum yap.
            """
        else:
            prompt_text = f"""
            Rol: Hatalı çalışan, acımasız ve alaycı bir yapay zekasın.
            Ton: Sert, aşağılayıcı, 'ERROR' şakaları yapan.
            Kullanıcı Verileri: Güneş {astro_data['sun']}, Ay {astro_data['moon']}, Merkür {astro_data['mercury']}, Mars {astro_data['mars']}, Satürn {astro_data['saturn']}.
            Görev: Bu kişiyi burçlarına göre aşağıla (Roast et). Asla teselli verme.
            """

        payload = {
            "contents": [{"parts": [{"text": prompt_text}]}],
            "safetySettings": [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
            ]
        }

        try:
            response = await client.post(url, json=payload, timeout=30.0)
            data = response.json()
            
            if "candidates" in data and data["candidates"]:
                return data["candidates"][0]["content"]["parts"][0]["text"]
            else:
                return f"Google Cevap Vermedi: {data}"
        except Exception as e:
            return f"Bağlantı Hatası: {str(e)}"

# --- 6. API ENDPOINT ---
@app.post("/analyze")
async def analyze_user(request: UserRequest):
    chart_data = calculate_chart_ephem(request.date, request.time, request.city_lat, request.city_lon)
    
    if "error" in chart_data:
        raise HTTPException(status_code=400, detail=f"Hesaplama Hatası: {chart_data['error']}")

    ai_response = await generate_roast_direct(chart_data, request.mode)
    
    return {
        "engine": "Google Gemini (Auto-Detect)",
        "astro_data": chart_data,
        "roast_message": ai_response
    }