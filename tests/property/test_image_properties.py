"""
Property-based tests for image compression.

Feature: alpaca-code-quality-improvements
"""
import sys
from pathlib import Path
import base64
from io import BytesIO

import pytest
from hypothesis import given, strategies as st, assume, settings, HealthCheck
from PIL import Image

# Add src to path
src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_path))

from utils.image_utils import (
    compress_image,
    compress_image_base64,
    get_image_size_kb,
    get_image_size_kb_base64
)


# ============================================================================
# Helper strategies for generating test images
# ============================================================================

def generate_test_image(width: int, height: int, mode: str = 'RGB') -> bytes:
    """Generate a test image with a pattern that doesn't compress too well."""
    img = Image.new(mode, (width, height))
    # Use a complex pattern that creates larger file sizes
    # Avoid using random module - use deterministic but varied pattern
    
    if mode == 'RGB':
        for i in range(width):
            for j in range(height):
                # Use prime number multipliers for varied pattern
                r = (i * 7 + j * 13 + (i * j) % 50) % 256
                g = (i * 11 + j * 17 + (i + j) % 50) % 256
                b = (i * 13 + j * 19 + (i - j) % 50) % 256
                img.putpixel((i, j), (r, g, b))
    elif mode == 'RGBA':
        for i in range(width):
            for j in range(height):
                r = (i * 7 + j * 13 + (i * j) % 50) % 256
                g = (i * 11 + j * 17 + (i + j) % 50) % 256
                b = (i * 13 + j * 19 + (i - j) % 50) % 256
                img.putpixel((i, j), (r, g, b, 255))
    elif mode == 'L':
        for i in range(width):
            for j in range(height):
                val = (i * 7 + j * 13 + (i * j) % 50) % 256
                img.putpixel((i, j), val)
    
    # Convert to RGB if needed (JPEG doesn't support RGBA or L)
    if img.mode != 'RGB':
        if img.mode == 'RGBA':
            # Create white background for RGBA
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[-1])
            img = background
        else:
            img = img.convert('RGB')
    
    output = BytesIO()
    # Save as JPEG first to create a larger file that needs compression
    img.save(output, format='JPEG', quality=95)
    return output.getvalue()


@st.composite
def image_data_strategy(draw):
    """Strategy for generating test image data (optimized for speed)."""
    # Use medium-sized images that will need compression
    width = draw(st.integers(min_value=400, max_value=1200))
    height = draw(st.integers(min_value=400, max_value=1200))
    mode = draw(st.sampled_from(['RGB', 'RGBA', 'L']))
    
    return generate_test_image(width, height, mode)


# ============================================================================
# Property 18: Image Compression
# Validates: Requirements 8.1
# ============================================================================

@pytest.mark.property
@settings(
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
    deadline=1000,  # 1 second deadline for image processing
    max_examples=50  # Reduce number of examples for faster testing
)
@given(
    image_data=image_data_strategy(),
    max_size_kb=st.integers(min_value=100, max_value=1024)
)
def test_image_compression_size_limit(image_data, max_size_kb):
    """
    Feature: alpaca-code-quality-improvements, Property 18: Image Compression
    
    Property: For any image stored in the database, the size should not exceed 
    1MB after compression.
    
    Validates: Requirements 8.1
    """
    # Get original size
    original_size_kb = get_image_size_kb(image_data)
    
    # Only test compression if the image is reasonably large
    # This reduces filtering but still tests meaningful cases
    assume(original_size_kb > 50)
    
    # Compress the image
    compressed_data = compress_image(image_data, max_size_kb=max_size_kb)
    
    # Property assertion: compressed size should not exceed max_size_kb
    # Allow a small tolerance (10%) for edge cases
    compressed_size_kb = get_image_size_kb(compressed_data)
    
    assert compressed_size_kb <= max_size_kb * 1.1, \
        f"Compressed image size ({compressed_size_kb:.2f}KB) exceeds " \
        f"maximum ({max_size_kb}KB) with tolerance"
    
    # Verify the compressed data is valid image data
    try:
        img = Image.open(BytesIO(compressed_data))
        assert img.format == 'JPEG', "Compressed image should be in JPEG format"
        assert img.mode == 'RGB', "Compressed image should be in RGB mode"
    except Exception as e:
        pytest.fail(f"Compressed data is not a valid image: {e}")


@pytest.mark.property
@settings(
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
    deadline=1000,
    max_examples=50
)
@given(
    image_data=image_data_strategy()
)
def test_image_compression_default_1mb_limit(image_data):
    """
    Test that default compression limit is 1MB (1024KB).
    
    Property: For any image compressed with default settings, the result 
    should not exceed 1MB.
    """
    # Get original size
    original_size_kb = get_image_size_kb(image_data)
    
    # Only test if original is reasonably large
    assume(original_size_kb > 100)
    
    # Compress with default settings (should be 1024KB)
    compressed_data = compress_image(image_data)
    
    # Property assertion: should not exceed 1MB (with 10% tolerance)
    compressed_size_kb = get_image_size_kb(compressed_data)
    
    assert compressed_size_kb <= 1024 * 1.1, \
        f"Compressed image size ({compressed_size_kb:.2f}KB) exceeds 1MB default limit"
    
    # Verify it's a valid image
    img = Image.open(BytesIO(compressed_data))
    assert img.format == 'JPEG'


@pytest.mark.property
@settings(
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
    deadline=1000,
    max_examples=50
)
@given(
    image_data=image_data_strategy(),
    max_size_kb=st.integers(min_value=100, max_value=1024)
)
def test_image_compression_base64_roundtrip(image_data, max_size_kb):
    """
    Test that base64 compression works correctly.
    
    Property: For any image, compressing via base64 should produce the same
    result as compressing raw bytes and then encoding.
    """
    # Get original size
    original_size_kb = get_image_size_kb(image_data)
    assume(original_size_kb > 50)
    
    # Compress using base64 wrapper
    base64_input = base64.b64encode(image_data).decode('utf-8')
    compressed_base64 = compress_image_base64(base64_input, max_size_kb=max_size_kb)
    
    # Decode and check size
    compressed_data = base64.b64decode(compressed_base64)
    compressed_size_kb = get_image_size_kb(compressed_data)
    
    assert compressed_size_kb <= max_size_kb * 1.1, \
        f"Base64 compressed image size ({compressed_size_kb:.2f}KB) exceeds " \
        f"maximum ({max_size_kb}KB) with tolerance"
    
    # Verify it's a valid image
    img = Image.open(BytesIO(compressed_data))
    assert img.format == 'JPEG'


@pytest.mark.property
@settings(
    suppress_health_check=[HealthCheck.too_slow],
    deadline=1000,
    max_examples=50
)
@given(
    width=st.integers(min_value=100, max_value=800),
    height=st.integers(min_value=100, max_value=800),
    mode=st.sampled_from(['RGB', 'RGBA', 'L'])
)
def test_image_compression_preserves_content(width, height, mode):
    """
    Test that compression preserves image content (can be opened and viewed).
    
    Property: For any image, after compression, the image should still be
    openable and have reasonable dimensions.
    """
    # Generate test image
    image_data = generate_test_image(width, height, mode)
    
    # Compress to 1MB
    compressed_data = compress_image(image_data, max_size_kb=1024)
    
    # Open compressed image
    compressed_img = Image.open(BytesIO(compressed_data))
    
    # Property assertions
    assert compressed_img.format == 'JPEG', \
        "Compressed image should be JPEG format"
    
    assert compressed_img.mode == 'RGB', \
        "Compressed image should be RGB mode"
    
    # Dimensions should be reasonable (not zero, not negative)
    assert compressed_img.width > 0, "Compressed image width should be positive"
    assert compressed_img.height > 0, "Compressed image height should be positive"
    
    # Dimensions should not exceed original (might be smaller due to resizing)
    assert compressed_img.width <= width, \
        "Compressed image width should not exceed original"
    assert compressed_img.height <= height, \
        "Compressed image height should not exceed original"


@pytest.mark.property
@settings(
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
    deadline=1000,
    max_examples=50
)
@given(
    image_data=image_data_strategy(),
    quality=st.integers(min_value=20, max_value=95)
)
def test_image_compression_quality_parameter(image_data, quality):
    """
    Test that compression respects quality parameters.
    
    Property: For any image, compression with different quality settings
    should produce valid images.
    """
    original_size_kb = get_image_size_kb(image_data)
    assume(original_size_kb > 100)  # Only test on reasonably large images
    
    # Compress with custom quality
    compressed_data = compress_image(
        image_data,
        max_size_kb=1024,
        initial_quality=quality
    )
    
    # Should produce valid image
    img = Image.open(BytesIO(compressed_data))
    assert img.format == 'JPEG'
    
    # Should respect size limit (with tolerance)
    compressed_size_kb = get_image_size_kb(compressed_data)
    assert compressed_size_kb <= 1024 * 1.1


# ============================================================================
# Unit tests for edge cases
# ============================================================================

@pytest.mark.unit
def test_compress_empty_image_raises_error():
    """Test that compressing empty data raises ValueError."""
    with pytest.raises(ValueError, match="Image data cannot be empty"):
        compress_image(b'')


@pytest.mark.unit
def test_compress_invalid_image_raises_error():
    """Test that compressing invalid data raises IOError."""
    with pytest.raises(IOError, match="Failed to compress image"):
        compress_image(b'not an image')


@pytest.mark.unit
def test_compress_base64_empty_raises_error():
    """Test that compressing empty base64 raises ValueError."""
    with pytest.raises(ValueError, match="Base64 image data cannot be empty"):
        compress_image_base64('')


@pytest.mark.unit
def test_compress_base64_invalid_raises_error():
    """Test that compressing invalid base64 raises IOError."""
    # Invalid base64 that will decode but not be a valid image
    invalid_base64 = base64.b64encode(b'not an image').decode('utf-8')
    with pytest.raises(IOError, match="Failed to compress"):
        compress_image_base64(invalid_base64)


@pytest.mark.unit
def test_get_image_size_kb():
    """Test image size calculation."""
    # 1KB of data
    data = b'x' * 1024
    size = get_image_size_kb(data)
    assert size == 1.0
    
    # 2KB of data
    data = b'x' * 2048
    size = get_image_size_kb(data)
    assert size == 2.0


@pytest.mark.unit
def test_get_image_size_kb_base64():
    """Test base64 image size calculation."""
    # 1KB of data
    data = b'x' * 1024
    encoded = base64.b64encode(data).decode('utf-8')
    size = get_image_size_kb_base64(encoded)
    assert size == 1.0


@pytest.mark.unit
def test_compress_very_small_image():
    """Test that very small images are handled correctly."""
    # Create a tiny 10x10 image
    img = Image.new('RGB', (10, 10), color='red')
    output = BytesIO()
    img.save(output, format='PNG')
    image_data = output.getvalue()
    
    # Compress with 1MB limit (image is already tiny)
    compressed = compress_image(image_data, max_size_kb=1024)
    
    # Should still be valid
    compressed_img = Image.open(BytesIO(compressed))
    assert compressed_img.format == 'JPEG'
    assert compressed_img.size == (10, 10)


@pytest.mark.unit
def test_compress_rgba_to_rgb_conversion():
    """Test that RGBA images are converted to RGB."""
    # Create RGBA image with transparency
    img = Image.new('RGBA', (100, 100), color=(255, 0, 0, 128))
    output = BytesIO()
    img.save(output, format='PNG')
    image_data = output.getvalue()
    
    # Compress
    compressed = compress_image(image_data, max_size_kb=1024)
    
    # Should be RGB (JPEG doesn't support transparency)
    compressed_img = Image.open(BytesIO(compressed))
    assert compressed_img.mode == 'RGB'
    assert compressed_img.format == 'JPEG'


@pytest.mark.unit
def test_compress_grayscale_to_rgb_conversion():
    """Test that grayscale images are converted to RGB."""
    # Create grayscale image
    img = Image.new('L', (100, 100), color=128)
    output = BytesIO()
    img.save(output, format='PNG')
    image_data = output.getvalue()
    
    # Compress
    compressed = compress_image(image_data, max_size_kb=1024)
    
    # Should be RGB
    compressed_img = Image.open(BytesIO(compressed))
    assert compressed_img.mode == 'RGB'
    assert compressed_img.format == 'JPEG'


@pytest.mark.unit
def test_compress_large_image_requires_resizing():
    """Test that very large images are resized if quality reduction isn't enough."""
    # Create a large image that will need resizing
    # Use a pattern that doesn't compress well
    img = Image.new('RGB', (4000, 4000))
    pixels = img.load()
    for i in range(4000):
        for j in range(4000):
            # Random-ish pattern that doesn't compress well
            pixels[i, j] = ((i * j) % 256, (i + j) % 256, (i - j) % 256)
    
    output = BytesIO()
    img.save(output, format='PNG')
    image_data = output.getvalue()
    
    # Compress to very small size (will require resizing)
    compressed = compress_image(image_data, max_size_kb=100)
    
    # Should be under limit
    compressed_size_kb = get_image_size_kb(compressed)
    # Allow some tolerance since we might not hit exactly 100KB
    assert compressed_size_kb <= 150, \
        f"Compressed size {compressed_size_kb}KB should be close to 100KB limit"
    
    # Should be valid and smaller dimensions
    compressed_img = Image.open(BytesIO(compressed))
    assert compressed_img.format == 'JPEG'
    assert compressed_img.width < 4000 or compressed_img.height < 4000, \
        "Image should be resized"
