import os
from typing import Optional
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # --------------------------------------------------------------------------
    # 1. Server & Application
    # --------------------------------------------------------------------------
    ENVIRONMENT: str = "production"
    PORT: int = 5001
    HOST: str = "0.0.0.0"
    APP_URL: str = "https://wa-api-hotel.up.railway.app"
    CORS_ORIGINS: str = "*"

    # --------------------------------------------------------------------------
    # 2. Hotel Information & Policies
    # --------------------------------------------------------------------------
    HOTEL_NAME: str = "Agnia Guesthouse"
    HOTEL_LEGAL_NAME: str = "Agnia Guesthouse Balikpapan"
    HOTEL_SLUG: str = "agnia_guesthouse"
    TENANT_ID: str = "13eb1ab8-aeb4-4218-ab8f-683097b32d99"
    HOTEL_STATUS: str = "active"
    HOTEL_TIMEZONE: str = "Asia/Makassar"
    HOTEL_LOCALE: str = "id_ID"
    HOTEL_CURRENCY: str = "IDR"
    HOTEL_ADDRESS: str = "Komplek Pelita Indah Blok A No. 13 RT.13 Kec. Balikpapan Selatan Kel. Sepinggan Raya, Balikpapan Selatan, Balikpapan, Kalimantan Timur 76115"
    HOTEL_PHONE: str = "+62 857-7652-6690"
    HOTEL_EMAIL: str = "info@agniaguesthouse.com"
    ADMIN_WHATSAPP_NUMBER: str = "6281805040354"
    CHECK_IN_TIME: str = "14:00 - 20:00 WITA"
    CHECK_OUT_TIME: str = "12:00 - 12:30 WITA"
    EXTRA_BED_PRICE: int = 75000
    CANCELLATION_POLICY: str = "Pembatalan gratis hingga 24 jam sebelum check-in. Penginapan ramah syariah (pasangan menginap wajib pasutri sah / membawa KTP & surat nikah). Kamar mandi luar bersama (shared bathroom) & dapur bersama."

    # --------------------------------------------------------------------------
    # 3. WhatsApp Gateway Settings
    # --------------------------------------------------------------------------
    WA_GATEWAY_URL: str = "https://wa.inovasiuitjbt.uk"
    WA_INSTANCE_ID: str = "6285284476962"
    WA_API_KEY: str = "sk_live_b1e4e4a0bace03e7c70f6ab8c1e5991d"
    WEBHOOK_SECRET: str = "Kerasakti123"
    PUBLIC_WEBHOOK_URL: Optional[str] = None

    @property
    def public_webhook_url(self) -> str:
        if self.PUBLIC_WEBHOOK_URL:
            return self.PUBLIC_WEBHOOK_URL
        return f"{self.APP_URL.rstrip('/')}/webhook/whatsapp"

    # --------------------------------------------------------------------------
    # 4. Garda LLM Settings
    # --------------------------------------------------------------------------
    GARDA_API_URL: str = "https://iss-uitjbt.inovasiuitjbt.uk/garda-api/v1/chat/completions"
    GARDA_API_KEY: str = "sk-garda-30f8204c5747651c99dce89d"
    GARDA_MODEL: str = "gemma4:e4b"
    GARDA_TIMEOUT_SECONDS: int = 45

    # --------------------------------------------------------------------------
    # 5. PostgreSQL Database Settings (Dedicated AI User: hotel_ai_agent)
    # --------------------------------------------------------------------------
    POSTGRES_USER: str = "hotel_ai_agent"
    POSTGRES_PASSWORD: str = "AiHotelSafePass_2026_Secure!"
    POSTGRES_SERVER: str = "trolley.proxy.rlwy.net"
    POSTGRES_PORT: int = 23804
    POSTGRES_DB: str = "railway"
    POSTGRES_SCHEMA: str = "tenant_agnia_guesthouse"
    DATABASE_URL: str = ""

    @property
    def postgres_connection_string(self) -> str:
        if self.DATABASE_URL and "sqlite" not in self.DATABASE_URL and "${{" not in self.DATABASE_URL:
            url = self.DATABASE_URL
            if url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql://", 1)
            return url
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # --------------------------------------------------------------------------
    # 6. Inquiries Database Settings (Chat log & inquiries)
    # --------------------------------------------------------------------------
    INQUIRIES_DATABASE_URL: str = "sqlite:///./hotel_inquiries.db"

    # --------------------------------------------------------------------------
    # 7. Backend API Settings (Anvieo Hospitality Backend)
    # --------------------------------------------------------------------------
    BACKEND_API_URL: str = "https://anvieo-backend-hospitality-production.up.railway.app"

    # --------------------------------------------------------------------------
    # 8. TriPay Payment Gateway Settings
    # --------------------------------------------------------------------------
    TRIPAY_API_KEY: str = "DEV-Z9SkjK8cIBm8Fd66weOuRFmEZchAXH0k5HjbfvHk"
    TRIPAY_PRIVATE_KEY: str = "LOEtf-8GESt-TJJZD-cw3VP-uxeK8"
    TRIPAY_MERCHANT_CODE: str = "T52086"
    TRIPAY_BASE_URL: str = "https://tripay.co.id/api-sandbox"
    TRIPAY_CALLBACK_URL: Optional[str] = None

    @property
    def tripay_callback_url(self) -> str:
        if self.TRIPAY_CALLBACK_URL:
            return self.TRIPAY_CALLBACK_URL
        return f"{self.APP_URL.rstrip('/')}/api/v1/payment/tripay-callback"

    # --------------------------------------------------------------------------
    # 9. BNB Smart Chain (BSC) & Web3 Crypto Settings
    # --------------------------------------------------------------------------
    BSC_RPC_URL: str = "https://data-seed-prebsc-1-s1.binance.org:8545/"
    BSC_CHAIN_ID: int = 97
    BSC_EXPLORER_URL: str = "https://testnet.bscscan.com"
    HOTEL_ESCROW_ADDRESS: str = "0x337610d27c682E347C9cD60BD4b3b107C9d34dDd"
    SECUREPAY_REGISTRY_ADDRESS: str = "0xca11bde05977b3631167028862be2a173976ca11"
    LOYALTY_TOKEN_ADDRESS: str = "0x84b9b910527ad5c03a9ca831909e21e236ea7b06"
    USDT_TOKEN_ADDRESS: str = "0x337610d27c682E347C9cD60BD4b3b107C9d34dDd"
    HOTEL_WALLET_ADDRESS: str = "0x036EAe4133c72d7DA3480b9F35f84577daaC5644"
    HOTEL_WALLET_PRIVATE_KEY: str = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
    EXCHANGE_RATE_USDT_IDR: int = 16000
    LOYALTY_REWARD_PERCENT: int = 5

    @property
    def CONTRACT_REGISTRY_ADDRESS(self) -> str:
        return self.SECUREPAY_REGISTRY_ADDRESS

    @property
    def CONTRACT_ESCROW_ADDRESS(self) -> str:
        return self.HOTEL_ESCROW_ADDRESS

    @property
    def CONTRACT_LOYALTY_TOKEN_ADDRESS(self) -> str:
        return self.LOYALTY_TOKEN_ADDRESS

    def __init__(self, **values):
        super().__init__(**values)
        # Prioritaskan nilai eksplisit dari .env lokal jika ada
        env_file_path = os.path.join(os.path.dirname(__file__), ".env")
        if os.path.exists(env_file_path):
            try:
                from dotenv import dotenv_values
                env_vals = dotenv_values(env_file_path)
                if env_vals.get("HOTEL_NAME"):
                    self.HOTEL_NAME = env_vals["HOTEL_NAME"]
                if env_vals.get("HOTEL_LEGAL_NAME"):
                    self.HOTEL_LEGAL_NAME = env_vals["HOTEL_LEGAL_NAME"]
                if env_vals.get("HOTEL_WALLET_ADDRESS"):
                    self.HOTEL_WALLET_ADDRESS = env_vals["HOTEL_WALLET_ADDRESS"]
                if env_vals.get("HOTEL_ESCROW_ADDRESS"):
                    self.HOTEL_ESCROW_ADDRESS = env_vals["HOTEL_ESCROW_ADDRESS"]
                if env_vals.get("SECUREPAY_REGISTRY_ADDRESS"):
                    self.SECUREPAY_REGISTRY_ADDRESS = env_vals["SECUREPAY_REGISTRY_ADDRESS"]
                if env_vals.get("LOYALTY_TOKEN_ADDRESS"):
                    self.LOYALTY_TOKEN_ADDRESS = env_vals["LOYALTY_TOKEN_ADDRESS"]
            except Exception:
                pass

        if not self.HOTEL_NAME or "anvieo" in self.HOTEL_NAME.lower():
            self.HOTEL_NAME = "Agnia Guesthouse"
        if not self.HOTEL_LEGAL_NAME or "anvieo" in self.HOTEL_LEGAL_NAME.lower():
            self.HOTEL_LEGAL_NAME = "Agnia Guesthouse Balikpapan"

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
