import unittest

import pytest

from snapred.meta.Callback import callback


class TestCallback(unittest.TestCase):
    def test_unsetThrows(self):
        testCallback = callback(str)
        with pytest.raises(AttributeError):
            testCallback.upper()
        with pytest.raises(AttributeError):
            testCallback == "test"

    def test_stringCallback(self):
        testCallback = callback(str)
        testCallback.update("test")
        assert testCallback.get() == "test"
        assert testCallback.upper() == "TEST"
        assert testCallback == "test"
        assert testCallback[0] == "t"

    def test_updateCallback(self):
        testCallback = callback(str)
        with pytest.raises(AttributeError):
            testCallback.get()
        testCallback.update("test")
        assert testCallback.get() == "test"

    def test_boolCallback(self):
        testCallback = callback(bool)
        testCallback.update(True)
        assert testCallback.get() is True
        assert testCallback.__bool__() is True
        assert testCallback

    def test_intCallback(self):
        testCallback = callback(int)
        testCallback.update(123)
        assert testCallback.get() == 123
        assert testCallback.__int__() == 123
        assert testCallback == 123
        assert testCallback + 1 == 124

    def test_floatCallback(self):
        testCallback = callback(float)
        testCallback.update(123.456)
        assert testCallback.get() == 123.456
        assert testCallback.__float__() == 123.456
        assert testCallback == 123.456
        assert testCallback + 1 == 124.456

    def test_callback_instances(self):
        """Test that callback() returns distinct instances but cached classes."""

        # Create two callbacks for int
        cb1 = callback(int)
        cb2 = callback(int)

        # Create one callback for str
        cb3 = callback(str)

        # Test 1: Different instances
        print("Test 1: Different instances")
        print(f"  cb1 is cb2: {cb1 is cb2}")  # Should be False
        print(f"  cb1 is not cb2: {cb1 is not cb2}")  # Should be True
        assert cb1 is not cb2, "cb1 and cb2 should be different instances"

        # Test 2: Same class for same type
        print("\nTest 2: Same class for same type")
        print(f"  cb1.__class__ is cb2.__class__: {cb1.__class__ is cb2.__class__}")  # Should be True
        assert cb1.__class__ is cb2.__class__, "cb1 and cb2 should have the same class"

        # Test 3: Different classes for different types
        print("\nTest 3: Different classes for different types")
        print(f"  cb1.__class__ is cb3.__class__: {cb1.__class__ is cb3.__class__}")  # Should be False
        assert cb1.__class__ is not cb3.__class__, "cb1 and cb3 should have different classes"

        # Test 4: Class names are correct
        print("\nTest 4: Class names are correct")
        print(f"  cb1.__class__.__name__: {cb1.__class__.__name__}")  # Should be Callback[int]
        print(f"  cb3.__class__.__name__: {cb3.__class__.__name__}")  # Should be Callback[str]
        assert cb1.__class__.__name__ == "Callback[int]", f"Expected 'Callback[int]', got '{cb1.__class__.__name__}'"
        assert cb3.__class__.__name__ == "Callback[str]", f"Expected 'Callback[str]', got '{cb3.__class__.__name__}'"

        # Test 5: Functionality still works
        print("\nTest 5: Functionality still works")
        cb1.update(10)
        cb2.update(20)

        print(f"  cb1.get(): {cb1.get()}")  # Should be 10
        print(f"  cb2.get(): {cb2.get()}")  # Should be 20
        assert cb1.get() == 10, f"Expected 10, got {cb1.get()}"
        assert cb2.get() == 20, f"Expected 20, got {cb2.get()}"

        # Test 6: Magic methods work
        print("\nTest 6: Magic methods work")
        result1 = cb1 + 5
        result2 = cb2 + 5
        print(f"  cb1 + 5: {result1}")  # Should be 15
        print(f"  cb2 + 5: {result2}")  # Should be 25
        assert result1 == 15, f"Expected 15, got {result1}"
        assert result2 == 25, f"Expected 25, got {result2}"

        print("\n✅ All tests passed!")
