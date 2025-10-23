#!/bin/bash
# Verification script for mock-media-service setup

echo "=========================================="
echo "Mock Media Service - Setup Verification"
echo "=========================================="
echo ""

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to check and report
check_item() {
  if [ $1 -eq 0 ]; then
    echo -e "${GREEN}✓${NC} $2"
  else
    echo -e "${RED}✗${NC} $2"
  fi
}

# 1. Check .env file exists
echo "1. Checking .env configuration..."
if [ -f "apps/mock-media-service/.env" ]; then
  check_item 0 ".env file exists"
  echo "   Configuration:"
  grep -v '^#' apps/mock-media-service/.env | grep -v '^$' | sed 's/^/     /'
else
  check_item 1 ".env file missing"
  echo -e "   ${YELLOW}Run: cat > apps/mock-media-service/.env << 'EOF'...${NC}"
fi
echo ""

# 2. Check stream-1 directory exists
echo "2. Checking audio fragments directory..."
if [ -d "apps/mock-media-service/src/assets/audio-fragments/stream-1" ]; then
  check_item 0 "stream-1 directory exists"
else
  check_item 1 "stream-1 directory missing"
  echo -e "   ${YELLOW}Run: mkdir -p apps/mock-media-service/src/assets/audio-fragments/stream-1${NC}"
fi
echo ""

# 3. Check fragment files exist
echo "3. Checking fragment files..."
FRAGMENT_COUNT=$(ls apps/mock-media-service/src/assets/audio-fragments/stream-1/*.m4s 2>/dev/null | wc -l | tr -d ' ')
if [ "$FRAGMENT_COUNT" -gt 0 ]; then
  check_item 0 "Found $FRAGMENT_COUNT m4s fragment files"
  echo "   Files:"
  ls -lh apps/mock-media-service/src/assets/audio-fragments/stream-1/*.m4s | awk '{print "     " $9, "(" $5 ")"}'
else
  check_item 1 "No m4s files found"
  echo -e "   ${YELLOW}Add m4s files to: apps/mock-media-service/src/assets/audio-fragments/stream-1/${NC}"
fi
echo ""

# 4. Check file naming convention
echo "4. Verifying file naming convention..."
EXPECTED_FILES=("fragment-0.m4s" "fragment-1.m4s" "fragment-2.m4s" "fragment-3.m4s")
ALL_NAMED_CORRECTLY=true
for file in "${EXPECTED_FILES[@]}"; do
  if [ -f "apps/mock-media-service/src/assets/audio-fragments/stream-1/$file" ]; then
    check_item 0 "$file present"
  else
    check_item 1 "$file missing"
    ALL_NAMED_CORRECTLY=false
  fi
done
echo ""

# 5. Check dependencies
echo "5. Checking dependencies..."
if npm list socket.io &>/dev/null; then
  check_item 0 "socket.io installed"
else
  check_item 1 "socket.io missing"
  echo -e "   ${YELLOW}Run: npm install${NC}"
fi

if npm list socket.io-client &>/dev/null; then
  check_item 0 "socket.io-client installed"
else
  check_item 1 "socket.io-client missing"
  echo -e "   ${YELLOW}Run: npm install socket.io-client --save-dev${NC}"
fi
echo ""

# 6. Check if server is running
echo "6. Checking if server is running..."
if curl -s http://localhost:4000/ > /dev/null 2>&1; then
  check_item 0 "Server is running on port 4000"
  echo "   Available streams:"
  curl -s http://localhost:4000/streams | grep -o '"streams":\[[^]]*\]' | sed 's/^/     /'
else
  check_item 1 "Server is not running"
  echo -e "   ${YELLOW}To start: npx nx serve mock-media-service${NC}"
fi
echo ""

# 7. Summary
echo "=========================================="
echo "Summary"
echo "=========================================="

if [ -f "apps/mock-media-service/.env" ] && \
   [ -d "apps/mock-media-service/src/assets/audio-fragments/stream-1" ] && \
   [ "$FRAGMENT_COUNT" -ge 4 ] && \
   [ "$ALL_NAMED_CORRECTLY" = true ]; then
  echo -e "${GREEN}✓ Setup is complete!${NC}"
  echo ""
  echo "Next steps:"
  echo "  1. Start the server:"
  echo "     npx nx serve mock-media-service"
  echo ""
  echo "  2. Test with the example client:"
  echo "     node apps/mock-media-service/example-client.js"
  echo ""
  echo "  3. Or use the detailed test subscriber:"
  echo "     node apps/mock-media-service/test-subscriber.js"
else
  echo -e "${YELLOW}⚠ Setup incomplete${NC}"
  echo ""
  echo "Please address the issues marked with ✗ above."
  echo "See SETUP.md for detailed instructions."
fi
echo ""

