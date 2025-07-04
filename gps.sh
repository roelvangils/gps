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
    # Parse the date and time components using zsh parameter expansion
    # Format: YYYY:MM:DD HH:MM:SS
    YEAR=${DATE_TIME:0:4}
    MONTH_NUM=${DATE_TIME:5:2}
    DAY=${DATE_TIME:8:2}
    HOUR=${DATE_TIME:11:2}
    MINUTE=${DATE_TIME:14:2}
    
    # Remove leading zeros from day
    DAY=$((10#$DAY))
    
    # Convert month number to month name
    case $MONTH_NUM in
        01) MONTH="January";;
        02) MONTH="February";;
        03) MONTH="March";;
        04) MONTH="April";;
        05) MONTH="May";;
        06) MONTH="June";;
        07) MONTH="July";;
        08) MONTH="August";;
        09) MONTH="September";;
        10) MONTH="October";;
        11) MONTH="November";;
        12) MONTH="December";;
    esac
    
    # Calculate day of week using Zeller's congruence
    # This is a portable way to get day of week without relying on date command
    local m=$((10#$MONTH_NUM))
    local y=$((10#$YEAR))
    local d=$((10#$DAY))
    
    if (( m < 3 )); then
        m=$((m + 12))
        y=$((y - 1))
    fi
    
    local c=$((y / 100))
    local k=$((y % 100))
    local f=$(( (d + (13*(m+1))/5 + k + k/4 + c/4 - 2*c) % 7 ))
    
    case $f in
        0) DAY_OF_WEEK="Saturday";;
        1) DAY_OF_WEEK="Sunday";;
        2) DAY_OF_WEEK="Monday";;
        3) DAY_OF_WEEK="Tuesday";;
        4) DAY_OF_WEEK="Wednesday";;
        5) DAY_OF_WEEK="Thursday";;
        6) DAY_OF_WEEK="Friday";;
    esac
    
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