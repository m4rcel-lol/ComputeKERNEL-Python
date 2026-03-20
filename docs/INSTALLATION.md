# Installation and Usage Guide

This document explains how to download, install, and run ComputeKERNEL-Python
(`computekernel-edu`) on Windows, Linux, and macOS.

## 1) Download the project

### Option A: Download ZIP from GitHub (all platforms)
1. Open the repository page in your browser.
2. Click **Code** > **Download ZIP**.
3. Extract the ZIP to a folder.
4. Open a terminal in the extracted project folder.

### Option B: Clone with Git (all platforms)
```bash
git clone https://github.com/m4rcel-lol/ComputeKERNEL-Python.git
cd ComputeKERNEL-Python
```

## 2) Install

The project requires Python 3.11 or newer.

### Windows (PowerShell)
```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install .
```

If script execution is blocked in PowerShell, run:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```
then activate the environment again.

### Linux (bash)
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install .
```

### macOS (zsh/bash)
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install .
```

## 3) Run

After installation, start the simulator with either command:

```bash
computekernel-edu
```

or:

```bash
python -m computekernel_edu
```

Show CLI help:

```bash
computekernel-edu --help
```

## 4) Optional run modes

Run with profile:

```bash
computekernel-edu debug
computekernel-edu safe
computekernel-edu performance
```

Run quietly:

```bash
computekernel-edu --quiet
```

## 5) Run tests

From the repository root:

```bash
python -m pytest -q
```
