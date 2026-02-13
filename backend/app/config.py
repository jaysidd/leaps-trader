"""
Application configuration
"""
from pydantic_settings import BaseSettings
from pydantic import model_validator
from functools import lru_cache
from dotenv import dotenv_values


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql://junaidsiddiqi@localhost/leaps_trader"

    # Redis
    REDIS_URL: str = ""  # Full Redis URL (Railway provides this, e.g. redis://default:pw@host:port)
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    # API Keys (optional for free tier)
    ALPHA_VANTAGE_API_KEY: str = "demo"  # Get from: https://www.alphavantage.co/support/#api-key
    FINVIZ_API_TOKEN: str = ""  # Finviz Elite API token (optional, for enhanced screening)
    FINNHUB_API_KEY: str = ""  # Get from: https://finnhub.io/ (free tier: 60 calls/min)
    FMP_API_KEY: str = ""  # Get from: https://financialmodelingprep.com/ (Ultimate: 3000 calls/min)
    FRED_API_KEY: str = ""  # Get from: https://fred.stlouisfed.org/docs/api/api_key.html

    # Tastytrade API (for Greeks and enhanced options data)
    # OAuth-based authentication (v11+)
    TASTYTRADE_PROVIDER_SECRET: str = ""  # Your OAuth provider secret
    TASTYTRADE_REFRESH_TOKEN: str = ""  # User's refresh token from OAuth flow

    # Telegram Bot (for remote commands)
    TELEGRAM_BOT_TOKEN: str = ""  # Get from @BotFather on Telegram
    TELEGRAM_ALLOWED_USERS: str = ""  # Comma-separated list of allowed user IDs (for security)

    # Alpaca API (for real-time data and trading)
    ALPACA_API_KEY: str = ""  # Get from: https://alpaca.markets/
    ALPACA_SECRET_KEY: str = ""  # Get from: https://alpaca.markets/
    ALPACA_PAPER: bool = True  # True for paper trading, False for live trading
    ALPACA_DATA_FEED: str = "sip"  # sip (paid) for full market data

    # Claude AI (for intelligent analysis)
    ANTHROPIC_API_KEY: str = ""  # Get from: https://console.anthropic.com/
    CLAUDE_MODEL_PRIMARY: str = "claude-sonnet-4-20250514"  # Main model for analysis
    CLAUDE_MODEL_FAST: str = "claude-haiku-4-5-20250514"  # Fast model for simple tasks
    CLAUDE_MODEL_ADVANCED: str = "claude-opus-4-5-20251101"  # Best model for complex decisions
    CLAUDE_MAX_TOKENS: int = 1024  # Default max tokens for responses

    # Claude AI Cost Tracking
    CLAUDE_COST_PER_1K_INPUT_TOKENS: float = 0.003  # $3 per 1M input tokens (Sonnet 4)
    CLAUDE_COST_PER_1K_OUTPUT_TOKENS: float = 0.015  # $15 per 1M output tokens (Sonnet 4)
    CLAUDE_DAILY_BUDGET: float = 10.0  # Daily budget in USD (prevents runaway costs)

    # API Rate Limits
    FMP_REQUESTS_PER_SECOND: int = 50  # FMP Ultimate tier: 3000 calls/min
    ALPHA_VANTAGE_REQUESTS_PER_MINUTE: int = 5
    ALPHA_VANTAGE_REQUESTS_PER_DAY: int = 500

    # Cache TTLs (in seconds)
    CACHE_TTL_QUOTE_MARKET_HOURS: int = 60  # 1 minute
    CACHE_TTL_QUOTE_AFTER_HOURS: int = 3600  # 1 hour
    CACHE_TTL_FUNDAMENTALS: int = 86400  # 24 hours
    CACHE_TTL_TECHNICAL_INDICATORS: int = 3600  # 1 hour

    # Application
    API_V1_PREFIX: str = "/api/v1"
    PROJECT_NAME: str = "LEAPS Trader"

    # Auth - API token for protected endpoints (trading, restart)
    # Set via TRADING_API_TOKEN env var or .env file. If empty, protected endpoints are unrestricted.
    TRADING_API_TOKEN: str = ""

    # App-wide password protection
    # Set APP_PASSWORD to require login before accessing the app. If empty, app is open (local dev).
    APP_PASSWORD: str = ""

    # TOTP 2FA (Google Authenticator / Authy)
    # Generate with: python3 -c "import pyotp; print(pyotp.random_base32())"
    # Set TOTP_SECRET to enable 2FA. If empty, only password is required.
    TOTP_SECRET: str = ""

    # Credential Encryption - Fernet key for encrypting stored broker passwords
    # Auto-generated on first run if empty. Persist in .env to survive restarts.
    CREDENTIAL_ENCRYPTION_KEY: str = ""

    # Deployment
    FRONTEND_URL: str = ""  # Production frontend URL (Railway domain), added to CORS automatically

    # CORS
    BACKEND_CORS_ORIGINS: list = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
        "http://localhost:5176",
        "https://webhook.leapstraders.com",
        "https://leapstraders.com",
    ]

    @model_validator(mode='after')
    def _fill_empty_from_dotenv(self):
        """
        If an env var exists but is empty (e.g. ANTHROPIC_API_KEY=''), fall
        back to the value from .env.  pydantic-settings treats a set-but-empty
        env var as authoritative, but for API keys an empty string is never
        intentional.
        """
        env_file_values = dotenv_values(".env")
        api_key_fields = [
            "ANTHROPIC_API_KEY", "ALPACA_API_KEY", "ALPACA_SECRET_KEY",
            "FINNHUB_API_KEY", "FMP_API_KEY", "FRED_API_KEY", "FINVIZ_API_TOKEN",
            "TELEGRAM_BOT_TOKEN", "TASTYTRADE_PROVIDER_SECRET",
            "TASTYTRADE_REFRESH_TOKEN", "CREDENTIAL_ENCRYPTION_KEY",
        ]
        for field in api_key_fields:
            current = getattr(self, field, "")
            dotenv_val = env_file_values.get(field, "")
            if not current and dotenv_val:
                object.__setattr__(self, field, dotenv_val)
        # Add production frontend URL to CORS origins if set
        if self.FRONTEND_URL and self.FRONTEND_URL not in self.BACKEND_CORS_ORIGINS:
            self.BACKEND_CORS_ORIGINS.append(self.FRONTEND_URL)
        return self

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()
