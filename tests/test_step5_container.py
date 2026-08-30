"""Step 5 — the shipped artifact.

Host-side smoke tests against the built Docker image, marked `container`.
Kept Python 3.9-compatible and free of project imports so they can run on
a host that lacks the package's own dependencies; everything else runs
inside the image (see test_s5_2).
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.container

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "storelink-buyer-mcp:testplan"

EXPECTED_TOOLS = sorted([
    "list_categories", "review_category", "replenish_store_stock",
    "plan_replenishment", "submit_replenishment", "get_purchase_order",
])

STDIO_PROBE = """
import asyncio, json
from fastmcp import Client

async def main():
    config = {"mcpServers": {"storelink": {"command": "storelink-buyer-mcp"}}}
    async with Client(config) as client:
        tools = sorted(tool.name for tool in await client.list_tools())
        print("TOOLS=" + json.dumps(tools))

asyncio.run(main())
"""


@pytest.fixture(scope="module")
def built_image():
    if shutil.which("docker") is None:
        pytest.skip("docker is not available on this host")
    result = subprocess.run(
        ["docker", "build", "-t", IMAGE, "."],
        cwd=str(ROOT), capture_output=True, text=True, timeout=600,
    )
    assert result.returncode == 0, result.stderr[-3000:]
    return IMAGE


def test_s5_1_image_builds(built_image):
    """Building the image is the assertion; failure surfaces in the fixture."""


def test_s5_2_full_suite_passes_inside_the_image(built_image):
    command = (
        "pip install -q 'pytest>=8,<9' 'pytest-asyncio>=0.24,<2' && "
        "PYTHONPATH=src python -m pytest -q -m 'not container' -p no:cacheprovider"
    )
    result = subprocess.run(
        ["docker", "run", "--rm", "--entrypoint", "sh",
         "-v", "{}:/workspace:ro".format(ROOT), "-w", "/workspace",
         built_image, "-c", command],
        capture_output=True, text=True, timeout=600,
    )
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-2000:]


def test_s5_3_stdio_server_answers_a_real_mcp_client(built_image):
    result = subprocess.run(
        ["docker", "run", "--rm", "--entrypoint", "python",
         built_image, "-c", STDIO_PROBE],
        capture_output=True, text=True, timeout=180,
    )
    assert result.returncode == 0, result.stderr[-3000:]
    tools_line = [line for line in result.stdout.splitlines() if line.startswith("TOOLS=")]
    assert tools_line, result.stdout[-2000:]
    assert json.loads(tools_line[-1][len("TOOLS="):]) == EXPECTED_TOOLS


def test_s5_4_demo_replenishes_store_47_only(built_image):
    result = subprocess.run(
        ["docker", "run", "--rm", "--entrypoint", "storelink-buyer-demo", built_image],
        capture_output=True, text=True, timeout=180,
    )
    assert result.returncode == 0, result.stderr[-3000:]
    assert '"R47-' in result.stdout          # an order was raised at store 47
    assert '"R102-' not in result.stdout     # and none at store 102
    assert '"no_action"' in result.stdout    # store 102's decision is shown
