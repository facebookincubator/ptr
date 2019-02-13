#!/bin/bash

# Simple script to build and release via twine to PyPI

function errorCheck() {
  if [ $? -ne 0 ]; then
    echo "ERROR: $@"
    exit 1
  fi
}

VENV_DIR=$1

if [ "$VENV_DIR" == "" ]; then
  echo "Please give a path for venv to create. Exiting"
  exit 2
fi

if [ -d "$VENV_DIR" ]; then
  echo "ERROR: $VENV_DIR exists"
  exit 69
fi

python3 -m venv "$VENV_DIR"
errorCheck "Unable to create a venv @ $VENV_DIR"

"$VENV_DIR/bin/pip" install --upgrade pip setuptools wheel twine
errorCheck "Unable to update packages via pip"

if [ -d dist ]; then
  echo "Moving old dist to /tmp"
  mv -v dist /tmp
fi

for build_type in "bdist_wheel" "sdist"
do
  "$VENV_DIR/bin/python" setup.py "$build_type"
  errorCheck "Unable to build $build_type of ptr"
done

echo -n "Upload to PyPI? (ctrl + c to cancel): "
read keep_going

for pkg_glob in "ptr*.whl" "ptr*.tar.gz"
do
  "$VENV_DIR/bin/twine" upload "dist/$pkg_glob"
done
