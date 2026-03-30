# -*- coding: utf-8 -*-
"""Tests for the CLI argument parser and backward-compatible translation."""

from clipvault.cli import build_parser


class TestCLIParser:
    def test_basic_url(self):
        parser = build_parser()
        args = parser.parse_args(["https://youtube.com/watch?v=abc"])
        assert args.url == "https://youtube.com/watch?v=abc"

    def test_skip_steps(self):
        parser = build_parser()
        args = parser.parse_args(["https://x.com/post", "--skip", "transcribe", "summarize"])
        assert "transcribe" in args.skip
        assert "summarize" in args.skip

    def test_dry_run(self):
        parser = build_parser()
        args = parser.parse_args(["https://x.com/post", "--dry-run"])
        assert args.dry_run is True

    def test_json_output_flag(self):
        parser = build_parser()
        args = parser.parse_args(["https://x.com/post", "--json"])
        assert args.json_output is True

    def test_defaults(self):
        parser = build_parser()
        args = parser.parse_args(["https://x.com/post"])
        assert args.dry_run is False
        assert args.skip == []
        assert args.log_level == "INFO"
        assert args.json_output is False
        assert args.no_resume is False
