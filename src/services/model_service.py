"""
Model service for business logic related to AI models.

This module provides business logic for model operations,
including model listing, validation, and management.
"""
from typing import Optional, List, Dict, Any
import re

try:
    from repositories.instance_repository import InstanceRepository
    from core.error_handler import ErrorHandler, AlpacaError, ErrorCategory
except ImportError:
    from ..repositories.instance_repository import InstanceRepository
    from ..core.error_handler import ErrorHandler, AlpacaError, ErrorCategory


class ModelService:
    """Business logic for model operations."""
    
    def __init__(self, instance_repo: Optional[InstanceRepository] = None):
        """
        Initialize model service.
        
        Args:
            instance_repo: Instance repository instance (creates new if None)
        """
        self.instance_repo = instance_repo or InstanceRepository()
    
    def get_models_for_instance(self, instance_id: str) -> List[str]:
        """
        Get all models available for an instance.
        
        Args:
            instance_id: The instance ID
            
        Returns:
            List of model names
        """
        try:
            return self.instance_repo.get_model_list(instance_id)
        except Exception as e:
            ErrorHandler.log_error(
                message="Failed to retrieve model list",
                exception=e,
                context={'instance_id': instance_id}
            )
            return []
    
    def set_models_for_instance(
        self,
        instance_id: str,
        model_list: List[str]
    ) -> None:
        """
        Set the model list for an instance.
        
        Args:
            instance_id: The instance ID
            model_list: List of model names
            
        Raises:
            AlpacaError: If update fails
        """
        # Validate model list
        if not isinstance(model_list, list):
            raise AlpacaError(
                "Model list must be a list",
                category=ErrorCategory.VALIDATION,
                user_message="Invalid model list format.",
                recoverable=True
            )
        
        # Remove duplicates and empty strings
        model_list = [m.strip() for m in model_list if m and m.strip()]
        model_list = list(dict.fromkeys(model_list))  # Remove duplicates while preserving order
        
        try:
            self.instance_repo.set_model_list(instance_id, model_list)
        except Exception as e:
            ErrorHandler.log_error(
                message="Failed to set model list",
                exception=e,
                context={'instance_id': instance_id, 'model_count': len(model_list)}
            )
            raise AlpacaError(
                "Failed to update model list",
                category=ErrorCategory.DATABASE,
                user_message="Could not save the model list. Please try again.",
                recoverable=True
            ) from e
    
    def add_model_to_instance(self, instance_id: str, model_name: str) -> None:
        """
        Add a model to an instance's model list.
        
        Args:
            instance_id: The instance ID
            model_name: The model name to add
            
        Raises:
            AlpacaError: If validation fails or update fails
        """
        # Validate model name
        if not model_name or not model_name.strip():
            raise AlpacaError(
                "Model name cannot be empty",
                category=ErrorCategory.VALIDATION,
                user_message="Please provide a model name.",
                recoverable=True
            )
        
        model_name = model_name.strip()
        
        try:
            self.instance_repo.add_model_to_list(instance_id, model_name)
        except Exception as e:
            ErrorHandler.log_error(
                message="Failed to add model",
                exception=e,
                context={'instance_id': instance_id, 'model_name': model_name}
            )
            raise AlpacaError(
                "Failed to add model",
                category=ErrorCategory.DATABASE,
                user_message="Could not add the model. Please try again.",
                recoverable=True
            ) from e
    
    def remove_model_from_instance(
        self,
        instance_id: str,
        model_name: str
    ) -> None:
        """
        Remove a model from an instance's model list.
        
        Args:
            instance_id: The instance ID
            model_name: The model name to remove
            
        Raises:
            AlpacaError: If update fails
        """
        try:
            self.instance_repo.remove_model_from_list(instance_id, model_name)
        except Exception as e:
            ErrorHandler.log_error(
                message="Failed to remove model",
                exception=e,
                context={'instance_id': instance_id, 'model_name': model_name}
            )
            raise AlpacaError(
                "Failed to remove model",
                category=ErrorCategory.DATABASE,
                user_message="Could not remove the model. Please try again.",
                recoverable=True
            ) from e
    
    def validate_model_name(self, model_name: str) -> bool:
        """
        Validate a model name format.
        
        Args:
            model_name: The model name to validate
            
        Returns:
            True if valid, False otherwise
        """
        if not model_name or not model_name.strip():
            return False
        
        # Model names should be alphanumeric with hyphens, underscores, dots, and colons
        # Examples: llama2, mistral:7b, codellama:13b-instruct
        pattern = r'^[a-zA-Z0-9][a-zA-Z0-9._:-]*$'
        return bool(re.match(pattern, model_name.strip()))
    
    def parse_model_name(self, model_name: str) -> Dict[str, str]:
        """
        Parse a model name into components.
        
        Args:
            model_name: The model name to parse (e.g., "llama2:13b-instruct")
            
        Returns:
            Dictionary with 'base', 'tag', and 'variant' keys
        """
        if not model_name:
            return {'base': '', 'tag': '', 'variant': ''}
        
        model_name = model_name.strip()
        
        # Split on colon to separate base from tag
        if ':' in model_name:
            base, tag = model_name.split(':', 1)
        else:
            base = model_name
            tag = ''
        
        # Split tag on hyphen to separate size from variant
        variant = ''
        if tag and '-' in tag:
            tag_parts = tag.split('-', 1)
            tag = tag_parts[0]
            variant = tag_parts[1]
        
        return {
            'base': base,
            'tag': tag,
            'variant': variant
        }
    
    def format_model_display_name(self, model_name: str) -> str:
        """
        Format a model name for display.
        
        Args:
            model_name: The model name
            
        Returns:
            Formatted display name
        """
        if not model_name:
            return "Unknown Model"
        
        parsed = self.parse_model_name(model_name)
        
        # Capitalize base name
        display_name = parsed['base'].capitalize()
        
        # Add tag if present
        if parsed['tag']:
            display_name += f" ({parsed['tag']}"
            if parsed['variant']:
                display_name += f"-{parsed['variant']}"
            display_name += ")"
        
        return display_name
    
    def get_model_size(self, model_name: str) -> Optional[str]:
        """
        Extract model size from model name.
        
        Args:
            model_name: The model name
            
        Returns:
            Model size (e.g., "7b", "13b") or None if not found
        """
        parsed = self.parse_model_name(model_name)
        tag = parsed['tag']
        
        # Check if tag looks like a size (e.g., "7b", "13b", "70b")
        if tag and re.match(r'^\d+[bB]$', tag):
            return tag.lower()
        
        return None
    
    def sort_models(self, models: List[str]) -> List[str]:
        """
        Sort models by base name and size.
        
        Args:
            models: List of model names
            
        Returns:
            Sorted list of model names
        """
        def model_sort_key(model_name: str) -> tuple:
            parsed = self.parse_model_name(model_name)
            base = parsed['base'].lower()
            
            # Extract numeric size for sorting
            size = 0
            if parsed['tag']:
                match = re.match(r'^(\d+)[bB]$', parsed['tag'])
                if match:
                    size = int(match.group(1))
            
            variant = parsed['variant'].lower()
            
            return (base, size, variant)
        
        try:
            return sorted(models, key=model_sort_key)
        except Exception as e:
            ErrorHandler.log_error(
                message="Failed to sort models",
                exception=e,
                context={'model_count': len(models)}
            )
            # Return unsorted if sorting fails
            return models
    
    def filter_models(
        self,
        models: List[str],
        search_term: Optional[str] = None,
        min_size: Optional[int] = None,
        max_size: Optional[int] = None
    ) -> List[str]:
        """
        Filter models by search term and size.
        
        Args:
            models: List of model names
            search_term: Optional search term to filter by
            min_size: Optional minimum size in billions (e.g., 7 for 7b)
            max_size: Optional maximum size in billions
            
        Returns:
            Filtered list of model names
        """
        filtered = models.copy()
        
        # Filter by search term
        if search_term and search_term.strip():
            search_lower = search_term.strip().lower()
            filtered = [m for m in filtered if search_lower in m.lower()]
        
        # Filter by size
        if min_size is not None or max_size is not None:
            size_filtered = []
            for model in filtered:
                size_str = self.get_model_size(model)
                if size_str:
                    # Extract numeric value
                    match = re.match(r'^(\d+)[bB]$', size_str)
                    if match:
                        size = int(match.group(1))
                        if min_size is not None and size < min_size:
                            continue
                        if max_size is not None and size > max_size:
                            continue
                        size_filtered.append(model)
                else:
                    # Include models without size info if no min_size specified
                    if min_size is None:
                        size_filtered.append(model)
            filtered = size_filtered
        
        return filtered
