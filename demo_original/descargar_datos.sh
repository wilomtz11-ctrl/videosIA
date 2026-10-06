#!/usr/bin/env bash
# Descarga las fronteras históricas (GeoJSON) que usa el video.
set -e
for y in 1800 1815 1880 1914 2010; do
  curl -sSL -o "world_$y.geojson" \
    "https://raw.githubusercontent.com/aourednik/historical-basemaps/master/geojson/world_$y.geojson"
  echo "descargado world_$y.geojson"
done
