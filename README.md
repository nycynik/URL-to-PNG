# Screenshot Comparison Tool
Takes a CSV with pairs of URLs (old and new) and creates screenshot comparisons between them.

# Setup

Create a python virtual environment in the root of the project folder.

    python -m venv ./.venv

Then activate it

    source .venv/bin/activate

Install the dependencies

    uv sync

Verify python is working with the dependencies

    python -c "import selenium; print(selenium.__version__)"

Run the program

    python main.py example.csv

You can replace the CSV with your own list of URL pairs. The CSV should have two columns: the first for old URLs and the second for new URLs to compare. It skips the first row assuming there is a header. Screenshot comparisons are placed in the output folder, which is created if it does not already exist.

## Output Structure

For each URL pair in your CSV, the tool creates a subfolder named with the row number and page title (e.g., `1-Google` or `2-Getting_Started_-_Company_Name`). Each subfolder contains:

- `old.png` - Screenshot of the original URL
- `new.png` - Screenshot of the updated URL  
- `diff.png` - Visual comparison highlighting differences with color coding:
  - **Red highlights** - Content removed (present in old but not new)
  - **Green highlights** - Content added (present in new but not old)
  - **Yellow highlights** - Other changes (moved or modified content)
  - **Dimmed background** - Unchanged areas for context

## Reports

After processing all comparisons, the tool automatically generates two reports in the output folder:

### comparison_report.csv
A structured CSV file containing:
- **title** - Page title extracted from the first URL
- **old_url_screenshot** - Path to the original screenshot
- **new_url_screenshot** - Path to the updated screenshot
- **diff_image** - Path to the visual diff image
- **folder_name** - Reference to the comparison subfolder

This CSV can be opened in Excel or used for further analysis and processing.

### summary_report.html
An interactive HTML summary page featuring:
- Visual dashboard with comparison statistics
- Success rate and total counts in attractive cards
- Interactive table with clickable links to view screenshots
- Green checkmarks (✓) for successful files, red X's (✗) for failures
- Responsive design that works on desktop and mobile
- Hover effects and professional styling

Open this file in any web browser to get a comprehensive overview of your comparison results with direct access to all generated images.

## Progress Tracking & Resume Capability

The tool automatically saves progress as it processes each URL pair, allowing you to safely resume from where you left off if the process is interrupted:

- **Automatic Progress Saving**: Each completed comparison is immediately saved to `progress.json` in your output folder
- **Crash Recovery**: If the tool stops unexpectedly (network issues, system crashes, etc.), simply re-run the same command to resume
- **No Data Loss**: Previously completed screenshots and comparisons are preserved - the tool will skip already processed rows
- **Accurate Statistics**: When resuming, all metrics and reports include data from both previous and current runs for complete accuracy
- **CSV Validation**: The tool validates that resume data matches the current CSV file - if you run with a different CSV, it will start fresh

When you re-run the tool, you'll see a yellow message indicating how many rows are being skipped from previous runs. If you switch to a different CSV file, the tool will detect this and start fresh rather than using incompatible progress data. The final reports will contain all comparison data, ensuring no work is lost.

## CSV Format

Your CSV file should look like this:

```csv
old_url,new_url
https://example.com/old-page,https://example.com/new-page
https://mysite.com/before,https://mysite.com/after
```

# Development

Thanks for thinking about how to make it better!

## We use Pre-commit hooks

Please install pre-commit hoooks (if you are using the virtual env for this repo. they are installed already.)

    uv add pre-commit

You can run the tests before pushing to the repo.

    pre-commit run --all-files

When you commit new code, the tests will automatically run.
