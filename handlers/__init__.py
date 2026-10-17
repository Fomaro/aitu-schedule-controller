from aiogram import Router
from .start import router as start_router
from .dashboard import router as dashboard_router
from .process import router as process_router
from .git_ops import router as git_router
from .roles import router as roles_router
from .logs import router as logs_router
from .broadcast import router as broadcast_router
from .diagnostics import router as diagnostics_router


def setup_handlers(root_router: Router):
    """Регистрирует все дочерние роутеры контроллера в корневой роутер."""
    root_router.include_router(start_router)
    root_router.include_router(dashboard_router)
    root_router.include_router(process_router)
    root_router.include_router(git_router)
    root_router.include_router(roles_router)
    root_router.include_router(logs_router)
    root_router.include_router(broadcast_router)
    root_router.include_router(diagnostics_router)


__all__ = ["setup_handlers"]
