"""
Variant Detector for KB Results

Detects when multiple KB results represent different variants (platform, model, etc.)
of the same topic, requiring user clarification before providing an answer.
"""

import re
from typing import TypedDict


class VariantInfo(TypedDict):
    """Structure returned by variant detection."""
    has_variants: bool
    topic: str | None
    variant_type: str | None  # "platform", "model", "processor", "hardware"
    options: list[str]


# Variant indicator patterns (case-insensitive)
VARIANT_PATTERNS = {
    # Terminal Models
    "terminal_model": [
        "hisense 560", "hisense-560", "hisense560", "hk560",
        "hisense 570", "hisense-570", "hisense570", "hk570",
        "hisense 568", "hisense-568", "hisense568", "hk568"
    ],
    
    # Terminal Operating Systems
    "terminal_type": ["android", "ios", "windows"],
    
    # Terminal Configuration Numbers
    "terminal_config": [
        "terminal 1", "terminal-1", "terminal1", "term 1", "term-1", "term01", "term 01",
        "terminal 2", "terminal-2", "terminal2", "term 2", "term-2", "term02", "term 02",
        "terminal 3", "terminal-3", "terminal3", "term 3", "term-3", "term03", "term 03",
        "terminal 3+", "terminal-3+", "term 3+"
    ],
    
    # Printer Types
    "printer": ["thermal", "impact", "snbc", "star", "epson"],
    
    # Payment Processors
    "processor": ["transafe", "datacap", "heartland", "tsys", "tsysf"],
    
    # EMV Readers
    "emv_reader": [
        "lane 3000", "lane-3000", "lane3000",
        "bbpos",
        "augusta", "idt", "idtech"
    ],
    
    # Hardware Types
    "hardware_type": [
        "terminal", "printer", 
        "emv reader", "emv-reader", 
        "cash drawer", "cash-drawer",
        "kitchen display system", "kds",
        "handheld"
    ],
    
    # onePOS Products
    "onepos_product": [
        "foh terminal", "foh-terminal", "front of house",
        "boh", "management console", "boh-management-console", "back of house",
        "onemetrix",
        "online ordering", "online-ordering",
        "chowly",
        "lunchbox",
        "oneview",
        "oneconnect",
        "oneschedule"
    ]
}


def _extract_filename(source: str) -> str:
    """Extract filename from full path."""
    if "/" in source:
        source = source.split("/")[-1]
    if "\\" in source:
        source = source.split("\\")[-1]
    # Remove extension
    if "." in source:
        source = source.rsplit(".", 1)[0]
    return source.lower()


def _detect_variants_in_filename(filename: str) -> dict[str, str]:
    """
    Detect variant indicators in a filename.
    
    Returns dict mapping variant_type -> variant_value
    Example: {"platform": "android"}
    """
    variants = {}
    filename_lower = filename.lower()
    
    for variant_type, indicators in VARIANT_PATTERNS.items():
        for indicator in indicators:
            # Use word boundaries to avoid partial matches
            pattern = r'\b' + re.escape(indicator) + r'\b'
            if re.search(pattern, filename_lower):
                variants[variant_type] = indicator
                break  # Only one variant per type per file
    
    return variants


def _extract_base_topic(filename: str, detected_variants: dict[str, str]) -> str:
    """
    Extract base topic by removing variant indicators and common separators.
    
    Example: 
        "bbpos-bluetooth-pairing-android" → "bbpos bluetooth pairing"
    """
    topic = filename.lower()
    
    # Remove all detected variant indicators
    for variant_value in detected_variants.values():
        topic = re.sub(r'\b' + re.escape(variant_value) + r'\b', '', topic)
    
    # Normalize separators to spaces
    topic = re.sub(r'[-_]+', ' ', topic)
    
    # Remove multiple spaces
    topic = re.sub(r'\s+', ' ', topic)
    
    return topic.strip()


def detect_variants(results: list) -> VariantInfo:
    """
    Detect if KB results contain multiple variants of the same topic.
    
    Args:
        results: List of documents from KB search, each with metadata["source"]
        
    Returns:
        VariantInfo dict with detection results
    """
    if not results or len(results) < 2:
        # No variants possible with 0 or 1 result
        return {
            "has_variants": False,
            "topic": None,
            "variant_type": None,
            "options": [],
        }
    
    # Analyze each result
    result_analysis = []
    for doc in results:
        source = doc.metadata.get("source", "")
        if not source:
            continue
            
        filename = _extract_filename(source)
        variants = _detect_variants_in_filename(filename)
        base_topic = _extract_base_topic(filename, variants)
        
        result_analysis.append({
            "filename": filename,
            "variants": variants,
            "base_topic": base_topic,
        })
    
    if not result_analysis:
        return {
            "has_variants": False,
            "topic": None,
            "variant_type": None,
            "options": [],
        }
    
    # Group by base topic
    topic_groups = {}
    for analysis in result_analysis:
        topic = analysis["base_topic"]
        if topic not in topic_groups:
            topic_groups[topic] = []
        topic_groups[topic].append(analysis)
    
    # Check each group for variant diversity
    for topic, group in topic_groups.items():
        if len(group) < 2:
            continue
        
        # Check each variant type
        for variant_type in VARIANT_PATTERNS.keys():
            variant_values = set()
            
            for item in group:
                if variant_type in item["variants"]:
                    variant_values.add(item["variants"][variant_type])
            
            # If we found 2+ different values for the same variant type
            if len(variant_values) >= 2:
                return {
                    "has_variants": True,
                    "topic": topic.title(),  # Capitalize for display
                    "variant_type": variant_type,
                    "options": sorted(list(variant_values)),
                }
    
    # No variants detected
    return {
        "has_variants": False,
        "topic": None,
        "variant_type": None,
        "options": [],
    }
