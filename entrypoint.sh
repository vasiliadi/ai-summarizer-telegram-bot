#!/bin/bash
set -ex

Xvfb -ac :99 -screen 0 1280x1024x16 > /dev/null 2>&1 &
python main.py
