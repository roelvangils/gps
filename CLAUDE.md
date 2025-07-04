# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a simple shell script utility that extracts GPS coordinates from image EXIF data and performs reverse geocoding to provide human-readable location information.

## Dependencies

The script requires the following tools to be installed:
- `exiftool` - For extracting EXIF metadata from images
- `jq` - For JSON parsing
- `curl` - For making API requests
- `zsh` - Z shell (script interpreter)

## Running the Script

```bash
# Make the script executable (if not already)
chmod +x gps.sh

# Run the script with an image file
./gps.sh <image_file>
```

## Architecture

This is a single-file utility (`gps.sh`) that:
1. Extracts GPS coordinates and datetime from image EXIF data using `exiftool`
2. Parses the JSON output with `jq`
3. Formats date/time into human-readable format (e.g., "Friday, December 15, 2023 at 14:30 (in the afternoon)")
4. Makes a reverse geocoding API call to OpenStreetMap Nominatim
5. Outputs formatted location information

## Platform Notes

- The script uses macOS-specific `date` command syntax (with `-j` flag)
- For cross-platform compatibility, the date parsing logic would need modification

## API Usage

The script uses the OpenStreetMap Nominatim API for reverse geocoding. This is a free service but has usage limits and requires a proper User-Agent header (which the script provides).

## Error Handling

The script exits silently with code 1 if:
- No file argument is provided
- No GPS coordinates are found in the image

## Output Format

The script outputs location information in one of two formats:
- With date/time: "This photo was taken on [day], [month] [date], [year] at [time] ([time of day]) at this address: [address] in [postal code] [city] ([country])."
- Without date/time: "This photo was taken at this address: [address] in [postal code] [city] ([country]). Data and time are unknown."