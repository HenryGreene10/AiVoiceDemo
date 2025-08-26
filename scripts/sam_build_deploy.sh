#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

sam build
sam deploy --guided


