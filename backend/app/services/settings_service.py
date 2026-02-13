"""
Settings service - manages application configuration

Handles:
- Database-stored settings (screening defaults, rate limits, etc.)
- API key status tracking (without exposing actual keys)
- .env file updates for API keys (secure handling)
"""
import os
import json
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path
from loguru import logger
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.settings import AppSettings, ApiKeyStatus
from app.config import get_settings, Settings


# Default settings that will be seeded on first run
DEFAULT_SETTINGS = {
    # Screening defaults
    "screening.market_cap_min": {
        "value": "1000000000",
        "value_type": "int",
        "category": "screening",
        "description": "Minimum market cap for screening ($)"
    },
    "screening.market_cap_max": {
        "value": "100000000000",
        "value_type": "int",
        "category": "screening",
        "description": "Maximum market cap for screening ($)"
    },
    "screening.revenue_growth_min": {
        "value": "10",
        "value_type": "float",
        "category": "screening",
        "description": "Minimum revenue growth (%)"
    },
    "screening.earnings_growth_min": {
        "value": "5",
        "value_type": "float",
        "category": "screening",
        "description": "Minimum earnings growth (%)"
    },
    "screening.rsi_min": {
        "value": "25",
        "value_type": "int",
        "category": "screening",
        "description": "Minimum RSI value"
    },
    "screening.rsi_max": {
        "value": "75",
        "value_type": "int",
        "category": "screening",
        "description": "Maximum RSI value"
    },
    "screening.iv_max": {
        "value": "100",
        "value_type": "int",
        "category": "screening",
        "description": "Maximum implied volatility (%)"
    },
    "screening.dte_min": {
        "value": "365",
        "value_type": "int",
        "category": "screening",
        "description": "Minimum days to expiration for LEAPS"
    },
    "screening.dte_max": {
        "value": "730",
        "value_type": "int",
        "category": "screening",
        "description": "Maximum days to expiration for LEAPS"
    },

    # Rate limits
    "rate_limit.fmp_requests_per_second": {
        "value": "40",
        "value_type": "int",
        "category": "rate_limit",
        "description": "FMP API requests per second"
    },
    "rate_limit.alpha_vantage_requests_per_minute": {
        "value": "5",
        "value_type": "int",
        "category": "rate_limit",
        "description": "Alpha Vantage requests per minute"
    },

    # Cache TTLs
    "cache.quote_market_hours_ttl": {
        "value": "60",
        "value_type": "int",
        "category": "cache",
        "description": "Quote cache TTL during market hours (seconds)"
    },
    "cache.quote_after_hours_ttl": {
        "value": "3600",
        "value_type": "int",
        "category": "cache",
        "description": "Quote cache TTL after hours (seconds)"
    },
    "cache.fundamentals_ttl": {
        "value": "86400",
        "value_type": "int",
        "category": "cache",
        "description": "Fundamentals cache TTL (seconds)"
    },
    "cache.technical_indicators_ttl": {
        "value": "3600",
        "value_type": "int",
        "category": "cache",
        "description": "Technical indicators cache TTL (seconds)"
    },

    # Feature flags
    "feature.enable_ai_analysis": {
        "value": "true",
        "value_type": "bool",
        "category": "feature",
        "description": "Enable Claude AI analysis features"
    },
    "feature.enable_sentiment_analysis": {
        "value": "true",
        "value_type": "bool",
        "category": "feature",
        "description": "Enable sentiment analysis"
    },
    "feature.enable_telegram_alerts": {
        "value": "false",
        "value_type": "bool",
        "category": "feature",
        "description": "Enable Telegram alert notifications"
    },

    # Auto-scan automation
    "automation.auto_scan_enabled": {
        "value": "false",
        "value_type": "bool",
        "category": "automation",
        "description": "Enable daily automated scanning at scheduled time"
    },
    "automation.auto_scan_presets": {
        "value": "[]",
        "value_type": "json",
        "category": "automation",
        "description": "JSON array of scan preset names to auto-run (e.g. [\"iv_crush\", \"momentum\"])"
    },
    "automation.auto_scan_auto_process": {
        "value": "true",
        "value_type": "bool",
        "category": "automation",
        "description": "Automatically run StrategySelector after scan completes"
    },
    "automation.auto_scan_mode": {
        "value": "interval",
        "value_type": "string",
        "category": "automation",
        "description": "Scan mode: 'interval' (continuous during market hours) or 'daily_cron' (once at 8:30 CT)"
    },
    "automation.auto_scan_interval_minutes": {
        "value": "30",
        "value_type": "int",
        "category": "automation",
        "description": "Minutes between scans in interval mode (15, 30, or 60)"
    },
    "automation.smart_scan_enabled": {
        "value": "false",
        "value_type": "bool",
        "category": "automation",
        "description": "Use market intelligence to auto-select scanning presets based on MRI, regime, and Fear & Greed"
    },

    # UI preferences
    "ui.default_preset": {
        "value": "moderate",
        "value_type": "string",
        "category": "ui",
        "description": "Default screening preset"
    },
    "ui.results_per_page": {
        "value": "25",
        "value_type": "int",
        "category": "ui",
        "description": "Number of results to show per page"
    },
    "ui.theme": {
        "value": "light",
        "value_type": "string",
        "category": "ui",
        "description": "UI theme (light/dark)"
    },
}

# API services that can have keys configured
API_SERVICES = [
    {
        "name": "fmp",
        "display_name": "Financial Modeling Prep",
        "description": "Fundamentals, stock info, insider trading, analyst ratings",
        "env_key": "FMP_API_KEY",
        "required": True,
        "always_available": False
    },
    {
        "name": "finviz",
        "display_name": "Finviz Elite",
        "description": "Pre-screening for large stock universes",
        "env_key": "FINVIZ_API_TOKEN",
        "required": False
    },
    {
        "name": "tastytrade",
        "display_name": "TastyTrade",
        "description": "Enhanced Greeks and IV data",
        "env_key": "TASTYTRADE_PROVIDER_SECRET",
        "required": False
    },
    {
        "name": "anthropic",
        "display_name": "Claude AI (Anthropic)",
        "description": "AI-powered market analysis",
        "env_key": "ANTHROPIC_API_KEY",
        "required": False
    },
    {
        "name": "telegram",
        "display_name": "Telegram Bot",
        "description": "Alert notifications via Telegram",
        "env_key": "TELEGRAM_BOT_TOKEN",
        "required": False
    },
    {
        "name": "alpha_vantage",
        "display_name": "Alpha Vantage",
        "description": "Additional market data (limited free tier)",
        "env_key": "ALPHA_VANTAGE_API_KEY",
        "required": False
    },
    {
        "name": "alpaca_api_key",
        "display_name": "Alpaca API Key",
        "description": "Real-time market data, trading, and heat maps",
        "env_key": "ALPACA_API_KEY",
        "required": False
    },
    {
        "name": "alpaca_secret_key",
        "display_name": "Alpaca Secret Key",
        "description": "Secret key for Alpaca API authentication",
        "env_key": "ALPACA_SECRET_KEY",
        "required": False
    },
]


class SettingsService:
    """Service for managing application settings"""

    def __init__(self):
        self.env_file_path = Path(__file__).parent.parent.parent / ".env"

    def _get_db(self):
        """Get database session as a context manager — guarantees close."""
        from contextlib import contextmanager

        @contextmanager
        def _session_scope():
            db = SessionLocal()
            try:
                yield db
            finally:
                db.close()

        return _session_scope()

    def _convert_value(self, value: str, value_type: str) -> Any:
        """Convert string value to appropriate type"""
        if value_type == "int":
            return int(value)
        elif value_type == "float":
            return float(value)
        elif value_type == "bool":
            return value.lower() in ("true", "1", "yes")
        elif value_type == "json":
            return json.loads(value)
        return value

    def _serialize_value(self, value: Any) -> str:
        """Serialize value to string for storage"""
        if isinstance(value, bool):
            return "true" if value else "false"
        elif isinstance(value, (dict, list)):
            return json.dumps(value)
        return str(value)

    def seed_defaults(self) -> None:
        """Seed default settings if they don't exist"""
        with self._get_db() as db:
            try:
                for key, config in DEFAULT_SETTINGS.items():
                    existing = db.query(AppSettings).filter(AppSettings.key == key).first()
                    if not existing:
                        setting = AppSettings(
                            key=key,
                            value=config["value"],
                            value_type=config["value_type"],
                            category=config["category"],
                            description=config.get("description", "")
                        )
                        db.add(setting)
                db.commit()
                logger.info("Default settings seeded successfully")
            except Exception as e:
                db.rollback()
                logger.error(f"Error seeding default settings: {e}")

    def seed_api_status(self) -> None:
        """Seed API key status entries"""
        settings = get_settings()

        with self._get_db() as db:
            try:
                for service in API_SERVICES:
                    existing = db.query(ApiKeyStatus).filter(
                        ApiKeyStatus.service_name == service["name"]
                    ).first()

                    if not existing:
                        # Check if key is configured in environment
                        is_configured = False
                        if service.get("always_available"):
                            is_configured = True
                        elif service.get("env_key"):
                            env_value = getattr(settings, service["env_key"], "")
                            is_configured = bool(env_value and env_value.strip())

                        status = ApiKeyStatus(
                            service_name=service["name"],
                            is_configured=is_configured,
                            is_valid=is_configured,  # Assume valid if configured
                            daily_limit=service.get("daily_limit")
                        )
                        db.add(status)
                    else:
                        # Update configuration status
                        if service.get("always_available"):
                            existing.is_configured = True
                        elif service.get("env_key"):
                            env_value = getattr(settings, service["env_key"], "")
                            existing.is_configured = bool(env_value and env_value.strip())

                db.commit()
                logger.info("API key status seeded successfully")
            except Exception as e:
                db.rollback()
                logger.error(f"Error seeding API key status: {e}")

    def seed_sector_mappings(self) -> None:
        """Seed default sector macro mappings if they don't exist"""
        from app.models.sector_macro_mapping import SectorMacroMapping, DEFAULT_SECTOR_MAPPINGS

        with self._get_db() as db:
            try:
                seeded_count = 0
                for mapping_data in DEFAULT_SECTOR_MAPPINGS:
                    existing = db.query(SectorMacroMapping).filter(
                        SectorMacroMapping.sector == mapping_data["sector"]
                    ).first()

                    if not existing:
                        mapping = SectorMacroMapping(
                            sector=mapping_data["sector"],
                            weight_fed_policy=mapping_data["weight_fed_policy"],
                            weight_recession=mapping_data["weight_recession"],
                            weight_elections=mapping_data["weight_elections"],
                            weight_trade=mapping_data["weight_trade"],
                            weight_crypto=mapping_data["weight_crypto"],
                            weight_markets=mapping_data["weight_markets"],
                        )
                        db.add(mapping)
                        seeded_count += 1

                db.commit()
                if seeded_count > 0:
                    logger.info(f"Seeded {seeded_count} sector macro mappings")
                else:
                    logger.debug("All sector macro mappings already exist")
            except Exception as e:
                db.rollback()
                logger.error(f"Error seeding sector macro mappings: {e}")

    def get_all_settings(self) -> Dict[str, Any]:
        """Get all settings grouped by category"""
        with self._get_db() as db:
            settings = db.query(AppSettings).all()

            result = {}
            for setting in settings:
                category = setting.category or "general"
                if category not in result:
                    result[category] = {}

                result[category][setting.key] = {
                    "value": self._convert_value(setting.value, setting.value_type),
                    "value_type": setting.value_type,
                    "description": setting.description,
                    "is_sensitive": setting.is_sensitive,
                    "updated_at": setting.updated_at.isoformat() if setting.updated_at else None
                }

            return result

    def get_setting(self, key: str) -> Optional[Any]:
        """Get a single setting value"""
        with self._get_db() as db:
            setting = db.query(AppSettings).filter(AppSettings.key == key).first()
            if setting:
                return self._convert_value(setting.value, setting.value_type)
            return None

    def update_setting(self, key: str, value: Any) -> bool:
        """Update a setting value"""
        with self._get_db() as db:
            try:
                setting = db.query(AppSettings).filter(AppSettings.key == key).first()
                if setting:
                    setting.value = self._serialize_value(value)
                    db.commit()
                    logger.info(f"Setting '{key}' updated to '{value}'")
                    return True
                return False
            except Exception as e:
                db.rollback()
                logger.error(f"Error updating setting '{key}': {e}")
                return False

    def update_settings_batch(self, updates: Dict[str, Any]) -> Dict[str, bool]:
        """Update multiple settings at once"""
        results = {}
        for key, value in updates.items():
            results[key] = self.update_setting(key, value)
        return results

    def get_api_key_status(self) -> List[Dict[str, Any]]:
        """Get status of all API keys (without exposing actual keys)"""
        settings = get_settings()

        with self._get_db() as db:
            statuses = db.query(ApiKeyStatus).all()
            result = []

            for status in statuses:
                service_info = next(
                    (s for s in API_SERVICES if s["name"] == status.service_name),
                    {}
                )

                # Re-check if configured from current environment
                is_configured = status.is_configured
                if service_info.get("env_key"):
                    env_value = getattr(settings, service_info["env_key"], "")
                    is_configured = bool(env_value and env_value.strip())

                result.append({
                    "service_name": status.service_name,
                    "display_name": service_info.get("display_name", status.service_name),
                    "description": service_info.get("description", ""),
                    "is_configured": is_configured,
                    "is_valid": status.is_valid,
                    "last_validated": status.last_validated.isoformat() if status.last_validated else None,
                    "last_used": status.last_used.isoformat() if status.last_used else None,
                    "usage_count": status.usage_count,
                    "error_count": status.error_count,
                    "last_error": status.last_error,
                    "daily_usage": status.daily_usage,
                    "daily_limit": status.daily_limit,
                    "env_key": service_info.get("env_key"),
                    "required": service_info.get("required", False),
                    "always_available": service_info.get("always_available", False)
                })

            return result

    def update_api_key(self, service_name: str, api_key: str) -> Dict[str, Any]:
        """
        Update an API key in the .env file.

        Security note: This writes to the .env file on the server.
        The actual key value is never stored in the database.
        """
        service_info = next(
            (s for s in API_SERVICES if s["name"] == service_name),
            None
        )

        if not service_info:
            return {"success": False, "error": "Unknown service"}

        env_key = service_info.get("env_key")
        if not env_key:
            return {"success": False, "error": "Service does not use API key"}

        try:
            # Read existing .env file
            env_content = ""
            if self.env_file_path.exists():
                with open(self.env_file_path, "r") as f:
                    env_content = f.read()

            # Update or add the key
            lines = env_content.split("\n")
            key_found = False
            new_lines = []

            for line in lines:
                if line.startswith(f"{env_key}="):
                    new_lines.append(f"{env_key}={api_key}")
                    key_found = True
                else:
                    new_lines.append(line)

            if not key_found:
                new_lines.append(f"{env_key}={api_key}")

            # Write back to .env file
            with open(self.env_file_path, "w") as f:
                f.write("\n".join(new_lines))

            # Update database status
            with self._get_db() as db:
                status = db.query(ApiKeyStatus).filter(
                    ApiKeyStatus.service_name == service_name
                ).first()
                if status:
                    status.is_configured = bool(api_key and api_key.strip())
                    status.is_valid = True  # Assume valid until proven otherwise
                    status.last_validated = datetime.utcnow()
                    status.last_error = None
                    db.commit()

            logger.info(f"API key for {service_name} updated successfully")
            return {
                "success": True,
                "message": f"API key for {service_info['display_name']} updated. Restart server to apply."
            }

        except Exception as e:
            logger.error(f"Error updating API key for {service_name}: {e}")
            return {"success": False, "error": str(e)}

    def record_api_usage(self, service_name: str, success: bool = True, error: str = None) -> None:
        """Record API usage for tracking"""
        with self._get_db() as db:
            try:
                status = db.query(ApiKeyStatus).filter(
                    ApiKeyStatus.service_name == service_name
                ).first()

                if status:
                    status.usage_count += 1
                    status.daily_usage += 1
                    status.last_used = datetime.utcnow()

                    if not success:
                        status.error_count += 1
                        status.last_error = error
                        status.is_valid = False

                    db.commit()
            except Exception as e:
                db.rollback()
                logger.error(f"Error recording API usage: {e}")

    def reset_daily_usage(self) -> None:
        """Reset daily usage counters (call daily via cron/scheduler)"""
        with self._get_db() as db:
            try:
                db.query(ApiKeyStatus).update({ApiKeyStatus.daily_usage: 0})
                db.commit()
                logger.info("Daily API usage counters reset")
            except Exception as e:
                db.rollback()
                logger.error(f"Error resetting daily usage: {e}")

    def get_settings_summary(self) -> Dict[str, Any]:
        """Get a summary of current configuration for the UI"""
        return {
            "settings": self.get_all_settings(),
            "api_keys": self.get_api_key_status(),
            "env_file_path": str(self.env_file_path),
            "env_file_exists": self.env_file_path.exists()
        }


# Global service instance
settings_service = SettingsService()
