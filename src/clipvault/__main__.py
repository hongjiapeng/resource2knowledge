# -*- coding: utf-8 -*-
"""Allow `python -m clipvault` to launch the CLI."""

from clipvault.cli import main
import sys

sys.exit(main())
