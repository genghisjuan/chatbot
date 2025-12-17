"""
Diagnostic script to test highlight detection in isolation.
Run this to test if the detection works outside of the main app.
"""
import sys
import io
from PIL import Image
import numpy as np

def test_highlight_detection(image_path):
    """Test the highlight detection function."""
    print(f"[DIAGNOSTIC] Loading image from: {image_path}")
    
    try:
        # Read image
        with open(image_path, 'rb') as f:
            image_bytes = f.read()
        
        print(f"[DIAGNOSTIC] Image size: {len(image_bytes)} bytes")
        
        # Open image
        img = Image.open(io.BytesIO(image_bytes))
        print(f"[DIAGNOSTIC] Image dimensions: {img.size}")
        print(f"[DIAGNOSTIC] Image mode: {img.mode}")
        
        img_array = np.array(img.convert('RGB'))
        h, w = img_array.shape[:2]
        print(f"[DIAGNOSTIC] Array shape: {img_array.shape}")
        
        # Vectorized HSV conversion for saturation
        r = img_array[:, :, 0].astype(float)
        g = img_array[:, :, 1].astype(float)
        b = img_array[:, :, 2].astype(float)
        
        max_val = np.maximum(np.maximum(r, g), b)
        min_val = np.minimum(np.minimum(r, g), b)
        
        # Saturation calculation
        sat = np.where(max_val == 0, 0, (max_val - min_val) / max_val * 255)
        
        print(f"[DIAGNOSTIC] Saturation range: {sat.min():.1f} - {sat.max():.1f}")
        print(f"[DIAGNOSTIC] Pixels with sat>100: {np.sum(sat > 100)}")
        
        # Find pixels with high saturation (>100) OR specific blue/red hues
        high_sat_mask = sat > 100
        
        # Detect blue/purple hues
        blue_mask = (b > r + 20) & (b > g + 20) & (b > 100)
        print(f"[DIAGNOSTIC] Blue pixels: {np.sum(blue_mask)}")
        
        # Detect red hues
        red_mask = (r > b + 20) & (r > g + 20) & (r > 100)
        print(f"[DIAGNOSTIC] Red pixels: {np.sum(red_mask)}")
        
        # Combine all detection methods
        highlight_mask = high_sat_mask | blue_mask | red_mask
        print(f"[DIAGNOSTIC] Total highlight pixels: {np.sum(highlight_mask)}")
        
        # Find bounding box
        rows = np.any(highlight_mask, axis=1)
        cols = np.any(highlight_mask, axis=0)
        
        if not rows.any() or not cols.any():
            print("[DIAGNOSTIC] ❌ NO HIGHLIGHT DETECTED")
            return False
        
        y1, y2 = np.where(rows)[0][[0, -1]]
        x1, x2 = np.where(cols)[0][[0, -1]]
        
        print(f"[DIAGNOSTIC] ✓ Bounding box: ({x1}, {y1}) to ({x2}, {y2})")
        
        # Calculate area
        highlight_area = (x2 - x1) * (y2 - y1)
        total_area = w * h
        area_ratio = highlight_area / total_area
        
        print(f"[DIAGNOSTIC] Area ratio: {area_ratio:.2%}")
        
        if area_ratio < 0.05 or area_ratio > 0.8:
            print(f"[DIAGNOSTIC] ❌ Area ratio out of bounds (5-80%)")
            return False
        
        print(f"[DIAGNOSTIC] ✓ HIGHLIGHT DETECTED SUCCESSFULLY")
        return True
        
    except Exception as e:
        print(f"[DIAGNOSTIC] ❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    # Test with the uploaded image
    test_image = r"C:\Users\John\.gemini\antigravity\brain\f38e65dc-8a3d-418c-9d4f-f955e05e7ba2\uploaded_image_1765919147805.png"
    
    print("=" * 60)
    print("HIGHLIGHT DETECTION DIAGNOSTIC TEST")
    print("=" * 60)
    
    result = test_highlight_detection(test_image)
    
    print("=" * 60)
    if result:
        print("RESULT: ✓ Detection should work")
    else:
        print("RESULT: ❌ Detection failed - debug needed")
    print("=" * 60)
