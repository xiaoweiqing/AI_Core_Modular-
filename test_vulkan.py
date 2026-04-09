import os
import sys
from pathlib import Path

# ==============================================================================
#      Vulkan Support Diagnostic Script for llama-cpp-python
# ==============================================================================
# This script attempts to load a GGUF model with maximum verbosity to
# check if the underlying library was compiled with Vulkan support.
# It is completely standalone and does not affect your main application.
# ==============================================================================

# --- [CONFIGURATION] ---
# IMPORTANT: Make sure this path points to your model file.
MODEL_PATH = "/mnt/data/model/Qwen3-30B-A3B-Instruct-2507-UD-TQ1_0.gguf"

def run_test():
    """
    Main test function.
    """
    print("="*60)
    print("   🚀 Starting Llama.cpp Vulkan Support Diagnostic Test 🚀")
    print("="*60)
    print(f"🐍 Python Executable: {sys.executable}")
    print(f"📝 Model Path: {MODEL_PATH}")
    print("-" * 60)

    # --- 1. Check if the model file exists ---
    if not Path(MODEL_PATH).is_file():
        print(f"❌ CRITICAL ERROR: Model file not found at the specified path.")
        print("   Please check the MODEL_PATH variable in this script.")
        print("-" * 60)
        sys.exit(1)
    else:
        print("✅ Model file found.")

    # --- 2. Attempt to import LlamaCpp ---
    try:
        from langchain_community.llms import LlamaCpp
        print("✅ LangChain LlamaCpp wrapper imported successfully.")
    except ImportError as e:
        print(f"❌ CRITICAL ERROR: Failed to import LlamaCpp.")
        print("   This likely means langchain-community or llama-cpp-python is not installed.")
        print(f"   Error details: {e}")
        print("-" * 60)
        sys.exit(1)

    # --- 3. Load the model with diagnostic flags ---
    print("\n⏳ Now attempting to load the model with Vulkan enabled...")
    print("   Watch the logs below carefully for 'backend is vulkan' and 'offloading layers'.")
    print("-" * 60)

    try:
        # This is the core of the test.
        # We instantiate the LlamaCpp class with:
        #   - n_gpu_layers=-1: An instruction to offload as many layers as possible.
        #   - verbose=True:   The critical flag to print all backend logs.
        llm = LlamaCpp(
            model_path=MODEL_PATH,
            n_gpu_layers=99,  # Request to offload many layers to the GPU
            verbose=True,   # CRITICAL: This forces the C++ logs to be printed
            n_ctx=512       # Use a small context size just for this test
        )
        
        print("-" * 60)
        print("✅ SUCCESS! The model was loaded without crashing.")
        print("   Please review the detailed logs printed above to confirm GPU usage.")
        print("=" * 60)

    except Exception as e:
        print("-" * 60)
        print(f"❌ ERROR: The model failed to load. This could be due to several reasons:")
        print("   - The model file is corrupt.")
        print("   - Not enough VRAM/RAM.")
        print("   - A critical error in the llama.cpp backend.")
        print("\n   Error Details:")
        print(f"   {e}")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    run_test()
