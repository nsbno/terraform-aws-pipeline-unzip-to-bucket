#!/usr/bin/env bash
#
# Copyright (C) 2020 Erlend Ekern <dev@ekern.me>
#
# Distributed under terms of the MIT license.

set -euo pipefail
IFS=$'\n\t'

lambda_file="./main.py"
venv_folder="./.env_$(date +'%s')"

python3.7 -m venv "$venv_folder"
source "$venv_folder/bin/activate"

# Linting and formatting
pip install -r ci_requirements.txt
black "$lambda_file"
flake8 "$lambda_file"

# Bundle production dependencies
mkdir ./package
# You can use this command to install production dependencies:
# pip install --target ./package -r requirements.txt
cp ./main.py ./states.json ./package
(cd ./package && zip -r ../package.zip .)

rm -rf "$venv_folder"
