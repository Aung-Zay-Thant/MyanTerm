#!/bin/bash
# Double-click in Finder to install MyanTerm (runs install.sh in Terminal).
cd "$(dirname "$0")" && ./install.sh
echo
read -r -p "Press Return to close this window. " _
