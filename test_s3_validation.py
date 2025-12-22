#!/usr/bin/env python3
"""Quick validation test for S3 path schema changes.

This script tests the S3 path validation logic to ensure:
1. Extensionless S3 paths are now accepted (PRIMARY FIX)
2. S3 paths with extensions still work (BACKWARD COMPATIBILITY)
3. Security validations still work (SECURITY INTACT)
"""

from pydantic import ValidationError
import sys
import os

# Add parent directory to path to import schemas
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "fastapi-service"))

from api.schemas import KafkaEventQueryParams, KafkaEventRequest


def test_s3_validation():
    """Test S3 path validation rules."""

    test_cases = [
        {
            "name": "✅ Valid: S3 path WITHOUT extension (PRIMARY FIX)",
            "s3_path": "uploads/document_12345",
            "should_pass": True,
            "description": "This should now PASS after removing file extension validation",
        },
        {
            "name": "✅ Valid: S3 path WITH extension (BACKWARD COMPATIBLE)",
            "s3_path": "documents/2024/sample.pdf",
            "should_pass": True,
            "description": "This should continue to PASS as before",
        },
        {
            "name": "✅ Valid: S3 path with subdirectories, no extension",
            "s3_path": "uploads/2024/12/document_999",
            "should_pass": True,
            "description": "Deep paths without extensions should now PASS",
        },
        {
            "name": "❌ Invalid: Directory traversal attack",
            "s3_path": "../secret/file.pdf",
            "should_pass": False,
            "description": "Security check: should FAIL (directory traversal)",
        },
        {
            "name": "❌ Invalid: Absolute path",
            "s3_path": "/root/file.pdf",
            "should_pass": False,
            "description": "Security check: should FAIL (absolute path)",
        },
        {
            "name": "✅ Edge case: S3 path ending with dot",
            "s3_path": "uploads/document.",
            "should_pass": True,
            "description": "Harmless edge case, should PASS",
        },
    ]

    print("=" * 80)
    print("S3 PATH VALIDATION TEST SUITE")
    print("=" * 80)
    print()

    passed = 0
    failed = 0

    for i, test in enumerate(test_cases, 1):
        print(f"Test {i}: {test['name']}")
        print(f"  S3 Path: '{test['s3_path']}'")
        print(f"  Expected: {'PASS' if test['should_pass'] else 'FAIL'}")
        print(f"  Description: {test['description']}")

        # Test with KafkaEventQueryParams
        try:
            params = KafkaEventQueryParams(
                request_id=12345,
                s3_path=test["s3_path"],
                iin="021223504060",
                first_name="Test",
                last_name="User",
            )
            result = "PASS"
            error_msg = None
        except ValidationError as e:
            result = "FAIL"
            error_msg = str(e.errors()[0]["msg"])

        # Check if result matches expectation
        if (result == "PASS" and test["should_pass"]) or (
            result == "FAIL" and not test["should_pass"]
        ):
            print(f"  ✅ Result: {result} (as expected)")
            if error_msg:
                print(f"     Error: {error_msg}")
            passed += 1
        else:
            print(
                f"  ❌ Result: {result} (UNEXPECTED! Expected {'PASS' if test['should_pass'] else 'FAIL'})"
            )
            if error_msg:
                print(f"     Error: {error_msg}")
            failed += 1

        print()

    print("=" * 80)
    print(
        f"TEST SUMMARY: {passed} passed, {failed} failed out of {len(test_cases)} tests"
    )
    print("=" * 80)

    if failed == 0:
        print("🎉 ALL TESTS PASSED! The validation changes are working correctly.")
        return 0
    else:
        print("⚠️  SOME TESTS FAILED! Please review the implementation.")
        return 1


if __name__ == "__main__":
    exit_code = test_s3_validation()
    sys.exit(exit_code)
