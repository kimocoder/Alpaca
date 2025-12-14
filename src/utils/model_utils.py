"""Utility functions for model management."""

import re


def estimate_memory_usage(parameter_size: str, quantization_level: str) -> str:
    """
    Estimate memory usage for a model based on parameter size and quantization level.
    
    Args:
        parameter_size: String like "7B", "13B", "70B", etc.
        quantization_level: String like "Q4_0", "Q5_K_M", "Q8_0", "F16", etc.
    
    Returns:
        Estimated memory usage as a human-readable string (e.g., "4.1 GB")
        Returns None if inputs are invalid or missing.
    """
    if not parameter_size or not quantization_level:
        return None
    
    # Extract parameter count in billions
    param_match = re.match(r'(\d+(?:\.\d+)?)\s*([BMK])', parameter_size.upper())
    if not param_match:
        return None
    
    param_value = float(param_match.group(1))
    param_unit = param_match.group(2)
    
    # Convert to billions
    if param_unit == 'M':
        param_billions = param_value / 1000
    elif param_unit == 'K':
        param_billions = param_value / 1000000
    else:  # B
        param_billions = param_value
    
    # Determine bits per parameter based on quantization level
    # Common quantization formats and their approximate bits per weight
    quant_bits = {
        'Q2': 2.5,   # 2-bit quantization
        'Q3': 3.5,   # 3-bit quantization
        'Q4': 4.5,   # 4-bit quantization (most common)
        'Q5': 5.5,   # 5-bit quantization
        'Q6': 6.5,   # 6-bit quantization
        'Q8': 8.5,   # 8-bit quantization
        'F16': 16,   # 16-bit float
        'F32': 32,   # 32-bit float
    }
    
    # Find matching quantization level
    bits_per_param = None
    quant_upper = quantization_level.upper()
    for key, bits in quant_bits.items():
        if quant_upper.startswith(key):
            bits_per_param = bits
            break
    
    if bits_per_param is None:
        # Default to Q4 if unknown
        bits_per_param = 4.5
    
    # Calculate memory in GB
    # Formula: (parameters * bits_per_param) / (8 bits/byte * 1024^3 bytes/GB)
    # Add ~20% overhead for model metadata, KV cache, etc.
    memory_gb = (param_billions * 1e9 * bits_per_param) / (8 * 1024**3) * 1.2
    
    # Format the output
    if memory_gb < 1:
        return f"{int(memory_gb * 1024)} MB"
    else:
        return f"{memory_gb:.1f} GB"
