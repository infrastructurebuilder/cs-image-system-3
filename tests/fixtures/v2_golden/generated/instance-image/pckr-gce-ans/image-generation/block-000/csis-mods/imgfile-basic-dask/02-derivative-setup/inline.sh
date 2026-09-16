#!/bin/sh
set -eu
echo 'derivative setup'
sudo mkdir -p /opt/derivative && echo 1.0.0 | sudo tee /opt/derivative/VERSION
