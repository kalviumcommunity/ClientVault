"""
ClientVault - Foundation Verification & Starter Entrypoint

Verifies that:
1. Virtual environment and dependencies (openai, chromadb, python-dotenv) are active.
2. Configuration can be loaded from .env or fallback defaults.
3. Workspace directory boundaries (data/, src/, prompts/, outputs/) exist.
4. ChromaDB local client can initialize cleanly without errors.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Base paths
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
PROMPTS_DIR = ROOT_DIR / "prompts"
OUTPUTS_DIR = ROOT_DIR / "outputs"
SRC_DIR = ROOT_DIR / "src"


def verify_workspace_structure() -> bool:
    """Check that all required concern directories exist."""
    required_dirs = [DATA_DIR, PROMPTS_DIR, OUTPUTS_DIR, SRC_DIR]
    all_exist = True
    for directory in required_dirs:
        if directory.is_dir():
            print(f"  [OK] Directory exists: {directory.relative_to(ROOT_DIR)}/")
        else:
            print(f"  [FAIL] Missing directory: {directory.relative_to(ROOT_DIR)}/")
            all_exist = False
    return all_exist


def verify_environment_and_keys():
    """Load and report status of required configuration keys."""
    # Load .env if present
    env_file = ROOT_DIR / ".env"
    if env_file.exists():
        load_dotenv(dotenv_path=env_file)
        print("  [OK] Loaded local .env file")
    else:
        print("  [INFO] No .env file found (using system env or defaults). Copy .env.example to .env to set local keys.")

    required_keys = [
        ("OPENAI_BASE_URL", os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")),
        ("OPENAI_API_KEY", os.getenv("OPENAI_API_KEY")),
        ("OPENAI_CHAT_MODEL", os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")),
        ("OPENAI_EMBEDDING_MODEL", os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")),
    ]

    for key_name, value in required_keys:
        if value:
            # Mask secret if it looks like an API key
            display_val = value if key_name != "OPENAI_API_KEY" else (value[:6] + "..." if len(value) > 6 else "[SET]")
            print(f"  [OK] Config {key_name}: {display_val}")
        else:
            print(f"  [WARN] Config {key_name}: Not configured (set in .env)")


def verify_dependencies() -> bool:
    """Verify core RAG dependencies can be imported and initialized."""
    try:
        import openai  # noqa: F401
        print("  [OK] Dependency imported: openai")
    except ImportError as e:
        print(f"  [FAIL] openai import failed: {e}")
        return False

    try:
        import chromadb
        print("  [OK] Dependency imported: chromadb")

        # Test in-memory or directory client initialization
        client = chromadb.PersistentClient(path=str(OUTPUTS_DIR / "chroma_test_db"))
        collection = client.get_or_create_collection(name="health_check")
        count = collection.count()
        print(f"  [OK] ChromaDB initialized successfully (collection count: {count})")
    except Exception as e:
        print(f"  [FAIL] chromadb initialization failed: {e}")
        return False

    return True


def main():
    print("=" * 65)
    print("  ClientVault — Foundation Health Check & Run Proof")
    print(f"  Python Version: {sys.version.split()[0]} ({sys.executable})")
    print("=" * 65)

    print("\n1. Verifying Workspace Directory Separation:")
    ws_ok = verify_workspace_structure()

    print("\n2. Verifying Environment & Configuration Keys:")
    verify_environment_and_keys()

    print("\n3. Verifying Core Dependencies & Local ChromaDB:")
    deps_ok = verify_dependencies()

    print("\n" + "=" * 65)
    if ws_ok and deps_ok:
        print("  STATUS: ALL CHECKS PASSED - WORKSPACE READY")
    else:
        print("  STATUS: CHECKS FAILED - REVIEW LOGS ABOVE")
    print("=" * 65)


if __name__ == "__main__":
    main()
