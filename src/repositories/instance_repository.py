"""
Instance repository for database operations related to instances.

This module provides database access methods for instance entities,
including CRUD operations and specialized queries.
"""
from typing import Optional, List, Dict, Any
import json

from .base_repository import BaseRepository


class InstanceRepository(BaseRepository):
    """Repository for instance-related database operations."""
    
    def get_by_id(self, instance_id: str) -> Optional[Dict[str, Any]]:
        """
        Get an instance by its ID.
        
        Args:
            instance_id: The instance ID to retrieve
            
        Returns:
            Instance dictionary or None if not found
        """
        results = self.execute_query(
            "SELECT id, pinned, type, properties FROM instance WHERE id = ?",
            (instance_id,),
            context="get_instance_by_id"
        )
        
        if results:
            row = results[0]
            return {
                'id': row['id'],
                'pinned': bool(row['pinned']),
                'type': row['type'],
                'properties': json.loads(row['properties'])
            }
        return None
    
    def get_all(self) -> List[Dict[str, Any]]:
        """
        Get all instances.
        
        Returns:
            List of instance dictionaries
        """
        results = self.execute_query(
            "SELECT id, pinned, type, properties FROM instance ORDER BY pinned DESC, id ASC",
            context="get_all_instances"
        )
        
        instances = []
        for row in results:
            instances.append({
                'id': row['id'],
                'pinned': bool(row['pinned']),
                'type': row['type'],
                'properties': json.loads(row['properties'])
            })
        return instances
    
    def get_pinned(self) -> List[Dict[str, Any]]:
        """
        Get all pinned instances.
        
        Returns:
            List of pinned instance dictionaries
        """
        results = self.execute_query(
            "SELECT id, pinned, type, properties FROM instance WHERE pinned = 1 ORDER BY id ASC",
            context="get_pinned_instances"
        )
        
        instances = []
        for row in results:
            instances.append({
                'id': row['id'],
                'pinned': True,
                'type': row['type'],
                'properties': json.loads(row['properties'])
            })
        return instances
    
    def create(self, instance: Dict[str, Any]) -> str:
        """
        Create a new instance.
        
        Args:
            instance: Instance dictionary with required fields
            
        Returns:
            The instance ID
        """
        instance_id = instance['id']
        pinned = int(instance.get('pinned', False))
        instance_type = instance['type']
        properties = json.dumps(instance.get('properties', {}))
        
        self.execute_update(
            "INSERT INTO instance (id, pinned, type, properties) VALUES (?, ?, ?, ?)",
            (instance_id, pinned, instance_type, properties),
            context="create_instance"
        )
        
        return instance_id
    
    def update(self, instance_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update an existing instance.
        
        Args:
            instance_id: The instance ID to update
            updates: Dictionary of fields to update
            
        Returns:
            True if instance was updated, False if not found
        """
        # Build dynamic update query
        set_clauses = []
        params = []
        
        if 'pinned' in updates:
            set_clauses.append("pinned = ?")
            params.append(int(updates['pinned']))
        
        if 'type' in updates:
            set_clauses.append("type = ?")
            params.append(updates['type'])
        
        if 'properties' in updates:
            set_clauses.append("properties = ?")
            params.append(json.dumps(updates['properties']))
        
        if not set_clauses:
            return False
        
        params.append(instance_id)
        query = f"UPDATE instance SET {', '.join(set_clauses)} WHERE id = ?"
        
        affected = self.execute_update(query, tuple(params), context="update_instance")
        return affected > 0
    
    def delete(self, instance_id: str) -> bool:
        """
        Delete an instance.
        
        Args:
            instance_id: The instance ID to delete
            
        Returns:
            True if instance was deleted, False if not found
        """
        affected = self.execute_update(
            "DELETE FROM instance WHERE id = ?",
            (instance_id,),
            context="delete_instance"
        )
        return affected > 0
    
    def exists(self, instance_id: str) -> bool:
        """
        Check if an instance exists.
        
        Args:
            instance_id: The instance ID to check
            
        Returns:
            True if instance exists, False otherwise
        """
        results = self.execute_query(
            "SELECT 1 FROM instance WHERE id = ? LIMIT 1",
            (instance_id,),
            context="check_instance_exists"
        )
        return len(results) > 0
    
    def get_model_list(self, instance_id: str) -> List[str]:
        """
        Get the model list for an online instance.
        
        Args:
            instance_id: The instance ID
            
        Returns:
            List of model names
        """
        results = self.execute_query(
            "SELECT list FROM online_instance_model_list WHERE id = ?",
            (instance_id,),
            context="get_instance_model_list"
        )
        
        if results:
            return json.loads(results[0]['list'])
        return []
    
    def set_model_list(self, instance_id: str, model_list: List[str]) -> None:
        """
        Set the model list for an online instance.
        
        Args:
            instance_id: The instance ID
            model_list: List of model names
        """
        # Check if entry exists
        exists = self.execute_query(
            "SELECT 1 FROM online_instance_model_list WHERE id = ? LIMIT 1",
            (instance_id,),
            context="check_model_list_exists"
        )
        
        if exists:
            self.execute_update(
                "UPDATE online_instance_model_list SET list = ? WHERE id = ?",
                (json.dumps(model_list), instance_id),
                context="update_instance_model_list"
            )
        else:
            self.execute_update(
                "INSERT INTO online_instance_model_list (id, list) VALUES (?, ?)",
                (instance_id, json.dumps(model_list)),
                context="create_instance_model_list"
            )
    
    def add_model_to_list(self, instance_id: str, model_name: str) -> None:
        """
        Add a model to an instance's model list.
        
        Args:
            instance_id: The instance ID
            model_name: The model name to add
        """
        model_list = self.get_model_list(instance_id)
        if model_name not in model_list:
            model_list.append(model_name)
            self.set_model_list(instance_id, model_list)
    
    def remove_model_from_list(self, instance_id: str, model_name: str) -> None:
        """
        Remove a model from an instance's model list.
        
        Args:
            instance_id: The instance ID
            model_name: The model name to remove
        """
        model_list = self.get_model_list(instance_id)
        if model_name in model_list:
            model_list.remove(model_name)
            self.set_model_list(instance_id, model_list)
