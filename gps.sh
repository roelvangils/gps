#!/usr/bin/env zsh

set -e # Exit immediately if a command exits with a non-zero status.
set -o pipefail # Exit status of a pipeline is the status of the last command to exit with a non-zero status.

# Check if a file was provided
if [ $# -eq 0 ]; then
    echo "Usage: $0 <image_file>"
    exit 1
fi

IMAGE_FILE="$1"

# Extract GPS coordinates and date/time using exiftool
EXIF_DATA=$(exiftool -j -n -gpslatitude -gpslongitude -DateTimeOriginal "$IMAGE_FILE")

# Check if EXIF data was extracted successfully
if [[ -z "$EXIF_DATA" || "$EXIF_DATA" == "null" ]]; then
    echo "Error: Could not extract EXIF data from $IMAGE_FILE" >&2
    exit 1
fi

# Parse EXIF data in one pass
read -r LAT LON DATE_TIME < <(echo "$EXIF_DATA" | jq -r '.[0] | "\(.GPSLatitude) \(.GPSLongitude) \(.DateTimeOriginal)"')

# Check if coordinates were found
if [[ "$LAT" == "null" || "$LON" == "null" ]]; then
    exit 1
fi

# Format date and time
if [[ "$DATE_TIME" != "null" ]]; then
    zmodload zsh/datetime
    # Parse the exif date format 'YYYY:MM:DD HH:MM:SS'
    strptime -r "%Y:%m:%d %H:%M:%S" "$DATE_TIME" epoch_time
    
    # Format all date/time parts in one go
    strftime "%A %B %-d %Y %H %M" "$epoch_time" | read -r DAY_OF_WEEK MONTH DAY YEAR HOUR MINUTE
    
    # Determine time of day
    if ((HOUR >= 5 && HOUR < 12)); then
        TIME_OF_DAY="in the morning"
    elif ((HOUR >= 12 && HOUR < 18)); then
        TIME_OF_DAY="in the afternoon"
    elif ((HOUR >= 18 && HOUR < 23)); then
        TIME_OF_DAY="in the evening"
    else # Covers 23:00-23:59 and 00:00-04:59
        TIME_OF_DAY="at night"
    fi
else
    DAY_OF_WEEK="Unknown day"
    MONTH="Unknown month"
    DAY="Unknown date"
    YEAR="Unknown year"
    HOUR="Unknown hour"
    MINUTE="Unknown minute"
    TIME_OF_DAY="Unknown time"
fi

# Get location data from OpenStreetMap Nominatim API
LOCATION_DATA=$(curl -s "https://nominatim.openstreetmap.org/reverse?format=json&lat=$LAT&lon=$LON&zoom=18&addressdetails=1" \
    -H "User-Agent: LocationFinder/1.0")

# Extract address components in one pass, using tabs as a separator
IFS=$'\t' read -r HOUSE_NUMBER ROAD POSTAL_CODE CITY COUNTRY < <(echo "$LOCATION_DATA" | jq -r '
    .address |
    [
        .house_number,
        .road,
        .postcode,
        (.city // .town // .village),
        .country
    ] | @tsv
')

# Set defaults for any empty values after parsing
ROAD=${ROAD:-"Unknown road"}
CITY=${CITY:-"Unknown city"}
COUNTRY=${COUNTRY:-"Unknown country"}

# Replace Belgium with multiple languages in the name
# NOTE: This is a brittle fix for a specific API output format.
if [[ "$COUNTRY" == *"Belg"* ]]; then
    COUNTRY="Belgium"
fi

# Format address component for output
if [[ -n "$HOUSE_NUMBER" ]]; then
    ADDRESS="$ROAD $HOUSE_NUMBER"
else
    ADDRESS="$ROAD"
fi

# Format final output
if [[ "$DAY_OF_WEEK" == "Unknown day" ]]; then
    echo "This photo was taken at this address: \"$ADDRESS\" in \"$POSTAL_CODE $CITY\" ($COUNTRY). Data and time are unknown."
else
    echo "This photo was taken on $DAY_OF_WEEK, $MONTH $DAY, $YEAR at $HOUR:$MINUTE ($TIME_OF_DAY) at this address: \"$ADDRESS\" in \"$POSTAL_CODE $CITY\" ($COUNTRY)."
fi