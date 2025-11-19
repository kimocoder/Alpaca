"""
Instance service for business logic related to instances.

This module provides business logic for instance operations,
including validation, lifecycle management, and configuration.
"""
import uuid
from typing import Optional, List, Dict, Any

try:
    from repositories.instance_repository import InstanceRepository
    from core.error_handler import ErrorHandler, AlpacaError, ErrorCategory
except ImportError:
    from ..repositories.instance_repository import InstanceRepository
    from ..core.error_handler import ErrorHandler, AlpacaError, ErrorCategory


class InstanceService:
    """Business logic for instance operations."""
    
    # Valid instance types
    VALID_TYPES = ['local', 'remote', 'cloud']
    
    def __init__(self, instance_repo: Optional[InstanceRepository] = None):
        """
        Initialize instance service.
        
        Args:
            instance_repo: Instance repository instance (creates new if None)
        """
        self.instance_repo = instance_repo or InstanceRepository()
    
    def create_instance(
        self,
        instance_type: str,
        properties: Dict[str, Any],
        pinned: bool = False
    ) -> str:
        """
        Create a new instance with validation.
        
        Args:
            instance_type: Type of instance ('local', 'remote', 'cloud')
            properties: Instance properties dictionary
            pinned: Whether to pin the instance
            
        Returns:
            The created instance ID
            
        Raises:
            AlpacaError: If validation fails or creation fails
        """
        # Validate instance type
        if instance_type not in self.VALID_TYPES:
            raise AlpacaError(
                f"Invalid instance type: {instance_type}",
                category=ErrorCategory.VALIDATION,
                user_message=f"Instance type must be one of: {', '.join(self.VALID_TYPES)}",
                recoverable=True
            )
        
        # Validate properties based on type
        self._validate_properties(instance_type, properties)
        
        # Create instance
        instance_id = str(uuid.uuid4())
        instance_data = {
            'id': instance_id,
            'type': instance_type,
            'properties': properties,
            'pinned': pinned
        }
        
        try:
            self.instance_repo.create(instance_data)
            return instance_id
        except Exception as e:
            ErrorHandler.log_error(
                message="Failed to create instance",
                exception=e,
                context={'type': instance_type, 'pinned': pinned}
            )
            raise AlpacaError(
                "Failed to create instance",
                category=ErrorCategory.DATABASE,
                user_message="Could not create the instance. Please try again.",
                recoverable=True
            ) from e
    
    def get_instance(self, instance_id: str) -> Optional[Dict[str, Any]]:
        """
        Get an instance by ID.
        
        Args:
            instance_id: The instance ID
            
        Returns:
            Instance dictionary or None if not found
        """
        try:
            return self.instance_repo.get_by_id(instance_id)
        except Exception as e:
            ErrorHandler.log_error(
                message="Failed to retrieve instance",
                exception=e,
                context={'instance_id': instance_id}
            )
            return None
    
    def get_all_instances(self) -> List[Dict[str, Any]]:
        """
        Get all instances.
        
        Returns:
            List of instance dictionaries
        """
        try:
            return self.instance_repo.get_all()
        except Exception as e:
            ErrorHandler.log_error(
                message="Failed to retrieve instances",
                exception=e
            )
            return []
    
    def get_pinned_instances(self) -> List[Dict[str, Any]]:
        """
        Get all pinned instances.
        
        Returns:
            List of pinned instance dictionaries
        """
        try:
            return self.instance_repo.get_pinned()
        except Exception as e:
            ErrorHandler.log_error(
                message="Failed to retrieve pinned instances",
                exception=e
            )
            return []
    
    def update_instance(
        self,
        instance_id: str,
        instance_type: Optional[str] = None,
        properties: Optional[Dict[str, Any]] = None,
        pinned: Optional[bool] = None
    ) -> bool:
        """
        Update an instance.
        
        Args:
            instance_id: The instance ID
            instance_type: New type (optional)
            properties: New properties (optional)
            pinned: New pinned status (optional)
            
        Returns:
            True if updated successfully
            
        Raises:
            AlpacaError: If validation fails
        """
        updates = {}
        
        if instance_type is not None:
            if instance_type not in self.VALID_TYPES:
                raise AlpacaError(
                    f"Invalid instance type: {instance_type}",
                    category=ErrorCategory.VALIDATION,
                    user_message=f"Instance type must be one of: {', '.join(self.VALID_TYPES)}",
                    recoverable=True
                )
            updates['type'] = instance_type
        
        if properties is not None:
            # Validate properties if type is being updated or get current type
            if instance_type:
                self._validate_properties(instance_type, properties)
            else:
                # Get current instance to validate against current type
                current = self.instance_repo.get_by_id(instance_id)
                if current:
                    self._validate_properties(current['type'], properties)
            updates['properties'] = properties
        
        if pinned is not None:
            updates['pinned'] = pinned
        
        if not updates:
            return False
        
        try:
            return self.instance_repo.update(instance_id, updates)
        except Exception as e:
            ErrorHandler.log_error(
                message="Failed to update instance",
                exception=e,
                context={'instance_id': instance_id, 'updates': updates}
            )
            raise AlpacaError(
                "Failed to update instance",
                category=ErrorCategory.DATABASE,
                user_message="Could not update the instance. Please try again.",
                recoverable=True
            ) from e
    
    def delete_instance(self, instance_id: str) -> bool:
        """
        Delete an instance.
        
        Args:
            instance_id: The instance ID
            
        Returns:
            True if deleted successfully
        """
        try:
            return self.instance_repo.delete(instance_id)
        except Exception as e:
            ErrorHandler.log_error(
                message="Failed to delete instance",
                exception=e,
                context={'instance_id': instance_id}
            )
            raise AlpacaError(
                "Failed to delete instance",
                category=ErrorCategory.DATABASE,
                user_message="Could not delete the instance. Please try again.",
                recoverable=True
            ) from e
    
    def pin_instance(self, instance_id: str) -> bool:
        """
        Pin an instance.
        
        Args:
            instance_id: The instance ID
            
        Returns:
            True if pinned successfully
        """
        return self.update_instance(instance_id, pinned=True)
    
    def unpin_instance(self, instance_id: str) -> bool:
        """
        Unpin an instance.
        
        Args:
            instance_id: The instance ID
            
        Returns:
            True if unpinned successfully
        """
        return self.update_instance(instance_id, pinned=False)
    
    def instance_exists(self, instance_id: str) -> bool:
        """
        Check if an instance exists.
        
        Args:
            instance_id: The instance ID
            
        Returns:
            True if instance exists
        """
        try:
            return self.instance_repo.exists(instance_id)
        except Exception as e:
            ErrorHandler.log_error(
                message="Failed to check instance existence",
                exception=e,
                context={'instance_id': instance_id}
            )
            return False
    
    def _validate_properties(
        self,
        instance_type: str,
        properties: Dict[str, Any]
    ) -> None:
        """
        Validate instance properties based on type.
        
        Args:
            instance_type: The instance type
            properties: Properties to validate
            
        Raises:
            AlpacaError: If validation fails
        """
        if not isinstance(properties, dict):
            raise AlpacaError(
                "Properties must be a dictionary",
                category=ErrorCategory.VALIDATION,
                user_message="Invalid instance configuration format.",
                recoverable=True
            )
        
        # Validate based on instance type
        if instance_type == 'local':
            self._validate_local_properties(properties)
        elif instance_type == 'remote':
            self._validate_remote_properties(properties)
        elif instance_type == 'cloud':
            self._validate_cloud_properties(properties)
    
    def _validate_local_properties(self, properties: Dict[str, Any]) -> None:
        """Validate properties for local instance."""
        # Local instances typically need model_directory
        if 'model_directory' in properties:
            model_dir = properties['model_directory']
            if not isinstance(model_dir, str) or not model_dir.strip():
                raise AlpacaError(
                    "Model directory must be a non-empty string",
                    category=ErrorCategory.VALIDATION,
                    user_message="Please provide a valid model directory path.",
                    recoverable=True
                )
    
    def _validate_remote_properties(self, properties: Dict[str, Any]) -> None:
        """Validate properties for remote instance."""
        # Remote instances need URL
        if 'url' not in properties:
            raise AlpacaError(
                "Remote instance requires 'url' property",
                category=ErrorCategory.VALIDATION,
                user_message="Please provide a URL for the remote instance.",
                recoverable=True
            )
        
        url = properties['url']
        if not isinstance(url, str) or not url.strip():
            raise AlpacaError(
                "URL must be a non-empty string",
                category=ErrorCategory.VALIDATION,
                user_message="Please provide a valid URL.",
                recoverable=True
            )
        
        # Basic URL validation
        if not (url.startswith('http://') or url.startswith('https://')):
            raise AlpacaError(
                "URL must start with http:// or https://",
                category=ErrorCategory.VALIDATION,
                user_message="Please provide a valid URL starting with http:// or https://",
                recoverable=True
            )
    
    def _validate_cloud_properties(self, properties: Dict[str, Any]) -> None:
        """Validate properties for cloud instance."""
        # Cloud instances need API key and endpoint
        required_fields = ['api_key', 'endpoint']
        
        for field in required_fields:
            if field not in properties:
                raise AlpacaError(
                    f"Cloud instance requires '{field}' property",
                    category=ErrorCategory.VALIDATION,
                    user_message=f"Please provide {field.replace('_', ' ')} for the cloud instance.",
                    recoverable=True
                )
            
            value = properties[field]
            if not isinstance(value, str) or not value.strip():
                raise AlpacaError(
                    f"{field} must be a non-empty string",
                    category=ErrorCategory.VALIDATION,
                    user_message=f"Please provide a valid {field.replace('_', ' ')}.",
                    recoverable=True
                )
    
    def get_instance_display_name(self, instance: Dict[str, Any]) -> str:
        """
        Get a display name for an instance.
        
        Args:
            instance: Instance dictionary
            
        Returns:
            Display name string
        """
        instance_type = instance.get('type', 'unknown')
        properties = instance.get('properties', {})
        
        if instance_type == 'local':
            return "Local Ollama"
        elif instance_type == 'remote':
            url = properties.get('url', 'Unknown')
            return f"Remote: {url}"
        elif instance_type == 'cloud':
            endpoint = properties.get('endpoint', 'Unknown')
            return f"Cloud: {endpoint}"
        else:
            return f"Instance ({instance_type})"
    
    def validate_instance_connection(
        self,
        instance_id: str
    ) -> Dict[str, Any]:
        """
        Validate that an instance can be connected to.
        
        Args:
            instance_id: The instance ID
            
        Returns:
            Dictionary with 'success' boolean and optional 'error' message
        """
        instance = self.get_instance(instance_id)
        if not instance:
            return {
                'success': False,
                'error': 'Instance not found'
            }
        
        # In a real implementation, this would test the actual connection
        # For now, just validate that required properties exist
        try:
            self._validate_properties(instance['type'], instance['properties'])
            return {'success': True}
        except AlpacaError as e:
            return {
                'success': False,
                'error': e.user_message or e.message
            }
