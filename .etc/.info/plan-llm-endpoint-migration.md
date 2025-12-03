# LLM Endpoint Migration Plan

## Overview

This document outlines the step-by-step plan to migrate from the current LLM endpoint to the new ForteBank payment LLM endpoint with a different response format.

### Current State
- **Endpoint**: `https://dl-ai-dev-app01-uv01.fortebank.com/openai/v1/completions/v2`
- **Response Format**: Custom format with potential variations in structure

### Target State
- **Endpoint**: `https://dl-ai-dev-app01-uv01.fortebank.com/openai/payment/out/completions`
- **Response Format**: Standard OpenAI-compatible format with `choices[0].message.content`

---

## Key Differences

### Request Format
Both endpoints use the **same request format** (no changes needed):
```json
{
    "Model": "gpt-4o",
    "Content": "prompt text",
    "Temperature": 0.1,
    "MaxTokens": 100
}
```

### Response Format Changes

**Old Endpoint** (`/openai/v1/completions/v2`):
- Response structure varies
- May have `choices[0].text`, `choices[0].message.content`, or direct `content` field
- Current code has fallback logic to handle multiple formats

**New Endpoint** (`/openai/payment/out/completions`):
- **Standardized OpenAI format**
- Always returns: `choices[0].message.content`
- Consistent structure with metadata (`usage`, `model`, `created`, etc.)

---

## Implementation Steps

### Step 1: Update LLM Client URL
**File**: [`llm_client.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/clients/llm_client.py)

**Changes**:
- Update line 17 to use the new endpoint URL
- Change from: `https://dl-ai-dev-app01-uv01.fortebank.com/openai/v1/completions/v2`
- Change to: `https://dl-ai-dev-app01-uv01.fortebank.com/openai/payment/out/completions`

**Impact**: Single line change in `call_fortebank_llm()` function

---

### Step 2: Keep Raw Response in `ask_llm()` ✨ **RECOMMENDED APPROACH**
**File**: [`llm_client.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/clients/llm_client.py)

**Current Logic** (lines 40-64):
The `ask_llm()` function has complex fallback logic trying to extract content from various response formats.

**New Logic** (Simplified - Better Architecture):
**Return the raw JSON response as-is** and let [`filter_llm_generic_response.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/processors/filter_llm_generic_response.py) handle extraction.

```python
def ask_llm(
    prompt: str, model: str = "gpt-4o", temperature: float = 0, max_tokens: int = 500
) -> str:
    """
    Calls the ForteBank LLM endpoint and returns the raw JSON response.
    
    The raw response is later processed by filter_llm_generic_response() 
    to extract the actual content from the provider-specific envelope.
    """
    return call_fortebank_llm(prompt, model=model, temperature=temperature, max_tokens=max_tokens)
```

**Benefits**:
- ✅ **Separation of concerns**: Client just calls API, filter handles parsing
- ✅ **Single source of truth**: All response parsing logic in one place ([`filter_llm_generic_response.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/processors/filter_llm_generic_response.py))
- ✅ **Easier to maintain**: Changes to response format only affect the filter
- ✅ **Better debugging**: Can inspect full raw responses in intermediate files
- ✅ **Already implemented**: Your existing filter already handles OpenAI format!

---

### Step 3: Verify Filter Handles New Response Format
**File**: [`filter_llm_generic_response.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/processors/filter_llm_generic_response.py)

**Good News**: Your existing filter **already handles** the new endpoint format! ✅

**Current Filter Logic** (lines 23-46):
The `_extract_from_openai_like()` function already:
1. ✅ Checks for `choices[0].message.content` (lines 28-34)
2. ✅ Fallback to `choices[0].text` (lines 35-39)
3. ✅ Fallback to root-level `content` (lines 41-45)
4. ✅ Parses inner JSON from string content

**What the Filter Does**:
```python
# New endpoint response:
{
  "choices": [{
    "message": {
      "content": "{\"document_type\": \"ID\", ...}"  # ← Filter extracts this
    }
  }]
}

# Filter output (parsed inner JSON):
{
  "document_type": "ID",
  ...
}
```

**Action Required**: 
- **None!** The filter already handles this format correctly.
- **Optional**: Add logging to track which extraction path was used (for debugging)

**Note**: Lines 88-90 skip prompt-echo dicts with `Model` and `Content` keys - this is correct behavior to avoid processing the request echo.


---

### Step 4: Update Error Handling
**File**: [`llm_client.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/clients/llm_client.py)

**Changes**:
- Add specific exception handling for:
  - Network errors (connection timeout, SSL issues)
  - HTTP errors (4xx, 5xx responses)
  - JSON parsing errors
  - Unexpected response structure
- Consider adding retry logic for transient failures
- Log detailed error information for debugging

---

### Step 5: Add Configuration Management (Optional but Recommended)
**File**: [`config.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/core/config.py)

**Enhancement**:
Move the LLM endpoint URL to configuration:
- Add `LLM_ENDPOINT_URL` environment variable
- Default value: `https://dl-ai-dev-app01-uv01.fortebank.com/openai/payment/out/completions`
- Benefits:
  - Easy switching between endpoints without code changes
  - Different URLs for dev/staging/prod environments
  - Better separation of concerns

---

### Step 6: Update Documentation
**Files to Update**:
1. [`llm_client.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/clients/llm_client.py) - Update docstrings
2. [`servers.md`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/.etc/.info-project-management/servers.md) - Mark old endpoint as deprecated
3. Any README files that reference the LLM integration

**Documentation Updates**:
- Document the new endpoint URL
- Document the expected response format
- Add example request/response
- Note the migration date

---

## Testing Strategy

### Step 7: Unit Testing
**Create/Update**: Test file for `llm_client.py`

**Test Cases**:
1. **Successful response parsing**
   - Mock the new endpoint response
   - Verify correct content extraction from `choices[0].message.content`

2. **Error handling**
   - Test network errors
   - Test malformed JSON responses
   - Test missing fields in response

3. **Edge cases**
   - Empty content
   - Very long responses
   - Special characters in content

---

### Step 8: Integration Testing
**Test with Real Endpoint**:

1. **Manual API test** (using curl or Postman):
   ```bash
   curl -X POST https://dl-ai-dev-app01-uv01.fortebank.com/openai/payment/out/completions \
     -H "Content-Type: application/json" \
     -d '{
       "Model": "gpt-4o",
       "Content": "test prompt",
       "Temperature": 0.1,
       "MaxTokens": 100
     }' \
     --insecure
   ```

2. **Test document type checker**:
   - Run `check_single_doc_type()` with sample OCR data
   - Verify LLM response is correctly parsed
   - Check that downstream filters work correctly

3. **Test data extractor**:
   - Run `extract_doc_data()` with sample OCR data
   - Verify extraction results are correct
   - Check JSON parsing in pipeline

---

### Step 9: End-to-End Testing
**Full Pipeline Test**:

1. **Upload test document** via FastAPI service
2. **Monitor pipeline execution**:
   - OCR processing
   - Document type checking (LLM call #1)
   - Data extraction (LLM call #2)
   - Response merging
3. **Verify final output** matches expected format
4. **Check logs** for any errors or warnings

**Test Documents**:
- Valid ID document
- Invalid/unclear document
- Multi-page document
- Edge cases (rotated, low quality, etc.)

---

### Step 10: Deployment & Rollback Plan

**Deployment Steps**:
1. **Backup current code**
   ```bash
   git checkout -b backup-before-llm-migration
   git push origin backup-before-llm-migration
   ```

2. **Deploy to development environment first**
   - Update code on dev server
   - Run integration tests
   - Monitor for 24-48 hours

3. **Deploy to production**
   - Update Docker image
   - Deploy via docker-compose
   - Monitor logs and metrics

**Rollback Plan**:
If issues are detected:
1. Revert to previous Docker image
2. Or: Change URL back to old endpoint in config
3. Restart services
4. Investigate issues before retry

---

## Files Affected

### Core Changes (Required)
1. [`llm_client.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/clients/llm_client.py)
   - ✅ Update URL (line 17) - **ONLY REQUIRED CHANGE**
   - ✅ Simplify `ask_llm()` to return raw response (lines 40-64) - **RECOMMENDED**
   - ⚠️ Add error handling (optional enhancement)

### Files That Already Work (No Changes Needed) ✅
2. [`filter_llm_generic_response.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/processors/filter_llm_generic_response.py)
   - ✅ Already handles OpenAI format via `_extract_from_openai_like()`
   - ✅ Already parses `choices[0].message.content`
   - ✅ Already has fallback logic
   - **No changes needed!**

### Dependent Files (No Changes Needed) ✅
3. [`agent_doc_type_checker.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/processors/agent_doc_type_checker.py)
   - Uses `ask_llm()` - no changes needed
   
4. [`agent_extractor.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/processors/agent_extractor.py)
   - Uses `ask_llm()` - no changes needed

5. [`orchestrator.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/orchestrator.py)
   - Calls `filter_llm_generic_response()` - no changes needed

### Optional Enhancements
6. [`config.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/core/config.py)
   - Add LLM_ENDPOINT_URL configuration

7. [`servers.md`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/.etc/.info-project-management/servers.md)
   - Update documentation


---

## Risk Assessment

### Low Risk ✅
- **URL change**: Simple string replacement
- **Request format**: Identical, no changes needed
- **Response format**: More standardized and predictable

### Medium Risk ⚠️
- **Parsing logic changes**: Need thorough testing
- **Error handling**: Must ensure graceful degradation
- **Backward compatibility**: Old endpoint may be deprecated

### Mitigation Strategies
1. **Comprehensive testing** before production deployment
2. **Gradual rollout** (dev → staging → production)
3. **Monitoring and alerting** for LLM call failures
4. **Quick rollback plan** if issues arise
5. **Keep old code in git history** for reference

---

## Success Criteria

✅ **Migration is successful when**:
1. All LLM calls use the new endpoint
2. Document type checking works correctly
3. Data extraction works correctly
4. No increase in error rates
5. Response times are acceptable
6. All tests pass
7. Documentation is updated

---

## Timeline Estimate

### Minimal Approach (URL Change Only)
| Step | Task | Estimated Time |
|------|------|----------------|
| 1 | Update URL in `llm_client.py` | 2 minutes |
| 8 | Integration testing | 30 minutes |
| 9 | End-to-end testing | 30 minutes |
| 10 | Deployment | 15 minutes |
| **Total** | | **~1-2 hours** |

### Recommended Approach (URL + Refactoring)
| Step | Task | Estimated Time |
|------|------|----------------|
| 1 | Update URL | 2 minutes |
| 2 | Simplify `ask_llm()` to return raw response | 15 minutes |
| 4 | Update error handling | 30 minutes |
| 5 | Add configuration (optional) | 30 minutes |
| 6 | Update documentation | 15 minutes |
| 7 | Unit testing | 30 minutes |
| 8 | Integration testing | 30 minutes |
| 9 | End-to-end testing | 1 hour |
| 10 | Deployment | 15 minutes |
| **Total** | | **~3-4 hours** |

> **Note**: The existing [`filter_llm_generic_response.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/processors/filter_llm_generic_response.py) already handles the new response format, so no changes are needed there!

---

## Next Steps

1. **Review this plan** with team/stakeholders
2. **Get approval** to proceed
3. **Schedule deployment window**
4. **Execute steps 1-6** (code changes)
5. **Execute steps 7-9** (testing)
6. **Execute step 10** (deployment)
7. **Monitor production** for 48 hours post-deployment

---

## Notes

- The new endpoint appears to be more stable and follows OpenAI standards
- Response format is consistent based on the Postman logs provided
- SSL certificate is self-signed (already handled with `ssl._create_unverified_context()`)
- No authentication headers required (same as current endpoint)
- Content-Type in Postman logs shows `text/plain` but `application/json` should work (already used in current code)
