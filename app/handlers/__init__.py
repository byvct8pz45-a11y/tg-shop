from aiogram import Router
from .common import router as common_router
from .order import router as order_router
from .review import router as review_router
from .client import router as client_router
from .admin import router as admin_router
from .channel import router as channel_router


def get_main_router() -> Router:
    main = Router()
    main.include_router(channel_router)   # channel_post — первым, чтобы не перехватывали другие
    main.include_router(common_router)
    main.include_router(order_router)
    main.include_router(review_router)
    main.include_router(client_router)
    main.include_router(admin_router)
    return main
