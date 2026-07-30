from .health import register_health_tools
from .person import register_person_tools
from .search import register_search_tools

__all__ = ["register_health_tools", "register_person_tools", "register_search_tools"]
