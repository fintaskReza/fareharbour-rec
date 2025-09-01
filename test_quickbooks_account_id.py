#!/usr/bin/env python3
"""
Test script for QuickBooks Account ID functionality
Run this script to verify that the account ID column was added and is working correctly.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from scripts.database import execute_query, add_quickbooks_account_id_column, get_database_connection

def test_database_column():
    """Test if the QuickBooks account ID column exists"""
    print("🔍 Testing QuickBooks Account ID Column...")

    try:
        # Check if column exists
        result = execute_query("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'quickbooks_mappings'
            AND column_name = 'quickbooks_account_id'
        """)

        if result and len(result) > 0:
            column_name, data_type, is_nullable = result[0]
            print(f"✅ Column exists: {column_name} ({data_type}, nullable: {is_nullable})")
            return True
        else:
            print("❌ Column does not exist")
            return False

    except Exception as e:
        print(f"❌ Error checking column: {str(e)}")
        return False

def test_add_column_function():
    """Test the add_quickbooks_account_id_column function"""
    print("\n🔧 Testing add_quickbooks_account_id_column function...")

    try:
        result = add_quickbooks_account_id_column()
        if result:
            print("✅ Function executed successfully")
            return True
        else:
            print("❌ Function returned False")
            return False
    except Exception as e:
        print(f"❌ Error running function: {str(e)}")
        return False

def test_sample_data():
    """Test inserting and retrieving sample data with account ID"""
    print("\n📊 Testing sample data operations...")

    try:
        # Insert test data
        test_mapping = {
            'mapping_type': 'test_tour',
            'fareharbour_item': 'Test Tour',
            'quickbooks_account': 'Test Revenue Account',
            'account_type': 'revenue',
            'quickbooks_account_id': '12345'
        }

        insert_result = execute_query("""
            INSERT INTO quickbooks_mappings (
                mapping_type, fareharbour_item, quickbooks_account,
                account_type, quickbooks_account_id
            ) VALUES (
                :mapping_type, :fareharbour_item, :quickbooks_account,
                :account_type, :quickbooks_account_id
            )
            ON CONFLICT (mapping_type, fareharbour_item) DO UPDATE SET
                quickbooks_account = EXCLUDED.quickbooks_account,
                account_type = EXCLUDED.account_type,
                quickbooks_account_id = EXCLUDED.quickbooks_account_id,
                updated_at = CURRENT_TIMESTAMP
        """, test_mapping)

        if insert_result:
            print("✅ Test data inserted successfully")
        else:
            print("❌ Failed to insert test data")
            return False

        # Retrieve test data
        select_result = execute_query("""
            SELECT mapping_type, fareharbour_item, quickbooks_account, quickbooks_account_id
            FROM quickbooks_mappings
            WHERE mapping_type = 'test_tour' AND fareharbour_item = 'Test Tour'
        """)

        if select_result and len(select_result) > 0:
            mapping_type, fh_item, qb_account, qb_account_id = select_result[0]
            print(f"✅ Retrieved: {fh_item} → {qb_account} (ID: {qb_account_id})")

            if qb_account_id == '12345':
                print("✅ Account ID stored and retrieved correctly")
            else:
                print(f"❌ Account ID mismatch: expected '12345', got '{qb_account_id}'")
                return False
        else:
            print("❌ Failed to retrieve test data")
            return False

        # Clean up test data
        cleanup_result = execute_query("""
            DELETE FROM quickbooks_mappings
            WHERE mapping_type = 'test_tour' AND fareharbour_item = 'Test Tour'
        """)

        if cleanup_result:
            print("✅ Test data cleaned up")
        else:
            print("⚠️ Could not clean up test data")

        return True

    except Exception as e:
        print(f"❌ Error in sample data test: {str(e)}")
        return False

def main():
    """Run all tests"""
    print("🧪 QuickBooks Account ID Test Suite")
    print("=" * 50)

    tests_passed = 0
    total_tests = 3

    # Test 1: Database column existence
    if test_database_column():
        tests_passed += 1

    # Test 2: Add column function
    if test_add_column_function():
        tests_passed += 1

    # Test 3: Sample data operations
    if test_sample_data():
        tests_passed += 1

    print("\n" + "=" * 50)
    print(f"📊 Test Results: {tests_passed}/{total_tests} tests passed")

    if tests_passed == total_tests:
        print("🎉 All tests passed! QuickBooks Account ID functionality is working correctly.")
        return True
    else:
        print("❌ Some tests failed. Please check the implementation.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

