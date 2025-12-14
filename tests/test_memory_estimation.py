"""Tests for model memory usage estimation."""

import sys
import os

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from utils.model_utils import estimate_memory_usage


def test_estimate_memory_usage_7b_q4():
    """Test memory estimation for 7B model with Q4 quantization."""
    result = estimate_memory_usage("7B", "Q4_0")
    assert result is not None
    assert "GB" in result
    # 7B Q4 should be around 4-5 GB
    value = float(result.split()[0])
    assert 3.5 <= value <= 5.5, f"Expected 3.5-5.5 GB, got {result}"


def test_estimate_memory_usage_13b_q5():
    """Test memory estimation for 13B model with Q5 quantization."""
    result = estimate_memory_usage("13B", "Q5_K_M")
    assert result is not None
    assert "GB" in result
    # 13B Q5 should be around 9-11 GB
    value = float(result.split()[0])
    assert 8 <= value <= 12, f"Expected 8-12 GB, got {result}"


def test_estimate_memory_usage_70b_q8():
    """Test memory estimation for 70B model with Q8 quantization."""
    result = estimate_memory_usage("70B", "Q8_0")
    assert result is not None
    assert "GB" in result
    # 70B Q8 should be around 70-80 GB
    value = float(result.split()[0])
    assert 65 <= value <= 85, f"Expected 65-85 GB, got {result}"


def test_estimate_memory_usage_small_model():
    """Test memory estimation for small model (< 1GB)."""
    result = estimate_memory_usage("500M", "Q4_0")
    assert result is not None
    # Small models should show MB
    assert "MB" in result or "GB" in result


def test_estimate_memory_usage_none_inputs():
    """Test that None inputs return None."""
    assert estimate_memory_usage(None, "Q4_0") is None
    assert estimate_memory_usage("7B", None) is None
    assert estimate_memory_usage(None, None) is None


def test_estimate_memory_usage_invalid_format():
    """Test that invalid parameter size returns None."""
    assert estimate_memory_usage("invalid", "Q4_0") is None
    assert estimate_memory_usage("", "Q4_0") is None


def test_estimate_memory_usage_f16():
    """Test memory estimation with F16 quantization."""
    result = estimate_memory_usage("7B", "F16")
    assert result is not None
    assert "GB" in result
    # F16 uses more memory than Q4
    value = float(result.split()[0])
    assert value > 10, f"F16 should use more memory, got {result}"


if __name__ == "__main__":
    # Run tests
    test_estimate_memory_usage_7b_q4()
    test_estimate_memory_usage_13b_q5()
    test_estimate_memory_usage_70b_q8()
    test_estimate_memory_usage_small_model()
    test_estimate_memory_usage_none_inputs()
    test_estimate_memory_usage_invalid_format()
    test_estimate_memory_usage_f16()
    print("All tests passed!")
