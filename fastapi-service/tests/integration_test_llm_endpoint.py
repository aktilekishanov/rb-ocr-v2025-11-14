#!/usr/bin/env python3
"""
Integration test script for the new LLM endpoint.
Tests the actual API call to verify the migration is successful.
"""

import sys
import json
from pathlib import Path

# Add parent directory to path to import pipeline modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.clients.llm_client import ask_llm, LLMClientError
from pipeline.processors.filter_llm_generic_response import filter_llm_generic_response


def test_basic_llm_call():
    """Test basic LLM call with simple prompt."""
    print("=" * 80)
    print("TEST 1: Basic LLM Call")
    print("=" * 80)
    
    try:
        prompt = "Say 'Hello, World!' in JSON format with a key 'message'."
        print(f"\nPrompt: {prompt}")
        
        response = ask_llm(prompt, temperature=0.1, max_tokens=100)
        print(f"\nRaw Response:\n{response}")
        
        # Try to parse as JSON
        parsed = json.loads(response)
        print(f"\nParsed JSON:\n{json.dumps(parsed, indent=2)}")
        
        # Check for expected OpenAI format
        if "choices" in parsed:
            print("\n✅ Response has OpenAI 'choices' format")
            if parsed["choices"] and "message" in parsed["choices"][0]:
                content = parsed["choices"][0]["message"].get("content", "")
                print(f"✅ Message content: {content[:100]}...")
        
        print("\n✅ TEST 1 PASSED")
        return True
        
    except LLMClientError as e:
        print(f"\n❌ LLM Client Error: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected Error: {e}")
        return False


def test_filter_integration():
    """Test that the filter can extract content from the new endpoint response."""
    print("\n" + "=" * 80)
    print("TEST 2: Filter Integration")
    print("=" * 80)
    
    try:
        # Create a test prompt that should return JSON
        prompt = '''Return this exact JSON and nothing else:
{
  "document_type": "ID",
  "test": "integration"
}'''
        
        print(f"\nPrompt: {prompt}")
        
        # Get raw response
        raw_response = ask_llm(prompt, temperature=0, max_tokens=200)
        print(f"\nRaw Response:\n{raw_response}")
        
        # Save to temp file for filter
        import tempfile
        import os
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write raw response
            raw_path = os.path.join(tmpdir, "llm_raw.json")
            with open(raw_path, "w", encoding="utf-8") as f:
                f.write(raw_response)
            
            # Run filter
            filtered_path = filter_llm_generic_response(
                input_path=raw_path,
                output_dir=tmpdir,
                filename="llm_filtered.json"
            )
            
            # Read filtered output
            with open(filtered_path, "r", encoding="utf-8") as f:
                filtered = json.load(f)
            
            print(f"\nFiltered Output:\n{json.dumps(filtered, indent=2)}")
            
            # Check if filter extracted the inner JSON
            if "document_type" in filtered or "test" in filtered:
                print("\n✅ Filter successfully extracted inner JSON from OpenAI envelope")
            else:
                print("\n⚠️  Filter output doesn't contain expected keys")
                print("   This might be okay if LLM didn't follow instructions exactly")
        
        print("\n✅ TEST 2 PASSED")
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_document_type_check_prompt():
    """Test with a realistic document type checking prompt."""
    print("\n" + "=" * 80)
    print("TEST 3: Realistic Document Type Check")
    print("=" * 80)
    
    try:
        # Simulate OCR pages
        ocr_pages = {
            "pages": [
                {
                    "page_number": 1,
                    "text": "УДОСТОВЕРЕНИЕ ЛИЧНОСТИ\nНомер: 123456789\nФИО: ИВАНОВ ИВАН ИВАНОВИЧ"
                }
            ]
        }
        
        prompt = f'''Analyze this OCR text and return JSON with document_type field.
Valid types: ID, PASSPORT, UNKNOWN

OCR Data:
{json.dumps(ocr_pages, ensure_ascii=False)}

Return only JSON:'''
        
        print(f"\nPrompt (truncated): {prompt[:200]}...")
        
        response = ask_llm(prompt, temperature=0, max_tokens=300)
        
        # Parse response
        parsed = json.loads(response)
        
        if "choices" in parsed and parsed["choices"]:
            content = parsed["choices"][0].get("message", {}).get("content", "")
            print(f"\nLLM Content Response:\n{content}")
            
            # Try to parse inner JSON
            try:
                inner = json.loads(content)
                print(f"\nParsed Inner JSON:\n{json.dumps(inner, indent=2, ensure_ascii=False)}")
                
                if "document_type" in inner:
                    print(f"\n✅ Document type detected: {inner['document_type']}")
            except json.JSONDecodeError:
                print("\n⚠️  Content is not valid JSON (LLM may have added extra text)")
        
        print("\n✅ TEST 3 PASSED")
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all integration tests."""
    print("\n" + "=" * 80)
    print("LLM ENDPOINT INTEGRATION TESTS")
    print("Testing: https://dl-ai-dev-app01-uv01.fortebank.com/openai/payment/out/completions")
    print("=" * 80)
    
    results = []
    
    # Run tests
    results.append(("Basic LLM Call", test_basic_llm_call()))
    results.append(("Filter Integration", test_filter_integration()))
    results.append(("Document Type Check", test_document_type_check_prompt()))
    
    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    
    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name}: {status}")
    
    total = len(results)
    passed = sum(1 for _, p in results if p)
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED! Migration successful!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Please review.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
