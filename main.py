"""
EU VAT Number Validator API
Validates European VAT numbers via EU VIES (official, free, no API key).
Covers all 27 EU member states + UK.
"""

import subprocess, json as _json
from typing import Optional

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="EU VAT Validator API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

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


class VATResult(BaseModel):
    vat_number: str
    country_code: str
    country_name: Optional[str] = None
    valid: bool
    company_name: Optional[str] = None
    company_address: Optional[str] = None
    request_date: Optional[str] = None


def curl_get(url: str) -> dict:
    cmd = ["curl", "-s", "-H", "Accept: application/json", "--connect-timeout", "10", "--max-time", "15", url]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return _json.loads(r.stdout) if r.returncode == 0 and r.stdout else {}


def validate_vat(country: str, vat: str) -> VATResult:
    data = curl_get(VIES_URL.format(country=country.upper(), vat=vat))
    if not data:
        return VATResult(vat_number=vat, country_code=country, valid=False)

    # Extract company name/address from viesApproximate
    approx = data.get("viesApproximate", {})
    name_match = approx.get("matchName", 3)
    company_name = approx.get("name") if name_match == 1 else None
    address_parts = [approx.get("street",""), approx.get("postalCode",""), approx.get("city","")]
    company_address = ", ".join([p for p in address_parts if p and p != "---"]) or None

    return VATResult(
        vat_number=f"{country.upper()}{vat}",
        country_code=country.upper(),
        country_name=COUNTRY_CODES.get(country.upper(), country),
        valid=data.get("isValid", False),
        company_name=company_name,
        company_address=company_address,
        request_date=data.get("requestDate", "")[:10],
    )


@app.api_route("/health", methods=["GET", "HEAD"])
async def health():
    return {"status": "ok", "source": "EU VIES"}


@app.get("/")
async def root():
    return {"service": "EU VAT Validator API", "version": "1.0.0", "countries": list(COUNTRY_CODES.values())}


@app.get("/validate", response_model=VATResult)
async def validate(
    vat: str = Query(..., description="Full VAT number, e.g. DE814584193 or IT01234567890"),
):
    # Extract country code from VAT number (first 2 chars)
    if len(vat) < 3:
        raise HTTPException(400, "VAT number too short, expected format: DE123456789")
    country = vat[:2].upper()
    number = vat[2:].strip()
    return validate_vat(country, number)


@app.get("/countries")
async def list_countries():
    return {"countries": [{"code": k, "name": v} for k, v in COUNTRY_CODES.items()]}
