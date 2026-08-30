#!/bin/sh
set -eu

image_name="storelink-buyer-mcp:exercise"
canary="LEAK_TEST_CONTAINER_SECRET_47_a1b2c3d4"
output_file="$(mktemp)"
trap 'rm -f "$output_file"' EXIT

docker build -t "$image_name" .
docker run --rm --entrypoint sh -v "$PWD:/workspace:ro" -w /workspace "$image_name" -c \
  "pip install -q 'pytest>=8,<9' 'pytest-asyncio>=0.24,<2' && PYTHONPATH=src python -m pytest -q"

docker run --rm --entrypoint storelink-buyer-demo \
  -e "KORRAL_STORE_KEY_47=$canary" "$image_name" >"$output_file" 2>&1

if grep -F "$canary" "$output_file" >/dev/null; then
  echo "FAIL: canary credential appeared in terminal output" >&2
  exit 1
fi

if docker image inspect "$image_name" | grep -E -e 'KORRAL_STORE_KEY_[0-9]+=' -e 'LEAK_TEST_.*SECRET' >/dev/null; then
  echo "FAIL: credential-like value appeared in image configuration" >&2
  exit 1
fi

if docker history --no-trunc "$image_name" | grep -E -e 'KORRAL_STORE_KEY_[0-9]+=' -e 'LEAK_TEST_.*SECRET' >/dev/null; then
  echo "FAIL: credential-like value appeared in image history" >&2
  exit 1
fi

if grep -rnE --exclude-dir=.git --exclude-dir=audit \
  -e '-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----' \
  -e 'sk_live_[A-Za-z0-9]+' \
  -e 'AKIA[0-9A-Z]{16}' .; then
  echo "FAIL: likely committed secret material found" >&2
  exit 1
fi

echo "PASS: tests, terminal output, repository scan, image config, and image history show no credential leakage"
