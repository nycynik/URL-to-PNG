import os
import time
import logging
import re
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from PIL import Image, ImageEnhance
import numpy as np
from skimage.metrics import structural_similarity as ssim
from selenium.webdriver.common.by import By

# Configure logging
logger = logging.getLogger(__name__)


def analyze_page_structure(driver, url):
    """
    Analyze the semantic structure of a webpage by counting key HTML elements.
    Args:
        driver (webdriver): Selenium WebDriver instance.
        url (str): URL of the page to analyze.
    Returns:
        dict: Count of semantic HTML elements, or empty dict if failed.
    """
    try:
        # Check if driver session is still valid
        try:
            driver.current_url  # This will raise an exception if session is invalid
        except Exception as session_error:
            logger.error(f"Driver session invalid when analyzing structure for {url}: {session_error}")
            return {}

        driver.get(url)
        time.sleep(2)  # Allow page to load
        
        # Define semantic HTML elements to count
        semantic_elements = [
            'h1', 'h2', 'h3', 'h4', 'h5', 'h6',  # Headings
            'section', 'article', 'aside', 'nav', 'header', 'footer', 'main',  # Semantic sections
            'p',  # Paragraphs
            'ul', 'ol', 'li',  # Lists
            'table', 'thead', 'tbody', 'tr', 'th', 'td',  # Tables
            'form', 'input', 'textarea', 'select', 'button',  # Forms
            'a',  # Links
            'img',  # Images
            'video', 'audio',  # Media
            'blockquote', 'cite',  # Quotes
            'code', 'pre',  # Code
            'figure', 'figcaption'  # Figures
        ]
        
        structure = {}
        total_elements = 0
        
        for element_type in semantic_elements:
            try:
                elements = driver.find_elements(By.TAG_NAME, element_type)
                count = len(elements)
                structure[element_type] = count
                total_elements += count
            except Exception as e:
                logger.warning(f"Could not count {element_type} elements: {e}")
                structure[element_type] = 0
        
        # Add total count for reference
        structure['_total_semantic_elements'] = total_elements
        
        logger.info(f"Analyzed structure for {url}: {total_elements} semantic elements")
        return structure
        
    except Exception as e:
        logger.warning(f"Could not analyze page structure for {url}: {e}")
        return {}


def calculate_structural_similarity(old_structure, new_structure):
    """
    Calculate structural similarity between two page structures.
    Args:
        old_structure (dict): Structure analysis of old page.
        new_structure (dict): Structure analysis of new page.
    Returns:
        dict: Structural similarity metrics.
    """
    if not old_structure or not new_structure:
        return {
            'structural_similarity': 0.0,
            'structural_differences': {},
            'total_structural_changes': 0
        }
    
    # Get all element types that appear in either structure
    all_elements = set(old_structure.keys()) | set(new_structure.keys())
    all_elements.discard('_total_semantic_elements')  # Remove meta field
    
    if not all_elements:
        return {
            'structural_similarity': 100.0,
            'structural_differences': {},
            'total_structural_changes': 0
        }
    
    differences = {}
    total_changes = 0
    matching_elements = 0
    
    for element_type in all_elements:
        old_count = old_structure.get(element_type, 0)
        new_count = new_structure.get(element_type, 0)
        
        if old_count != new_count:
            difference = new_count - old_count
            differences[element_type] = {
                'old_count': old_count,
                'new_count': new_count,
                'difference': difference
            }
            total_changes += abs(difference)
        else:
            matching_elements += 1
    
    # Calculate similarity as percentage of elements that match exactly
    total_element_types = len(all_elements)
    similarity_percentage = (matching_elements / total_element_types * 100) if total_element_types > 0 else 100.0
    
    return {
        'structural_similarity': round(similarity_percentage, 1),
        'structural_differences': differences,
        'total_structural_changes': total_changes,
        'matching_element_types': matching_elements,
        'total_element_types': total_element_types
    }


def trim_bottom_whitespace(image_path, tolerance=5):
    """
    Trim uniform colored area from the bottom of an image.
    Args:
        image_path (str): Path to the image file.
        tolerance (int): Color difference tolerance for considering pixels the same.
    Returns:
        bool: True if image was trimmed, False otherwise.
    """
    try:
        # Open the image
        img = Image.open(image_path)
        img_array = np.array(img)
        height, width = img_array.shape[:2]
        
        # Start from the bottom and work upward
        trim_line = height
        
        # Get the bottom row as reference
        if len(img_array.shape) == 3:  # Color image
            bottom_row = img_array[-1, :, :]
            reference_color = np.mean(bottom_row, axis=0)
        else:  # Grayscale
            bottom_row = img_array[-1, :]
            reference_color = np.mean(bottom_row)
        
        # Find where content differs from bottom color
        for y in range(height - 1, -1, -1):
            if len(img_array.shape) == 3:  # Color image
                row = img_array[y, :, :]
                row_color = np.mean(row, axis=0)
                color_diff = np.max(np.abs(row_color - reference_color))
            else:  # Grayscale
                row = img_array[y, :]
                row_color = np.mean(row)
                color_diff = abs(row_color - reference_color)
            
            if color_diff > tolerance:
                trim_line = y + 1
                break
        
        # Only trim if we're removing at least 50 pixels and more than 5% of image
        min_trim = 50
        min_percentage = 0.05
        pixels_to_remove = height - trim_line
        
        if pixels_to_remove >= min_trim and pixels_to_remove >= (height * min_percentage):
            # Crop the image
            if len(img_array.shape) == 3:
                cropped_array = img_array[:trim_line, :, :]
            else:
                cropped_array = img_array[:trim_line, :]
            
            # Save the cropped image
            cropped_img = Image.fromarray(cropped_array)
            cropped_img.save(image_path, 'PNG', optimize=True)
            
            logger.info(f"Trimmed {pixels_to_remove} pixels from bottom of {image_path} ({pixels_to_remove/height*100:.1f}%)")
            return True
        
    except Exception as e:
        logger.warning(f"Could not trim whitespace from {image_path}: {e}")
    
    return False


def get_page_title(driver, url):
    """
    Get the page title from a URL.
    Args:
        driver (webdriver): Selenium WebDriver instance.
        url (str): URL of the page to get title from.
    Returns:
        Tuple[str, str]: Sanitized page title, or empty string if failed, and original page title, or empty string if failed.
    """
    try:
        # Check if driver session is still valid
        try:
            driver.current_url  # This will raise an exception if session is invalid
        except Exception as session_error:
            logger.error(f"Driver session invalid when getting title for {url}: {session_error}")
            return ["", ""]

        driver.get(url)
        time.sleep(2)  # Allow page to load
        original_title = driver.title
        # Sanitize title for use in folder name
        if original_title:
            # Remove invalid characters and replace problematic punctuation
            title = re.sub(r'[<>:"/\\|?*\']', '', original_title)
            title = re.sub(r'[,;]', '-', title)  # Replace commas and semicolons with dashes
            title = re.sub(r'\s+', '_', title)  # Replace spaces with underscores (do this last)
            # Limit length
            title = title[:50]
        return [title, original_title]
    except Exception as e:
        logger.warning(f"Could not get title for {url}: {e}")
        return ["", ""]  # Return empty strings if failed


def capture_full_page_screenshot(driver, url, save_path):
    """
    Capture a full-page screenshot of the given URL.
    Args:
        driver (webdriver): Selenium WebDriver instance.
        url (str): URL of the page to capture.
        save_path (str): Path to save the screenshot.
    """
    # Check if driver session is still valid
    try:
        driver.current_url  # This will raise an exception if session is invalid
    except Exception as session_error:
        logger.error(f"Driver session invalid when capturing {url}: {session_error}")
        raise Exception(f"WebDriver session is no longer valid: {session_error}")

    # resize the window to original size again
    driver.set_window_size(1920, 1080)  # Set to a standard size before capturing

    driver.get(url)
    # Allow the page to load
    time.sleep(2)

    # Get the total page dimensions
    total_width = driver.execute_script("return Math.max(document.body.scrollWidth, document.body.offsetWidth, document.documentElement.clientWidth, document.documentElement.scrollWidth, document.documentElement.offsetWidth);")
    total_height = driver.execute_script("return Math.max(document.body.scrollHeight, document.body.offsetHeight, document.documentElement.clientHeight, document.documentElement.scrollHeight, document.documentElement.offsetHeight);")

    logger.info(f"Page dimensions: {total_width}x{total_height}")

    # Use Chrome's built-in full page screenshot capability
    # This works better than resizing the window
    original_size = driver.get_window_size()

    try:
        # Enable full page screenshots in Chrome
        driver.execute_cdp_cmd('Emulation.setDeviceMetricsOverride', {
            'width': total_width,
            'height': total_height,
            'deviceScaleFactor': 1,
            'mobile': False,
            'screenWidth': total_width,
            'screenHeight': total_height,
        })

        # let the window reflow/react to new dimensions
        time.sleep(2)

        # Take the screenshot
        result = driver.execute_cdp_cmd('Page.captureScreenshot', {
            'format': 'png',
            'captureBeyondViewport': True
        })

        # Save the screenshot
        import base64
        with open(save_path, 'wb') as f:
            f.write(base64.b64decode(result['data']))

        logger.info(f"Full page screenshot saved: {save_path}")

    except Exception as e:
        logger.warning(f"CDP method failed, falling back to window resize: {e}")
        # Fallback to original method
        driver.set_window_size(total_width, total_height)
        time.sleep(2)  # Give it time to resize
        driver.save_screenshot(save_path)

    finally:
        # Reset window size
        driver.set_window_size(original_size['width'], original_size['height'])
    
    # Trim bottom whitespace from the screenshot
    trim_bottom_whitespace(save_path)


def fetch_url(url, output_file):
    """
    Fetch a single URL and save a screenshot to the specified output file.
    Args:
        url (str): URL of the page to capture.
        output_file (str): Full path where the screenshot should be saved.
    """
    # Initialize the WebDriver with headless options
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

    try:

        # Ensure the output directory exists
        os.makedirs(os.path.dirname(output_file), exist_ok=True)

        # Capture the screenshot
        capture_full_page_screenshot(driver, url, output_file)
        logger.info(f"Screenshot saved for {url} to {output_file}")

    except Exception as e:
        logger.error(f"Error capturing {url}: {e}")
        raise
    finally:
        # Close the driver
        driver.quit()


def create_diff_image(old_image_path, new_image_path, diff_image_path, old_structure=None, new_structure=None):
    """
    Create a visual diff image highlighting differences between two screenshots and calculate combined metrics.
    Args:
        old_image_path (str): Path to the old/original image.
        new_image_path (str): Path to the new/updated image.
        diff_image_path (str): Path where the diff image should be saved.
        old_structure (dict): Optional structural analysis of old page.
        new_structure (dict): Optional structural analysis of new page.
    Returns:
        dict: Combined visual and structural similarity metrics.
    """
    try:
        # Load both images
        old_img = Image.open(old_image_path).convert('RGB')
        new_img = Image.open(new_image_path).convert('RGB')

        # Get dimensions and ensure they match (resize if needed)
        old_width, old_height = old_img.size
        new_width, new_height = new_img.size

        # Use the larger dimensions to avoid losing content
        max_width = max(old_width, new_width)
        max_height = max(old_height, new_height)

        # Resize images to match if needed
        if old_img.size != (max_width, max_height):
            old_img = old_img.resize((max_width, max_height), Image.Resampling.LANCZOS)
        if new_img.size != (max_width, max_height):
            new_img = new_img.resize((max_width, max_height), Image.Resampling.LANCZOS)

        logger.info(f"Creating diff for images of size {max_width}x{max_height}")

        # Convert to numpy arrays for easier pixel manipulation
        old_array = np.array(old_img)
        new_array = np.array(new_img)

        # Create the diff array
        diff_array = np.zeros_like(old_array)

        # Calculate pixel differences
        # Using a threshold to account for minor compression differences
        threshold = 30  # Adjust this value to control sensitivity

        # Find pixels that are different between old and new
        pixel_diff = np.abs(old_array.astype(int) - new_array.astype(int))
        changed_pixels = np.sum(pixel_diff, axis=2) > threshold

        # Create base image (grayscale version of new image for context)
        gray_new = ImageEnhance.Brightness(new_img.convert('L').convert('RGB')).enhance(0.3)
        diff_array = np.array(gray_new)

        # Highlight changes:
        # Red for content that was removed (present in old but not new)
        # Green for content that was added (present in new but not old)

        # Find areas where old image has content but new doesn't (removals)
        old_brightness = np.mean(old_array, axis=2)
        new_brightness = np.mean(new_array, axis=2)

        # Removals: areas that were bright in old but dark in new
        removed_mask = (old_brightness > new_brightness + threshold) & changed_pixels
        diff_array[removed_mask] = [255, 100, 100]  # Red highlight

        # Additions: areas that were dark in old but bright in new
        added_mask = (new_brightness > old_brightness + threshold) & changed_pixels
        diff_array[added_mask] = [100, 255, 100]  # Green highlight

        # General changes (neither clearly addition nor removal)
        other_changes = changed_pixels & ~removed_mask & ~added_mask
        diff_array[other_changes] = [255, 255, 100]  # Yellow highlight

        # Convert back to PIL Image and save
        diff_img = Image.fromarray(diff_array.astype(np.uint8))
        diff_img.save(diff_image_path, 'PNG', optimize=True)

        # Calculate similarity metrics
        total_pixels = max_width * max_height
        changed_pixel_count = np.sum(changed_pixels)
        change_percentage = (changed_pixel_count / total_pixels) * 100

        # Calculate SSIM score
        # Convert to grayscale for SSIM calculation
        old_gray = np.array(old_img.convert('L'))
        new_gray = np.array(new_img.convert('L'))

        # Calculate visual similarity (SSIM)
        ssim_score = ssim(old_gray, new_gray)
        visual_similarity = ((ssim_score + 1) / 2) * 100  # Convert to 0-100 scale

        # Calculate structural similarity if structure data is provided
        structural_metrics = calculate_structural_similarity(old_structure, new_structure)
        structural_similarity = structural_metrics.get('structural_similarity', 100.0)

        # Combine visual and structural similarities for overall score
        # Weight visual similarity more heavily (70%) since it's the primary comparison
        combined_similarity = (visual_similarity * 0.7) + (structural_similarity * 0.3)

        # Determine change magnitude based on combined similarity
        if combined_similarity >= 98:
            change_magnitude = "None"
        elif combined_similarity >= 85:
            change_magnitude = "Minimal"
        elif combined_similarity >= 70:
            change_magnitude = "Moderate"
        else:
            change_magnitude = "Significant"

        # Create comprehensive metrics dictionary
        metrics = {
            'visual_similarity': round(visual_similarity, 1),
            'structural_similarity': round(structural_similarity, 1),
            'similarity_score': round(combined_similarity, 1),  # Combined score for backward compatibility
            'change_percentage': round(change_percentage, 1),
            'change_magnitude': change_magnitude,
            'ssim_raw': round(ssim_score, 3),
            'structural_differences': structural_metrics.get('structural_differences', {}),
            'total_structural_changes': structural_metrics.get('total_structural_changes', 0)
        }

        logger.info(f"Diff image created: {diff_image_path}")
        logger.info(f"Visual: {metrics['visual_similarity']}%, Structural: {metrics['structural_similarity']}%, Combined: {metrics['similarity_score']}% ({metrics['change_magnitude']})")

        return metrics

    except Exception as e:
        logger.error(f"Error creating diff image: {e}")
        raise
