# Tests to verify that main.py can be run with different arguments
import os
import pytest
from main import confirm_options_and_fetch_urls
import shutil


def test_valid_csv_and_output_folder():
    # Test that the function can be called with a valid CSV file and output folder

    # Create a temporary CSV file
    csv_file = 'test.csv'
    with open(csv_file, 'w') as f:
        f.write('url\n')
        f.write('http://example.com\n')

    # Create a temporary output folder
    output_folder = 'test_output'

    # Call the function
    confirm_options_and_fetch_urls(csv_file, output_folder, skip_confirmation=True)

    # Check that the output folder was created
    assert os.path.exists(output_folder)
    assert os.path.isdir(output_folder)

    # Check that the screenshot file was created
    screenshot_file = os.path.join(output_folder, 'screenshot_example.com.png')
    assert os.path.isfile(screenshot_file)

    # Clean up
    os.remove(csv_file)
    shutil.rmtree(output_folder)


# Test that the function raises an error with an invalid CSV file
def test_invalid_csv():
    # Call the function with an invalid CSV file
    with pytest.raises(FileNotFoundError):
        confirm_options_and_fetch_urls('invalid.csv', output_folder='output', skip_confirmation=True)


# Test that the function raises an error with an invalid output folder
def test_invalid_output_folder():
    # Create a temporary CSV file
    csv_file = 'test.csv'
    with open(csv_file, 'w') as f:
        f.write('url\n')
        f.write('http://example.com\n')

    # Call the function with an invalid output folder
    with pytest.raises(OSError):
        confirm_options_and_fetch_urls(csv_file, output_folder='/invalid/output/folder', skip_confirmation=True)

    # Clean up
    os.remove(csv_file)
