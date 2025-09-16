# Database connection and query functions
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
import streamlit as st
import json
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


def save_journal_to_database(journal_data):
    """Save journal entry to database with auto-generated journal code"""
    try:
        # Generate journal code using database function
        journal_code_query = """
        SELECT generate_journal_code(:journal_date, :journal_type_param)
        """
        journal_code_result = execute_query(journal_code_query, {
            'journal_date': journal_data.get('journal_date'),
            'journal_type_param': journal_data.get('journal_type', 'V1')
        })

        if not journal_code_result:
            st.error("❌ Failed to generate journal code")
            return None

        journal_code = journal_code_result[0][0]

        # Insert journal into database
        insert_query = """
        INSERT INTO journals (
            journal_code, journal_type, journal_date,
            total_debits, total_credits, balance_difference, rounding_adjustment,
            status, notes, raw_data, created_by
        ) VALUES (
            :journal_code, :journal_type, :journal_date,
            :total_debits, :total_credits, :balance_difference, :rounding_adjustment,
            :status, :notes, :raw_data, :created_by
        )
        RETURNING id, journal_code
        """

        # Convert raw_data dict to JSON string for JSONB storage
        raw_data = journal_data.get('raw_data', {})
        try:
            raw_data_json = json.dumps(raw_data, default=str) if raw_data else '{}'
        except (TypeError, ValueError) as e:
            st.warning(f"⚠️ Could not serialize raw_data to JSON: {e}. Using empty JSON object.")
            raw_data_json = '{}'

        params = {
            'journal_code': journal_code,
            'journal_type': journal_data.get('journal_type', 'V1'),
            'journal_date': journal_data.get('journal_date'),
            'total_debits': journal_data.get('total_debits', 0),
            'total_credits': journal_data.get('total_credits', 0),
            'balance_difference': journal_data.get('balance_difference', 0),
            'rounding_adjustment': journal_data.get('rounding_adjustment', 0),
            'status': journal_data.get('status', 'draft'),
            'notes': journal_data.get('notes', ''),
            'raw_data': raw_data_json,
            'created_by': journal_data.get('created_by', 'system')
        }

        result = execute_query(insert_query, params)

        if result:
            journal_id, generated_code = result[0]
            st.success(f"✅ Journal saved successfully with code: {generated_code}")
            return {'id': journal_id, 'journal_code': generated_code}

        return None

    except Exception as e:
        st.error(f"❌ Error saving journal to database: {str(e)}")
        return None


def get_journals_from_database(status_filter=None, date_from=None, date_to=None, journal_type=None):
    """Retrieve journals from database with optional filters"""
    try:
        query = """
        SELECT id, journal_code, journal_type, journal_date,
               total_debits, total_credits, balance_difference, rounding_adjustment,
               status, notes, created_at, created_by
        FROM journals
        WHERE 1=1
        """

        params = {}

        if status_filter:
            query += " AND status = :status"
            params['status'] = status_filter

        if date_from:
            query += " AND journal_date >= :date_from"
            params['date_from'] = date_from

        if date_to:
            query += " AND journal_date <= :date_to"
            params['date_to'] = date_to

        if journal_type:
            query += " AND journal_type = :journal_type"
            params['journal_type'] = journal_type

        query += " ORDER BY journal_date DESC, created_at DESC"

        result = execute_query(query, params)

        if result:
            journals = []
            for row in result:
                journals.append({
                    'id': row[0],
                    'journal_code': row[1],
                    'journal_type': row[2],
                    'journal_date': row[3],
                    'total_debits': float(row[4]) if row[4] else 0,
                    'total_credits': float(row[5]) if row[5] else 0,
                    'balance_difference': float(row[6]) if row[6] else 0,
                    'rounding_adjustment': float(row[7]) if row[7] else 0,
                    'status': row[8],
                    'notes': row[9],
                    'created_at': row[10],
                    'created_by': row[11]
                })
            return journals

        return []

    except Exception as e:
        st.error(f"❌ Error retrieving journals from database: {str(e)}")
        return []


def update_journal_status(journal_id, new_status, notes=None):
    """Update journal status and optionally add notes"""
    try:
        query = """
        UPDATE journals
        SET status = :status, notes = :notes, updated_at = CURRENT_TIMESTAMP
        WHERE id = :journal_id
        """

        params = {
            'journal_id': journal_id,
            'status': new_status,
            'notes': notes
        }

        result = execute_query(query, params)
        return result is not None

    except Exception as e:
        st.error(f"❌ Error updating journal status: {str(e)}")
        return False


def get_next_journal_code(journal_date, journal_type):
    """Get the next available journal code for a given date and type"""
    try:
        query = "SELECT generate_journal_code(:journal_date, :journal_type_param)"
        result = execute_query(query, {
            'journal_date': journal_date,
            'journal_type_param': journal_type
        })

        if result:
            return result[0][0]

        return None

    except Exception as e:
        st.error(f"❌ Error generating journal code: {str(e)}")
        return None


def save_journal_to_database_with_code(journal_data):
    """Save journal entry to database using a pre-generated journal code"""
    try:
        # Use the pre-generated journal code from journal_data
        journal_code = journal_data.get('journal_code')
        if not journal_code:
            st.error("❌ No journal code provided")
            return None

        # Insert journal into database
        insert_query = """
        INSERT INTO journals (
            journal_code, journal_type, journal_date,
            total_debits, total_credits, balance_difference, rounding_adjustment,
            status, notes, raw_data, created_by
        ) VALUES (
            :journal_code, :journal_type, :journal_date,
            :total_debits, :total_credits, :balance_difference, :rounding_adjustment,
            :status, :notes, :raw_data, :created_by
        )
        RETURNING id, journal_code
        """

        # Convert raw_data dict to JSON string for JSONB storage
        raw_data = journal_data.get('raw_data', {})
        try:
            raw_data_json = json.dumps(raw_data, default=str) if raw_data else '{}'
        except (TypeError, ValueError) as e:
            st.warning(f"⚠️ Could not serialize raw_data to JSON: {e}. Using empty JSON object.")
            raw_data_json = '{}'

        params = {
            'journal_code': journal_code,
            'journal_type': journal_data.get('journal_type', 'V1'),
            'journal_date': journal_data.get('journal_date'),
            'total_debits': journal_data.get('total_debits', 0),
            'total_credits': journal_data.get('total_credits', 0),
            'balance_difference': journal_data.get('balance_difference', 0),
            'rounding_adjustment': journal_data.get('rounding_adjustment', 0),
            'status': journal_data.get('status', 'draft'),
            'notes': journal_data.get('notes', ''),
            'raw_data': raw_data_json,
            'created_by': journal_data.get('created_by', 'system')
        }

        result = execute_query(insert_query, params)

        if result:
            journal_id, generated_code = result[0]
            st.success(f"✅ Journal saved successfully with code: {generated_code}")
            return {'id': journal_id, 'journal_code': generated_code}

        return None

    except Exception as e:
        st.error(f"❌ Error saving journal to database: {str(e)}")
        return None
