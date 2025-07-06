#!/usr/bin/env zsh

set -e # Exit immediately if a command exits with a non-zero status.
set -o pipefail # Exit status of a pipeline is the status of the last command to exit with a non-zero status.

# Helper function to format exposure time
format_exposure_time() {
    local exp_time=$1
    if [[ "$exp_time" == "null" || -z "$exp_time" ]]; then
        echo "Unknown"
        return
    fi
    
    # If exposure time is 1 second or more
    if (( $(echo "$exp_time >= 1" | bc -l) )); then
        echo "${exp_time}s"
    else
        # Convert to fraction
        local denominator=$(echo "scale=0; 1 / $exp_time" | bc -l)
        echo "1/${denominator}s"
    fi
}

# Helper function to decode flash value
decode_flash() {
    local flash_value=$1
    if [[ "$flash_value" == "null" || -z "$flash_value" ]]; then
        echo "Unknown"
        return
    fi
    
    # Convert to integer
    local flash_int=$((flash_value))
    if (( flash_int & 1 )); then
        echo "Flash fired"
    else
        echo "Flash did not fire"
    fi
}

# Default options - all disabled
INCLUDE_DATE=false
INCLUDE_WEATHER=false
INCLUDE_POI=false
INCLUDE_HOLIDAYS=false
INCLUDE_VENUES=false
INCLUDE_NEWS=false
INCLUDE_ELEVATION=false
INCLUDE_CONTEXT=false
OUTPUT_FORMAT="json"
INCLUDE_ALL=false

# Parse command line options
while [[ $# -gt 0 ]]; do
    case $1 in
        --date)
            INCLUDE_DATE=true
            shift
            ;;
        --weather)
            INCLUDE_WEATHER=true
            shift
            ;;
        --poi|--pois)
            INCLUDE_POI=true
            shift
            ;;
        --holidays)
            INCLUDE_HOLIDAYS=true
            shift
            ;;
        --venues)
            INCLUDE_VENUES=true
            shift
            ;;
        --news)
            INCLUDE_NEWS=true
            shift
            ;;
        --elevation)
            INCLUDE_ELEVATION=true
            shift
            ;;
        --context)
            INCLUDE_CONTEXT=true
            shift
            ;;
        --all)
            INCLUDE_ALL=true
            INCLUDE_DATE=true
            INCLUDE_WEATHER=true
            INCLUDE_POI=true
            INCLUDE_HOLIDAYS=true
            INCLUDE_VENUES=true
            INCLUDE_NEWS=true
            INCLUDE_ELEVATION=true
            INCLUDE_CONTEXT=true
            shift
            ;;
        --text)
            OUTPUT_FORMAT="text"
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS] <image_file>"
            echo ""
            echo "Options:"
            echo "  --date       Include date and time information"
            echo "  --weather    Include weather data (requires date)"
            echo "  --poi        Include nearby points of interest"
            echo "  --holidays   Include holiday information (requires date)"
            echo "  --venues     Include nearby restaurants and bars"
            echo "  --news       Include historical events (requires date)"
            echo "  --elevation  Include elevation data"
            echo "  --context    Include AI-friendly context summary"
            echo "  --all        Include all available information"
            echo "  --text       Output in human-readable text (default: JSON)"
            echo "  --help       Show this help message"
            echo ""
            echo "Default: JSON output with basic location data only"
            echo ""
            echo "Examples:"
            echo "  $0 photo.jpg                    # Basic location in JSON"
            echo "  $0 --date --weather photo.jpg   # Location + date + weather"
            echo "  $0 --all photo.jpg              # All available information"
            echo "  $0 --text --date photo.jpg      # Human-readable with date"
            exit 0
            ;;
        *)
            IMAGE_FILE="$1"
            shift
            ;;
    esac
done

# Check if a file was provided
if [[ -z "$IMAGE_FILE" ]]; then
    echo "Error: No image file provided"
    echo "Usage: $0 [OPTIONS] <image_file>"
    exit 1
fi


# Extract comprehensive EXIF data including GPS, date/time, and camera settings
EXIF_DATA=$(exiftool -j -n -gpslatitude -gpslongitude -DateTimeOriginal -Make -Model -LensModel -LensID -Software -ExposureTime -FNumber -ISO -FocalLength -Flash -ExposureMode -WhiteBalance -MeteringMode -ExposureProgram -ExposureCompensation -FocalLengthIn35mmFormat "$IMAGE_FILE")

# Check if EXIF data was extracted successfully
if [[ -z "$EXIF_DATA" || "$EXIF_DATA" == "null" ]]; then
    echo "Error: Could not extract EXIF data from $IMAGE_FILE" >&2
    exit 1
fi

# Parse EXIF data in one pass
read -r LAT LON DATE_TIME < <(echo "$EXIF_DATA" | jq -r '.[0] | "\(.GPSLatitude) \(.GPSLongitude) \(.DateTimeOriginal)"')

# Extract camera information
CAMERA_MAKE=$(echo "$EXIF_DATA" | jq -r '.[0].Make // "Unknown"')
CAMERA_MODEL=$(echo "$EXIF_DATA" | jq -r '.[0].Model // "Unknown"')
LENS_MODEL=$(echo "$EXIF_DATA" | jq -r '.[0].LensModel // .[0].LensID // "Unknown"')
SOFTWARE=$(echo "$EXIF_DATA" | jq -r '.[0].Software // "Unknown"')

# Extract exposure settings
EXPOSURE_TIME=$(echo "$EXIF_DATA" | jq -r '.[0].ExposureTime // null')
F_NUMBER=$(echo "$EXIF_DATA" | jq -r '.[0].FNumber // null')
ISO=$(echo "$EXIF_DATA" | jq -r '.[0].ISO // null')
FOCAL_LENGTH=$(echo "$EXIF_DATA" | jq -r '.[0].FocalLength // null')
FOCAL_LENGTH_35MM=$(echo "$EXIF_DATA" | jq -r '.[0].FocalLengthIn35mmFormat // null')
FLASH=$(echo "$EXIF_DATA" | jq -r '.[0].Flash // null')
EXPOSURE_MODE=$(echo "$EXIF_DATA" | jq -r '.[0].ExposureMode // "Unknown"')
WHITE_BALANCE=$(echo "$EXIF_DATA" | jq -r '.[0].WhiteBalance // "Unknown"')
METERING_MODE=$(echo "$EXIF_DATA" | jq -r '.[0].MeteringMode // "Unknown"')
EXPOSURE_PROGRAM=$(echo "$EXIF_DATA" | jq -r '.[0].ExposureProgram // "Unknown"')
EXPOSURE_COMPENSATION=$(echo "$EXIF_DATA" | jq -r '.[0].ExposureCompensation // null')

# Check if coordinates were found
if [[ "$LAT" == "null" || "$LON" == "null" ]]; then
    echo "Error: No GPS coordinates found in image" >&2
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
    SECOND=${DATE_TIME:17:2}
    
    # Remove leading zeros for display
    DAY=$((10#$DAY))
    HOUR_NUM=$((10#$HOUR))
    
    # Keep original values with leading zeros for API calls
    DAY_PADDED=${DATE_TIME:8:2}
    MONTH_PADDED=${DATE_TIME:5:2}
    
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
    if ((HOUR_NUM >= 5 && HOUR_NUM < 12)); then
        TIME_OF_DAY="morning"
        TIME_OF_DAY_TEXT="in the morning"
    elif ((HOUR_NUM >= 12 && HOUR_NUM < 18)); then
        TIME_OF_DAY="afternoon"
        TIME_OF_DAY_TEXT="in the afternoon"
    elif ((HOUR_NUM >= 18 && HOUR_NUM < 23)); then
        TIME_OF_DAY="evening"
        TIME_OF_DAY_TEXT="in the evening"
    else
        TIME_OF_DAY="night"
        TIME_OF_DAY_TEXT="at night"
    fi
    
    # Format ISO timestamp
    TIMESTAMP="${YEAR}-${MONTH_PADDED}-${DAY_PADDED}T${HOUR}:${MINUTE}:${SECOND}"
    HAS_DATETIME=true
else
    HAS_DATETIME=false
    TIMESTAMP="null"
    DAY_OF_WEEK="Unknown day"
    MONTH="Unknown month"
    DAY="Unknown date"
    YEAR="Unknown year"
    HOUR="Unknown hour"
    MINUTE="Unknown minute"
    TIME_OF_DAY="unknown"
    TIME_OF_DAY_TEXT="Unknown time"
fi

# Get location data from OpenStreetMap Nominatim API
LOCATION_DATA=$(curl -s "https://nominatim.openstreetmap.org/reverse?format=json&lat=$LAT&lon=$LON&zoom=18&addressdetails=1" \
    -H "User-Agent: LocationFinder/1.0" || echo '{}')

# Extract address components
HOUSE_NUMBER=$(echo "$LOCATION_DATA" | jq -r '.address.house_number // ""')
ROAD=$(echo "$LOCATION_DATA" | jq -r '.address.road // ""')
POSTAL_CODE=$(echo "$LOCATION_DATA" | jq -r '.address.postcode // ""')
CITY=$(echo "$LOCATION_DATA" | jq -r '.address.city // .address.city_district // .address.town // .address.village // ""')
COUNTRY=$(echo "$LOCATION_DATA" | jq -r '.address.country // ""')
COUNTRY_CODE=$(echo "$LOCATION_DATA" | jq -r '.address.country_code // ""' | tr '[:lower:]' '[:upper:]')
STATE=$(echo "$LOCATION_DATA" | jq -r '.address.state // ""')

# Set defaults for any empty values
ROAD=${ROAD:-"Unknown road"}
CITY=${CITY:-"Unknown city"}
COUNTRY=${COUNTRY:-"Unknown country"}

# Fix Belgium country name
if [[ "$COUNTRY" == *"Belg"* ]]; then
    COUNTRY="Belgium"
fi

# Format address
if [[ -n "$HOUSE_NUMBER" ]]; then
    STREET="$ROAD $HOUSE_NUMBER"
else
    STREET="$ROAD"
fi

# Format camera settings
FORMATTED_EXPOSURE_TIME=$(format_exposure_time "$EXPOSURE_TIME")
FORMATTED_FLASH=$(decode_flash "$FLASH")

# Format F-number
if [[ "$F_NUMBER" != "null" && -n "$F_NUMBER" ]]; then
    FORMATTED_F_NUMBER="f/${F_NUMBER}"
else
    FORMATTED_F_NUMBER="Unknown"
fi

# Format focal lengths
if [[ "$FOCAL_LENGTH" != "null" && -n "$FOCAL_LENGTH" ]]; then
    FORMATTED_FOCAL_LENGTH="${FOCAL_LENGTH}mm"
else
    FORMATTED_FOCAL_LENGTH="Unknown"
fi

if [[ "$FOCAL_LENGTH_35MM" != "null" && -n "$FOCAL_LENGTH_35MM" ]]; then
    FORMATTED_FOCAL_LENGTH_35MM="${FOCAL_LENGTH_35MM}mm"
else
    FORMATTED_FOCAL_LENGTH_35MM="Unknown"
fi

# Format exposure compensation
if [[ "$EXPOSURE_COMPENSATION" != "null" && -n "$EXPOSURE_COMPENSATION" ]]; then
    FORMATTED_EXPOSURE_COMP="${EXPOSURE_COMPENSATION} EV"
else
    FORMATTED_EXPOSURE_COMP="Unknown"
fi

# Initialize JSON output structure
JSON_OUTPUT='{}'

# Always include basic location data
JSON_OUTPUT=$(echo "$JSON_OUTPUT" | jq --arg lat "$LAT" --arg lon "$LON" --arg street "$STREET" --arg postal "$POSTAL_CODE" --arg city "$CITY" --arg country "$COUNTRY" --arg country_code "$COUNTRY_CODE" --arg state "$STATE" '.location = {
    "coordinates": {
        "lat": ($lat | tonumber),
        "lon": ($lon | tonumber)
    },
    "address": {
        "street": $street,
        "postal_code": $postal,
        "city": $city,
        "state": $state,
        "country": $country,
        "country_code": $country_code
    }
}')

# Add date/time information if requested
if [[ "$INCLUDE_DATE" == "true" && "$HAS_DATETIME" == "true" ]]; then
    JSON_OUTPUT=$(echo "$JSON_OUTPUT" | jq --arg ts "$TIMESTAMP" --arg dow "$DAY_OF_WEEK" --arg tod "$TIME_OF_DAY" --arg lt "${HOUR}:${MINUTE}" --argjson has_dt "$HAS_DATETIME" --arg year "$YEAR" --arg month "$MONTH" --arg day "$DAY" '.datetime = {
        "timestamp": $ts,
        "year": $year,
        "month": $month,
        "day": ($day | tonumber),
        "day_of_week": $dow,
        "time_of_day": $tod,
        "local_time": $lt,
        "has_datetime": $has_dt
    }')
fi

# Always add camera information
JSON_OUTPUT=$(echo "$JSON_OUTPUT" | jq --arg make "$CAMERA_MAKE" --arg model "$CAMERA_MODEL" --arg lens "$LENS_MODEL" --arg soft "$SOFTWARE" --arg exp_time "$FORMATTED_EXPOSURE_TIME" --arg f_num "$FORMATTED_F_NUMBER" --argjson iso "$ISO" --arg focal "$FORMATTED_FOCAL_LENGTH" --arg focal35 "$FORMATTED_FOCAL_LENGTH_35MM" --arg flash "$FORMATTED_FLASH" --arg exp_mode "$EXPOSURE_MODE" --arg wb "$WHITE_BALANCE" --arg meter "$METERING_MODE" --arg exp_prog "$EXPOSURE_PROGRAM" --arg exp_comp "$FORMATTED_EXPOSURE_COMP" '.camera = {
    "make": $make,
    "model": $model,
    "lens_model": $lens,
    "software": $soft
} | .exposure = {
    "shutter_speed": $exp_time,
    "aperture": $f_num,
    "iso": $iso,
    "focal_length": $focal,
    "focal_length_35mm": $focal35,
    "exposure_compensation": $exp_comp,
    "exposure_mode": $exp_mode,
    "exposure_program": $exp_prog,
    "metering_mode": $meter,
    "white_balance": $wb,
    "flash": $flash
}')
# Get elevation data if requested
if [[ "$INCLUDE_ELEVATION" == "true" ]]; then
    ELEVATION_DATA=$(curl -s "https://api.open-elevation.com/api/v1/lookup?locations=$LAT,$LON" || echo '{"results":[{"elevation":null}]}')
    ELEVATION=$(echo "$ELEVATION_DATA" | jq -r '.results[0].elevation // null')
    
    if [[ "$ELEVATION" != "null" ]]; then
        JSON_OUTPUT=$(echo "$JSON_OUTPUT" | jq --argjson elev "$ELEVATION" '.location.elevation_m = $elev')
    fi
fi
# Get weather data if requested
if [[ "$INCLUDE_WEATHER" == "true" && "$HAS_DATETIME" == "true" ]]; then
    # Get weather data from Open-Meteo (including UV index)
    WEATHER_DATA=$(curl -s "https://archive-api.open-meteo.com/v1/era5?latitude=$LAT&longitude=$LON&start_date=${YEAR}-${MONTH_PADDED}-${DAY_PADDED}&end_date=${YEAR}-${MONTH_PADDED}-${DAY_PADDED}&hourly=temperature_2m,precipitation,weathercode,cloudcover&daily=uv_index_max&timezone=auto" || echo '{}')
    
    # Extract weather for the specific hour
    if [[ -n "$WEATHER_DATA" && "$WEATHER_DATA" != "{}" ]]; then
        TEMP=$(echo "$WEATHER_DATA" | jq -r ".hourly.temperature_2m[$HOUR_NUM] // null")
        PRECIP=$(echo "$WEATHER_DATA" | jq -r ".hourly.precipitation[$HOUR_NUM] // null")
        WEATHER_CODE=$(echo "$WEATHER_DATA" | jq -r ".hourly.weathercode[$HOUR_NUM] // null")
        CLOUD_COVER=$(echo "$WEATHER_DATA" | jq -r ".hourly.cloudcover[$HOUR_NUM] // null")
        UV_INDEX=$(echo "$WEATHER_DATA" | jq -r '.daily.uv_index_max[0] // null')
        TIMEZONE=$(echo "$WEATHER_DATA" | jq -r '.timezone // "UTC"')
        
        # Decode weather code to description
        case $WEATHER_CODE in
            0) WEATHER_DESC="clear sky";;
            1|2) WEATHER_DESC="mainly clear";;
            3) WEATHER_DESC="overcast";;
            45|48) WEATHER_DESC="foggy";;
            51|53|55) WEATHER_DESC="drizzle";;
            61|63|65) WEATHER_DESC="rain";;
            71|73|75) WEATHER_DESC="snow";;
            80|81|82) WEATHER_DESC="rain showers";;
            95|96|99) WEATHER_DESC="thunderstorm";;
            *) WEATHER_DESC="unknown";;
        esac
    else
        TEMP="null"
        PRECIP="null"
        WEATHER_DESC="unknown"
        CLOUD_COVER="null"
        UV_INDEX="null"
        TIMEZONE="UTC"
    fi
    
    # Get sunrise/sunset from Open-Meteo
    SUNRISE_SUNSET_DATA=$(curl -s "https://api.open-meteo.com/v1/forecast?latitude=$LAT&longitude=$LON&daily=sunrise,sunset&start_date=${YEAR}-${MONTH_PADDED}-${DAY_PADDED}&end_date=${YEAR}-${MONTH_PADDED}-${DAY_PADDED}&timezone=auto" || echo '{}')
    
    if [[ -n "$SUNRISE_SUNSET_DATA" && "$SUNRISE_SUNSET_DATA" != "{}" ]]; then
        SUNRISE=$(echo "$SUNRISE_SUNSET_DATA" | jq -r '.daily.sunrise[0] // null')
        SUNSET=$(echo "$SUNRISE_SUNSET_DATA" | jq -r '.daily.sunset[0] // null')
        
        if [[ "$SUNRISE" != "null" && "$SUNSET" != "null" ]]; then
            # Extract hour from ISO timestamp
            SUNRISE_HOUR=$(echo "$SUNRISE" | cut -d'T' -f2 | cut -d':' -f1)
            SUNSET_HOUR=$(echo "$SUNSET" | cut -d'T' -f2 | cut -d':' -f1)
            SUNRISE_TIME="${SUNRISE_HOUR}:$(echo "$SUNRISE" | cut -d'T' -f2 | cut -d':' -f2)"
            SUNSET_TIME="${SUNSET_HOUR}:$(echo "$SUNSET" | cut -d'T' -f2 | cut -d':' -f2)"
        else
            SUNRISE_HOUR=6
            SUNSET_HOUR=18
            SUNRISE_TIME="06:00"
            SUNSET_TIME="18:00"
        fi
    else
        SUNRISE_HOUR=6
        SUNSET_HOUR=18
        SUNRISE_TIME="06:00"
        SUNSET_TIME="18:00"
    fi
    
    # Check if it's daylight
    if (( HOUR_NUM >= SUNRISE_HOUR && HOUR_NUM <= SUNSET_HOUR )); then
        IS_DAYLIGHT="true"
    else
        IS_DAYLIGHT="false"
    fi
    
    # Add weather data to JSON
    JSON_OUTPUT=$(echo "$JSON_OUTPUT" | jq --argjson temp "$TEMP" --arg desc "$WEATHER_DESC" --argjson precip "$PRECIP" --argjson cloud "$CLOUD_COVER" --argjson uv "$UV_INDEX" --arg sunrise "$SUNRISE_TIME" --arg sunset "$SUNSET_TIME" --arg daylight "$IS_DAYLIGHT" --arg tz "$TIMEZONE" '
        .weather = {
            "temperature_c": $temp,
            "description": $desc,
            "precipitation_mm": $precip,
            "cloud_cover_percent": $cloud,
            "uv_index": $uv,
            "sunrise": $sunrise,
            "sunset": $sunset,
            "is_daylight": ($daylight == "true"),
            "timezone": $tz
        }
    ')
fi
# Get nearby POIs if requested
if [[ "$INCLUDE_POI" == "true" ]]; then
    OVERPASS_QUERY="[out:json][timeout:10];(node[\"tourism\"](around:1000,$LAT,$LON);node[\"historic\"](around:1000,$LAT,$LON);node[\"amenity\"~\"^(museum|theatre|library|place_of_worship|university|college|school|hospital|town_hall|cinema|community_centre)$\"](around:1000,$LAT,$LON);way[\"tourism\"](around:1000,$LAT,$LON);way[\"historic\"](around:1000,$LAT,$LON););out body;>;out skel qt;"
    
    POI_DATA=$(curl -s "https://overpass-api.de/api/interpreter" \
        -H "User-Agent: LocationFinder/1.0" \
        --data-urlencode "data=$OVERPASS_QUERY" || echo '{"elements":[]}')
    
    # Process POIs
    POIS=$(echo "$POI_DATA" | jq '
        .elements 
        | map(select(.tags.name != null and .lat != null and .lon != null))
        | map({
            name: .tags.name,
            type: (
                if .tags.tourism then .tags.tourism
                elif .tags.historic then "historic"
                elif .tags.amenity then .tags.amenity
                else "unknown"
                end
            ),
            lat: .lat,
            lon: .lon,
            description: (.tags.description // null),
            website: (.tags.website // null)
        })
        | map(. + {
            distance_m: (((.lat - '$LAT') * 111320) * ((.lat - '$LAT') * 111320) + 
                        ((.lon - '$LON') * 111320 * '$LAT' / 90) * ((.lon - '$LON') * 111320 * '$LAT' / 90))
                        | sqrt | floor
        })
        | sort_by(.distance_m)
        | .[0:5]
    ')
    
    # Add POIs to JSON
    JSON_OUTPUT=$(echo "$JSON_OUTPUT" | jq --argjson pois "$POIS" '.nearby_pois = $pois')
fi
# Get holidays if requested
if [[ "$INCLUDE_HOLIDAYS" == "true" && "$HAS_DATETIME" == "true" && -n "$COUNTRY_CODE" && "$COUNTRY_CODE" != "" ]]; then
    
    HOLIDAYS_DATA=$(curl -s "https://date.nager.at/api/v3/publicholidays/${YEAR}/${COUNTRY_CODE}" || echo '[]')
    
    # Check if the date matches any holiday
    HOLIDAYS=$(echo "$HOLIDAYS_DATA" | jq -r --arg date "${YEAR}-${MONTH_PADDED}-${DAY_PADDED}" '
        map(select(.date == $date)) |
        map({
            name: .name,
            localName: .localName,
            type: (if .global then "national" else "regional" end),
            counties: .counties
        })
    ')
    
    # Check for nearby holidays (within 7 days)
    NEARBY_HOLIDAYS=$(echo "$HOLIDAYS_DATA" | jq -r --arg date "${YEAR}-${MONTH_PADDED}-${DAY_PADDED}" '
        map(select(
            (.date | split("-") | .[0:2] | join("-")) == ($date | split("-") | .[0:2] | join("-"))
        )) |
        map(select(.date != $date)) |
        map({
            name: .name,
            date: .date,
            days_away: ((.date | split("-") | .[2] | tonumber) - ($date | split("-") | .[2] | tonumber))
        }) |
        map(select(.days_away >= -7 and .days_away <= 7)) |
        sort_by(.days_away | if . < 0 then (. * -1) + 100 else . end) |
        .[0:3]
    ')
    
    # Add holidays to JSON
    JSON_OUTPUT=$(echo "$JSON_OUTPUT" | jq --argjson holidays "$HOLIDAYS" --argjson nearby "$NEARBY_HOLIDAYS" '
        .holidays = {
            "on_date": $holidays,
            "nearby": $nearby
        }
    ')
fi

# Get venues (restaurants and bars) if requested
if [[ "$INCLUDE_VENUES" == "true" ]]; then
    DINING_QUERY="[out:json][timeout:10];(node[\"amenity\"~\"^(restaurant|bar|pub|cafe)$\"](around:300,$LAT,$LON););out body;>;out skel qt;"
    
    DINING_DATA=$(curl -s "https://overpass-api.de/api/interpreter" \
        -H "User-Agent: LocationFinder/1.0" \
        --data-urlencode "data=$DINING_QUERY" || echo '{"elements":[]}')
    
    # Process restaurants and bars
    VENUES='{"restaurants": [], "bars": []}'
    if [[ -n "$DINING_DATA" && "$DINING_DATA" != '{"elements":[]}' ]]; then
        RESTAURANTS=$(echo "$DINING_DATA" | jq '
            .elements 
            | map(select(.tags.name and .tags.amenity == "restaurant" and .lat and .lon))
            | map({
                name: .tags.name,
                cuisine: (.tags.cuisine // null),
                distance_m: (((.lat - '$LAT') * 111320) * ((.lat - '$LAT') * 111320) + 
                            ((.lon - '$LON') * 111320 * '$LAT' / 90) * ((.lon - '$LON') * 111320 * '$LAT' / 90))
                            | sqrt | floor
            })
            | sort_by(.distance_m)
            | .[0:2]
        ')
        
        BARS=$(echo "$DINING_DATA" | jq '
            .elements 
            | map(select(.tags.name and (.tags.amenity == "bar" or .tags.amenity == "pub") and .lat and .lon))
            | map({
                name: .tags.name,
                distance_m: (((.lat - '$LAT') * 111320) * ((.lat - '$LAT') * 111320) + 
                            ((.lon - '$LON') * 111320 * '$LAT' / 90) * ((.lon - '$LON') * 111320 * '$LAT' / 90))
                            | sqrt | floor
            })
            | sort_by(.distance_m)
            | .[0:2]
        ')
        
        VENUES=$(jq -n --argjson restaurants "$RESTAURANTS" --argjson bars "$BARS" '{restaurants: $restaurants, bars: $bars}')
    fi
    
    # Add venues to JSON
    JSON_OUTPUT=$(echo "$JSON_OUTPUT" | jq --argjson venues "$VENUES" '.nearby_venues = $venues')
fi

# Get news events if requested
if [[ "$INCLUDE_NEWS" == "true" && "$HAS_DATETIME" == "true" ]]; then
    # For historical news, we'll use Wikipedia's "On this day" API
    WIKI_DATE="${MONTH_NUM}/${DAY_PADDED}"
    WIKI_DATA=$(curl -s "https://en.wikipedia.org/api/rest_v1/feed/onthisday/events/${WIKI_DATE}" -H "Accept: application/json" 2>/dev/null || echo '{}')
    
    if [[ -n "$WIKI_DATA" && "$WIKI_DATA" != "{}" ]]; then
        # Get the most notable event with proper escaping
        # More aggressive cleaning of control characters and HTML entities
        MAIN_EVENT=$(echo "$WIKI_DATA" | jq -c '
            .events[0] // null | 
            if . then {
                text: (.text | gsub("[\n\r\t]"; " ") | gsub("[\u0000-\u001f]"; "") | gsub("&[a-zA-Z0-9#]+;"; "")),
                year: .year
            } else null end
        ' 2>/dev/null || echo "null")
        
        if [[ "$MAIN_EVENT" != "null" && -n "$MAIN_EVENT" ]]; then
            NEWS_EVENTS=$(jq -n --argjson main "$MAIN_EVENT" '{"main_event": $main, "headlines": []}' 2>/dev/null || echo '{"main_event": null, "headlines": []}')
        else
            NEWS_EVENTS='{"main_event": null, "headlines": []}'
        fi
        
        # Add news to JSON
        JSON_OUTPUT=$(echo "$JSON_OUTPUT" | jq --argjson news "$NEWS_EVENTS" '.news_events = $news' 2>/dev/null || echo "$JSON_OUTPUT")
    else
        # No Wikipedia data available
        NEWS_EVENTS='{"main_event": null, "headlines": []}'
        JSON_OUTPUT=$(echo "$JSON_OUTPUT" | jq --argjson news "$NEWS_EVENTS" '.news_events = $news')
    fi
fi

# Generate AI context if requested
if [[ "$INCLUDE_CONTEXT" == "true" ]]; then
    AI_CONTEXT="Photo taken"
    
    if [[ "$INCLUDE_DATE" == "true" && "$HAS_DATETIME" == "true" ]]; then
        AI_CONTEXT="$AI_CONTEXT on $DAY_OF_WEEK, $MONTH $DAY, $YEAR at ${HOUR}:${MINUTE} ($TIME_OF_DAY)"
    fi
    
    AI_CONTEXT="$AI_CONTEXT in $CITY, $COUNTRY"
    
    if [[ "$INCLUDE_ELEVATION" == "true" && "$ELEVATION" != "null" ]]; then
        AI_CONTEXT="$AI_CONTEXT at ${ELEVATION}m elevation"
    fi
    
    if [[ "$INCLUDE_WEATHER" == "true" && "$WEATHER_DESC" != "unknown" && "$WEATHER_DESC" != "null" ]]; then
        AI_CONTEXT="$AI_CONTEXT with $WEATHER_DESC"
        if [[ "$TEMP" != "null" ]]; then
            AI_CONTEXT="$AI_CONTEXT (${TEMP}°C)"
        fi
    fi
    
    if [[ "$INCLUDE_POI" == "true" && -n "$POIS" ]]; then
        POI_COUNT=$(echo "$POIS" | jq 'length')
        if [[ $POI_COUNT -gt 0 ]]; then
            FIRST_POI=$(echo "$POIS" | jq -r '.[0].name')
            FIRST_POI_DIST=$(echo "$POIS" | jq -r '.[0].distance_m')
            AI_CONTEXT="$AI_CONTEXT. Location is ${FIRST_POI_DIST}m from $FIRST_POI"
        fi
    fi
    
    AI_CONTEXT="${AI_CONTEXT}."
    
    # Escape AI context for JSON
    AI_CONTEXT_ESCAPED=$(echo "$AI_CONTEXT" | sed 's/\\/\\\\/g; s/"/\\"/g; s/\t/ /g; s/\n/ /g; s/\r//g')
    
    # Add context to JSON
    JSON_OUTPUT=$(echo "$JSON_OUTPUT" | jq --arg context "$AI_CONTEXT_ESCAPED" '.ai_context = $context')
fi

# Output the result
if [[ "$OUTPUT_FORMAT" == "text" ]]; then
    # Generate human-readable text output
    if [[ "$INCLUDE_DATE" == "true" && "$HAS_DATETIME" == "true" ]]; then
        echo "This photo was taken on $DAY_OF_WEEK, $MONTH $DAY, $YEAR at $HOUR:$MINUTE ($TIME_OF_DAY_TEXT) at this address: $STREET in $POSTAL_CODE $CITY ($COUNTRY)."
    else
        echo "This photo was taken at this address: $STREET in $POSTAL_CODE $CITY ($COUNTRY)."
    fi
    
    if [[ "$INCLUDE_WEATHER" == "true" && "$WEATHER_DESC" != "unknown" ]]; then
        echo "Weather: $WEATHER_DESC, ${TEMP}°C"
    fi
    
    if [[ "$INCLUDE_POI" == "true" && -n "$POIS" ]]; then
        POI_COUNT=$(echo "$POIS" | jq 'length')
        if [[ $POI_COUNT -gt 0 ]]; then
            echo "Nearby points of interest:"
            echo "$POIS" | jq -r '.[] | "  - \(.name) (\(.type)): \(.distance_m)m"'
        fi
    fi
else
    # Output JSON
    echo "$JSON_OUTPUT" | jq -c '.'
fi
