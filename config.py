import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

FMP_API_KEY = os.getenv("FMP_API_KEY")
FMP_BASE_URL = "https://financialmodelingprep.com/stable"

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
CACHE_TTL_HOURS = 24

PROJECTION_YEARS = 5
RISK_FREE_RATE_DEFAULT = 0.043   # fallback if FRED fetch fails
EQUITY_RISK_PREMIUM = 0.055      # Damodaran ERP estimate
TAX_RATE_DEFAULT = 0.21
