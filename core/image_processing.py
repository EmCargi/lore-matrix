import cv2
import numpy as np


def deskew_image(image):
    """
    Detects the skew angle of text contours in the image and rotates it to straighten the text lines.
    """
    # Convert to grayscale if color
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    
    # Threshold to invert the image (text becomes white, background black)
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    
    # Find all coordinates where pixel value is > 0 (foreground text pixels)
    coords = np.column_stack(np.where(thresh > 0))
    if len(coords) == 0:
        return image
        
    # Compute the minimum area rectangle enclosing the text coordinates
    # minAreaRect returns: (center(x, y), size(width, height), angle_of_rotation)
    rect = cv2.minAreaRect(coords)
    angle = rect[-1]
    
    # minAreaRect angle rules in OpenCV:
    # Historically returned angle in [-90, 0).
    # Correct the angle to get a true deviation from vertical/horizontal.
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
        
    # Ignore tiny skew angles or extreme false positives (larger than 25 degrees)
    if abs(angle) < 0.5 or abs(angle) > 25.0:
        return image
        
    # Perform rotation around the center
    (h, w) = image.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(image, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    
    print(f"  [DESKEW] Corrected skew angle: {angle:.2f} degrees.")
    return rotated

def preprocess_image_for_ocr(img, binarize=False, denoise=True, contrast=True, deskew=False):
    """
    Applies image enhancement stages to improve OCR text readability.
    - binarize: Applies adaptive thresholding (Gaussian).
    - denoise: Uses Bilateral Filtering to blur out screentones while keeping text edges sharp.
    - contrast: Uses Contrast Limited Adaptive Histogram Equalization (CLAHE).
    - deskew: Straightens text lines if the page has a physical rotation skew.
    """
    processed = img.copy()
    
    # 1. Automatic Deskewing
    if deskew:
        processed = deskew_image(processed)
        
    # 2. Convert to Grayscale
    if len(processed.shape) == 3:
        gray = cv2.cvtColor(processed, cv2.COLOR_BGR2GRAY)
    else:
        gray = processed
        
    # 3. Bilateral Filter Denoising
    if denoise:
        # 9 is diameter of pixel neighborhood, 75 is filter sigma values
        gray = cv2.bilateralFilter(gray, 9, 75, 75)
        
    # 4. CLAHE Contrast Enhancement
    if contrast:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)
        
    # 5. Adaptive Thresholding (Binarization)
    if binarize:
        gray = cv2.adaptiveThreshold(
            gray, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            11, 2
        )
        
    return gray
