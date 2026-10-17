# Changelog — Jev MCP

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.3.0] — 2026-10-16

### Added

- Experimental image assets across all judgment tools: base64 PNG/JPEG or absolute local paths,
  explicit `allow_images`, nested and embedded references, full decoding and bounded multipart uploads.
- `jev_box` and batch `type: box` with validated normalized coordinates and nullable confidence.
  Raw Box answers remain available; optional targets use application-level Noul presence gates.
- Per-request `long_context` opt-in with a larger bounded text budget and documented TypeSafe header.
- Optional vision/evaluation dependencies and `vision prepare|run|evaluate`: EXIF/RGB preparation,
  hashes and coordinate transforms, resolution/compression variants, tiles, offline overlays/plots,
  frozen group manifests, annotation isolation, bounded live runs, fingerprints and safe resume.
- Calibration, classification, Score, presence-gated localization, coverage-risk, latency,
  token and recorded-price cost metrics, plus six runnable synthetic task examples.

### Changed

- **Model-default migration:** the default is now `jev-1.14.0`. Set `JEV_MODEL=jev-1.13.0`
  or pass `model` per request to retain the prior model. Experimental features remain opt-in.
- Require `typesafe-sdk>=0.7.5,<1`; local image files additionally require `JEV_IMAGE_ROOTS`.
- Update API contracts and the canonical Jev decision skill; regenerate Cursor and Codex mirrors.

### Fixed

- Restore canonical safety metadata and valid relative links in 25 framework workflow skills,
  resolving the frontmatter release gate without weakening validation.

## [0.2.0] — 2026-09-22

### Added

- Stdio MCP tools for TypeSafe System One: `jev_choice`, `jev_score`, `jev_noul`, and `jev_system_one`.
- `jev-mcp` CLI / `scripts/run_jev_mcp.py` launcher with `JEV_TOKEN` (or `TYPESAFE_API_KEY`) auth and pinned default model `jev-1.13.0`.
- Project MCP config entry `jev-rw-systemone` and mocked unit tests for credentials, normalize, and tools.
- Project seeded from synthet-code-framework.

