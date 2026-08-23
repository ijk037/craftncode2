"""
API v1 — Central Router — Sahayak AI
"""
from fastapi import APIRouter
from app.api.v1.endpoints.database import router as database_router
from app.api.v1.endpoints.government_import import router as govt_import_router
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.chat import router as chat_router
from app.api.v1.endpoints.schemes import router as schemes_router
from app.api.v1.endpoints.eligibility import router as eligibility_router
from app.api.v1.endpoints.recommendations import router as recommendations_router
from app.api.v1.endpoints.admin_translations import router as admin_translations_router
from app.api.v1.endpoints.admin_tms import router as admin_tms_router
from app.api.v1.endpoints.admin_dashboard import router as admin_dashboard_router
from app.api.v1.endpoints.admin_users import router as admin_users_router
from app.api.v1.endpoints.admin_system import router as admin_system_router
from app.api.v1.endpoints.admin_analytics import router as admin_analytics_router
from app.api.v1.endpoints.admin_schemes import router as admin_schemes_router
from app.api.v1.endpoints.recommend_router import router as recommend_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(database_router)
api_router.include_router(auth_router)
api_router.include_router(chat_router)
api_router.include_router(schemes_router)
api_router.include_router(eligibility_router)
api_router.include_router(recommendations_router)
api_router.include_router(recommend_router)
api_router.include_router(govt_import_router)
api_router.include_router(admin_translations_router)
api_router.include_router(admin_tms_router)
api_router.include_router(admin_dashboard_router)
api_router.include_router(admin_users_router)
api_router.include_router(admin_system_router)
api_router.include_router(admin_analytics_router)
api_router.include_router(admin_schemes_router)
