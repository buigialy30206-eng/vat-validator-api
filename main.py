"""
EU VAT Number Validator API
Validates European VAT numbers via EU VIES (official, free, no API key).
"""
import subprocess, json as _json, time, threading
from typing import Optional
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from ratelimit import RateLimitMiddleware

app = FastAPI(title="EU VAT Validator API", version="1.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.add_middleware(RateLimitMiddleware)

VIES_URL = "https://ec.europa.eu/taxation_customs/vies/rest-api/ms/{country}/vat/{vat}"

COUNTRY_CODES = {
    "AT": "Austria", "BE": "Belgium", "BG": "Bulgaria", "HR": "Croatia",
    "CY": "Cyprus", "CZ": "Czech Republic", "DK": "Denmark", "EE": "Estonia",
    "FI": "Finland", "FR": "France", "DE": "Germany", "GR": "Greece",
    "HU": "Hungary", "IE": "Ireland", "IT": "Italy", "LV": "Latvia",
    "LT": "Lithuania", "LU": "Luxembourg", "MT": "Malta", "NL": "Netherlands",
    "PL": "Poland", "PT": "Portugal", "RO": "Romania", "SK": "Slovakia",
    "SI": "Slovenia", "ES": "Spain", "SE": "Sweden", "GB": "United Kingdom",
}

_cache = {}
_cache_lock = threading.Lock()
CACHE_TTL = 86400  # 24 hours — VAT numbers don't change often

class VATResult(BaseModel):
    vat_number: str
    country_code: str
    country_name: Optional[str] = None
    valid: bool
    company_name: Optional[str] = None
    company_address: Optional[str] = None
    request_date: Optional[str] = None
    error: str = ""

def curl_get(url: str) -> dict:
    cmd = ["curl", "-s", "-H", "Accept: application/json",
           "--connect-timeout", "8", "--max-time", "12", url]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return _json.loads(r.stdout) if r.returncode == 0 and r.stdout else {}
    except:
        return {}

def validate_vat(country: str, vat: str) -> VATResult:
    full_vat = f"{country.upper()}{vat}"
    
    # Check cache
    with _cache_lock:
        entry = _cache.get(full_vat)
        if entry and time.time() - entry["ts"] < CACHE_TTL:
            return VATResult(**entry["data"])

    data = curl_get(VIES_URL.format(country=country.upper(), vat=vat))
    if not data:
        result = VATResult(vat_number=full_vat, country_code=country, valid=False,
                           error="VIES API unavailable")
        return result

    approx = data.get("viesApproximate", {})
    name_match = approx.get("matchName", 3)
    company_name = approx.get("name") if name_match == 1 else None
    addr = [approx.get("street",""), approx.get("postalCode",""), approx.get("city","")]
    company_address = ", ".join([p for p in addr if p and p != "---"]) or None

    result = VATResult(
        vat_number=full_vat,
        country_code=country.upper(),
        country_name=COUNTRY_CODES.get(country.upper(), country),
        valid=data.get("isValid", False),
        company_name=company_name,
        company_address=company_address,
        request_date=data.get("requestDate", "")[:10],
    )

    # Cache result
    with _cache_lock:
        _cache[full_vat] = {"data": result.model_dump(), "ts": time.time()}
        if len(_cache) > 1000:
            oldest = min(_cache, key=lambda k: _cache[k]["ts"])
            del _cache[oldest]

    return result

@app.api_route("/health", methods=["GET", "HEAD"])
async def health():
    return {"status": "ok", "source": "EU VIES", "cache_size": len(_cache)}

@app.get("/")
async def root():
    return {"service": "EU VAT Validator API", "version": "1.1.0"}

@app.get("/validate", response_model=VATResult)
async def validate(vat: str = Query(..., description="Full VAT number, e.g. DE814584193")):
    if len(vat) < 3:
        raise HTTPException(400, "VAT number too short")
    country = vat[:2].upper()
    number = vat[2:].strip()
    return validate_vat(country, number)

@app.get("/countries")
async def list_countries():
    return {"countries": [{"code": k, "name": v} for k, v in COUNTRY_CODES.items()]}
