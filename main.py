import os
import csv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time


def capture_full_page_screenshot(driver, url, save_path):
    # Function to take a full-page screenshot

    driver.get(url)
    # Allow the page to load
    time.sleep(2)
    # Capture full page screenshot
    original_size = driver.get_window_size()
    required_width = driver.execute_script('return document.body.parentNode.scrollWidth')
    required_height = driver.execute_script('return document.body.parentNode.scrollHeight')
    driver.set_window_size(required_width, required_height)
    driver.save_screenshot(save_path)
    driver.set_window_size(original_size['width'], original_size['height'])


def fetch_urls(csv_file, output_folder):

    # Initialize the WebDriver
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))

    try:
        # Set the window size to a reasonable default
        driver.set_window_size(1920, 1080)
    
        # Create output folder if it doesn't exist
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)

        # Read URLs from a CSV file after skipping header
        with open(csv_file, mode='r') as file:
            reader = csv.reader(file)
            next(reader)  # Skip header
            for row in reader:
                if not row:
                    continue
                # Assuming the URL is in the first column
                url = row[0]
                file_name = f"screenshot_{url.replace('http://', '').replace('https://', '').replace('/', '_')}.png"
                # Ensure the file name is valid
                file_name = ''.join(c for c in file_name if c.isalnum() or c in ('_', '-', '.'))
                # Ensure the file name not too long
                if len(file_name) > 255:
                    file_name = file_name[:255]
                file_path = os.path.join(output_folder, file_name)
                try:
                    capture_full_page_screenshot(driver, url, file_path)
                    print(f"Screenshot saved for {url}")
                except Exception as e:
                    print(f"Error capturing {url}: {e}")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        # Close the driver
        driver.quit()


def main():
    # read in the params from the command line (csv path, and output folder)
    import argparse
    parser = argparse.ArgumentParser(description='Capture screenshots of URLs from a CSV file.')

    parser.add_argument('csv_file', type=str, help='Path to the CSV file containing URLs')
    parser.add_argument('--output_folder', type=str, default='output', help='Output folder for screenshots')

    args = parser.parse_args()
    csv_file = args.csv_file
    output_folder = args.output_folder

    # Verify the CSV:
    # Check if the CSV file exists
    if not os.path.exists(csv_file):
        print(f"CSV file {csv_file} does not exist.")
        return
    # Check if the CSV file is empty
    if os.path.getsize(csv_file) == 0:
        print(f"CSV file {csv_file} is empty.")
        return

    # Print the options back to the user, and ask for confirmation
    path_status = " (exists)" if os.path.exists(output_folder) and os.path.isdir(output_folder) else " (will be created)"
    print(f"CSV file: {csv_file}")
    print(f"Output folder: {output_folder} {path_status}")
    # confirm the options, but get only one character
    print("Please confirm the options above.")
    print("Press 'y' to confirm, or any other key to exit.")

    confirm = input("Is this correct? (y/n): ")
    if confirm.lower() != 'y':
        print("Exiting.")
        return

    # Check if the output folder exists
    if not os.path.exists(output_folder):
        print(f"Output folder {output_folder} does not exist. Creating it.")
        os.makedirs(output_folder)    
    # Check if the output folder is valid
    if not os.path.isdir(output_folder):
        print(f"Output folder {output_folder} is not a directory.")
        return    
    # Check if the output folder is writable
    if not os.access(output_folder, os.W_OK):
        print(f"Output folder {output_folder} is not writable.")
        return

    # Call the function to fetch URLs
    fetch_urls(csv_file, output_folder='output')


if __name__ == "__main__":
    main()
