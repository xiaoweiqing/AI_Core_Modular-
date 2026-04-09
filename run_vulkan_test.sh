#!/bin/bash
# ==============================================================================
#  Launcher for the Vulkan Diagnostic Script
# ==============================================================================
# This script activates the correct Conda environment and then runs the
# test_vulkan.py script to check for GPU support.
# ==============================================================================

# --- Configuration ---
CONDA_ENV_NAME="aic-final"
PYTHON_TEST_SCRIPT="test_vulkan.py"

# --- Main Logic ---
clear

# --- Activate Conda Environment ---
echo ">> Activating Conda environment: '${CONDA_ENV_NAME}'..."
if [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
else
    echo "❌ CRITICAL: Conda installation not found."
    exit 1
fi

conda activate "${CONDA_ENV_NAME}"
if [ $? -ne 0 ]; then
    echo "❌ CRITICAL: Failed to activate Conda environment '${CONDA_ENV_NAME}'."
    exit 1
fi
echo "✅ Conda environment activated."
echo ""

# --- Run the Python Diagnostic Script ---
echo ">> Executing the Python diagnostic script..."
echo ""

python "${PYTHON_TEST_SCRIPT}"

echo ""
echo ">> Diagnostic script has finished."
read -p "Press any key to close..."
