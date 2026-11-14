# Makefile for the mcp-server-macos Python package

# Variables
# The import name (the PyPI distribution is "mcp-server-macos").
PACKAGE_NAME = mcp_server_macos
PYTHON = python3
PIP = $(PYTHON) -m pip
VENV_DIR = .venv
TEST_DIR = tests
DIST_DIR = dist

# Colors for output
GREEN = \033[0;32m
YELLOW = \033[0;33m
NC = \033[0m # No Color

# Default target
.PHONY: help
help:
	@echo "$(GREEN)mcp-server-macos Python package Makefile$(NC)"
	@echo ""
	@echo "Setup:"
	@echo "  $(YELLOW)venv$(NC)             - Create a virtual environment in $(VENV_DIR)"
	@echo "  $(YELLOW)install$(NC)          - Install the package in development mode"
	@echo "  $(YELLOW)install-dev$(NC)      - Install the package with development dependencies"
	@echo ""
	@echo "Checks:"
	@echo "  $(YELLOW)test$(NC)             - Run the unit and live tests (the live ones show a notification)"
	@echo "  $(YELLOW)test-unit$(NC)        - Run the unit tests only (safe: nothing on this Mac changes)"
	@echo "  $(YELLOW)test-live$(NC)        - Run the live tests only"
	@echo "  $(YELLOW)test-coverage$(NC)    - Run the unit tests with a coverage report, failing under the $(COVERAGE_MIN)% CI gates on"
	@echo "  $(YELLOW)lint$(NC)             - Run the linter (flake8)"
	@echo "  $(YELLOW)type-check$(NC)       - Run the type checker (mypy)"
	@echo "  $(YELLOW)check$(NC)            - Run lint, type-check and test-unit: what CI runs on a pull request, except the live tests"
	@echo ""
	@echo "Running:"
	@echo "  $(YELLOW)inspect$(NC)          - Open the MCP Inspector on the server, to list and call its tools (needs npx)"
	@echo ""
	@echo "Packaging:"
	@echo "  $(YELLOW)build$(NC)            - Build the wheel and source distribution"
	@echo "  $(YELLOW)validate$(NC)         - Build and check the distributions"
	@echo "  $(YELLOW)version$(NC)          - Show the current version"
	@echo "  $(YELLOW)clean$(NC)            - Remove build, test and cache artifacts"

# Create virtual environment
.PHONY: venv
venv:
	@echo "$(GREEN)Creating virtual environment...$(NC)"
	$(PYTHON) -m venv $(VENV_DIR)
	@echo "$(YELLOW)To activate: source $(VENV_DIR)/bin/activate$(NC)"

# Install package in development mode
.PHONY: install
install:
	@echo "$(GREEN)Installing package in development mode...$(NC)"
	$(PIP) install -e .

# Install development dependencies (pytest, flake8, mypy, build, twine)
.PHONY: install-dev
install-dev:
	@echo "$(GREEN)Installing development dependencies...$(NC)"
	$(PIP) install -e ".[dev]"

# The unit tests and the live ones, which call the tools against this Mac: a notification shows up.
.PHONY: test
test:
	@echo "$(GREEN)Running the unit and live tests...$(NC)"
	$(PYTHON) -m pytest $(TEST_DIR) -v -rs

# The unit tests, which don't touch the system (they also run on Linux).
.PHONY: test-unit
test-unit:
	@echo "$(GREEN)Running unit tests...$(NC)"
	$(PYTHON) -m pytest $(TEST_DIR)/unit -v

.PHONY: test-live
test-live:
	@echo "$(GREEN)Running live tests...$(NC)"
	$(PYTHON) -m pytest $(TEST_DIR)/live -v -rs

# The unit tests with coverage, held to the gate CI applies on every Python.
# Keep it in step with --cov-fail-under in .github/workflows/test.yml.
COVERAGE_MIN = 90

.PHONY: test-coverage
test-coverage:
	@echo "$(GREEN)Running unit tests with coverage...$(NC)"
	$(PYTHON) -m pytest $(TEST_DIR)/unit --cov=$(PACKAGE_NAME) --cov-report=html --cov-report=term --cov-fail-under=$(COVERAGE_MIN)
	@echo "$(YELLOW)HTML report available at htmlcov/index.html$(NC)"

# Run linter
.PHONY: lint
lint:
	@echo "$(GREEN)Running linter (flake8)...$(NC)"
	$(PYTHON) -m flake8 $(PACKAGE_NAME) $(TEST_DIR)

# Run type checker (config in pyproject.toml)
.PHONY: type-check
type-check:
	@echo "$(GREEN)Running type checker (mypy)...$(NC)"
	$(PYTHON) -m mypy $(PACKAGE_NAME) $(TEST_DIR)

# Everything CI runs on a pull request, except the live tests
.PHONY: check
check: lint type-check test-unit
	@echo "$(GREEN)All checks passed!$(NC)"

# The MCP Inspector: a page in the browser that lists the server's tools and calls them.
.PHONY: inspect
inspect:
	npx @modelcontextprotocol/inspector $(PYTHON) -m $(PACKAGE_NAME)

# Build package. Releases are published by the GitHub workflow when a
# release is created, so there is no publish target here.
.PHONY: build
build: clean
	@echo "$(GREEN)Building package...$(NC)"
	$(PYTHON) -m build

# Validate package: the metadata PyPI reads, and what the wheel holds
.PHONY: validate
validate: build
	@echo "$(GREEN)Validating package...$(NC)"
	$(PYTHON) -m twine check --strict $(DIST_DIR)/*
	$(PYTHON) .github/wheel_check.py

# Show current version
.PHONY: version
version:
	@$(PYTHON) -c "import $(PACKAGE_NAME); print($(PACKAGE_NAME).__version__)"

# Clean build artifacts
.PHONY: clean
clean:
	@echo "$(GREEN)Cleaning build artifacts...$(NC)"
	rm -rf build $(DIST_DIR) *.egg-info .pytest_cache .mypy_cache htmlcov .coverage coverage.xml
	find . -path ./$(VENV_DIR) -prune -o -type d -name "__pycache__" -exec rm -rf {} +
