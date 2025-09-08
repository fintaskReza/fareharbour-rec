# Database connection and query functions
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
import streamlit as st
from scripts.config import DATABASE_URL

@st.cache_resource
def get_database_connection():
    """Create and cache database connection"""
    try:
        engine = create_engine(DATABASE_URL)
        return engine
    except Exception as e:
        st.error(f"Failed to connect to database: {e}")
        return None

def execute_query(query, params=None):
    """Execute a database query and return results"""
    engine = get_database_connection()
    if engine is None:
        return None

    try:
        with engine.connect() as conn:
            result = conn.execute(text(query), params or {})
            if result.returns_rows:
                return result.fetchall()
            else:
                conn.commit()
                return True
    except SQLAlchemyError as e:
        st.error(f"Database error: {e}")
        return None

def add_quickbooks_account_id_column():
    """Add QuickBooks account ID column to quickbooks_mappings table if it doesn't exist"""
    try:
        # Check if column exists
        check_query = """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'quickbooks_mappings'
        AND column_name = 'quickbooks_account_id'
        """

        result = execute_query(check_query)
        if result and len(result) > 0:
            st.info("✅ QuickBooks account ID column already exists")
            return True

        # Add the column if it doesn't exist
        alter_query = """
        ALTER TABLE quickbooks_mappings
        ADD COLUMN quickbooks_account_id VARCHAR(50)
        """

        result = execute_query(alter_query)
        if result:
            st.success("✅ Successfully added QuickBooks account ID column to database")
            return True
        else:
            st.error("❌ Failed to add QuickBooks account ID column")
            return False

    except Exception as e:
        st.error(f"❌ Error adding QuickBooks account ID column: {str(e)}")
        return False

def save_quickbooks_accounts_to_db(accounts_data):
    """Save QuickBooks accounts to database"""
    if not accounts_data:
        return False

    try:
        # First, mark all existing accounts as inactive
        update_query = "UPDATE quickbooks_accounts SET active = false, updated_at = CURRENT_TIMESTAMP"
        execute_query(update_query)

        # Insert or update accounts
        for account in accounts_data:
            account_id = account.get('Id', '')
            name = account.get('Name', '')
            fully_qualified_name = account.get('FullyQualifiedName', '')
            classification = account.get('Classification', '')
            account_type = account.get('AccountType', '')
            account_subtype = account.get('AccountSubType', '')
            active = account.get('Active', True)

            if not account_id or not name:
                continue

            # Insert or update account
            insert_query = """
            INSERT INTO quickbooks_accounts
            (account_id, name, fully_qualified_name, classification, account_type, account_subtype, active, updated_at)
            VALUES (:account_id, :name, :fully_qualified_name, :classification, :account_type, :account_subtype, :active, CURRENT_TIMESTAMP)
            ON CONFLICT (account_id) DO UPDATE SET
                name = EXCLUDED.name,
                fully_qualified_name = EXCLUDED.fully_qualified_name,
                classification = EXCLUDED.classification,
                account_type = EXCLUDED.account_type,
                account_subtype = EXCLUDED.account_subtype,
                active = EXCLUDED.active,
                updated_at = CURRENT_TIMESTAMP
            """

            execute_query(insert_query, {
                'account_id': account_id,
                'name': name,
                'fully_qualified_name': fully_qualified_name,
                'classification': classification,
                'account_type': account_type,
                'account_subtype': account_subtype,
                'active': active
            })

        return True

    except Exception as e:
        st.error(f"❌ Error saving QuickBooks accounts to database: {str(e)}")
        return False

def load_quickbooks_accounts_from_db():
    """Load QuickBooks accounts from database"""
    try:
        query = """
        SELECT account_id, name, fully_qualified_name, classification, account_type, account_subtype, active
        FROM quickbooks_accounts
        WHERE active = true
        ORDER BY name
        """

        result = execute_query(query)
        if result:
            accounts_data = []
            for row in result:
                account = {
                    'Id': row[0],
                    'Name': row[1],
                    'FullyQualifiedName': row[2] or row[1],  # Use name if fully qualified name is null
                    'Classification': row[3],
                    'AccountType': row[4],
                    'AccountSubType': row[5],
                    'Active': row[6]
                }
                accounts_data.append(account)

            return accounts_data
        else:
            return []

    except Exception as e:
        st.error(f"❌ Error loading QuickBooks accounts from database: {str(e)}")
        return []
