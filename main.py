import argparse
import csv
import hashlib
import logging
import multiprocessing as mp
import os
import time

from colorama import Back, Fore, Style, init
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from database import ProgressDatabase, generate_folder_name
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
    """Check if the current CSV matches the one from the progress database."""
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
    chrome_options.add_argument("--remote-debugging-port=9222")  # Add debugging port
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")  # Prevent detection

    # Set Chrome binary path for macOS
    if os.name == "posix" and os.uname().sysname == "Darwin":
        # macOS specific path to Chrome binary
        if os.path.exists("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"):
            # Use the standard Chrome binary path for macOS
            logger.info("Using standard Chrome binary path for macOS")
            chrome_options.binary_location = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        else:
            logger.warning("Standard Chrome binary path not found, using default location")
    else:
        # For other OS, use the default Chrome binary location
        logger.info("Using default Chrome binary location")
        chrome_options.binary_location = "/usr/bin/google-chrome"  # Default for Linux

    # Set service args to improve stability
    service_args = ["--verbose", "--log-level=INFO"]

    try:
        # Try with explicit service configuration
        service = Service(ChromeDriverManager().install(), service_args=service_args)
        driver = webdriver.Chrome(service=service, options=chrome_options)

        # Test the connection
        driver.get("data:text/html,<html><body>Test</body></html>")
        return driver

    except Exception as e:
        logger.error(f"Failed to create WebDriver: {e}")
        # Fallback: try without service args
        try:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.get("data:text/html,<html><body>Test</body></html>")
            return driver
        except Exception as e2:
            logger.error(f"Fallback WebDriver creation also failed: {e2}")
            raise Exception(f"Could not create WebDriver: {e2}")


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
    """Load progress from previous run - URL-based system doesn't need CSV validation."""
    db = ProgressDatabase(output_folder)

    try:
        # For URL-based system, we don't need to validate against specific CSV
        # Different CSVs can reuse the same URL comparisons
        completed_urls = db.get_completed_urls()
        previous_results = db.get_all_results()

        return completed_urls, previous_results
    except Exception as e:
        logger.warning(f"Could not load progress from database: {e}")
        return set(), []


def save_progress(output_folder, csv_file):
    """Save CSV metadata to database (called once at start)."""
    db = ProgressDatabase(output_folder)
    try:
        csv_info = get_csv_info(csv_file)
        db.save_csv_metadata(csv_info)
    except Exception as e:
        logger.error(f"Could not save CSV metadata: {e}")


def save_result(output_folder, result):
    """Save individual result to database (thread-safe)."""
    db = ProgressDatabase(output_folder)
    try:
        db.save_result(result)
    except Exception as e:
        logger.error(f"Could not save result: {e}")


def process_single_row(args):
    """
    Worker function to process a single CSV row with its own WebDriver.
    Args:
        args (tuple): (row_data, row_number, output_folder)
    Returns:
        dict: Result dictionary with metrics and status
    """
    row_data, row_number, output_folder = args

    # Initialize colorama for this process
    init()

    try:
        start_time = time.time()

        old_url = row_data[0] if len(row_data) > 0 else ""
        new_url = row_data[1] if len(row_data) > 1 else ""

        if not old_url:
            return None

        # Check if this URL combination was already completed AND files exist
        db = ProgressDatabase(output_folder)
        if db.is_url_completed(old_url, new_url):
            # Verify that the actual screenshot files exist
            subfolder_name = generate_folder_name(old_url, new_url)
            subfolder_path = os.path.join(output_folder, subfolder_name)
            old_file_path = os.path.join(subfolder_path, "old.png")
            new_file_path = os.path.join(subfolder_path, "new.png") if new_url else None

            # Check if required files exist
            files_exist = os.path.exists(old_file_path)
            if files_exist and new_url:
                files_exist = files_exist and os.path.exists(new_file_path)

            if files_exist:
                print(
                    f"{Fore.LIGHTBLACK_EX}┅ {Fore.CYAN}Process {mp.current_process().name}: "
                    f"Row {Style.BRIGHT}{Fore.CYAN}{row_number}{Style.RESET_ALL}{Fore.WHITE}: "
                    f"{Fore.GREEN}Skipping ({Style.DIM}Already completed{Style.NORMAL}{Fore.GREEN})"
                    f"{Style.RESET_ALL}"
                )
                return None
            else:
                print(
                    f"{Fore.LIGHTBLACK_EX}┅ {Fore.CYAN}Process {mp.current_process().name}: "
                    f"Row {Style.BRIGHT}{Fore.CYAN}{row_number}{Style.RESET_ALL}{Fore.WHITE}: "
                    f"{Fore.YELLOW}Re-processing ({Style.DIM}Missing screenshot files{Style.NORMAL}{Fore.YELLOW})"
                    f"{Style.RESET_ALL}"
                )

        # Create a separate WebDriver for this worker
        driver = create_webdriver()

        # Get page title from the first URL
        try:
            [page_title, original_title] = get_page_title(driver, old_url)
        except Exception as title_error:
            logger.error(f"Failed to get title for {old_url}, retrying with new driver: {title_error}")
            # Try restarting driver and retry once more
            driver.quit()
            driver = create_webdriver()
            try:
                [page_title, original_title] = get_page_title(driver, old_url)
            except Exception as retry_error:
                logger.error(f"Failed to get title for {old_url} even after driver restart: {retry_error}")
                page_title = ""
                original_title = ""

        # Create subfolder name using URL-based generation
        subfolder_name = generate_folder_name(old_url, new_url)

        # Status update
        print(
            f"{Fore.LIGHTBLACK_EX}╓ {Fore.CYAN}Process {mp.current_process().name}: "
            f"Row {Style.BRIGHT}{Fore.CYAN}{row_number}{Style.RESET_ALL}{Fore.WHITE}: "
            f"{Style.BRIGHT}{Fore.CYAN}{page_title if page_title else subfolder_name}{Style.RESET_ALL}"
        )

        # Create subfolder path
        try:
            subfolder_path = os.path.join(output_folder, subfolder_name)
            os.makedirs(subfolder_path, exist_ok=True)
        except Exception as e:
            print(f"Error creating subfolder {subfolder_name}: {e}")
            return None

        # Initialize result data
        result = {
            "old_url": old_url,
            "new_url": new_url,
            "title": page_title or "No title",
            "original_title": original_title,
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
                f"{Fore.LIGHTBLACK_EX}╟─ {Fore.BLUE}Process {mp.current_process().name}: "
                f"Analyzing page structure for {old_url}...{Style.RESET_ALL}"
            )
            old_structure = analyze_page_structure(driver, old_url)
            if new_url:
                print(
                    f"{Fore.LIGHTBLACK_EX}╟─ {Fore.BLUE}Process {mp.current_process().name}: "
                    f"Analyzing page structure for {new_url}...{Style.RESET_ALL}"
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
                    f"{Fore.LIGHTBLACK_EX}╟─ {Fore.BLUE}Process {mp.current_process().name}: "
                    f"Screenshot saved for {old_url}: {Style.BRIGHT}{Fore.BLUE}{old_file_path}{Style.RESET_ALL}"
                )
                result["old_screenshot_exists"] = True
                screenshot_success = True
                break
            except Exception as e:
                logger.error(f"Screenshot attempt {attempt + 1} failed for {old_url}: {e}")
                if attempt < max_retries - 1:  # Don't restart on last attempt
                    print(
                        f"{Fore.LIGHTBLACK_EX}╟── {Fore.YELLOW}Process {mp.current_process().name}: "
                        f"Screenshot failed, restarting WebDriver and retrying...{Style.RESET_ALL}"
                    )
                    driver.quit()
                    driver = create_webdriver()
                else:
                    print(
                        f"{Fore.LIGHTBLACK_EX}╟── {Fore.RED}Process {mp.current_process().name}: "
                        f"Failed to capture screenshot for {old_url} after {max_retries} attempts{Style.RESET_ALL}"
                    )

        # Take screenshot of new URL if old screenshot succeeded and new URL is provided
        if screenshot_success and new_url:
            new_file_path = os.path.join(subfolder_path, "new.png")

            for attempt in range(max_retries):
                try:
                    capture_full_page_screenshot(driver, new_url, new_file_path)
                    print(
                        f"{Fore.LIGHTBLACK_EX}╟─ {Fore.BLUE}Process {mp.current_process().name}: "
                        f"Screenshot saved for {new_url}: {Style.BRIGHT}{Fore.BLUE}{new_file_path}{Style.RESET_ALL}"
                    )
                    result["new_screenshot_exists"] = True

                    # Create diff image and get metrics with structural analysis
                    diff_file_path = os.path.join(subfolder_path, "diff.png")
                    metrics = create_diff_image(
                        old_file_path, new_file_path, diff_file_path, old_structure, new_structure
                    )
                    print(
                        f"{Fore.LIGHTBLACK_EX}╟─ {Fore.BLUE}Process {mp.current_process().name}: "
                        f"Diff image created: {Style.BRIGHT}{Fore.BLUE}{diff_file_path}{Style.RESET_ALL}"
                    )
                    result["diff_exists"] = True
                    result["metrics"] = metrics
                    break
                except Exception as e:
                    logger.error(f"Screenshot attempt {attempt + 1} failed for {new_url}: {e}")
                    if attempt < max_retries - 1:  # Don't restart on last attempt
                        print(
                            f"{Fore.LIGHTBLACK_EX}╟─ {Fore.YELLOW}Process {mp.current_process().name}: "
                            f"Screenshot failed, restarting WebDriver and retrying...{Style.RESET_ALL}"
                        )
                        driver.quit()
                        driver = create_webdriver()
                    else:
                        print(
                            f"{Fore.LIGHTBLACK_EX}╟─ {Fore.RED}Process {mp.current_process().name}: "
                            f"Failed to capture screenshot for {new_url} after {max_retries} attempts{Style.RESET_ALL}"
                        )

        # Save result to database (thread-safe)
        save_result(output_folder, result)

        # Calculate elapsed time for this row
        elapsed_time = time.time() - start_time
        print(
            f"{Fore.LIGHTBLACK_EX}╙─ {Fore.BLUE}Process {mp.current_process().name}: "
            f"{Fore.CYAN}Complete "
            f"{Fore.BLUE}[{Fore.CYAN}{elapsed_time:.2f}s{Fore.BLUE}]{Style.RESET_ALL}"
        )

        return result

    except Exception as e:
        logger.error(f"Error processing row {row_number}: {e}")
        return None
    finally:
        # Always close the driver
        driver.quit()


def generate_comparison_data(csv_file, output_folder, num_processes=4, live_reports=True):
    """
    Generate comparison data by taking screenshots and analyzing URLs from a CSV file using parallel processing.
    Args:
        csv_file (str): Path to the CSV file containing URLs.
        output_folder (str): Path to the output folder for screenshots.
        num_processes (int): Number of parallel processes to use.
        live_reports (bool): Whether to generate reports during processing.
    Returns:
        list: List of comparison results with metrics.
    """

    # Load progress from previous runs
    completed_urls, previous_results = load_progress(output_folder, csv_file)

    # Save CSV metadata to database (for reporting purposes)
    save_progress(output_folder, csv_file)

    if completed_urls:
        print(f"{Fore.YELLOW}Found {len(completed_urls)} previously completed URL combinations.{Style.RESET_ALL}")

    try:
        # Create output folder if it doesn't exist
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)

        # Here we go
        print(f"\n{Back.LIGHTBLACK_EX}{Fore.CYAN}  Comparing Pages (Parallel)  {Style.RESET_ALL}")
        print(f"{Fore.CYAN}Using {num_processes} parallel processes{Style.RESET_ALL}")

        # Read all rows from CSV and prepare work items
        work_items = []
        with open(csv_file, mode="r") as file:
            reader = csv.reader(file)
            next(reader)  # Skip header
            row_number = 1
            for row in reader:
                if row and len(row) > 0 and row[0]:  # Only process rows with data
                    work_items.append((row, row_number, output_folder))
                row_number += 1

        print(f"{Fore.CYAN}Total rows to process: {len(work_items)}{Style.RESET_ALL}")

        # Process rows in parallel with live reporting
        if work_items:
            if live_reports:
                # Use callback-based processing for live updates
                with mp.Pool(processes=num_processes) as pool:
                    print(f"{Fore.CYAN}Starting parallel processing with live reports...{Style.RESET_ALL}")

                    # Track progress
                    completed_count = 0
                    total_count = len(work_items)

                    # Submit all work items and track completion
                    result_objects = []
                    for work_item in work_items:
                        print(
                            f"{Fore.LIGHTBLACK_EX}┅ {Fore.CYAN}Process {mp.current_process().name}: "
                            f"Starting {work_item[1]}...{Style.RESET_ALL}"
                        )
                        result_obj = pool.apply_async(process_single_row, args=(work_item,))
                        result_objects.append(result_obj)

                    # Monitor progress and generate reports periodically
                    while result_objects:
                        # Check for completed work
                        completed_this_batch = []
                        remaining_objects = []

                        for result_obj in result_objects:
                            if result_obj.ready():
                                completed_this_batch.append(result_obj)
                                completed_count += 1
                            else:
                                remaining_objects.append(result_obj)

                        result_objects = remaining_objects

                        # Update progress if we have completions
                        if completed_this_batch:
                            print(
                                f"{Fore.GREEN}Progress: {completed_count}/{total_count} "
                                f"({completed_count / (total_count * 100):.1f}%) completed{Style.RESET_ALL}"
                            )

                            # Generate reports every 10 completions or at end
                            if completed_count % 10 == 0 or len(result_objects) == 0:
                                print(f"{Fore.CYAN}Generating interim reports...{Style.RESET_ALL}")
                                db = ProgressDatabase(output_folder)
                                current_results = db.get_all_results()
                                generate_reports(output_folder, current_results, quiet=True)
                                print(
                                    f"{Fore.GREEN}Reports updated! "
                                    f"({len(current_results)} total results){Style.RESET_ALL}"
                                )

                        # Wait a bit before checking again (unless we're done)
                        if result_objects:
                            time.sleep(2)

                    print(f"\n{Fore.GREEN}Parallel processing completed!{Style.RESET_ALL}")
                    print(f"{Fore.GREEN}Successfully processed: {completed_count} items{Style.RESET_ALL}")
            else:
                # Traditional processing without live updates
                with mp.Pool(processes=num_processes) as pool:
                    results = pool.map(process_single_row, work_items)
                    valid_results = [r for r in results if r is not None]
                    print(f"\n{Fore.GREEN}Parallel processing completed!{Style.RESET_ALL}")
                    print(f"{Fore.GREEN}Successfully processed: {len(valid_results)} items{Style.RESET_ALL}")

        # Load all results from database (includes both new and previously completed)
        db = ProgressDatabase(output_folder)
        all_results = db.get_all_results()

        return all_results

    except Exception as e:
        print(f"An error occurred: {e}")
        logger.error(f"Error in parallel processing: {e}")
        return []


def generate_reports(output_folder, comparison_results, quiet=False):
    """
    Generate reports from comparison results.
    Args:
        output_folder (str): Path to the output folder for reports.
        comparison_results (list): List of comparison results with metrics.
        quiet (bool): Whether to suppress output messages.
    """
    try:
        if not quiet:
            print(f"{Fore.CYAN}Generating reports...{Style.RESET_ALL}")

        # Generate CSV report with metrics
        csv_report = generate_comparison_report_csv(output_folder, comparison_results)
        if csv_report and not quiet:
            print(f"{Fore.GREEN}CSV report generated: {csv_report}{Style.RESET_ALL}")

        # Generate summary report with metrics
        summary_report = generate_summary_report(output_folder, comparison_results)
        if summary_report and not quiet:
            print(f"{Fore.GREEN}Summary report generated: {summary_report}{Style.RESET_ALL}")

    except Exception as e:
        if not quiet:
            print(f"{Fore.YELLOW}Warning: Could not generate reports: {e}{Style.RESET_ALL}")
        logger.warning(f"Report generation failed: {e}")


def process_urls(csv_file, output_folder, reports_only=False, num_processes=4, live_reports=True):
    """
    Process URLs from a CSV file - generate comparison data and/or reports.
    Args:
        csv_file (str): Path to the CSV file containing URLs.
        output_folder (str): Path to the output folder for screenshots and reports.
        reports_only (bool): If True, skip data generation and only generate reports.
        num_processes (int): Number of parallel processes to use.
        live_reports (bool): Whether to generate reports during processing.
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
        comparison_results = generate_comparison_data(csv_file, output_folder, num_processes, live_reports)

    print(f"{Style.BRIGHT}Compared {len(comparison_results)} results.{Style.RESET_ALL}")

    # Generate final reports (always with full output)
    generate_reports(output_folder, comparison_results, quiet=False)


def confirm_options_and_fetch_urls(
    csv_file, output_folder, skip_confirmation=False, reports_only=False, num_processes=4, live_reports=True
):
    """
    Confirm the options and fetch URLs from a CSV file.
    Args:
        csv_file (str): Path to the CSV file containing URLs.
        output_folder (str): Path to the output folder for screenshots.
        skip_confirmation (bool): Whether to skip confirmation step.
        reports_only (bool): Whether to generate reports only (skip screenshot capture).
        num_processes (int): Number of parallel processes to use.
        live_reports (bool): Whether to generate reports during processing.
    """

    # Initialize colorama
    init()

    tool_mode = " - Reports Only" if reports_only else f" - {num_processes} Processes"
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
    progress_info = ""
    if not reports_only:
        try:
            db = ProgressDatabase(output_folder)
            summary = db.get_progress_summary()
            if summary["completed_urls"] > 0:
                progress_info = f" {Fore.YELLOW}({summary['completed_urls']} URLs completed, "
                f"{summary['completion_percentage']:.1f}% done){Style.RESET_ALL}"
        except Exception:
            pass
    else:
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
    print(f"{Style.BRIGHT}Reports only {Fore.CYAN}:{Style.RESET_ALL} {reports_only}")
    print(f"{Style.BRIGHT}Live reports {Fore.CYAN}:{Style.RESET_ALL} {live_reports}")

    if not reports_only:
        print(f"{Style.BRIGHT}Processes    {Fore.CYAN}:{Style.RESET_ALL} {num_processes}")
        live_status = "enabled" if live_reports else "disabled"
        print(f"{Style.BRIGHT}Live Reports {Fore.CYAN}:{Style.RESET_ALL} {live_status}")

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
    process_urls(csv_file, output_folder, reports_only, num_processes, live_reports)


def main():
    # Set multiprocessing start method for better compatibility
    if mp.get_start_method(allow_none=True) is None:
        mp.set_start_method("spawn")

    # read in the params from the command line (csv path, and output folder)
    parser = argparse.ArgumentParser(description="Compare URLs by capturing screenshots and generating reports.")

    parser.add_argument("csv_file", type=str, help="Path to the CSV file containing URLs")
    parser.add_argument(
        "-o", "--output-folder", type=str, default="output", help="Output folder for screenshots, data, and reports"
    )
    parser.add_argument("-y", "--skip-confirmation", action="store_true", help="Skip confirmation step")
    parser.add_argument("--reports-only", action="store_true", help="Generate reports only (skip screenshot capture)")
    parser.add_argument(
        "-p", "--processes", type=int, default=4, help="Number of parallel processes to use (default: 4)"
    )
    parser.add_argument(
        "--no-live-reports", action="store_true", help="Disable live report generation during processing"
    )

    args = parser.parse_args()
    csv_file = args.csv_file
    output_folder = args.output_folder
    skip_confirmation = args.skip_confirmation
    reports_only = args.reports_only
    num_processes = args.processes
    live_reports = not args.no_live_reports

    # Call the function to confirm options and fetch URLs
    confirm_options_and_fetch_urls(
        csv_file, output_folder, skip_confirmation, reports_only, num_processes, live_reports
    )


if __name__ == "__main__":
    main()
