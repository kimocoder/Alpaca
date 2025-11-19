"""
Message list model with lazy loading for virtual scrolling.

This module provides a GTK ListModel implementation that loads messages
on-demand in batches, enabling efficient rendering of large chat histories.
"""
import logging
from typing import Optional, Dict, Any, List
from gi.repository import GObject, Gio, GLib

logger = logging.getLogger(__name__)


class MessageListModel(GObject.Object, Gio.ListModel):
    """
    List model with lazy loading for messages.
    
    This model implements on-demand loading of messages in batches,
    allowing virtual scrolling to efficiently handle large chat histories.
    """
    
    __gtype_name__ = 'AlpacaMessageListModel'
    
    def __init__(self, chat_id: str, message_service, batch_size: int = 50):
        """
        Initialize the message list model.
        
        Args:
            chat_id: The chat ID to load messages from
            message_service: MessageService instance for loading messages
            batch_size: Number of messages to load per batch (default: 50)
        """
        super().__init__()
        self.chat_id = chat_id
        self.message_service = message_service
        self.batch_size = batch_size
        self._cache: Dict[int, Any] = {}
        self._total_count = self._get_total_count()
        self._loaded_batches = set()
        
        logger.debug(
            f"MessageListModel initialized: chat_id={chat_id}, "
            f"total_count={self._total_count}, batch_size={batch_size}"
        )
    
    def _get_total_count(self) -> int:
        """Get the total number of messages in the chat."""
        try:
            return self.message_service.count_messages(self.chat_id)
        except Exception as e:
            logger.error(f"Failed to get message count: {e}")
            return 0
    
    def _load_batch(self, position: int) -> None:
        """
        Load a batch of messages containing the requested position.
        
        Args:
            position: The message position that triggered the load
        """
        # Calculate which batch this position belongs to
        batch_index = position // self.batch_size
        
        # Skip if already loaded
        if batch_index in self._loaded_batches:
            return
        
        # Calculate offset for this batch
        offset = batch_index * self.batch_size
        
        logger.debug(
            f"Loading batch {batch_index}: offset={offset}, "
            f"limit={self.batch_size}"
        )
        
        try:
            # Load messages for this batch
            messages = self.message_service.get_messages_for_chat(
                self.chat_id,
                limit=self.batch_size,
                offset=offset
            )
            
            # Cache the loaded messages
            for i, message in enumerate(messages):
                cache_position = offset + i
                self._cache[cache_position] = message
            
            # Mark batch as loaded
            self._loaded_batches.add(batch_index)
            
            logger.debug(
                f"Batch {batch_index} loaded: {len(messages)} messages cached"
            )
            
        except Exception as e:
            logger.error(f"Failed to load batch {batch_index}: {e}")
    
    def do_get_item_type(self) -> GObject.GType:
        """Return the type of items in this model."""
        # Return GObject type - actual message widgets will be created separately
        return GObject.TYPE_OBJECT
    
    def do_get_n_items(self) -> int:
        """Return the total number of items in the model."""
        return self._total_count
    
    def do_get_item(self, position: int) -> Optional[Any]:
        """
        Get item at the specified position, loading if necessary.
        
        Args:
            position: The position of the item to retrieve
            
        Returns:
            Message data dictionary or None if position is invalid
        """
        if position < 0 or position >= self._total_count:
            return None
        
        # Load batch if not in cache
        if position not in self._cache:
            self._load_batch(position)
        
        # Return cached item
        return self._cache.get(position)
    
    def get_message_data(self, position: int) -> Optional[Dict[str, Any]]:
        """
        Get message data at the specified position.
        
        This is a convenience method that returns the message dictionary
        directly without GObject wrapping.
        
        Args:
            position: The position of the message
            
        Returns:
            Message data dictionary or None
        """
        return self.do_get_item(position)
    
    def unload_all(self) -> None:
        """
        Unload all cached messages to free memory.
        
        This should be called when switching away from a chat to
        release memory used by cached messages.
        """
        logger.debug(
            f"Unloading all messages: {len(self._cache)} cached items"
        )
        self._cache.clear()
        self._loaded_batches.clear()
    
    def refresh(self) -> None:
        """
        Refresh the model by reloading the message count.
        
        This should be called when messages are added or removed
        from the chat.
        """
        old_count = self._total_count
        self._total_count = self._get_total_count()
        
        if old_count != self._total_count:
            logger.debug(
                f"Message count changed: {old_count} -> {self._total_count}"
            )
            # Clear cache to force reload
            self._cache.clear()
            self._loaded_batches.clear()
            # Notify listeners of the change
            self.items_changed(0, old_count, self._total_count)
    
    def get_cache_size(self) -> int:
        """
        Get the number of messages currently cached in memory.
        
        Returns:
            Number of cached messages
        """
        return len(self._cache)
    
    def get_loaded_batch_count(self) -> int:
        """
        Get the number of batches currently loaded.
        
        Returns:
            Number of loaded batches
        """
        return len(self._loaded_batches)
