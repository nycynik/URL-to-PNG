# URL-to-PNG
Takes a CSV of web urls and creates a folder of image captures of those links.

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

You can replace the CSV with your own list of URLs, it skips the first row assuming there is a header there. output is placed in the output folder, which is created if it does not already exist.

# Development

Thanks for thinking about how to make it better!

## We use Pre-commit hooks

Please install pre-commit hoooks (if you are using the virtual env for this repo. they are installed already.)

    uv add pre-commit

You can run the tests before pushing to the repo.

    pre-commit run --all-files

When you commit new code, the tests will automatically run.
