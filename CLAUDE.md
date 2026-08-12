# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Personal AI Health Agent that analyzes Garmin/Whoop/Coros data along with a morning intake journal to derive insights and suggest training and nutrition protocol based on current health and fitness goals.

## Current state

This repository is a bare skeleton — most files exist but are empty, and no dependencies, build tooling, tests, or commands have been established yet:

- `src/agent.py`, `src/tools/__init__.py`, `src/__init__.py`, `tests/__init__.py` — empty placeholder files
- `requirements.txt` — empty (no Python dependencies pinned yet)
- `.env.example` — empty (no environment variables documented yet)
- `data/` — empty directory (`.gitkeep` only), presumably intended for local health data exports (Garmin/Whoop/Coros) and journal entries

There is no build, lint, or test command to run yet because no code or tooling has been added. When adding the first real implementation, also establish and document these commands here (e.g. how to install dependencies, run the agent, and run tests) so future sessions don't have to rediscover them.

## Architecture notes

The intended shape, based on the directory layout, is a `src/agent.py` entrypoint that orchestrates calls into `src/tools/` (presumably per-data-source integrations such as Garmin/Whoop/Coros clients and journal parsing) to produce training/nutrition recommendations. `.env.example` implies API credentials/config will be loaded from environment variables — check there first for what integrations expect before adding new ones. As this fills in, update this section with the real data flow (how data sources are pulled/parsed, how the journal is ingested, and how recommendations are generated) rather than a per-file inventory.
