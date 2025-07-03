import csv
import logging
import os

# Configure logging
logger = logging.getLogger(__name__)

# disable E501 for the whole file
# pylint: disable=C0301


def generate_comparison_report_csv(output_folder, comparison_results=None, report_filename="comparison_report.csv"):
    """
    Generate a CSV report of all URL comparisons performed.
    Args:
        output_folder (str): Path to the output folder containing comparison subfolders.
        comparison_results (list): Optional list of comparison results with metrics.
        report_filename (str): Name of the CSV report file to create.
    Returns:
        str: Path to the generated report file.
    """
    try:
        report_path = os.path.join(output_folder, report_filename)

        # Use provided comparison results if available, otherwise scan folders
        comparison_data = []

        if comparison_results:
            # Use the metrics data from the comparison process
            for result in comparison_results:
                old_image_rel = (
                    os.path.join(result["subfolder_name"], "old.png") if result["old_screenshot_exists"] else ""
                )
                new_image_rel = (
                    os.path.join(result["subfolder_name"], "new.png") if result["new_screenshot_exists"] else ""
                )
                diff_image_rel = os.path.join(result["subfolder_name"], "diff.png") if result["diff_exists"] else ""

                data = {
                    "url_hash": result.get("url_hash", ""),
                    "title": result["title"],
                    "old_url": result["old_url"],
                    "new_url": result.get("new_url", ""),
                    "old_image": old_image_rel,
                    "new_image": new_image_rel,
                    "diff_image": diff_image_rel,
                    "folder_name": result["subfolder_name"],
                }

                # Add metrics if available
                if result["metrics"]:
                    data.update(
                        {
                            "visual_similarity": result["metrics"].get("visual_similarity", ""),
                            "structural_similarity": result["metrics"].get("structural_similarity", ""),
                            "similarity_score": result["metrics"]["similarity_score"],
                            "change_percentage": result["metrics"]["change_percentage"],
                            "change_magnitude": result["metrics"]["change_magnitude"],
                        }
                    )
                else:
                    data.update(
                        {
                            "visual_similarity": "",
                            "structural_similarity": "",
                            "similarity_score": "",
                            "change_percentage": "",
                            "change_magnitude": "",
                        }
                    )

                comparison_data.append(data)
        else:
            # Fallback to scanning folders (legacy behavior)
            if not os.path.exists(output_folder):
                logger.warning(f"Output folder {output_folder} does not exist")
                return None

            for item in os.listdir(output_folder):
                subfolder_path = os.path.join(output_folder, item)

                # Skip files, only process directories
                if not os.path.isdir(subfolder_path):
                    continue

                # Skip the report file itself if it exists in the folder
                if item == report_filename:
                    continue

                # Extract domain and hash from folder name (new URL-based format)
                if "_" in item and len(item.split("_")[-1]) == 16:  # URL-based format: domain_hash
                    parts = item.split("_")
                    hash_part = parts[-1]
                    domain_part = "_".join(parts[:-1])
                    title = domain_part.replace("_", " ")
                    url_hash = hash_part
                elif "-" in item:  # Legacy format: number-title
                    row_number, title = item.split("-", 1)
                    title = title.replace("_", " ")
                    url_hash = ""
                else:
                    title = "No title available"
                    url_hash = item if len(item) == 16 else ""

                # Check for required files
                old_image = os.path.join(subfolder_path, "old.png")
                new_image = os.path.join(subfolder_path, "new.png")
                diff_image = os.path.join(subfolder_path, "diff.png")

                # Only include entries where at least old.png exists
                if os.path.exists(old_image):
                    # Convert to relative paths for the CSV (makes links more portable)
                    old_image_rel = os.path.join(item, "old.png")
                    new_image_rel = os.path.join(item, "new.png") if os.path.exists(new_image) else ""
                    diff_image_rel = os.path.join(item, "diff.png") if os.path.exists(diff_image) else ""

                    data_entry = {
                        "url_hash": url_hash,
                        "title": title,
                        "old_url": "",  # Not available from folder scan
                        "new_url": "",  # Not available from folder scan
                        "old_image": old_image_rel,
                        "new_image": new_image_rel,
                        "diff_image": diff_image_rel,
                        "folder_name": item,
                        "visual_similarity": "",
                        "structural_similarity": "",
                        "similarity_score": "",
                        "change_percentage": "",
                        "change_magnitude": "",
                    }

                    # Add row_number for backward compatibility if available
                    if "row_number" in locals():
                        data_entry["row_number"] = int(row_number)

                    comparison_data.append(data_entry)

        # Sort by row number if available, otherwise by folder name
        comparison_data.sort(key=lambda x: x.get("row_number", 999999) if x.get("row_number") else x["folder_name"])

        # Write the CSV report
        with open(report_path, "w", newline="", encoding="utf-8") as csvfile:
            fieldnames = [
                "url_hash",
                "title",
                "old_url",
                "new_url",
                "old_url_screenshot",
                "new_url_screenshot",
                "diff_image",
                "visual_similarity",
                "structural_similarity",
                "similarity_score",
                "change_percentage",
                "change_magnitude",
                "folder_name",
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            # Write header
            writer.writeheader()

            # Write data rows
            for data in comparison_data:
                writer.writerow(
                    {
                        "url_hash": data["url_hash"],
                        "title": data["title"],
                        "old_url": data["old_url"],
                        "new_url": data["new_url"],
                        "old_url_screenshot": data["old_image"],
                        "new_url_screenshot": data["new_image"],
                        "diff_image": data["diff_image"],
                        "visual_similarity": data["visual_similarity"],
                        "structural_similarity": data["structural_similarity"],
                        "similarity_score": data["similarity_score"],
                        "change_percentage": data["change_percentage"],
                        "change_magnitude": data["change_magnitude"],
                        "folder_name": data["folder_name"],
                    }
                )

        logger.info(f"Comparison report generated: {report_path}")
        logger.info(f"Report includes {len(comparison_data)} comparisons")

        return report_path

    except Exception as e:
        logger.error(f"Error generating comparison report: {e}")
        raise


def generate_summary_report(output_folder, comparison_results=None, report_filename="summary_report.html"):
    """
    Generate an HTML summary report of the comparison results.
    Args:
        output_folder (str): Path to the output folder containing comparison subfolders.
        comparison_results (list): Optional list of comparison results with metrics.
        report_filename (str): Name of the HTML report file to create.
    Returns:
        str: Path to the generated report file.
    """
    try:
        report_path = os.path.join(output_folder, report_filename)

        if not os.path.exists(output_folder):
            logger.warning(f"Output folder {output_folder} does not exist")
            return None

        # Count comparisons and analyze
        total_comparisons = 0
        successful_comparisons = 0
        failed_comparisons = 0
        comparisons_with_diffs = 0
        similarity_scores = []
        moderate_or_higher_changes = 0

        comparison_details = []

        if comparison_results:
            # Use provided comparison results
            for result in comparison_results:
                total_comparisons += 1

                if result["old_screenshot_exists"] and result["new_screenshot_exists"]:
                    successful_comparisons += 1
                    if result["diff_exists"]:
                        comparisons_with_diffs += 1
                else:
                    failed_comparisons += 1

                # Collect metrics for analysis
                if result["metrics"]:
                    similarity_scores.append(result["metrics"]["similarity_score"])
                    # Count moderate or higher changes (exclude "None" and "Minimal")
                    if result["metrics"]["change_magnitude"] in ["Moderate", "Significant"]:
                        moderate_or_higher_changes += 1

                comparison_details.append(
                    {
                        "row": result.get("url_hash", "N/A"),
                        "title": result["title"],
                        "original_title": result.get("original_title", result["title"]),
                        "old": result["old_screenshot_exists"],
                        "new": result["new_screenshot_exists"],
                        "diff": result["diff_exists"],
                        "metrics": result["metrics"],
                        "subfolder_name": result["subfolder_name"],
                        "old_url": result.get("old_url", ""),
                        "new_url": result.get("new_url", ""),
                    }
                )
        else:
            # Fallback to scanning folders
            for item in os.listdir(output_folder):
                subfolder_path = os.path.join(output_folder, item)

                # Skip files, only process directories
                if not os.path.isdir(subfolder_path):
                    continue

                # Skip report files
                if item.endswith(".csv") or item.endswith(".html"):
                    continue

                total_comparisons += 1

                # Check what files exist
                old_exists = os.path.exists(os.path.join(subfolder_path, "old.png"))
                new_exists = os.path.exists(os.path.join(subfolder_path, "new.png"))
                diff_exists = os.path.exists(os.path.join(subfolder_path, "diff.png"))

                if old_exists and new_exists:
                    successful_comparisons += 1
                    if diff_exists:
                        comparisons_with_diffs += 1
                else:
                    failed_comparisons += 1

                # Extract title for details (support both old and new formats)
                if "_" in item and len(item.split("_")[-1]) == 16:  # URL-based format
                    parts = item.split("_")
                    hash_part = parts[-1]
                    domain_part = "_".join(parts[:-1])
                    title = domain_part.replace("_", " ")
                    row_identifier = hash_part
                elif "-" in item:  # Legacy format
                    row_number, title = item.split("-", 1)
                    title = title.replace("_", " ")
                    row_identifier = row_number
                else:
                    row_identifier = item
                    title = "No title"

                comparison_details.append(
                    {
                        "row": row_identifier,
                        "title": title,
                        "original_title": title,
                        "old": old_exists,
                        "new": new_exists,
                        "diff": diff_exists,
                        "metrics": None,
                        "subfolder_name": item,  # The actual folder name
                        "old_url": "",
                        "new_url": "",
                    }
                )

        # Sort by row identifier (handle both numeric and hash formats)
        def sort_key(x):
            row_val = x["row"]
            try:
                return (0, int(row_val))  # Numeric rows first
            except (ValueError, TypeError):
                return (1, str(row_val))  # Hash-based rows second, alphabetically

        comparison_details.sort(key=sort_key)

        # Calculate metrics
        average_similarity = sum(similarity_scores) / len(similarity_scores) if similarity_scores else 0
        comparisons_with_metrics = len(similarity_scores)

        # Calculate average visual and structural similarities
        visual_similarities = []
        structural_similarities = []

        # Count magnitude categories for bar chart
        magnitude_counts = {"None": 0, "Minimal": 0, "Moderate": 0, "Significant": 0}
        if comparison_results:
            for result in comparison_results:
                if result["metrics"]:
                    magnitude = result["metrics"]["change_magnitude"]
                    if magnitude in magnitude_counts:
                        magnitude_counts[magnitude] += 1

                    # Collect visual and structural similarities
                    if result["metrics"].get("visual_similarity") is not None:
                        visual_similarities.append(result["metrics"]["visual_similarity"])
                    if result["metrics"].get("structural_similarity") is not None:
                        structural_similarities.append(result["metrics"]["structural_similarity"])

        average_visual_similarity = sum(visual_similarities) / len(visual_similarities) if visual_similarities else 0
        average_structural_similarity = (
            sum(structural_similarities) / len(structural_similarities) if structural_similarities else 0
        )

        # Count similarity score ranges for second chart
        similarity_ranges = {"90-100%": 0, "80-89%": 0, "70-79%": 0, "Below 70%": 0}
        if comparison_results:
            for result in comparison_results:
                if result["metrics"] and result["metrics"].get("similarity_score") is not None:
                    score = result["metrics"]["similarity_score"]
                    if score >= 90:
                        similarity_ranges["90-100%"] += 1
                    elif score >= 80:
                        similarity_ranges["80-89%"] += 1
                    elif score >= 70:
                        similarity_ranges["70-79%"] += 1
                    else:
                        similarity_ranges["Below 70%"] += 1

        # Write HTML summary report
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(
                """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Screenshot Comparison Summary Report</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .container {
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        h1 {
            color: #333;
            border-bottom: 3px solid #007acc;
            padding-bottom: 10px;
        }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin: 30px 0;
        }
        .stat-card {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 6px;
            text-align: center;
            border-left: 4px solid #007acc;
        }
        .stat-number {
            font-size: 2em;
            font-weight: bold;
            color: #007acc;
        }
        .stat-label {
            color: #666;
            margin-top: 5px;
        }
        .success-rate {
            border-left-color: #28a745;
        }
        .success-rate .stat-number {
            color: #28a745;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 30px;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        th {
            background-color: #f8f9fa;
            font-weight: 600;
            color: #333;
        }
        tr:hover {
            background-color: #f8f9fa;
        }
        .status-icon {
            font-size: 1.2em;
            font-weight: bold;
        }
        .status-success {
            color: #28a745;
        }
        .status-fail {
            color: #dc3545;
        }
        .file-link {
            color: #007acc;
            text-decoration: none;
            padding: 2px 6px;
            border-radius: 3px;
            background: #e3f2fd;
        }
        .file-link:hover {
            background: #bbdefb;
        }
        .title-cell {
            max-width: 300px;
            padding: 8px 12px;
        }
        .title-main {
            font-weight: 500;
            color: #333;
            margin-bottom: 2px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .title-id {
            font-size: 0.85em;
            color: #888;
            font-family: 'Courier New', monospace;
            margin-top: 2px;
        }
        .metrics-cell {
            text-align: center;
            font-weight: 600;
        }
        .magnitude-none {
            color: #155724;
            background: #c3e6cb;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 0.85em;
            font-weight: 600;
        }
        .magnitude-minimal {
            color: #28a745;
            background: #d4edda;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 0.85em;
        }
        .magnitude-moderate {
            color: #ffc107;
            background: #fff3cd;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 0.85em;
        }
        .magnitude-significant {
            color: #dc3545;
            background: #f8d7da;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 0.85em;
        }
        .filter-container {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 6px;
            margin: 20px 0;
            border: 1px solid #dee2e6;
        }
        .filter-group {
            display: inline-block;
            margin-right: 20px;
            margin-bottom: 10px;
        }
        .filter-group label {
            font-weight: 600;
            margin-right: 8px;
            color: #495057;
        }
        .filter-group select, .filter-group input {
            padding: 5px 10px;
            border: 1px solid #ced4da;
            border-radius: 4px;
            background: white;
        }
        .clear-filters {
            background: #6c757d;
            color: white;
            border: none;
            padding: 6px 12px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.9em;
        }
        .clear-filters:hover {
            background: #5a6268;
        }
        .hidden {
            display: none !important;
        }
        .charts-container {
            display: flex;
            gap: 20px;
            margin: 30px 0;
        }
        .chart-container {
            background: #f8f9fa;
            padding: 25px;
            border-radius: 8px;
            border: 1px solid #dee2e6;
            flex: 1;
        }
        .chart-title {
            font-size: 1.2em;
            font-weight: 600;
            color: #333;
            margin-bottom: 20px;
            text-align: center;
        }
        @media (max-width: 768px) {
            .charts-container {
                flex-direction: column;
            }
        }
        .bar-chart {
            display: flex;
            align-items: flex-end;
            justify-content: space-around;
            height: 200px;
            padding: 0 20px;
            background: white;
            border-radius: 6px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .bar-group {
            display: flex;
            flex-direction: column;
            align-items: center;
            flex: 1;
            max-width: 120px;
        }
        .bar {
            width: 60px;
            margin-bottom: 10px;
            border-radius: 4px 4px 0 0;
            position: relative;
            transition: all 0.3s ease;
        }
        .bar:hover {
            opacity: 0.8;
            transform: translateY(-2px);
        }
        .bar-none {
            background: linear-gradient(135deg, #e9ecef, #ced4da);
        }
        .bar-minimal {
            background: linear-gradient(135deg, #e9ecef, #ced4da);
        }
        .bar-moderate {
            background: linear-gradient(135deg, #e9ecef, #ced4da);
        }
        .bar-significant {
            background: linear-gradient(135deg, #e9ecef, #ced4da);
        }
        .bar-range-excellent {
            background: linear-gradient(135deg, #e9ecef, #ced4da);
        }
        .bar-range-good {
            background: linear-gradient(135deg, #e9ecef, #ced4da);
        }
        .bar-range-fair {
            background: linear-gradient(135deg, #e9ecef, #ced4da);
        }
        .bar-range-poor {
            background: linear-gradient(135deg, #e9ecef, #ced4da);
        }
        .bar-value {
            position: absolute;
            top: -25px;
            left: 50%;
            transform: translateX(-50%);
            font-weight: 600;
            font-size: 0.9em;
            color: #333;
        }
        .bar-label {
            font-weight: 600;
            color: #495057;
            text-align: center;
            font-size: 0.9em;
        }
        .bar-sublabel {
            font-size: 0.8em;
            color: #6c757d;
            margin-top: 2px;
        }
        .modal {
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0,0,0,0.8);
        }
        .modal-content {
            position: relative;
            background-color: #fefefe;
            margin: 2% auto;
            padding: 20px;
            border-radius: 8px;
            width: 95%;
            max-width: 1400px;
            height: 90%;
            overflow: hidden;
        }
        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 2px solid #dee2e6;
        }
        .modal-title {
            font-size: 1.4em;
            font-weight: 600;
            color: #333;
        }
        .close {
            color: #aaa;
            font-size: 28px;
            font-weight: bold;
            cursor: pointer;
            padding: 5px 10px;
            border-radius: 4px;
            transition: all 0.2s ease;
        }
        .close:hover {
            color: #000;
            background-color: #f8f9fa;
        }
        .comparison-container {
            display: flex;
            gap: 15px;
            height: calc(100% - 80px);
        }
        .screenshot-panel {
            flex: 1;
            display: flex;
            flex-direction: column;
            border: 1px solid #dee2e6;
            border-radius: 6px;
            overflow: hidden;
            background: #f8f9fa;
        }
        .panel-header {
            background: #343a40;
            color: white;
            padding: 12px 15px;
            font-weight: 600;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .panel-controls {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .view-selector {
            background: white;
            color: #333;
            border: 1px solid #ced4da;
            border-radius: 4px;
            padding: 4px 8px;
            font-size: 0.9em;
        }
        .screenshot-wrapper {
            flex: 1;
            overflow: auto;
            padding: 15px;
            background: white;
        }
        .screenshot-image {
            max-width: 100%;
            height: auto;
            border: 1px solid #dee2e6;
            border-radius: 4px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        .view-link {
            color: #007acc;
            text-decoration: none;
            padding: 4px 8px;
            border-radius: 3px;
            background: rgba(0,122,204,0.1);
            font-weight: 500;
            cursor: pointer;
        }
        .view-link:hover {
            background: rgba(0,122,204,0.2);
            text-decoration: none;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Screenshot Comparison Summary Report</h1>

        <div class="stats">
            <div class="stat-card">
                <div class="stat-number">"""
                + str(total_comparisons)
                + """</div>
                <div class="stat-label">Total Comparisons</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">"""
                + f"{average_visual_similarity:.1f}%"
                + """</div>
                <div class="stat-label">Visual Similarity</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">"""
                + f"{average_structural_similarity:.1f}%"
                + """</div>
                <div class="stat-label">Structural Similarity</div>
            </div>
            <div class="stat-card success-rate">
                <div class="stat-number">"""
                + f"{average_similarity:.1f}%"
                + """</div>
                <div class="stat-label">Average Similarity</div>
            </div>
        </div>
"""
            )

            # Add charts if we have data
            if comparisons_with_metrics > 0:
                f.write(
                    """
        <div class="charts-container">
"""
                )

                # First chart: Change Magnitude Distribution
                total_magnitude_results = sum(magnitude_counts.values())
                f.write(
                    """            <div class="chart-container">
                <div class="chart-title">Change Magnitude Distribution</div>
                <div class="bar-chart">
"""
                )

                for magnitude, count in magnitude_counts.items():
                    percentage = (count / total_magnitude_results * 100) if total_magnitude_results > 0 else 0
                    bar_height = max(20, percentage * 1.5)  # Minimum height of 20px, scale factor of 1.5

                    f.write(
                        f"""                    <div class="bar-group">
                        <div class="bar bar-{magnitude.lower()}" style="height: {bar_height}px;">
                            <div class="bar-value">{percentage:.1f}%</div>
                        </div>
                        <div class="bar-label">{magnitude}</div>
                        <div class="bar-sublabel">({count} pages)</div>
                    </div>
"""
                    )

                f.write(
                    """                </div>
            </div>
"""
                )

                # Second chart: Similarity Score Ranges
                total_similarity_results = sum(similarity_ranges.values())
                f.write(
                    """            <div class="chart-container">
                <div class="chart-title">Similarity Score Distribution</div>
                <div class="bar-chart">
"""
                )

                # Define colors for similarity ranges
                range_colors = {
                    "90-100%": "range-excellent",
                    "80-89%": "range-good",
                    "70-79%": "range-fair",
                    "Below 70%": "range-poor",
                }

                for range_label, count in similarity_ranges.items():
                    percentage = (count / total_similarity_results * 100) if total_similarity_results > 0 else 0
                    bar_height = max(20, percentage * 1.5)  # Minimum height of 20px, scale factor of 1.5
                    color_class = range_colors.get(range_label, "range-default")

                    f.write(
                        f"""                    <div class="bar-group">
                        <div class="bar bar-{color_class}" style="height: {bar_height}px;">
                            <div class="bar-value">{percentage:.1f}%</div>
                        </div>
                        <div class="bar-label">{range_label}</div>
                        <div class="bar-sublabel">({count} pages)</div>
                    </div>
"""
                    )

                f.write(
                    """                </div>
            </div>
        </div>
"""
                )

            f.write(
                """
        <div class="filter-container">
            <h3 style="margin-top: 0; margin-bottom: 15px; color: #333;">Filters</h3>
            <div class="filter-group">
                <label for="magnitudeFilter">Magnitude:</label>
                <select id="magnitudeFilter">
                    <option value="">All</option>
                    <option value="None">None</option>
                    <option value="Minimal">Minimal</option>
                    <option value="Moderate">Moderate</option>
                    <option value="Significant">Significant</option>
                </select>
            </div>
            <div class="filter-group">
                <label for="titleFilter">Title:</label>
                <input type="text" id="titleFilter" placeholder="Search titles...">
            </div>
            <div class="filter-group">
                <label for="statusFilter">Status:</label>
                <select id="statusFilter">
                    <option value="">All</option>
                    <option value="complete">Complete (has diff)</option>
                    <option value="incomplete">Incomplete</option>
                </select>
            </div>
            <button class="clear-filters" onclick="clearAllFilters()">Clear Filters</button>
        </div>

        <table>
            <thead>
                <tr>
                    <th>Title</th>
                    <th>Visual</th>
                    <th>Structural</th>
                    <th>Combined</th>
                    <th>Change %</th>
                    <th>Magnitude</th>
                    <th>Old | New | Diff SS</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
"""
            )

            for detail in comparison_details:
                # Use the actual subfolder name directly
                folder_path = detail["subfolder_name"]

                # Create file links if files exist
                old_link = (
                    f'<a href="{folder_path}/old.png" class="file-link" target="_blank">View</a>'
                    if detail["old"]
                    else '<span class="status-icon status-fail">✗</span>'
                )
                new_link = (
                    f'<a href="{folder_path}/new.png" class="file-link" target="_blank">View</a>'
                    if detail["new"]
                    else '<span class="status-icon status-fail">✗</span>'
                )
                diff_link = (
                    f'<a href="{folder_path}/diff.png" class="file-link" target="_blank">View</a>'
                    if detail["diff"]
                    else '<span class="status-icon status-fail">✗</span>'
                )

                # Use checkmarks for successful files and add side-by-side view link
                if detail["old"]:
                    old_link = (
                        "<span>"
                        f'<a href="{folder_path}/old.png" class="file-link" target="_blank">'
                        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">'
                        '<g fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2">'
                        '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/>'
                        "</g></svg></a>"
                        "</span>"
                    )
                if detail["new"]:
                    new_link = (
                        f'<a href="{folder_path}/new.png" class="file-link" target="_blank">'
                        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">'
                        '<g fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2">'
                        '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" />'
                        '<path d="M14 2v4a2 2 0 0 0 2 2h4M9 15h6m-3 3v-6" />'
                        "</g></svg></a>"
                    )
                if detail["diff"]:
                    diff_link = (
                        f'<a href="{folder_path}/diff.png" class="file-link" target="_blank">'
                        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">'
                        '<path fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Zm-6 8h6m-3 3V7M9 17h6" />'
                        "</svg>"
                        "</a>"
                    )

                # Add side-by-side comparison link if both old and new exist
                if detail["old"] and detail["new"]:
                    # Prepare metrics object for JavaScript
                    metrics_js = "null"
                    if detail.get("metrics"):
                        metrics = detail["metrics"]
                        metrics_js = (
                            f"{{visual: {metrics.get('visual_similarity', 'null')}, "
                            f"structural: {metrics.get('structural_similarity', 'null')}, "
                            f"combined: {metrics.get('similarity_score', 'null')}, "
                            f"change: {metrics.get('change_percentage', 'null')}, "
                            f"magnitude: '{metrics.get('change_magnitude', 'N/A')}'}}"
                        )

                    comparison_link = (
                        f'<a class="view-link" onclick="openComparison('
                        f"'{detail['title']}', '{folder_path}/old.png', "
                        f"'{folder_path}/new.png', '{folder_path}/diff.png', "
                        f"{str(detail['diff']).lower()}, {metrics_js}, "
                        f"'{detail.get('old_url', '')}', '{detail.get('new_url', '')}'"
                        f')">Compare</a>'
                    )

                # Add metrics columns
                visual_cell = ""
                structural_cell = ""
                combined_cell = ""
                change_cell = ""
                magnitude_cell = ""

                if detail.get("metrics"):
                    metrics = detail["metrics"]
                    visual_cell = (
                        f'{metrics.get("visual_similarity", "-")}%' if metrics.get("visual_similarity") else "-"
                    )
                    structural_cell = (
                        f'{metrics.get("structural_similarity", "-")}%' if metrics.get("structural_similarity") else "-"
                    )
                    combined_cell = f'{metrics["similarity_score"]}%'
                    change_cell = f'{metrics["change_percentage"]}%'
                    magnitude_class = f'magnitude-{metrics["change_magnitude"].lower()}'
                    magnitude_cell = f'<span class="{magnitude_class}">{metrics["change_magnitude"]}</span>'
                else:
                    visual_cell = "-"
                    structural_cell = "-"
                    combined_cell = "-"
                    change_cell = "-"
                    magnitude_cell = "-"

                f.write(
                    f"""                <tr>
                    <td class="title-cell" title="{detail['title']}">
                        <div class="title-main">{detail['title']}</div>
                        <div class="title-id">{detail['row']}</div>
                    </td>
                    <td class="metrics-cell">{visual_cell}</td>
                    <td class="metrics-cell">{structural_cell}</td>
                    <td class="metrics-cell">{combined_cell}</td>
                    <td class="metrics-cell">{change_cell}</td>
                    <td class="metrics-cell">{magnitude_cell}</td>
                    <td>{old_link} | {new_link} | {diff_link}</td>
                    <td>{comparison_link}</td>
                </tr>
"""
                )

            f.write(
                """            </tbody>
        </table>
    </div>

    <!-- Comparison Modal -->
    <div id="comparisonModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <div class="modal-title" id="modalTitle">Screenshot Comparison</div>
                <span class="close">&times;</span>
            </div>
            <div class="comparison-container">
                <div class="screenshot-panel">
                    <div class="panel-header">
                        <span>Original</span>
                        <a id="oldUrlLink" class="view-link" target="_blank" style="display: none;">🔗 View Page</a>
                    </div>
                    <div class="screenshot-wrapper">
                        <img id="oldScreenshot" class="screenshot-image" src="" alt="Original screenshot">
                    </div>
                </div>
                <div class="screenshot-panel">
                    <div class="panel-header">
                            <select id="viewSelector" class="view-selector">
                                <option value="new">New Version</option>
                                <option value="diff">Difference View</option>
                            </select>
                        <a id="newUrlLink" class="view-link" target="_blank" style="display: none;">🔗 View Page</a>
                    </div>
                    <div class="screenshot-wrapper">
                        <img id="newScreenshot" class="screenshot-image" src="" alt="New screenshot">
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script type="text/javascript">
        // Modal functionality
        let currentNewPath = '';
        let currentDiffPath = '';
        let hasDiff = false;

        function closeModal() {
            document.getElementById('comparisonModal').style.display = 'none';
        }

        // Event listeners for modal
        document.querySelector('.close').onclick = closeModal;

        window.onclick = function(event) {
            const modal = document.getElementById('comparisonModal');
            if (event.target === modal) {
                closeModal();
            }
        }

        // View selector change
        document.getElementById('viewSelector').addEventListener('change', function() {
            const newScreenshot = document.getElementById('newScreenshot');
            if (this.value === 'new') {
                newScreenshot.src = currentNewPath;
                newScreenshot.alt = 'New screenshot';
            } else if (this.value === 'diff' && hasDiff) {
                newScreenshot.src = currentDiffPath;
                newScreenshot.alt = 'Difference view';
            }
        });

        // Synchronized scrolling
        let isScrolling = false;

        function setupSyncedScrolling() {
            const leftWrapper = document.querySelector('.screenshot-panel:first-child .screenshot-wrapper');
            const rightWrapper = document.querySelector('.screenshot-panel:last-child .screenshot-wrapper');

            function syncScroll(source, target) {
                if (isScrolling) return;
                isScrolling = true;

                const sourceScrollTop = source.scrollTop;
                const sourceScrollLeft = source.scrollLeft;
                const sourceScrollHeight = source.scrollHeight - source.clientHeight;
                const sourceScrollWidth = source.scrollWidth - source.clientWidth;

                const targetScrollHeight = target.scrollHeight - target.clientHeight;
                const targetScrollWidth = target.scrollWidth - target.clientWidth;

                // Calculate proportional scroll positions
                const scrollTopRatio = sourceScrollHeight > 0 ? sourceScrollTop / sourceScrollHeight : 0;
                const scrollLeftRatio = sourceScrollWidth > 0 ? sourceScrollLeft / sourceScrollWidth : 0;

                target.scrollTop = scrollTopRatio * targetScrollHeight;
                target.scrollLeft = scrollLeftRatio * targetScrollWidth;

                setTimeout(() => { isScrolling = false; }, 10);
            }

            leftWrapper.addEventListener('scroll', () => syncScroll(leftWrapper, rightWrapper));
            rightWrapper.addEventListener('scroll', () => syncScroll(rightWrapper, leftWrapper));
        }

        // Setup synced scrolling when modal opens
        function openComparison(title, oldPath, newPath, diffPath, diffExists, metrics, oldUrl, newUrl) {
            document.getElementById('modalTitle').innerHTML = title;

            // Add metrics to title if provided
            if (metrics && typeof metrics === 'object') {
                // Helper function to get color based on similarity score
                function getSimilarityColor(value) {
                    if (value >= 90) return '#28a745'; // Green
                    if (value >= 80) return '#e67e22'; // Darker orange/amber
                    if (value >= 70) return '#fd7e14'; // Orange
                    return '#dc3545'; // Red
                }

                // Helper function to get color based on change percentage (lower is better)
                function getChangeColor(value) {
                    if (value <= 5) return '#28a745'; // Green
                    if (value <= 15) return '#e67e22'; // Darker orange/amber
                    if (value <= 30) return '#fd7e14'; // Orange
                    return '#dc3545'; // Red
                }

                // Helper function to get magnitude color
                function getMagnitudeColor(magnitude) {
                    switch(magnitude) {
                        case 'None': return '#28a745'; // Green
                        case 'Minimal': return '#17a2b8'; // Blue
                        case 'Moderate': return '#e67e22'; // Darker orange/amber
                        case 'Significant': return '#dc3545'; // Red
                        default: return '#666'; // Gray
                    }
                }

                const visualColor = metrics.visual ? getSimilarityColor(metrics.visual) : '#666';
                const structuralColor = metrics.structural ? getSimilarityColor(metrics.structural) : '#666';
                const combinedColor = metrics.combined ? getSimilarityColor(metrics.combined) : '#666';
                const changeColor = metrics.change ? getChangeColor(metrics.change) : '#666';
                const magnitudeColor = getMagnitudeColor(metrics.magnitude);

                const metricsHtml = `
                    <div style="font-size: 0.8em; font-weight: normal; margin-top: 5px;">
                        Visual: <span style="color: ${visualColor}; font-weight: 600;">${metrics.visual || '-'}%</span> |
                        Structural: <span style="color: ${structuralColor}; font-weight: 600;">${metrics.structural || '-'}%</span> |
                        Combined: <span style="color: ${combinedColor}; font-weight: 600;">${metrics.combined || '-'}%</span> |
                        Change: <span style="color: ${changeColor}; font-weight: 600;">${metrics.change || '-'}%</span> |
                        <span style="color: ${magnitudeColor}; font-weight: 600;">${metrics.magnitude || '-'}</span>
                    </div>
                `;
                document.getElementById('modalTitle').innerHTML = title + metricsHtml;
            }

            document.getElementById('oldScreenshot').src = oldPath;
            document.getElementById('newScreenshot').src = newPath;

            // Update URL links if available
            const oldUrlLink = document.getElementById('oldUrlLink');
            const newUrlLink = document.getElementById('newUrlLink');

            if (oldUrl && oldUrl.trim() !== '') {
                oldUrlLink.href = oldUrl;
                oldUrlLink.style.display = 'inline-block';
                oldUrlLink.title = oldUrl;
            } else {
                oldUrlLink.style.display = 'none';
            }

            if (newUrl && newUrl.trim() !== '') {
                newUrlLink.href = newUrl;
                newUrlLink.style.display = 'inline-block';
                newUrlLink.title = newUrl;
            } else {
                newUrlLink.style.display = 'none';
            }

            currentNewPath = newPath;
            currentDiffPath = diffPath;
            hasDiff = diffExists;

            // Update view selector options
            const selector = document.getElementById('viewSelector');
            selector.innerHTML = '<option value="new">New Version</option>';
            if (diffExists) {
                selector.innerHTML += '<option value="diff">Difference View</option>';
            }
            selector.value = 'new';

            document.getElementById('comparisonModal').style.display = 'block';

            // Setup synchronized scrolling after modal is visible and images load
            setTimeout(setupSyncedScrolling, 100);
        }

        // Filter functionality
      function applyFilters() {
          const magnitudeFilter = document.getElementById('magnitudeFilter').value;
          const titleFilter = document.getElementById('titleFilter').value.toLowerCase();
          const statusFilter = document.getElementById('statusFilter').value;
          const rows = document.querySelectorAll('tbody tr');

          rows.forEach(row => {
              let show = true;
              const magnitudeCell = row.cells[6]; // Magnitude column
              const titleCell = row.cells[1]; // Title column
              const diffCell = row.cells[9]; // Diff image column

              // Apply magnitude filter
              if (magnitudeFilter) {
                  const magnitudeSpan = magnitudeCell.querySelector('span');
                  const magnitude = magnitudeSpan ? magnitudeSpan.textContent.trim() : '';
                  if (magnitude !== magnitudeFilter) {
                      show = false;
                  }
              }

              // Apply title filter
              if (titleFilter) {
                  const title = titleCell.textContent.toLowerCase();
                  if (!title.includes(titleFilter)) {
                      show = false;
                  }
              }

              // Apply status filter
              if (statusFilter) {
                  const hasDiff = diffCell.querySelector('.status-success');
                  const status = hasDiff ? 'complete' : 'incomplete';
                  if (status !== statusFilter) {
                      show = false;
                  }
              }

              row.style.display = show ? '' : 'none';
          });
      }

      function clearAllFilters() {
          document.getElementById('magnitudeFilter').value = '';
          document.getElementById('titleFilter').value = '';
          document.getElementById('statusFilter').value = '';
          applyFilters();
      }

      // Add event listeners
      document.getElementById('magnitudeFilter').addEventListener('change', applyFilters);
      document.getElementById('titleFilter').addEventListener('input', applyFilters);
      document.getElementById('statusFilter').addEventListener('change', applyFilters);

    </script>
</body>
</html>"""
            )

        logger.info(f"Summary report generated: {report_path}")
        return report_path

    except Exception as e:
        logger.error(f"Error generating summary report: {e}")
        raise
