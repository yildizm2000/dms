# DMS Simulator

This repository contains the original **SharpNTCIP** library archive along with a simple DMS simulator script written in Python.

The `simulate_dms.py` script renders a scrolling line of text similar to a dynamic message sign (DMS). It understands a very small subset of MULTI markup used by NTCIP signs. Color codes are entered using `[cbN]` to start a color (where `N` is 1-4) and `[cb]` to reset the color.

## Usage

```bash
python3 simulate_dms.py "THIS IS [cb3]A TEST[cb] MESSAGE" --width 30 --delay 0.1
```

The text will scroll across the terminal with simple ANSI colors. Width controls the display width and delay controls the speed.
