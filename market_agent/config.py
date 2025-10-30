import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    def __init__(self):
        self.finnhub_api_key = os.getenv("FINNHUB_API_KEY")

    def require_api_key(self):
        if not self.finnhub_api_key:
            raise RuntimeError("FINNHUB_API_KEY not set. Export it or put it in a .env file.")
        return self.finnhub_api_key

settings = Settings()