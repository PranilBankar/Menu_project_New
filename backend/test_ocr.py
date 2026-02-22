import sys
import os
from pathlib import Path
import cv2
import numpy as np

# Add backend directory to sys.path so we can import app modules
backend_dir = Path(__file__).parent
sys.path.append(str(backend_dir))

from app.services.ocr.ocr_engine import get_ocr_engine

def create_dummy_menu():
    # Create a white image
    img = np.ones((500, 600, 3), dtype=np.uint8) * 255
    
    # Text to add
    texts = [
        ("Starters", (50, 50), 1.5),
        ("Tomato Soup ........ Rs. 150", (50, 100), 1.0),
        ("French Fries ....... 250 INR", (50, 150), 1.0),
        ("Main Course", (50, 250), 1.5),
        ("Grilled Chicken .... 350/-", (50, 300), 1.0),
        ("Vegetable Pasta .... Rs. 300", (50, 350), 1.0),
    ]
    
    for text, pos, scale in texts:
        cv2.putText(img, text, pos, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), 2)
        
    image_path = str(backend_dir / "dummy_menu.jpg")
    cv2.imwrite(image_path, img)
    return image_path

def main():
    print("Creating dummy menu image...")
    image_path = create_dummy_menu()
    print(f"Saved dummy image at: {image_path}")
    
    print("\nInitializing OCR Engine...")
    engine = get_ocr_engine()
    
    print("\nExtracting text...")
    try:
        results = engine.extract_text(image_path)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return
        
    print("\n--- Raw Results ---")
    for res in results:
        print(f"Text: '{res['text']}' (Confidence: {res['confidence']:.2f})")
        
    print("\n--- Cleaned Text ---")
    cleaned = engine.clean_text(results)
    for res in cleaned:
        print(f"Cleaned Text: '{res['text']}'")

    print("\n--- Extracted Prices ---")
    prices = engine.extract_prices(cleaned)
    for text, price in prices:
        print(f"Full Text: '{text}' -> Extracted Price: {price}")
        
if __name__ == "__main__":
    main()
