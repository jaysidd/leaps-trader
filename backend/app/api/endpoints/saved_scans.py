"""
Saved Scans API endpoints
Persist and manage screening results across sessions
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from loguru import logger
from datetime import datetime

from app.database import get_db
from app.models.saved_scan import SavedScanResult, SavedScanMetadata

router = APIRouter()


class SaveScanRequest(BaseModel):
    """Request to save scan results"""
    scan_type: str  # Preset name like "iv_crush", "momentum", etc.
    display_name: Optional[str] = None  # User-friendly name
    results: List[Dict[str, Any]]  # Stock results from screener


class SavedStockResponse(BaseModel):
    """Response for a single saved stock"""
    id: int
    scan_type: str
    symbol: str
    company_name: Optional[str]
    score: Optional[float]
    current_price: Optional[float]
    market_cap: Optional[float]
    iv_rank: Optional[float]
    iv_percentile: Optional[float]
    stock_data: Optional[Dict[str, Any]]
    scanned_at: Optional[str]


@router.get("/categories")
async def get_saved_scan_categories(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Get all saved scan categories with metadata.
    Returns list of scan types with stock counts and last run times.
    """
    metadata_list = db.query(SavedScanMetadata).order_by(
        SavedScanMetadata.last_run_at.desc()
    ).all()

    categories = [m.to_dict() for m in metadata_list]

    return {
        "categories": categories,
        "total_categories": len(categories),
        "total_stocks": sum(c.get("stock_count", 0) for c in categories)
    }


@router.get("/results/{scan_type}")
async def get_saved_scan_results(scan_type: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Get all saved results for a specific scan type.

    Args:
        scan_type: The preset name (e.g., "iv_crush", "momentum")

    Returns:
        List of stocks saved under this scan type
    """
    # Get metadata
    metadata = db.query(SavedScanMetadata).filter(
        SavedScanMetadata.scan_type == scan_type
    ).first()

    if not metadata:
        return {
            "scan_type": scan_type,
            "display_name": scan_type,
            "stocks": [],
            "stock_count": 0,
            "last_run_at": None
        }

    # Get results sorted by score
    results = db.query(SavedScanResult).filter(
        SavedScanResult.scan_type == scan_type
    ).order_by(SavedScanResult.score.desc()).all()

    return {
        "scan_type": scan_type,
        "display_name": metadata.display_name or scan_type,
        "description": metadata.description,
        "stocks": [r.to_dict() for r in results],
        "stock_count": len(results),
        "last_run_at": metadata.last_run_at.isoformat() if metadata.last_run_at else None
    }


@router.post("/save")
async def save_scan_results(request: SaveScanRequest, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Save screening results for a scan type.
    This will clear existing results for the scan type and save the new ones.

    Args:
        request: SaveScanRequest with scan_type and results

    Returns:
        Confirmation with count of saved stocks
    """
    try:
        scan_type = request.scan_type

        # Clear existing results for this scan type
        deleted_count = db.query(SavedScanResult).filter(
            SavedScanResult.scan_type == scan_type
        ).delete()

        logger.info(f"Cleared {deleted_count} existing results for scan type: {scan_type}")

        # Save new results
        saved_count = 0
        for stock in request.results:
            # Extract common fields from stock data
            saved_result = SavedScanResult(
                scan_type=scan_type,
                symbol=stock.get("symbol", ""),
                company_name=stock.get("company_name") or stock.get("name"),
                score=stock.get("composite_score") or stock.get("score"),
                current_price=stock.get("current_price") or stock.get("price"),
                market_cap=stock.get("market_cap"),
                iv_rank=stock.get("iv_rank"),
                iv_percentile=stock.get("iv_percentile"),
                stock_data=stock,  # Store full data as JSON
                scanned_at=datetime.utcnow()
            )
            db.add(saved_result)
            saved_count += 1

        # Update or create metadata
        metadata = db.query(SavedScanMetadata).filter(
            SavedScanMetadata.scan_type == scan_type
        ).first()

        if metadata:
            metadata.stock_count = saved_count
            metadata.last_run_at = datetime.utcnow()
            if request.display_name:
                metadata.display_name = request.display_name
        else:
            metadata = SavedScanMetadata(
                scan_type=scan_type,
                display_name=request.display_name or scan_type,
                stock_count=saved_count,
                last_run_at=datetime.utcnow()
            )
            db.add(metadata)

        db.commit()

        logger.info(f"Saved {saved_count} results for scan type: {scan_type}")

        return {
            "success": True,
            "scan_type": scan_type,
            "saved_count": saved_count,
            "message": f"Saved {saved_count} stocks for {scan_type}"
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error saving scan results: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/category/{scan_type}")
async def delete_scan_category(scan_type: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Delete all results for a specific scan type.

    Args:
        scan_type: The preset name to delete

    Returns:
        Confirmation with count of deleted stocks
    """
    try:
        # Delete results
        deleted_count = db.query(SavedScanResult).filter(
            SavedScanResult.scan_type == scan_type
        ).delete()

        # Delete metadata
        db.query(SavedScanMetadata).filter(
            SavedScanMetadata.scan_type == scan_type
        ).delete()

        db.commit()

        logger.info(f"Deleted {deleted_count} results for scan type: {scan_type}")

        return {
            "success": True,
            "scan_type": scan_type,
            "deleted_count": deleted_count,
            "message": f"Deleted {deleted_count} stocks from {scan_type}"
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting scan category: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/stock/{scan_type}/{symbol}")
async def delete_stock_from_scan(scan_type: str, symbol: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Delete a specific stock from a scan type.

    Args:
        scan_type: The preset name
        symbol: The stock symbol to remove

    Returns:
        Confirmation
    """
    try:
        # Delete the specific stock
        deleted_count = db.query(SavedScanResult).filter(
            SavedScanResult.scan_type == scan_type,
            SavedScanResult.symbol == symbol.upper()
        ).delete()

        if deleted_count == 0:
            raise HTTPException(
                status_code=404,
                detail=f"Stock {symbol} not found in {scan_type}"
            )

        # Update metadata stock count
        metadata = db.query(SavedScanMetadata).filter(
            SavedScanMetadata.scan_type == scan_type
        ).first()

        if metadata:
            remaining = db.query(SavedScanResult).filter(
                SavedScanResult.scan_type == scan_type
            ).count()
            metadata.stock_count = remaining

        db.commit()

        logger.info(f"Deleted {symbol} from scan type: {scan_type}")

        return {
            "success": True,
            "scan_type": scan_type,
            "symbol": symbol,
            "message": f"Removed {symbol} from {scan_type}"
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting stock from scan: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class BulkDeleteRequest(BaseModel):
    """Request to delete multiple stocks from a scan type"""
    scan_type: str
    symbols: List[str]


@router.post("/delete-stocks")
async def bulk_delete_stocks(request: BulkDeleteRequest, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Delete multiple stocks from a scan type in one operation.
    """
    try:
        upper_symbols = [s.upper() for s in request.symbols]
        deleted_count = db.query(SavedScanResult).filter(
            SavedScanResult.scan_type == request.scan_type,
            SavedScanResult.symbol.in_(upper_symbols)
        ).delete(synchronize_session='fetch')

        # Update metadata stock count
        metadata = db.query(SavedScanMetadata).filter(
            SavedScanMetadata.scan_type == request.scan_type
        ).first()

        if metadata:
            remaining = db.query(SavedScanResult).filter(
                SavedScanResult.scan_type == request.scan_type
            ).count()
            metadata.stock_count = remaining

        db.commit()

        logger.info(f"Bulk deleted {deleted_count} stocks from {request.scan_type}")

        return {
            "success": True,
            "scan_type": request.scan_type,
            "deleted_count": deleted_count,
            "symbols": upper_symbols,
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error bulk deleting stocks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/all")
async def clear_all_saved_scans(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Clear all saved scan results and metadata.

    Returns:
        Confirmation with counts
    """
    try:
        # Delete all results
        results_deleted = db.query(SavedScanResult).delete()

        # Delete all metadata
        metadata_deleted = db.query(SavedScanMetadata).delete()

        db.commit()

        logger.info(f"Cleared all saved scans: {results_deleted} results, {metadata_deleted} categories")

        return {
            "success": True,
            "results_deleted": results_deleted,
            "categories_deleted": metadata_deleted,
            "message": "All saved scans cleared"
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error clearing all saved scans: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/check/{scan_type}")
async def check_scan_exists(scan_type: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Check if a scan type has saved results.
    Useful for showing indicators on the screener page.

    Args:
        scan_type: The preset name to check

    Returns:
        Boolean indicating if saved results exist
    """
    metadata = db.query(SavedScanMetadata).filter(
        SavedScanMetadata.scan_type == scan_type
    ).first()

    if metadata and metadata.stock_count > 0:
        return {
            "scan_type": scan_type,
            "has_results": True,
            "stock_count": metadata.stock_count,
            "last_run_at": metadata.last_run_at.isoformat() if metadata.last_run_at else None
        }

    return {
        "scan_type": scan_type,
        "has_results": False,
        "stock_count": 0,
        "last_run_at": None
    }


@router.get("/check-all")
async def check_all_scans(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Check which scan types have saved results.
    Returns a map of scan_type -> has_results for all presets.
    Useful for batch-checking indicators on the screener page.

    Returns:
        Map of scan types to their saved status
    """
    metadata_list = db.query(SavedScanMetadata).all()

    scan_status = {}
    for m in metadata_list:
        scan_status[m.scan_type] = {
            "has_results": m.stock_count > 0,
            "stock_count": m.stock_count,
            "last_run_at": m.last_run_at.isoformat() if m.last_run_at else None
        }

    return {
        "scan_status": scan_status,
        "total_scans_with_data": sum(1 for s in scan_status.values() if s["has_results"])
    }
