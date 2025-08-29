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
