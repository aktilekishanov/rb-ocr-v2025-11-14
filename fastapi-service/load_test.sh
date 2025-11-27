#!/bin/bash
# Simple bash load testing script using curl
# Sends all files in parallel using background processes

# Configuration
DIR="${1:-sample-docs}"
URL="${2:-http://localhost:8001/v1/verify}"
FIO="${3:-Иванов Иван Иванович}"

echo "========================================================================"
echo "🚀 LOAD TEST (Bash version)"
echo "========================================================================"
echo "Directory:  $DIR"
echo "URL:        $URL"
echo "FIO:        $FIO"
echo "========================================================================"

if [ ! -d "$DIR" ]; then
    echo "❌ Directory not found: $DIR"
    echo "💡 Create it with: mkdir -p $DIR"
    exit 1
fi

# Count files
FILE_COUNT=$(find "$DIR" -type f \( -iname "*.pdf" -o -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.png" \) | wc -l)

if [ "$FILE_COUNT" -eq 0 ]; then
    echo "❌ No PDF/image files found in $DIR"
    exit 1
fi

echo "Files found: $FILE_COUNT"
echo ""

# Create temp directory for results
TEMP_DIR=$(mktemp -d)
echo "Temp results: $TEMP_DIR"
echo ""

# Counter
REQUEST_NUM=0

# Start time
START_TIME=$(date +%s)

# Send all requests in parallel
while IFS= read -r FILE; do
    REQUEST_NUM=$((REQUEST_NUM + 1))
    FILENAME=$(basename "$FILE")
    
    echo "📤 Request $REQUEST_NUM: Sending $FILENAME..."
    
    # Send request in background
    (
        REQ_START=$(date +%s.%N)
        RESPONSE=$(curl -s -w "\n%{http_code}\n%{time_total}" \
            -X POST "$URL" \
            -F "file=@$FILE" \
            -F "fio=$FIO" \
            2>&1)
        
        HTTP_CODE=$(echo "$RESPONSE" | tail -2 | head -1)
        TIME_TOTAL=$(echo "$RESPONSE" | tail -1)
        BODY=$(echo "$RESPONSE" | head -n -2)
        
        if [ "$HTTP_CODE" -eq 200 ]; then
            VERDICT=$(echo "$BODY" | grep -o '"verdict":[^,}]*' | cut -d':' -f2)
            echo "✅ Request $REQUEST_NUM: Success! Verdict=$VERDICT Time=${TIME_TOTAL}s" | tee "$TEMP_DIR/$REQUEST_NUM.log"
        else
            echo "❌ Request $REQUEST_NUM: Failed! Status=$HTTP_CODE Time=${TIME_TOTAL}s" | tee "$TEMP_DIR/$REQUEST_NUM.log"
        fi
        
        echo "$HTTP_CODE|$TIME_TOTAL|$FILENAME" > "$TEMP_DIR/$REQUEST_NUM.result"
    ) &
    
done < <(find "$DIR" -type f \( -iname "*.pdf" -o -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.png" \))

echo ""
echo "⏱️  All $REQUEST_NUM requests launched, waiting for completion..."
echo ""

# Wait for all background jobs
wait

# Calculate summary
END_TIME=$(date +%s)
TOTAL_TIME=$((END_TIME - START_TIME))

SUCCESSFUL=0
FAILED=0
TOTAL_RESPONSE_TIME=0

for RESULT_FILE in "$TEMP_DIR"/*.result; do
    if [ -f "$RESULT_FILE" ]; then
        HTTP_CODE=$(cut -d'|' -f1 "$RESULT_FILE")
        RESP_TIME=$(cut -d'|' -f2 "$RESULT_FILE")
        
        if [ "$HTTP_CODE" -eq 200 ]; then
            SUCCESSFUL=$((SUCCESSFUL + 1))
            TOTAL_RESPONSE_TIME=$(echo "$TOTAL_RESPONSE_TIME + $RESP_TIME" | bc)
        else
            FAILED=$((FAILED + 1))
        fi
    fi
done

echo ""
echo "========================================================================"
echo "📊 LOAD TEST SUMMARY"
echo "========================================================================"
echo "Total requests:   $REQUEST_NUM"
echo "Total time:       ${TOTAL_TIME}s"
echo "✅ Successful:     $SUCCESSFUL"
echo "❌ Failed:         $FAILED"

if [ "$SUCCESSFUL" -gt 0 ]; then
    AVG_TIME=$(echo "scale=2; $TOTAL_RESPONSE_TIME / $SUCCESSFUL" | bc)
    echo ""
    echo "⏱️  Average response time: ${AVG_TIME}s"
fi

echo "========================================================================"

# Cleanup
rm -rf "$TEMP_DIR"

echo ""
echo "✅ Load test complete!"
