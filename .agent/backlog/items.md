# Local backlog

| ID | Status | Priority | Owner | Title | Notes |
|----|--------|----------|-------|-------|-------|
| L-001 | Review | p1 | agent | Implement Jev MCP System One tools | Tools: jev_choice, jev_score, jev_noul, jev_system_one. Shipped in v0.2.0. |
| L-002 | In progress | p1 | agent | Image assets and Box for Jev 1.14 | `images` arg + `box` type; opt-in via JEV_IMAGE_ROOTS; docs/images.md. Branch feat/L-002-image-assets. |
| L-003 | Done | p2 | agent | Move engineering/ out of jev-mcp | Stale copy of jev-engineering; canonical source moved to a private repo. Merged in #4 (3c409ad). |
| L-004 | Ready | p1 | — | Clear Dependabot alerts in uv.lock | 44 open (5 critical, 23 high, 16 moderate). Pillow 12.3.0 -> 13.0.0 needs the `Pillow>=11,<13` cap raised in vision/evaluation/dev extras (touches L-002 image assets); PyJWT 2.14.0 -> 2.15.0 and opentelemetry-api 1.44.0 -> 1.45.1 are lock bumps. |
