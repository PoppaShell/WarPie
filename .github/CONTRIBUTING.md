# Contributing to WarPie

Thank you for your interest in contributing to WarPie, a Raspberry Pi-based wardriving platform!

## How to Contribute

- **Bug Reports**: Open an [issue](https://github.com/PoppaShell/WarPie/issues) with reproduction steps
- **Feature Requests**: Create an issue to discuss before implementing
- **Code Contributions**: Submit pull requests for fixes or features
- **Documentation**: Help improve guides and examples

## Development Setup

### Prerequisites

- Python 3.12+
- Bash 4.0+
- Node.js 18+ (for JS linting)

### Setup

```bash
# Clone the repository
git clone https://github.com/PoppaShell/WarPie.git
cd WarPie

# Install Python dev dependencies
pip install -r requirements-dev.txt

# Install pre-commit hooks
pre-commit install
```

## Code Style

### Python
- **Linter/Formatter**: Ruff (configured in `pyproject.toml`)
- **Line length**: 100 characters
- **Target**: Python 3.12+

```bash
ruff check --fix .
ruff format .
```

### Bash
- **Linter**: ShellCheck
- Use `set -euo pipefail` at script start
- Support `--json` mode for CLI tools

```bash
shellcheck bin/*.sh install/*.sh
```

### JavaScript (Embedded)
- **Linter**: ESLint (configured in `.eslintrc.json`)
- Extracted from Python files for linting

```bash
npm run lint
```

## Testing

```bash
# Python tests
pytest tests/

# With coverage
pytest tests/ --cov=bin --cov-report=html

# Bash linting
shellcheck bin/*.sh

# JavaScript tests
npm test
```

## Pull Request Process

1. **Create a feature branch** from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make changes** with clear commits:
   ```bash
   git commit -m "feat: add network filtering support"
   ```

3. **Run pre-commit checks**:
   ```bash
   pre-commit run --all-files
   ```

4. **Run tests**:
   ```bash
   pytest tests/
   ```

5. **Push and create PR**:
   ```bash
   git push origin feature/your-feature-name
   ```

## Commit Messages

Follow conventional commits:
- `fix:` - Bug fixes
- `feat:` - New features
- `docs:` - Documentation
- `refactor:` - Code improvements
- `test:` - Test additions
- `chore:` - Maintenance

## Code of Conduct

- Be respectful and constructive
- Welcome diverse perspectives
- Keep discussions focused and professional

## License

By contributing, you agree your work will be licensed under **GPL-3.0**.

---

Questions? Open a discussion or check existing issues.
