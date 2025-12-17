"""
Patch B Security Hardening Test Suite

Tests all three security features with flags ON/OFF to verify:
1. Default behavior unchanged (flags OFF)
2. Security features work correctly (flags ON)
"""
import asyncio
import json
import os
import sys
from io import BytesIO

# Add app to path
sys.path.insert(0, os.getcwd())

from fastapi import UploadFile
from fastapi.datastructures import Headers
from app.api.chat import _parse_conversation_history, _read_and_validate_image_upload
from app.core.config import settings


class MockUploadFile:
    """Mock UploadFile for testing"""
    def __init__(self, content: bytes, content_type: str, filename: str = "test.jpg"):
        self.content = content
        self.content_type = content_type
        self.filename = filename
        self._position = 0
    
    async def read(self, size: int = -1) -> bytes:
        """Read bytes from mock file"""
        if size == -1:
            result = self.content[self._position:]
            self._position = len(self.content)
            return result
        else:
            result = self.content[self._position:self._position + size]
            self._position += len(result)
            return result


def print_test(name: str):
    """Print test header"""
    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print('='*60)


def print_result(passed: bool, message: str):
    """Print test result"""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status}: {message}")


async def test_history_parsing_default():
    """Test 1: History parsing with flags OFF (baseline)"""
    print_test("History Parsing - Default Behavior (Flags OFF)")
    
    # Save original settings
    original_strict = settings.STRICT_HISTORY_VALIDATION
    original_sanitize = settings.SANITIZE_ERRORS
    
    try:
        # Ensure flags are OFF
        settings.STRICT_HISTORY_VALIDATION = False
        settings.SANITIZE_ERRORS = False
        
        # Test 1.1: Valid small history
        try:
            history = '[{"role":"user","content":"hello"},{"role":"assistant","content":"hi"}]'
            result = _parse_conversation_history(history)
            print_result(len(result) == 2, "Valid 2-message history parsed")
        except Exception as e:
            print_result(False, f"Failed to parse valid history: {e}")
        
        # Test 1.2: Valid large history (150 messages) - should work when flag OFF
        try:
            large_history = json.dumps([
                {"role": "user", "content": f"message {i}"} for i in range(150)
            ])
            result = _parse_conversation_history(large_history)
            print_result(len(result) == 150, "Large history (150 msgs) allowed when flag OFF")
        except Exception as e:
            print_result(False, f"Large history rejected when it shouldn't be: {e}")
        
        # Test 1.3: Invalid JSON - should still fail
        try:
            _parse_conversation_history("{invalid json")
            print_result(False, "Invalid JSON should have failed")
        except Exception:
            print_result(True, "Invalid JSON rejected as expected")
    
    finally:
        # Restore settings
        settings.STRICT_HISTORY_VALIDATION = original_strict
        settings.SANITIZE_ERRORS = original_sanitize


async def test_history_parsing_strict():
    """Test 2: History parsing with STRICT_HISTORY_VALIDATION=True"""
    print_test("History Parsing - Strict Validation (Flag ON)")
    
    original_strict = settings.STRICT_HISTORY_VALIDATION
    
    try:
        settings.STRICT_HISTORY_VALIDATION = True
        
        # Test 2.1: Valid history within limits
        try:
            history = json.dumps([{"role": "user", "content": "hello"}] * 50)
            result = _parse_conversation_history(history)
            print_result(len(result) == 50, "50 messages accepted (under 100 limit)")
        except Exception as e:
            print_result(False, f"Valid history rejected: {e}")
        
        # Test 2.2: Exceeds message limit (>100)
        try:
            history = json.dumps([{"role": "user", "content": "test"}] * 101)
            _parse_conversation_history(history)
            print_result(False, "101 messages should be rejected")
        except Exception as e:
            print_result("maximum length" in str(e), f"101 messages rejected: {e}")
        
        # Test 2.3: Non-array history
        try:
            _parse_conversation_history('{"not": "array"}')
            print_result(False, "Non-array should be rejected")
        except Exception as e:
            print_result("must be a JSON array" in str(e), f"Non-array rejected: {e}")
        
        # Test 2.4: Message exceeds char limit (>10K)
        try:
            big_msg = "x" * 10001
            history = json.dumps([{"role": "user", "content": big_msg}])
            _parse_conversation_history(history)
            print_result(False, "10K+ char message should be rejected")
        except Exception as e:
            print_result("exceeds maximum length" in str(e), f"Large message rejected: {e}")
        
        # Test 2.5: Missing required fields
        try:
            history = json.dumps([{"role": "user"}])  # Missing content
            _parse_conversation_history(history)
            print_result(False, "Message missing 'content' should be rejected")
        except Exception as e:
            print_result("missing required fields" in str(e), f"Missing field rejected: {e}")
    
    finally:
        settings.STRICT_HISTORY_VALIDATION = original_strict


async def test_image_upload_stream_capped():
    """Test 3: Image upload with stream-capped reading"""
    print_test("Image Upload - Stream-Capped Reading")
    
    # Create valid JPEG header
    jpeg_header = b'\xff\xd8\xff\xe0' + b'\x00\x10' + b'JFIF'
    
    # Test 3.1: Small valid image
    try:
        small_image = jpeg_header + (b'\x00' * 1000)
        mock_file = MockUploadFile(small_image, "image/jpeg")
        result = await _read_and_validate_image_upload(mock_file)
        print_result(len(result) == len(small_image), f"Small image read correctly ({len(result)} bytes)")
    except Exception as e:
        print_result(False, f"Small image failed: {e}")
    
    # Test 3.2: Image at size limit (9.9MB - should work)
    try:
        size_9_9mb = 9_900_000
        large_image = jpeg_header + (b'\x00' * (size_9_9mb - len(jpeg_header)))
        mock_file = MockUploadFile(large_image, "image/jpeg")
        result = await _read_and_validate_image_upload(mock_file)
        print_result(len(result) == size_9_9mb, f"9.9MB image accepted ({len(result)} bytes)")
    except Exception as e:
        print_result(False, f"9.9MB image failed: {e}")
    
    # Test 3.3: Image exceeds limit (11MB - should fail with 413)
    try:
        size_11mb = 11_000_000
        huge_image = jpeg_header + (b'\x00' * (size_11mb - len(jpeg_header)))
        mock_file = MockUploadFile(huge_image, "image/jpeg")
        await _read_and_validate_image_upload(mock_file)
        print_result(False, "11MB image should be rejected")
    except Exception as e:
        is_413 = "413" in str(e) or "too large" in str(e).lower()
        print_result(is_413, f"11MB image rejected with 413: {e}")
    
    # Test 3.4: Invalid content type
    try:
        mock_file = MockUploadFile(jpeg_header, "application/pdf")
        await _read_and_validate_image_upload(mock_file)
        print_result(False, "Invalid content type should be rejected")
    except Exception as e:
        print_result("Unsupported file type" in str(e), f"Invalid type rejected: {e}")


async def test_error_sanitization():
    """Test 4: Error message sanitization"""
    print_test("Error Sanitization Toggle")
    
    original_sanitize = settings.SANITIZE_ERRORS
    
    try:
        # Test 4.1: SANITIZE_ERRORS = False (shows details)
        settings.SANITIZE_ERRORS = False
        try:
            _parse_conversation_history("{bad json")
        except Exception as e:
            has_details = "Invalid JSON" in str(e) and "bad json" in str(e).lower()
            print_result(has_details, f"Flag OFF: Error includes details - {e}")
        
        # Test 4.2: SANITIZE_ERRORS = True (sanitized)
        settings.SANITIZE_ERRORS = True
        try:
            _parse_conversation_history("{bad json")
        except Exception as e:
            is_sanitized = "Invalid conversation history format" in str(e)
            has_no_details = "bad json" not in str(e).lower()
            print_result(is_sanitized and has_no_details, f"Flag ON: Error sanitized - {e}")
    
    finally:
        settings.SANITIZE_ERRORS = original_sanitize


async def test_combined_flags():
    """Test 5: Both flags enabled together"""
    print_test("Combined Security Flags (Both ON)")
    
    original_strict = settings.STRICT_HISTORY_VALIDATION
    original_sanitize = settings.SANITIZE_ERRORS
    
    try:
        settings.STRICT_HISTORY_VALIDATION = True
        settings.SANITIZE_ERRORS = True
        
        # Test: Invalid large history with sanitized error
        try:
            history = json.dumps([{"role": "user", "content": "test"}] * 101)
            _parse_conversation_history(history)
            print_result(False, "Should reject 101 messages")
        except Exception as e:
            # Should get rejection but error might be sanitized
            rejected = "maximum length" in str(e) or "exceeds" in str(e)
            print_result(rejected, f"Rejected with appropriate error: {e}")
    
    finally:
        settings.STRICT_HISTORY_VALIDATION = original_strict
        settings.SANITIZE_ERRORS = original_sanitize


async def run_all_tests():
    """Run complete test suite"""
    print("\n" + "="*60)
    print("PATCH B SECURITY HARDENING - TEST SUITE")
    print("="*60)
    print(f"\nCurrent Config:")
    print(f"  SANITIZE_ERRORS: {settings.SANITIZE_ERRORS}")
    print(f"  STRICT_HISTORY_VALIDATION: {settings.STRICT_HISTORY_VALIDATION}")
    
    await test_history_parsing_default()
    await test_history_parsing_strict()
    await test_image_upload_stream_capped()
    await test_error_sanitization()
    await test_combined_flags()
    
    print("\n" + "="*60)
    print("TEST SUITE COMPLETE")
    print("="*60)
    print("\nNext Steps:")
    print("1. Review results above")
    print("2. All ✅ = Ready for staging deployment")
    print("3. Set flags in .env to test production config:")
    print("   SANITIZE_ERRORS=true")
    print("   STRICT_HISTORY_VALIDATION=true")


if __name__ == "__main__":
    asyncio.run(run_all_tests())
