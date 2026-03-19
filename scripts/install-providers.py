"""Install protoClaw providers into nanobot's package.

Copies custom provider modules into the installed nanobot package and
patches the CLI to use them. This runs at Docker build time.
"""

import importlib.util
import shutil
from pathlib import Path

# Find installed nanobot package
nanobot_pkg = Path(importlib.util.find_spec("nanobot").submodule_search_locations[0])
providers_dir = nanobot_pkg / "providers"
cli_path = nanobot_pkg / "cli" / "commands.py"

# Copy custom providers
src_dir = Path("/opt/protoclaw/providers")
for src in src_dir.glob("*.py"):
    dst = providers_dir / src.name
    shutil.copy2(src, dst)
    print(f"Installed provider: {src.name} -> {dst}")

# Patch CLI to use OmniCoderProvider for omnicoder models
cli_text = cli_path.read_text()
if "OmniCoderProvider" not in cli_text:
    old = """        provider = provider_cls("""
    new = """        # protoClaw: Use OmniCoderProvider for models with XML-style tool calls
        if "omnicoder" in model.lower():
            from nanobot.providers.omnicoder_provider import OmniCoderProvider
            provider_cls = OmniCoderProvider

        provider = provider_cls("""

    # Find the right insertion point (after provider_cls = LiteLLMProvider)
    marker = "provider_cls = LiteLLMProvider"
    if marker in cli_text:
        # Already has provider_cls pattern from our earlier edit
        pass
    else:
        # Stock nanobot — need to add provider_cls pattern
        old_stock = """        provider = LiteLLMProvider("""
        new_stock = """        # protoClaw: Use OmniCoderProvider for models with XML-style tool calls
        provider_cls = LiteLLMProvider
        if "omnicoder" in model.lower():
            from nanobot.providers.omnicoder_provider import OmniCoderProvider
            provider_cls = OmniCoderProvider

        provider = provider_cls("""
        cli_text = cli_text.replace(old_stock, new_stock)

    cli_path.write_text(cli_text)
    print(f"Patched CLI: {cli_path}")

# Patch loop.py to strip orphaned </think> tags
loop_path = nanobot_pkg / "agent" / "loop.py"
loop_text = loop_path.read_text()
if "orphaned </think>" not in loop_text:
    old_strip = '''        return re.sub(r"<think>[\\s\\S]*?</think>", "", text).strip() or None'''
    new_strip = '''        # Strip paired <think>…</think> blocks
        text = re.sub(r"<think>[\\s\\S]*?</think>", "", text)
        # Strip orphaned </think> tags (model may omit opening tag)
        text = re.sub(r"</think>\\s*", "", text)
        return text.strip() or None'''
    if old_strip in loop_text:
        loop_text = loop_text.replace(old_strip, new_strip)
        loop_path.write_text(loop_text)
        print(f"Patched loop.py: {loop_path}")

print("protoClaw providers installed successfully.")
