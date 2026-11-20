import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def pytest_addoption(parser):
    parser.addoption(
        '--headed',
        action='store_true',
        default=False,
        help='Run Playwright E2E browser tests with a visible browser window.',
    )
    parser.addoption(
        '--slowmo',
        type=int,
        default=0,
        help='Slow down Playwright actions by N milliseconds (useful with --headed).',
    )
