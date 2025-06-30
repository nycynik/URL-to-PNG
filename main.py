import argparse
import csv
import hashlib
import json
import logging
import os

from colorama import Back, Fore, Style, init
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from reporting import generate_comparison_report_csv, generate_summary_report
from screenshot import analyze_page_structure, capture_full_page_screenshot, create_diff_image, get_page_title

# Configure logging
logger = logging.getLogger(__name__)


def get_csv_info(csv_file):
    """Get identifying information about a CSV file."""
    try:
        # Get basic file info
        csv_info = {
            "filename": os.path.basename(csv_file),
            "size": os.path.getsize(csv_file),
            "row_count": 0,
            "content_hash": "",
        }

        # Count rows and create content hash
        hasher = hashlib.md5()
        with open(csv_file, "r", encoding="utf-8") as f:
            content = f.read()
            hasher.update(content.encode("utf-8"))
            csv_info["content_hash"] = hasher.hexdigest()

            # Count rows (excluding header)
            reader = csv.reader(content.strip().split("\n"))
            next(reader, None)  # Skip header
            csv_info["row_count"] = sum(1 for row in reader if row)

        return csv_info
    except Exception as e:
        logger.warning(f"Could not get CSV info for {csv_file}: {e}")
        return {
            "filename": os.path.basename(csv_file) if csv_file else "unknown",
            "size": 0,
            "row_count": 0,
            "content_hash": "",
        }


def csv_matches_progress(stored_csv_info, current_csv_info):
    """Check if the current CSV matches the one from the progress file."""
    if not stored_csv_info or not current_csv_info:
        return False

    # Compare filename, size, and content hash
    return (
        stored_csv_info.get("filename") == current_csv_info.get("filename")
        and stored_csv_info.get("size") == current_csv_info.get("size")
        and stored_csv_info.get("content_hash") == current_csv_info.get("content_hash")
    )


def is_driver_alive(driver):
    """Check if the WebDriver session is still alive and responsive."""
    try:
        # Try a simple command that should always work if session is alive
        driver.current_url
        driver.title  # Another quick check
        return True
    except Exception as e:
        logger.warning(f"WebDriver session appears to be dead: {e}")
        return False


def create_webdriver():
    """Create a new WebDriver instance with standard options."""
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--headless")  # Run without UI - prevents screensaver issues
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-plugins")
    chrome_options.add_argument("--disable-web-security")
    chrome_options.add_argument("--allow-running-insecure-content")
    chrome_options.add_argument("--disable-features=VizDisplayCompositor")
    chrome_options.add_argument("--window-size=1920,1080")  # Set default window size for headless

    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)


def restart_driver_if_needed(driver, row_number=None):
    """Check if driver is alive and restart if needed."""
    if not is_driver_alive(driver):
        row_info = f" (row {row_number})" if row_number else ""
        print(f"{Fore.YELLOW}WebDriver connection lost{row_info}. Restarting...{Style.RESET_ALL}")
        logger.warning(f"WebDriver session lost{row_info}, creating new session")

        try:
            driver.quit()
        except Exception:
            pass  # Driver might already be dead

        # Create new driver
        new_driver = create_webdriver()
        print(f"{Fore.GREEN}WebDriver restarted successfully{Style.RESET_ALL}")
        logger.info("New WebDriver session created")
        return new_driver

    return driver


def load_progress(output_folder, csv_file):
    """Load progress from previous run and validate it matches the current CSV."""
    progress_file = os.path.join(output_folder, "progress.json")
    if os.path.exists(progress_file):
        try:
            with open(progress_file, "r") as f:
                progress = json.load(f)

                # Check if the progress matches the current CSV file
                stored_csv_info = progress.get("csv_info", {})
                current_csv_info = get_csv_info(csv_file)

                if not csv_matches_progress(stored_csv_info, current_csv_info):
                    print(
                        f"{Fore.YELLOW}Warning: Found existing progress file, "
                        f"but it appears to be for a different CSV.{Style.RESET_ALL}"
                    )
                    progress_csv_name = stored_csv_info.get("filename", "unknown")
                    progress_csv_rows = stored_csv_info.get("row_count", 0)
                    print(
                        f"{Fore.YELLOW}Progress file CSV: {progress_csv_name} ({progress_csv_rows} rows)"
                        f"{Style.RESET_ALL}"
                    )
                    print(
                        f"{Fore.YELLOW}Current CSV: {current_csv_info.get('filename', 'unknown')} "
                        f"({current_csv_info.get('row_count', 0)} rows){Style.RESET_ALL}"
                    )
                    print(f"{Fore.YELLOW}Starting fresh with new CSV file.{Style.RESET_ALL}")
                    return set(), []

                completed_rows = set(progress.get("completed_rows", []))
                previous_results = progress.get("comparison_results", [])
                return completed_rows, previous_results
        except Exception as e:
            logger.warning(f"Could not load progress file: {e}")
    return set(), []


def save_progress(output_folder, completed_rows, comparison_results, csv_file):
    """Save progress and results to resume later."""
    progress_file = os.path.join(output_folder, "progress.json")
    try:
        csv_info = get_csv_info(csv_file)
        with open(progress_file, "w") as f:
            json.dump(
                {
                    "completed_rows": list(completed_rows),
                    "comparison_results": comparison_results,
                    "csv_info": csv_info,
                },
                f,
                indent=2,
            )
    except Exception as e:
        logger.error(f"Could not save progress: {e}")


def generate_comparison_data(csv_file, output_folder):
    """
    Generate comparison data by taking screenshots and analyzing URLs from a CSV file.
    Args:
        csv_file (str): Path to the CSV file containing URLs.
        output_folder (str): Path to the output folder for screenshots.
    Returns:
        list: List of comparison results with metrics.
    """

    # Initialize the WebDriver
    driver = create_webdriver()

    # Load progress from previous runs
    completed_rows, previous_results = load_progress(output_folder, csv_file)

    # Start with previous results and add new ones
    comparison_results = previous_results.copy()

    if completed_rows:
        print(
            f"{Fore.YELLOW}Resuming from previous run. Skipping {len(completed_rows)} completed rows.{Style.RESET_ALL}"
        )

    try:

        # Create output folder if it doesn't exist
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)

        # Here we go
        print(f"\n{Back.LIGHTBLACK_EX}{Fore.CYAN}  Comparing Pages  {Style.RESET_ALL}")

        # Read URLs from a CSV file after skipping header
        with open(csv_file, mode="r") as file:
            reader = csv.reader(file)
            next(reader)  # Skip header
            row_number = 1
            for row in reader:
                start_time = os.times().elapsed

                if not row:
                    continue

                # Expect two columns: old_url, new_url
                old_url = row[0] if len(row) > 0 else ""
                new_url = row[1] if len(row) > 1 else ""

                if not old_url:
                    continue

                # Check if this row was already completed
                if row_number in completed_rows:
                    print(
                        f"{Fore.LIGHTBLACK_EX}┅ {Fore.CYAN}"
                        f"Processing row {Style.BRIGHT}{Fore.CYAN}{row_number}{Style.RESET_ALL}{Fore.WHITE}: "
                        f"{Fore.GREEN}Skipping ({Style.DIM}Already completed{Style.NORMAL}{Fore.GREEN})"
                        f"{Style.RESET_ALL}"
                    )
                    row_number += 1
                    continue

                # Check WebDriver health before processing this row
                # Perform more frequent health checks for longer runs
                if row_number % 10 == 0 or not is_driver_alive(driver):
                    driver = restart_driver_if_needed(driver, row_number)

                # Get page title from the first URL
                try:
                    [page_title, original_title] = get_page_title(driver, old_url)
                except Exception as title_error:
                    logger.error(f"Failed to get title for {old_url}, retrying with new driver: {title_error}")
                    # Try restarting driver and retry once more
                    driver = restart_driver_if_needed(driver, row_number)
                    try:
                        [page_title, original_title] = get_page_title(driver, old_url)
                    except Exception as retry_error:
                        logger.error(f"Failed to get title for {old_url} even after driver restart: {retry_error}")
                        page_title = ""
                        original_title = ""

                # Create subfolder name: number + title (if available)
                if page_title:
                    subfolder_name = f"{row_number}-{page_title}"
                else:
                    subfolder_name = str(row_number)

                # Status update
                print(
                    f"{Fore.LIGHTBLACK_EX}╓ {Fore.CYAN}Processing row {Style.BRIGHT}"
                    f"{Fore.CYAN}{row_number}{Style.RESET_ALL}{Fore.WHITE}: "
                    f"{Style.BRIGHT}{Fore.CYAN}"
                    f"{page_title if page_title else subfolder_name}{Style.RESET_ALL}"
                )

                # Create subfolder path
                try:
                    subfolder_path = os.path.join(output_folder, subfolder_name)
                    os.makedirs(subfolder_path, exist_ok=True)
                except Exception as e:
                    print(f"Error creating subfolder {subfolder_name}: {e}")
                    continue

                # Initialize result data
                result = {
                    "row_number": row_number,
                    "title": page_title or "No title",
                    "original_title": original_title,
                    "old_url": old_url,
                    "new_url": new_url,
                    "subfolder_name": subfolder_name,
                    "old_screenshot_exists": False,
                    "new_screenshot_exists": False,
                    "diff_exists": False,
                    "metrics": None,
                }

                # Collect structural data for both pages
                old_structure = {}
                new_structure = {}

                try:
                    print(
                        f"{Fore.LIGHTBLACK_EX}╟─ {Fore.BLUE}Analyzing page structure for {old_url}..."
                        f"{Style.RESET_ALL}"
                    )
                    old_structure = analyze_page_structure(driver, old_url)
                    if new_url:
                        print(
                            f"{Fore.LIGHTBLACK_EX}╟─ {Fore.BLUE}Analyzing page structure for {new_url}..."
                            f"{Style.RESET_ALL}"
                        )
                        new_structure = analyze_page_structure(driver, new_url)
                except Exception as e:
                    logger.warning(f"Could not analyze page structures: {e}")

                # Take screenshot of old URL with retry logic
                old_file_path = os.path.join(subfolder_path, "old.png")
                screenshot_success = False
                max_retries = 2

                for attempt in range(max_retries):
                    try:
                        capture_full_page_screenshot(driver, old_url, old_file_path)
                        print(
                            f"{Fore.LIGHTBLACK_EX}╟─ {Fore.BLUE}Screenshot saved for {old_url}: "
                            f"{Style.BRIGHT}{Fore.BLUE}{old_file_path}{Style.RESET_ALL}"
                        )
                        result["old_screenshot_exists"] = True
                        screenshot_success = True
                        break
                    except Exception as e:
                        logger.error(f"Screenshot attempt {attempt + 1} failed for {old_url}: {e}")
                        if attempt < max_retries - 1:  # Don't restart on last attempt
                            print(
                                f"{Fore.LIGHTBLACK_EX}╟── {Fore.YELLOW}Screenshot failed, "
                                f"restarting WebDriver and retrying...{Style.RESET_ALL}"
                            )
                            driver = restart_driver_if_needed(driver, row_number)
                        else:
                            print(
                                f"{Fore.LIGHTBLACK_EX}╟── {Fore.RED} Failed to capture screenshot for {old_url} "
                                f"after {max_retries} attempts{Style.RESET_ALL}"
                            )

                # Take screenshot of new URL if old screenshot succeeded and new URL is provided
                if screenshot_success and new_url:
                    new_file_path = os.path.join(subfolder_path, "new.png")

                    for attempt in range(max_retries):
                        try:
                            capture_full_page_screenshot(driver, new_url, new_file_path)
                            print(
                                f"{Fore.LIGHTBLACK_EX}╟─ {Fore.BLUE}Screenshot saved for {new_url}: "
                                f"{Style.BRIGHT}{Fore.BLUE}{new_file_path}{Style.RESET_ALL}"
                            )
                            result["new_screenshot_exists"] = True

                            # Create diff image and get metrics with structural analysis
                            diff_file_path = os.path.join(subfolder_path, "diff.png")
                            metrics = create_diff_image(
                                old_file_path, new_file_path, diff_file_path, old_structure, new_structure
                            )
                            print(
                                f"{Fore.LIGHTBLACK_EX}╟─ {Fore.BLUE}Diff image created: "
                                f"{Style.BRIGHT}{Fore.BLUE}{diff_file_path}{Style.RESET_ALL}"
                            )
                            result["diff_exists"] = True
                            result["metrics"] = metrics
                            break
                        except Exception as e:
                            logger.error(f"Screenshot attempt {attempt + 1} failed for {new_url}: {e}")
                            if attempt < max_retries - 1:  # Don't restart on last attempt
                                print(
                                    f"{Fore.LIGHTBLACK_EX}╟─ {Fore.YELLOW}Screenshot failed, "
                                    f"restarting WebDriver and retrying...{Style.RESET_ALL}"
                                )
                                driver = restart_driver_if_needed(driver, row_number)
                            else:
                                print(
                                    f"{Fore.LIGHTBLACK_EX}╟─ {Fore.RED}Failed to capture screenshot for "
                                    f"{new_url} after {max_retries} attempts{Style.RESET_ALL}"
                                )

                # Add result to our collection
                comparison_results.append(result)

                # Mark row as completed and save progress
                completed_rows.add(row_number)
                save_progress(output_folder, completed_rows, comparison_results, csv_file)
                # calculate elapsed time for this row
                elapsed_time = os.times().elapsed - start_time
                print(
                    f"{Fore.LIGHTBLACK_EX}╙─ {Fore.BLUE}Complete [{Fore.CYAN}{elapsed_time:.2f}s{Fore.BLUE}]"
                    f"{Style.RESET_ALL}"
                )

                row_number += 1

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        # Close the driver
        driver.quit()

    return comparison_results


def generate_reports(output_folder, comparison_results):
    """
    Generate reports from comparison results.
    Args:
        output_folder (str): Path to the output folder for reports.
        comparison_results (list): List of comparison results with metrics.
    """
    try:
        print(f"{Fore.CYAN}Generating reports...{Style.RESET_ALL}")

        # Generate CSV report with metrics
        csv_report = generate_comparison_report_csv(output_folder, comparison_results)
        if csv_report:
            print(f"{Fore.GREEN}CSV report generated: {csv_report}{Style.RESET_ALL}")

        # Generate summary report with metrics
        summary_report = generate_summary_report(output_folder, comparison_results)
        if summary_report:
            print(f"{Fore.GREEN}Summary report generated: {summary_report}{Style.RESET_ALL}")

    except Exception as e:
        print(f"{Fore.YELLOW}Warning: Could not generate reports: {e}{Style.RESET_ALL}")


def process_urls(csv_file, output_folder, reports_only=False):
    """
    Process URLs from a CSV file - generate comparison data and/or reports.
    Args:
        csv_file (str): Path to the CSV file containing URLs.
        output_folder (str): Path to the output folder for screenshots and reports.
        reports_only (bool): If True, skip data generation and only generate reports.
    """
    if reports_only:
        # Reports only mode - load existing data and generate reports
        _, comparison_results = load_progress(output_folder, csv_file)

        if not comparison_results:
            print(
                f"{Back.WHITE} {Fore.RED}ERROR{Fore.CYAN}: {Style.RESET_ALL} "
                f"No comparison data found in {output_folder}."
            )
            print(
                f"{Fore.YELLOW}Run the tool without --reports-only first "
                f"to generate screenshots and data.{Style.RESET_ALL}"
            )
            return
    else:
        # Full mode - generate data and then reports
        comparison_results = generate_comparison_data(csv_file, output_folder)

    print(f"{Style.BRIGHT}Compared {len(comparison_results)} results.{Style.RESET_ALL}")
    generate_reports(output_folder, comparison_results)


def confirm_options_and_fetch_urls(csv_file, output_folder, skip_confirmation=False, reports_only=False):
    """
    Confirm the options and fetch URLs from a CSV file.
    Args:
        csv_file (str): Path to the CSV file containing URLs.
        output_folder (str): Path to the output folder for screenshots.
        skip_confirmation (bool): Whether to skip confirmation step.
        reports_only (bool): Whether to generate reports only (skip screenshot capture).
    """

    # Initialize colorama
    init()

    tool_mode = " - Reports Only" if reports_only else ""
    print(f"{Style.BRIGHT}{Back.LIGHTBLACK_EX}{Fore.CYAN}  URL Comparison Tool{tool_mode}  {Style.RESET_ALL}")

    # Verify the CSV:
    # Check if the CSV file exists
    if not os.path.exists(csv_file):
        print(f"{Back.WHITE} {Fore.RED}ERROR{Fore.CYAN}: {Style.RESET_ALL} CSV file {csv_file} does not exist.")
        raise FileNotFoundError(f"CSV file {csv_file} does not exist.")

    # Check if the CSV file is empty
    if os.path.getsize(csv_file) == 0:
        print(f"{Back.WHITE} {Fore.YELLOW}WARNING{Fore.CYAN}: {Style.RESET_ALL} CSV file {csv_file} is empty.")
        return

    # Check for existing progress
    progress_file = os.path.join(output_folder, "progress.json")
    progress_info = ""
    if os.path.exists(progress_file) and not reports_only:
        try:
            completed_rows, _ = load_progress(output_folder, csv_file)
            if completed_rows:
                max_completed = max(completed_rows)
                progress_info = f" {Fore.YELLOW}(resuming from row {max_completed + 1}, "
                f"{len(completed_rows)} completed){Style.RESET_ALL}"
        except Exception:
            pass
    elif reports_only:
        try:
            _, comparison_results = load_progress(output_folder, csv_file)
            if comparison_results:
                progress_info = f" {Fore.GREEN}({len(comparison_results)} results found){Style.RESET_ALL}"
        except Exception:
            pass

    # Print the options back to the user, and ask for confirmation
    path_status = (
        " (folder exists)"
        if os.path.exists(output_folder) and os.path.isdir(output_folder)
        else f" {Fore.GREEN}(will be created)"
    )
    print(f"{Style.BRIGHT}CSV file     {Fore.CYAN}:{Style.RESET_ALL} {csv_file}")
    print(
        f"{Style.BRIGHT}Output folder{Fore.CYAN}:{Style.RESET_ALL} {output_folder}"
        f"{path_status}{progress_info}{Style.RESET_ALL}"
    )

    # confirm the options, but get only one character
    print(f"\nPlease confirm the options above.{Style.RESET_ALL}")
    print(f"Press '{Style.BRIGHT}y{Style.RESET_ALL}' to confirm, or any other key to exit.{Style.RESET_ALL}")

    if not skip_confirmation:
        confirm = input(
            f"\n{Style.BRIGHT}{Fore.YELLOW}Everything look good so far? "
            f"{Style.DIM}{Fore.GREEN}[y/{Style.BRIGHT}{Fore.GREEN}N{Style.DIM}{Fore.GREEN}]"
            f"{Style.RESET_ALL}: "
        )
        if confirm.lower() != "y":
            print(f"{Fore.RED}Exiting.{Style.RESET_ALL}")
            return

    # Check if the output folder exists
    if not os.path.exists(output_folder):
        print(f"{Fore.YELLOW}Output folder {output_folder} does not exist. {Fore.GREEN}Creating it.{Style.RESET_ALL}")
        os.makedirs(output_folder)
    # Check if the output folder is valid
    if not os.path.isdir(output_folder):
        print(f"{Fore.RED}ERROR: Output folder {output_folder} is not a directory.{Style.RESET_ALL}")
        return
    # Check if the output folder is writable
    if not os.access(output_folder, os.W_OK):
        print(f"{Fore.RED}ERROR: Output folder {output_folder} is not writable.{Style.RESET_ALL}")
        return

    # Process URLs - generate data and/or reports
    process_urls(csv_file, output_folder, reports_only)


def main():
    # read in the params from the command line (csv path, and output folder)
    parser = argparse.ArgumentParser(description="Compare URLs by capturing screenshots and generating reports.")

    parser.add_argument("csv_file", type=str, help="Path to the CSV file containing URLs")
    parser.add_argument(
        "--output_folder", type=str, default="output", help="Output folder for screenshots, data, and reports"
    )
    parser.add_argument("--skip-confirmation", action="store_true", help="Skip confirmation step")
    parser.add_argument("--reports-only", action="store_true", help="Generate reports only (skip screenshot capture)")

    args = parser.parse_args()
    csv_file = args.csv_file
    output_folder = args.output_folder
    skip_confirmation = args.skip_confirmation
    reports_only = args.reports_only

    # Call the function to confirm options and fetch URLs
    confirm_options_and_fetch_urls(csv_file, output_folder, skip_confirmation, reports_only)


if __name__ == "__main__":
    main()
