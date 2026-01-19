"""
Memory Manager - Gestión de historial de conversaciones usando LangChain
"""
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.chat_history import BaseChatMessageHistory

# Almacenamiento en memoria de sesiones (diccionario simple)
_session_store: dict[str, ChatMessageHistory] = {}


def get_session_history(session_id: str) -> BaseChatMessageHistory:
    """
    Obtiene o crea el historial de chat para una sesión específica.
    
    Args:
        session_id: Identificador único de la sesión/conversación
        
    Returns:
        Historial de mensajes de la sesión
    """
    if session_id not in _session_store:
        _session_store[session_id] = ChatMessageHistory()
    return _session_store[session_id]


def clear_session(session_id: str) -> bool:
    """
    Limpia el historial de una sesión específica.
    
    Args:
        session_id: Identificador de la sesión a limpiar
        
    Returns:
        True si se limpió exitosamente, False si no existía
    """
    if session_id in _session_store:
        del _session_store[session_id]
        return True
    return False


def list_sessions() -> list[str]:
    """
    Lista todas las sesiones activas.
    
    Returns:
        Lista de IDs de sesiones activas
    """
    return list(_session_store.keys())
