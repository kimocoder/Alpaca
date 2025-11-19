"""
Image utility functions for Alpaca.

Provides image compression and processing functionality.
"""
import base64
import logging
from io import BytesIO
from typing import Optional

from PIL import Image

logger = logging.getLogger(__name__)


def compress_image(
    image_data: bytes,
    max_size_kb: int = 1024,
    initial_quality: int = 95,
    min_quality: int = 20
) -> bytes:
    """
    Compress an image to a target maximum size.
    
    This function takes image data and compresses it to ensure the resulting
    file size does not exceed the specified maximum. It uses an iterative
    approach, adjusting JPEG quality until the target size is achieved.
    
    Args:
        image_data: Raw image bytes (can be any format PIL supports)
        max_size_kb: Maximum size in kilobytes (default: 1024 = 1MB)
        initial_quality: Starting JPEG quality (1-100, default: 95)
        min_quality: Minimum acceptable quality (1-100, default: 20)
    
    Returns:
        Compressed image data as bytes in JPEG format
    
    Raises:
        ValueError: If image_data is invalid or cannot be processed
        IOError: If image cannot be opened or processed
    
    Examples:
        >>> with open('large_image.png', 'rb') as f:
        ...     data = f.read()
        >>> compressed = compress_image(data, max_size_kb=500)
        >>> len(compressed) <= 500 * 1024
        True
    """
    if not image_data:
        raise ValueError("Image data cannot be empty")
    
    max_size_bytes = max_size_kb * 1024
    
    try:
        # Open the image
        img = Image.open(BytesIO(image_data))
        
        # Convert RGBA to RGB if necessary (JPEG doesn't support transparency)
        if img.mode in ('RGBA', 'LA', 'P'):
            # Create a white background
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Start with initial quality
        quality = initial_quality
        compressed_data = None
        
        # Iteratively reduce quality until size is acceptable
        while quality >= min_quality:
            output = BytesIO()
            img.save(output, format='JPEG', quality=quality, optimize=True)
            compressed_data = output.getvalue()
            
            # Check if we've reached the target size
            if len(compressed_data) <= max_size_bytes:
                logger.debug(
                    f"Compressed image to {len(compressed_data)} bytes "
                    f"(quality={quality})"
                )
                return compressed_data
            
            # Reduce quality for next iteration
            quality -= 5
        
        # If we couldn't get below max_size with quality reduction alone,
        # try resizing the image
        if compressed_data and len(compressed_data) > max_size_bytes:
            logger.warning(
                f"Could not compress to {max_size_kb}KB with quality reduction alone. "
                f"Attempting to resize image."
            )
            
            # Calculate resize factor to reduce file size
            # Rough estimate: reducing dimensions by sqrt(target/current) ratio
            size_ratio = max_size_bytes / len(compressed_data)
            scale_factor = size_ratio ** 0.5  # Square root because area is 2D
            
            new_width = int(img.width * scale_factor * 0.9)  # 0.9 for safety margin
            new_height = int(img.height * scale_factor * 0.9)
            
            # Ensure minimum dimensions
            new_width = max(new_width, 100)
            new_height = max(new_height, 100)
            
            resized_img = img.resize((new_width, new_height), Image.LANCZOS)
            
            # Try compression again with resized image
            quality = initial_quality
            while quality >= min_quality:
                output = BytesIO()
                resized_img.save(output, format='JPEG', quality=quality, optimize=True)
                compressed_data = output.getvalue()
                
                if len(compressed_data) <= max_size_bytes:
                    logger.info(
                        f"Compressed image to {len(compressed_data)} bytes "
                        f"after resizing to {new_width}x{new_height} (quality={quality})"
                    )
                    return compressed_data
                
                quality -= 5
        
        # If we still can't compress enough, return the best we got
        logger.warning(
            f"Could not compress image below {max_size_kb}KB. "
            f"Returning {len(compressed_data)} bytes."
        )
        return compressed_data
        
    except Exception as e:
        logger.error(f"Error compressing image: {e}")
        raise IOError(f"Failed to compress image: {e}") from e


def compress_image_base64(
    image_base64: str,
    max_size_kb: int = 1024,
    initial_quality: int = 95,
    min_quality: int = 20
) -> str:
    """
    Compress a base64-encoded image to a target maximum size.
    
    This is a convenience wrapper around compress_image() that handles
    base64 encoding/decoding.
    
    Args:
        image_base64: Base64-encoded image string
        max_size_kb: Maximum size in kilobytes (default: 1024 = 1MB)
        initial_quality: Starting JPEG quality (1-100, default: 95)
        min_quality: Minimum acceptable quality (1-100, default: 20)
    
    Returns:
        Compressed image data as base64-encoded string
    
    Raises:
        ValueError: If image_base64 is invalid
        IOError: If image cannot be processed
    
    Examples:
        >>> encoded = base64.b64encode(image_bytes).decode('utf-8')
        >>> compressed = compress_image_base64(encoded, max_size_kb=500)
        >>> len(base64.b64decode(compressed)) <= 500 * 1024
        True
    """
    if not image_base64:
        raise ValueError("Base64 image data cannot be empty")
    
    try:
        # Decode base64 to bytes
        image_data = base64.b64decode(image_base64)
        
        # Compress the image
        compressed_data = compress_image(
            image_data,
            max_size_kb=max_size_kb,
            initial_quality=initial_quality,
            min_quality=min_quality
        )
        
        # Encode back to base64
        return base64.b64encode(compressed_data).decode('utf-8')
        
    except Exception as e:
        logger.error(f"Error compressing base64 image: {e}")
        raise IOError(f"Failed to compress base64 image: {e}") from e


def get_image_size_kb(image_data: bytes) -> float:
    """
    Get the size of image data in kilobytes.
    
    Args:
        image_data: Raw image bytes
    
    Returns:
        Size in kilobytes (float)
    
    Examples:
        >>> data = b'fake image data'
        >>> get_image_size_kb(data)
        0.0146484375
    """
    return len(image_data) / 1024


def get_image_size_kb_base64(image_base64: str) -> float:
    """
    Get the size of a base64-encoded image in kilobytes.
    
    Args:
        image_base64: Base64-encoded image string
    
    Returns:
        Size in kilobytes (float)
    
    Examples:
        >>> encoded = base64.b64encode(b'fake image data').decode('utf-8')
        >>> get_image_size_kb_base64(encoded)
        0.0146484375
    """
    image_data = base64.b64decode(image_base64)
    return get_image_size_kb(image_data)
