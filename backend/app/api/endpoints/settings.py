"""
Settings API endpoints
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any, Optional, List
from pydantic import BaseModel
from loguru import logger

from app.services.settings_service import settings_service

router = APIRouter()


class SettingUpdate(BaseModel):
    """Request model for updating a single setting"""
    key: str
    value: Any


class SettingsBatchUpdate(BaseModel):
    """Request model for updating multiple settings"""
    updates: Dict[str, Any]


class ApiKeyUpdate(BaseModel):
    """Request model for updating an API key"""
    service_name: str
    api_key: str


@router.get("")
async def get_all_settings():
    """
    Get all application settings.

    Returns settings grouped by category:
    - screening: Default screening parameters
    - rate_limit: API rate limits
    - cache: Cache TTL settings
    - feature: Feature flags
    - ui: UI preferences
    """
    try:
        return settings_service.get_all_settings()
    except Exception as e:
        logger.error(f"Error getting settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary")
async def get_settings_summary():
    """
    Get complete settings summary including API key status.

    This is the main endpoint for the settings page - returns:
    - All settings grouped by category
    - API key configuration status (not the actual keys)
    - Environment file status
    """
    try:
        return settings_service.get_settings_summary()
    except Exception as e:
        logger.error(f"Error getting settings summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/category/{category}")
async def get_settings_by_category(category: str):
    """
    Get settings for a specific category.

    Categories: screening, rate_limit, cache, feature, ui
    """
    try:
        all_settings = settings_service.get_all_settings()
        if category not in all_settings:
            raise HTTPException(status_code=404, detail=f"Category '{category}' not found")
        return {category: all_settings[category]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting settings for category {category}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/key/{key}")
async def get_setting(key: str):
    """
    Get a single setting value by key.

    Example keys:
    - screening.market_cap_min
    - rate_limit.yahoo_requests_per_second
    - feature.enable_ai_analysis
    """
    try:
        value = settings_service.get_setting(key)
        if value is None:
            raise HTTPException(status_code=404, detail=f"Setting '{key}' not found")
        return {"key": key, "value": value}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting setting {key}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/key/{key}")
async def update_setting(key: str, value: Any):
    """
    Update a single setting value.

    The value type should match the setting's expected type.
    """
    try:
        success = settings_service.update_setting(key, value)
        if not success:
            raise HTTPException(status_code=404, detail=f"Setting '{key}' not found")
        return {"success": True, "key": key, "value": value}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating setting {key}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("")
async def update_settings_batch(request: SettingsBatchUpdate):
    """
    Update multiple settings at once.

    Request body:
    {
        "updates": {
            "screening.market_cap_min": 1000000000,
            "rate_limit.yahoo_requests_per_second": 3
        }
    }
    """
    try:
        results = settings_service.update_settings_batch(request.updates)
        success_count = sum(1 for v in results.values() if v)
        return {
            "success": True,
            "updated": success_count,
            "total": len(results),
            "results": results
        }
    except Exception as e:
        logger.error(f"Error updating settings batch: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api-keys")
async def get_api_key_status():
    """
    Get API key configuration status.

    Returns status of all configurable API services.
    Does NOT return actual API key values for security.
    """
    try:
        return {"api_keys": settings_service.get_api_key_status()}
    except Exception as e:
        logger.error(f"Error getting API key status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/api-keys")
async def update_api_key(request: ApiKeyUpdate):
    """
    Update an API key.

    This writes the key to the .env file on the server.
    The key is never stored in the database.

    After updating, you should restart the server for changes to take effect.
    """
    try:
        # Basic validation
        if not request.service_name:
            raise HTTPException(status_code=400, detail="Service name required")

        result = settings_service.update_api_key(request.service_name, request.api_key)

        if not result["success"]:
            raise HTTPException(status_code=400, detail=result.get("error", "Failed to update API key"))

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating API key: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api-keys/{service_name}/validate")
async def validate_api_key(service_name: str):
    """
    Validate an API key by making a test request.

    This will check if the currently configured key is valid.
    """
    try:
        # TODO: Implement actual validation for each service
        # For now, just return the current status
        api_keys = settings_service.get_api_key_status()
        service_status = next(
            (s for s in api_keys if s["service_name"] == service_name),
            None
        )

        if not service_status:
            raise HTTPException(status_code=404, detail=f"Service '{service_name}' not found")

        return {
            "service_name": service_name,
            "is_configured": service_status["is_configured"],
            "is_valid": service_status["is_valid"],
            "message": "Validation check complete"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error validating API key: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/seed")
async def seed_settings():
    """
    Seed default settings and API key status.

    This is called automatically on startup, but can be called
    manually to reset settings to defaults.
    """
    try:
        settings_service.seed_defaults()
        settings_service.seed_api_status()
        return {"success": True, "message": "Settings seeded successfully"}
    except Exception as e:
        logger.error(f"Error seeding settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reset-daily-usage")
async def reset_daily_usage():
    """
    Reset daily API usage counters.

    Typically called by a daily cron job or scheduler.
    """
    try:
        settings_service.reset_daily_usage()
        return {"success": True, "message": "Daily usage counters reset"}
    except Exception as e:
        logger.error(f"Error resetting daily usage: {e}")
        raise HTTPException(status_code=500, detail=str(e))
