from fastapi import APIRouter

from app.api.routes import admin, auth, bookings, deals, health, profile, travelers, watches

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(profile.router, prefix="/profile", tags=["profile"])
api_router.include_router(travelers.router, prefix="/travelers", tags=["travelers"])
api_router.include_router(watches.router, prefix="/watches", tags=["watches"])
api_router.include_router(deals.router, tags=["deals"])
api_router.include_router(bookings.router, tags=["bookings"])
