"""
OCR Engine - Extract text from menu images using PaddleOCR
"""
import cv2
import numpy as np
from PIL import Image
from paddleocr import PaddleOCR
from typing import List, Dict, Tuple
import re
from pathlib import Path

from app.core.config import settings


class OCREngine:
    """
    Handles OCR extraction from menu images with preprocessing
    """
    
    def __init__(self):
        """Initialize PaddleOCR"""
        self.ocr = PaddleOCR(
            use_angle_cls=True,
            lang='en'
        )
    
    def preprocess_image(self, image_path: str) -> np.ndarray:
        """
        Preprocess image for better OCR results
        
        Steps:
        1. Read image
        2. Convert to grayscale
        3. Enhance contrast
        4. Denoise
        
        Args:
            image_path: Path to the image file
            
        Returns:
            Preprocessed image as numpy array
        """
        # Read image
        img = cv2.imread(image_path)
        
        if img is None:
            raise ValueError(f"Could not read image: {image_path}")
        
        # Convert to grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Enhance contrast using CLAHE
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        
        # Denoise
        denoised = cv2.fastNlMeansDenoising(enhanced, None, 10, 7, 21)
        
        # Threshold to get binary image
        _, binary = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        return binary
    
    def extract_text(self, image_path: str, preprocess: bool = True) -> List[Dict]:
        """
        Extract text with bounding boxes from image
        
        Args:
            image_path: Path to menu image
            preprocess: Whether to preprocess image
            
        Returns:
            List of dictionaries with text, bbox, and confidence
        """
        try:
            # Preprocess if needed
            if preprocess:
                img = self.preprocess_image(image_path)
            else:
                img = cv2.imread(image_path)
            
            # Run OCR
            result = self.ocr.ocr(img)
            
            # Parse results
            extracted_data = []
            
            if result and result[0]:
                for line in result[0]:
                    bbox = line[0]
                    text = line[1][0]
                    confidence = line[1][1]
                    
                    extracted_data.append({
                        "text": text,
                        "bbox": bbox,
                        "confidence": confidence
                    })
            
            return extracted_data
            
        except Exception as e:
            raise
    
    def clean_text(self, ocr_results: List[Dict]) -> List[Dict]:
        """
        Clean and normalize OCR output
        
        Args:
            ocr_results: Raw OCR results
            
        Returns:
            Cleaned OCR results
        """
        cleaned_results = []
        
        for item in ocr_results:
            text = item["text"]
            
            # Skip very short or noisy text
            if len(text.strip()) < 2:
                continue
            
            # Normalize currency
            text = self._normalize_currency(text)
            
            # Clean whitespace
            text = " ".join(text.split())
            
            # Update item
            item["text"] = text
            cleaned_results.append(item)
        
        return cleaned_results
    
    def _normalize_currency(self, text: str) -> str:
        """Normalize currency symbols and formats"""
        # Replace various rupee symbols with ₹
        text = re.sub(r'Rs\.?|INR|rs', '₹', text, flags=re.IGNORECASE)
        
        # Standardize price format
        text = re.sub(r'₹\s*(\d+)', r'₹\1', text)
        
        return text
    
    def extract_prices(self, ocr_results: List[Dict]) -> List[Tuple[str, float]]:
        """
        Extract prices from OCR results
        
        Args:
            ocr_results: Cleaned OCR results
            
        Returns:
            List of (text, price) tuples
        """
        prices = []
        
        for item in ocr_results:
            text = item["text"]
            
            # Find price patterns
            price_patterns = [
                r'₹\s*(\d+(?:,\d+)*(?:\.\d{2})?)',  # ₹180 or ₹1,200.50
                r'(\d+(?:,\d+)*(?:\.\d{2})?)\s*₹',  # 180₹
                r'(\d+)\s*/-',  # 180/-
            ]
            
            for pattern in price_patterns:
                match = re.search(pattern, text)
                if match:
                    price_str = match.group(1).replace(',', '')
                    try:
                        price = float(price_str)
                        prices.append((text, price))
                        break
                    except ValueError:
                        continue
        
        return prices
    
    def get_text_blocks(self, ocr_results: List[Dict]) -> str:
        """
        Combine all OCR text into a single string
        
        Args:
            ocr_results: OCR results
            
        Returns:
            Combined text string
        """
        return "\n".join([item["text"] for item in ocr_results])


# Singleton instance
_ocr_engine = None

def get_ocr_engine() -> OCREngine:
    """Get or create OCR engine instance"""
    global _ocr_engine
    if _ocr_engine is None:
        _ocr_engine = OCREngine()
    return _ocr_engine
