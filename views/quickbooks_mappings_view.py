# QuickBooks Account Mappings View
import streamlit as st
import pandas as pd
from scripts.database import execute_query
from scripts.data_loaders import load_sales_csv_data

# Import requests for API calls
try:
    import requests
except ImportError:
    st.error("❌ The 'requests' library is required for QuickBooks API integration. Please install it with: pip install requests")
    requests = None

# Import database functions
from scripts.database import execute_query, add_quickbooks_account_id_column

def quickbooks_mappings_page():
    """QuickBooks Account Mappings Page"""
    st.title("🔗 QuickBooks Account Mappings")

    # Ensure database column exists
    add_quickbooks_account_id_column()

    # Compact CSS
    st.markdown("""
    <style>
    .stTabs [data-baseweb="tab-list"] {gap: 4px; margin-bottom: 1rem;}
    .stTabs [data-baseweb="tab"] {padding: 8px 16px; font-size: 0.9rem;}
    </style>
    """, unsafe_allow_html=True)

    # File upload for populating dropdowns
    st.sidebar.header("📁 Data Source")
    csv_file = st.sidebar.file_uploader(
        "Upload Sales CSV to populate mappings",
        type=['csv'],
        help="Upload FareHarbour sales report to extract tours and payment types"
    )

    # QuickBooks accounts refresh
    st.sidebar.header("🔄 QuickBooks Integration")

    # Debug mode toggle
    debug_mode = st.sidebar.checkbox("🐛 Debug Mode", help="Show detailed debug information when loading accounts",
                                   value=st.session_state.get('qb_debug_mode', False))
    st.session_state.qb_debug_mode = debug_mode
    if debug_mode:
        st.sidebar.info("🐛 Debug mode enabled - detailed logs will be shown")

    # Check if accounts have been loaded
    accounts_loaded = hasattr(st.session_state, 'qb_accounts_cache')

    if not accounts_loaded:
        st.sidebar.info("💡 Click 'Load Accounts' to fetch QuickBooks data")

    # Refresh/Load button
    button_text = "🔄 Refresh Accounts" if accounts_loaded else "📥 Load QuickBooks Accounts"
    button_help = "Fetch latest accounts from QuickBooks API" if accounts_loaded else "Load accounts from QuickBooks API for the first time"

    if st.sidebar.button(button_text, help=button_help, type="primary"):
        with st.spinner("Fetching QuickBooks accounts..."):
            account_count, categorized_accounts = refresh_quickbooks_accounts()

            if account_count is not None:
                st.sidebar.success(f"✅ Loaded {account_count} QuickBooks accounts!")
                st.rerun()
            else:
                st.sidebar.error("❌ Failed to load QuickBooks accounts")

    # Asset accounts button
    st.sidebar.header("🏦 Asset Accounts")
    asset_accounts_loaded = hasattr(st.session_state, 'qb_asset_accounts')

    if not asset_accounts_loaded:
        st.sidebar.info("💰 Click to load asset accounts for payment mappings")

    if st.sidebar.button("💰 Load Asset Accounts", help="Load QuickBooks asset accounts for payment type mappings",
                        type="secondary"):
        with st.spinner("Fetching asset accounts..."):
            asset_accounts = get_asset_accounts()

            if asset_accounts:
                st.sidebar.success(f"✅ Loaded {len(asset_accounts)} asset accounts!")
                st.rerun()
            else:
                st.sidebar.error("❌ Failed to load asset accounts")

    # Show asset accounts summary
    if asset_accounts_loaded:
        asset_count = len(st.session_state.qb_asset_accounts)
        st.sidebar.metric("🏦 Asset Accounts", asset_count)

        # Show last fetch time
        if hasattr(st.session_state, 'qb_asset_accounts_last_fetch'):
            st.sidebar.caption(f"Assets updated: {st.session_state.qb_asset_accounts_last_fetch.strftime('%H:%M:%S')}")

    # Show account summary in sidebar (only if accounts are loaded)
    if accounts_loaded:
        accounts = st.session_state.qb_accounts_cache
        total_accounts = sum(len(acc_list) for acc_list in accounts.values())
        st.sidebar.metric("📊 Total Accounts", total_accounts)

        with st.sidebar.expander("📈 Account Breakdown"):
            for category, acc_list in accounts.items():
                st.write(f"**{category}**: {len(acc_list)}")

        # Show last refresh time
        if hasattr(st.session_state, 'qb_accounts_last_fetch'):
            st.sidebar.caption(f"Last updated: {st.session_state.qb_accounts_last_fetch.strftime('%H:%M:%S')}")

        # Test API connection
        if st.sidebar.button("🔍 Test API Connection", help="Test the QuickBooks API connection"):
            test_api_connection()

        # Debug: Show raw API response
        if st.sidebar.button("🐛 Debug Raw Response", help="Show raw API response for debugging"):
            debug_raw_response()
    else:
        # Show placeholder metrics when no accounts loaded
        st.sidebar.metric("📊 Total Accounts", 0)
        st.sidebar.caption("No accounts loaded yet")

    # Initialize session state for mappings if not exists
    if 'qb_mappings_data' not in st.session_state:
        st.session_state.qb_mappings_data = load_quickbooks_mappings()

    # Check if QuickBooks accounts have been loaded
    accounts_loaded = hasattr(st.session_state, 'qb_accounts_cache')

    if not accounts_loaded:
        st.warning("⚠️ **No QuickBooks accounts loaded yet!** Please click 'Load QuickBooks Accounts' in the sidebar to fetch your account data before creating mappings.")
        st.info("💡 This ensures your dropdowns are populated with real QuickBooks account names.")

    # Database column verification
    if debug_mode:
        st.info("🔍 **Debug Mode Active** - Enhanced logging enabled for database operations")

    # Create tabs for different mapping types
    tab1, tab2, tab3 = st.tabs(["🎪 Tour Revenue Mappings", "💰 Fee Revenue Mappings", "💳 Payment Type Mappings"])

    # Extract data from CSV if uploaded
    tours_list, fees_list, payment_types_list = [], [], []
    if csv_file is not None:
        df = load_sales_csv_data(csv_file)
        if df is not None and not df.empty:
            tours_list, fees_list, payment_types_list = extract_mapping_items(df)

    with tab1:
        st.subheader("🎪 Tour Revenue Mappings")
        create_tour_revenue_mappings_table(tours_list)

    with tab2:
        st.subheader("💰 Fee Revenue Mappings")
        create_fee_revenue_mappings_table(fees_list)

    with tab3:
        st.subheader("💳 Payment Type Mappings")
        create_payment_type_mappings_table(payment_types_list)

    # Global save/reset actions
    st.markdown("---")
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("💾 Save All Mappings", type="primary", help="Save all mappings to database"):
            save_result = save_all_mappings()
            if save_result:
                st.success("✅ All mappings saved successfully!")
                st.session_state.qb_mappings_data = load_quickbooks_mappings()  # Refresh data
                st.rerun()
            else:
                st.error("❌ Error saving mappings. Please try again.")

    with col2:
        if st.button("🔄 Refresh from Database", help="Reload mappings from database"):
            st.session_state.qb_mappings_data = load_quickbooks_mappings()
            st.success("✅ Mappings refreshed from database!")
            st.rerun()

    with col3:
        if st.button("📊 View Mapping Summary", help="Show summary of current mappings"):
            show_mapping_summary()

def extract_mapping_items(df):
    """Extract unique tours, fees, and payment types from CSV data"""
    try:
        # Extract unique tours
        tours_list = sorted(df['Item'].dropna().unique().tolist()) if 'Item' in df.columns else []

        # Extract fees from database (since fees are managed there)
        fees_list = []
        try:
            fees_query = execute_query("SELECT DISTINCT name FROM fees ORDER BY name")
            if fees_query:
                fees_list = [fee[0] for fee in fees_query]
                st.success(f"✅ Loaded {len(fees_list)} fees from database")
            else:
                st.warning("⚠️ No fees found in database")
        except Exception as db_error:
            if "SSL connection has been closed" in str(db_error) or "connection" in str(db_error).lower():
                st.warning("⚠️ Database connection issue. Using fallback fee list.")
                # Provide some common fee types as fallback
                fees_list = [
                    "Park Fee", "Fuel Surcharge", "Stewardship Fee", "Booking Fee",
                    "Processing Fee", "Service Fee", "Cancellation Fee", "Other Fee"
                ]
                st.info(f"📝 Using {len(fees_list)} default fee types")
            else:
                st.error(f"❌ Database error loading fees: {str(db_error)}")
                fees_list = []

        # Extract unique payment types
        payment_types_list = sorted(df['Payment Type'].dropna().unique().tolist()) if 'Payment Type' in df.columns else []

        return tours_list, fees_list, payment_types_list

    except Exception as e:
        st.error(f"❌ Error extracting mapping items: {str(e)}")
        return [], [], []

def fetch_quickbooks_accounts(asset_accounts_only=False):
    """Fetch QuickBooks accounts from API"""
    if requests is None:
        st.error("❌ Requests library not available. Cannot fetch QuickBooks accounts.")
        return None

    try:
        # Use specific webhook for asset accounts, general webhook for all accounts
        if asset_accounts_only:
            webhook_url = "https://n8n.fintask.ie/webhook/ec29217c-05bf-4629-98d2-a2eb9034aebf"
        else:
            webhook_url = "https://n8n.fintask.ie/webhook/b25e21c8-fbf1-4cea-9fff-bf682956b0c1"

        response = requests.get(webhook_url, timeout=30)
        response.raise_for_status()

        accounts_data = response.json()

        # Debug logging (only when debug mode is enabled)
        debug_mode = st.session_state.get('qb_debug_mode', False)
        if debug_mode:
            st.write(f"DEBUG: Raw response type: {type(accounts_data)}")
            if isinstance(accounts_data, dict):
                st.write(f"DEBUG: Response is dict with keys: {list(accounts_data.keys())}")
            elif isinstance(accounts_data, list):
                st.write(f"DEBUG: Response is list with {len(accounts_data)} items")
                if accounts_data:
                    st.write(f"DEBUG: First item keys: {list(accounts_data[0].keys()) if isinstance(accounts_data[0], dict) else 'Not a dict'}")
            else:
                st.write(f"DEBUG: Response is: {type(accounts_data)} - {str(accounts_data)[:200]}...")

        # Handle different response formats
        if isinstance(accounts_data, list) and len(accounts_data) > 0:
            # Check if the first item is a QueryResponse wrapper
            first_item = accounts_data[0]
            if isinstance(first_item, dict) and 'QueryResponse' in first_item:
                query_response = first_item['QueryResponse']
                if 'Account' in query_response:
                    # QuickBooks QueryResponse format with nested Account array
                    accounts_data = query_response['Account']
                    if debug_mode:
                        st.write(f"DEBUG: Extracted {len(accounts_data)} accounts from QueryResponse.Account")
                else:
                    st.error("❌ QueryResponse found but no 'Account' key")
                    return None
            elif isinstance(first_item, dict) and 'accounts' in first_item:
                # Some APIs wrap accounts in an 'accounts' key
                accounts_data = first_item['accounts']
                if debug_mode:
                    st.write(f"DEBUG: Extracted {len(accounts_data)} accounts from 'accounts' key")
            else:
                # The list might already be the accounts array
                if debug_mode:
                    st.write(f"DEBUG: Treating list as direct accounts array with {len(accounts_data)} items")
        elif isinstance(accounts_data, dict):
            # Check if it's a wrapper object with accounts inside
            if 'QueryResponse' in accounts_data and 'Account' in accounts_data['QueryResponse']:
                # QuickBooks QueryResponse format
                accounts_data = accounts_data['QueryResponse']['Account']
                if debug_mode:
                    st.write(f"DEBUG: Extracted {len(accounts_data)} accounts from QueryResponse")
            elif 'accounts' in accounts_data:
                # Some APIs wrap accounts in an 'accounts' key
                accounts_data = accounts_data['accounts']
                if debug_mode:
                    st.write(f"DEBUG: Extracted {len(accounts_data)} accounts from 'accounts' key")
            else:
                # Single account as dict
                accounts_data = [accounts_data]
                if debug_mode:
                    st.write("DEBUG: Converted single account dict to list")

        # Ensure we have a list
        if not isinstance(accounts_data, list):
            st.error(f"❌ Unexpected response format: {type(accounts_data)}")
            return None

        # Filter out any non-dict items
        accounts_data = [acc for acc in accounts_data if isinstance(acc, dict)]
        if debug_mode:
            st.write(f"DEBUG: Final account count after filtering: {len(accounts_data)}")

        # Additional validation
        if len(accounts_data) == 0:
            st.warning("⚠️ No valid account objects found in response")
        elif len(accounts_data) == 1:
            st.warning(f"⚠️ Only 1 account found. Expected multiple accounts based on QueryResponse structure.")
            if debug_mode:
                st.write(f"DEBUG: Single account: {accounts_data[0].get('Name', 'Unknown')}")
        else:
            st.success(f"✅ Successfully parsed {len(accounts_data)} accounts")

        return accounts_data

    except requests.exceptions.RequestException as e:
        st.warning(f"⚠️ Could not fetch QuickBooks accounts from API: {str(e)}")
        return None
    except Exception as e:
        st.error(f"❌ Error processing QuickBooks accounts: {str(e)}")
        import traceback
        st.error(f"Traceback: {traceback.format_exc()}")
        return None

def categorize_quickbooks_accounts(accounts_data):
    """Categorize QuickBooks accounts based on their classification and type"""
    if not accounts_data:
        return get_fallback_accounts()

    revenue_accounts = []
    asset_accounts = []
    liability_accounts = []
    expense_accounts = []

    # Also store account IDs for mapping
    account_ids = {}

    for account in accounts_data:
        try:
            name = account.get('FullyQualifiedName', account.get('Name', 'Unknown'))
            account_id = account.get('Id', '')
            classification = account.get('Classification', '').lower()
            account_type = account.get('AccountType', '').lower()
            account_subtype = account.get('AccountSubType', '').lower()
            active = account.get('Active', True)

            # Skip inactive accounts
            if not active:
                continue

            # Store account ID mapping
            account_ids[name] = account_id

            # Primary categorization based on classification
            if classification == 'revenue':
                revenue_accounts.append(name)
                # Debug: st.write(f"DEBUG: {name} -> Revenue (classification: {classification})")
            elif classification == 'asset':
                asset_accounts.append(name)
                # Debug: st.write(f"DEBUG: {name} -> Asset (classification: {classification})")
            elif classification == 'liability':
                liability_accounts.append(name)
                # Debug: st.write(f"DEBUG: {name} -> Liability (classification: {classification})")
            elif classification == 'expense':
                expense_accounts.append(name)
                # Debug: st.write(f"DEBUG: {name} -> Expense (classification: {classification})")
            else:
                # Secondary categorization based on account type
                if account_type in ['accounts receivable', 'accountsreceivable', 'bank accounts', 'bankaccounts',
                                   'other current assets', 'othercurrentassets', 'fixed assets', 'fixedassets',
                                   'other assets', 'otherassets', 'cash and cash equivalents', 'cashandcashequivalents']:
                    asset_accounts.append(name)
                    # Debug: st.write(f"DEBUG: {name} -> Asset (account_type: {account_type})")
                elif account_type in ['accounts payable', 'accountspayable', 'credit card', 'creditcard',
                                     'other current liabilities', 'othercurrentliabilities', 'long term liabilities',
                                     'longtermliabilities', 'other liabilities', 'otherliabilities']:
                    liability_accounts.append(name)
                    # Debug: st.write(f"DEBUG: {name} -> Liability (account_type: {account_type})")
                elif account_type in ['income', 'other income', 'otherincome', 'sales of product income',
                                     'salesofproductincome', 'service/fees income', 'service/feesincome']:
                    revenue_accounts.append(name)
                    # Debug: st.write(f"DEBUG: {name} -> Revenue (account_type: {account_type})")
                elif account_type in ['cost of goods sold', 'costofgoodssold', 'expenses', 'other expenses',
                                     'otherexpenses', 'cost of labor', 'costoflabor']:
                    expense_accounts.append(name)
                    # Debug: st.write(f"DEBUG: {name} -> Expense (account_type: {account_type})")
                else:
                    # Fallback categorization based on account subtype
                    if account_subtype in ['accountsreceivable', 'bank', 'cashandcashequivalents', 'clearing',
                                          'money market', 'moneymarket', 'rents held in trust', 'rentsheldintrust',
                                          'savings', 'trust accounts', 'trustaccounts']:
                        asset_accounts.append(name)
                    elif account_subtype in ['accountspayable', 'creditcard', 'lineofcredit', 'loanpayable']:
                        liability_accounts.append(name)
                    elif account_subtype in ['services', 'sales', 'salestaxpayable']:
                        revenue_accounts.append(name)
                    else:
                        # Final fallback based on name patterns
                        if any(keyword in name.lower() for keyword in ['revenue', 'sales', 'income', 'fees']):
                            revenue_accounts.append(name)
                        elif any(keyword in name.lower() for keyword in ['cash', 'bank', 'receivable', 'clearing', 'deposit']):
                            asset_accounts.append(name)
                        elif any(keyword in name.lower() for keyword in ['payable', 'liability', 'credit', 'loan']):
                            liability_accounts.append(name)
                        elif any(keyword in name.lower() for keyword in ['expense', 'cost', 'salary', 'wage']):
                            expense_accounts.append(name)
                        else:
                            # Default to asset for truly uncategorized accounts
                            asset_accounts.append(name)

        except Exception as e:
            st.warning(f"⚠️ Error processing account: {str(e)}")
            continue

    return {
        'Revenue Accounts': sorted(revenue_accounts),
        'Asset Accounts': sorted(asset_accounts),
        'Liability Accounts': sorted(liability_accounts),
        'Expense Accounts': sorted(expense_accounts),
        'Account IDs': account_ids
    }

def get_fallback_accounts():
    """Fallback accounts when API is unavailable"""
    return {
        'Revenue Accounts': [
            'Tour Revenue - General',
            'Tour Revenue - Whale Watching',
            'Tour Revenue - Bear Watching',
            'Tour Revenue - Hot Springs',
            'Fee Revenue - Park Fees',
            'Fee Revenue - Fuel Surcharge',
            'Fee Revenue - Stewardship',
            'Other Revenue'
        ],
        'Asset Accounts': [
            'Cash - Operating',
            'Cash - Savings',
            'Undeposited Funds',
            'Accounts Receivable',
            'Credit Card Clearing',
            'PayPal Clearing',
            'Square Clearing',
            'Stripe Clearing'
        ],
        'Liability Accounts': [
            'Accounts Payable - Affiliates',
            'Gift Card Liability',
            'Voucher Clearing',
            'Refunds Payable'
        ],
        'Expense Accounts': [],
        'Account IDs': {}  # Empty for fallback
    }

def test_api_connection():
    """Test the QuickBooks API connection and show response details"""
    if requests is None:
        st.error("❌ Requests library not available")
        return

    try:
        webhook_url = "https://n8n.fintask.ie/webhook/b25e21c8-fbf1-4cea-9fff-bf682956b0c1"

        with st.spinner("Testing API connection..."):
            response = requests.get(webhook_url, timeout=30)

        st.info(f"📡 **Response Status**: {response.status_code}")

        if response.status_code == 200:
            try:
                data = response.json()

                # Handle both single account and list of accounts
                if isinstance(data, dict):
                    accounts = [data]
                elif isinstance(data, list):
                    accounts = data
                else:
                    accounts = []

                st.success(f"✅ **Success!** Retrieved {len(accounts)} accounts")

                # Show sample account structure
                if accounts:
                    with st.expander("🔍 Sample Account Structure"):
                        sample = accounts[0]
                        st.json({
                            "Name": sample.get('Name', 'N/A'),
                            "FullyQualifiedName": sample.get('FullyQualifiedName', 'N/A'),
                            "Classification": sample.get('Classification', 'N/A'),
                            "AccountType": sample.get('AccountType', 'N/A'),
                            "AccountSubType": sample.get('AccountSubType', 'N/A'),
                            "Active": sample.get('Active', 'N/A')
                        })

                    # Show account type breakdown
                    classifications = {}
                    account_types = {}
                    for account in accounts:
                        classification = account.get('Classification', 'Unknown')
                        account_type = account.get('AccountType', 'Unknown')
                        classifications[classification] = classifications.get(classification, 0) + 1
                        account_types[account_type] = account_types.get(account_type, 0) + 1

                    col1, col2 = st.columns(2)
                    with col1:
                        st.write("**Account Classifications:**")
                        for classification, count in classifications.items():
                            st.write(f"- {classification}: {count} accounts")

                    with col2:
                        st.write("**Account Types:**")
                        for account_type, count in sorted(account_types.items()):
                            st.write(f"- {account_type}: {count} accounts")

                    # Test categorization
                    test_accounts = categorize_quickbooks_accounts(accounts[:5])  # Test with first 5 accounts
                    with st.expander("🧪 Categorization Test (First 5 accounts)"):
                        for category, account_list in test_accounts.items():
                            st.write(f"**{category}:** {len(account_list)} accounts")
                            if account_list:
                                for account in account_list[:3]:  # Show first 3
                                    st.write(f"  • {account}")

            except Exception as e:
                st.error(f"❌ Error parsing JSON response: {str(e)}")
                st.code(response.text[:500])
        else:
            st.error(f"❌ API returned status {response.status_code}")
            st.code(response.text[:500])

    except requests.exceptions.RequestException as e:
        st.error(f"❌ Connection Error: {str(e)}")
    except Exception as e:
        st.error(f"❌ Unexpected Error: {str(e)}")

def debug_raw_response():
    """Show raw API response for debugging purposes"""
    if requests is None:
        st.error("❌ Requests library not available")
        return

    try:
        webhook_url = "https://n8n.fintask.ie/webhook/b25e21c8-fbf1-4cea-9fff-bf682956b0c1"

        with st.spinner("Fetching raw response..."):
            response = requests.get(webhook_url, timeout=30)

        st.info(f"📡 **Response Status**: {response.status_code}")
        st.info(f"📏 **Response Length**: {len(response.text)} characters")

        # Show headers
        with st.expander("📋 Response Headers"):
            headers_df = pd.DataFrame(list(response.headers.items()), columns=['Header', 'Value'])
            st.dataframe(headers_df, use_container_width=True)

        # Show raw text (truncated if too long)
        max_length = 5000
        raw_text = response.text
        is_truncated = len(raw_text) > max_length

        with st.expander("📄 Raw Response Text" + (" (truncated)" if is_truncated else "")):
            display_text = raw_text[:max_length] + ("..." if is_truncated else "")
            st.code(display_text, language='json')

        # Try to parse as JSON and show structure
        if response.status_code == 200:
            try:
                data = response.json()

                with st.expander("🔍 Parsed JSON Structure"):
                    if isinstance(data, dict):
                        st.write("**Root Level Keys:**")
                        for key in data.keys():
                            if isinstance(data[key], (list, dict)):
                                st.write(f"- `{key}`: {type(data[key]).__name__} with {len(data[key])} items")
                            else:
                                st.write(f"- `{key}`: {type(data[key]).__name__} = {data[key]}")
                    elif isinstance(data, list):
                        st.write(f"**Root Level:** Array with {len(data)} items")
                        if data and len(data) > 0:
                            st.write("**First Item Structure:**")
                            if isinstance(data[0], dict):
                                for key in data[0].keys():
                                    value = data[0][key]
                                    if isinstance(value, (list, dict)):
                                        st.write(f"- `{key}`: {type(value).__name__} with {len(value)} items")
                                        # Special handling for QueryResponse
                                        if key == 'QueryResponse' and isinstance(value, dict):
                                            for subkey in value.keys():
                                                subvalue = value[subkey]
                                                if isinstance(subvalue, list):
                                                    st.write(f"  - `{subkey}`: Array with {len(subvalue)} items")
                                                    if subkey == 'Account' and len(subvalue) > 0:
                                                        st.write(f"    - First account: {subvalue[0].get('Name', 'Unknown')}")
                                                else:
                                                    st.write(f"  - `{subkey}`: {type(subvalue).__name__}")
                                    else:
                                        st.write(f"- `{key}`: {type(value).__name__} = {str(value)[:50]}{'...' if len(str(value)) > 50 else ''}")
                            else:
                                st.write(f"- Item type: {type(data[0]).__name__}")
                    else:
                        st.write(f"**Root Level:** {type(data).__name__}")

                    # QuickBooks specific analysis
                    if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
                        first_item = data[0]
                        if 'QueryResponse' in first_item and isinstance(first_item['QueryResponse'], dict):
                            qr = first_item['QueryResponse']
                            if 'Account' in qr and isinstance(qr['Account'], list):
                                accounts = qr['Account']
                                st.write(f"**QuickBooks Analysis:** Found {len(accounts)} accounts in QueryResponse.Account")
                                if accounts:
                                    # Show account classifications
                                    classifications = {}
                                    for acc in accounts:
                                        classification = acc.get('Classification', 'Unknown')
                                        classifications[classification] = classifications.get(classification, 0) + 1

                                    st.write("**Account Classifications:**")
                                    for cls, count in classifications.items():
                                        st.write(f"- {cls}: {count} accounts")

            except Exception as e:
                st.warning(f"⚠️ Could not parse as JSON: {str(e)}")

    except requests.exceptions.RequestException as e:
        st.error(f"❌ Connection Error: {str(e)}")
    except Exception as e:
        st.error(f"❌ Unexpected Error: {str(e)}")

def refresh_quickbooks_accounts():
    """Force refresh of QuickBooks accounts from API"""
    try:
        accounts_data = fetch_quickbooks_accounts()

        if accounts_data:
            categorized_accounts = categorize_quickbooks_accounts(accounts_data)
            st.session_state.qb_accounts_cache = categorized_accounts
            st.session_state.qb_accounts_last_fetch = pd.Timestamp.now()
            return len(accounts_data), categorized_accounts
        else:
            return None, None
    except Exception as e:
        st.error(f"❌ Error refreshing accounts: {str(e)}")
        return None, None

def get_asset_accounts():
    """Get only asset accounts from QuickBooks API"""
    try:
        accounts_data = fetch_quickbooks_accounts(asset_accounts_only=True)

        if accounts_data:
            # Categorize accounts and return only asset accounts
            categorized_accounts = categorize_quickbooks_accounts(accounts_data)

            # Store in session state for asset accounts specifically
            st.session_state.qb_asset_accounts = categorized_accounts.get('Asset Accounts', [])
            st.session_state.qb_asset_accounts_last_fetch = pd.Timestamp.now()

            asset_count = len(st.session_state.qb_asset_accounts)
            st.success(f"✅ Successfully loaded {asset_count} asset accounts")

            return st.session_state.qb_asset_accounts
        else:
            st.warning("⚠️ Failed to fetch asset accounts from API")
            return get_fallback_accounts().get('Asset Accounts', [])
    except Exception as e:
        st.error(f"❌ Error fetching asset accounts: {str(e)}")
        return get_fallback_accounts().get('Asset Accounts', [])

def get_quickbooks_accounts():
    """Get QuickBooks account list from cache or fallback"""
    # Check if we have cached accounts
    if hasattr(st.session_state, 'qb_accounts_cache'):
        return st.session_state.qb_accounts_cache

    # If no cached accounts, return fallback
    return get_fallback_accounts()

def create_tour_revenue_mappings_table(tours_list):
    """Create editable table for tour to revenue account mappings"""
    qb_accounts = get_quickbooks_accounts()
    revenue_accounts = qb_accounts.get('Revenue Accounts', [])

    if not tours_list:
        st.info("💡 Upload a sales CSV to populate tour mappings automatically.")
        return

    # Get existing mappings for this type
    existing_mappings = {
        mapping['fareharbour_item']: mapping
        for mapping in st.session_state.qb_mappings_data
        if mapping['mapping_type'] == 'tour_revenue'
    }

    # Prepare data for data editor - ensure consistency with session state
    mappings_data = []
    for tour in tours_list:
        existing = existing_mappings.get(tour, {})
        # Always use the value from session state if it exists, otherwise empty
        qb_account = existing.get('quickbooks_account', '') if existing else ''
        mappings_data.append({
            'Tour Name': tour,
            'QuickBooks Account': qb_account,
            'Status': 'Mapped' if existing and qb_account else 'Unmapped'
        })

    if mappings_data:
        # Create a unique key for this session to avoid conflicts
        editor_key = f"tour_mappings_editor_{len(tours_list)}_{hash(str(tours_list))}"

        # Use on_change callback to handle updates immediately
        def on_tour_mapping_change():
            # This will be called when data changes
            pass

        edited_df = st.data_editor(
            pd.DataFrame(mappings_data),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Tour Name": st.column_config.TextColumn("Tour Name", disabled=True, width="medium"),
                "QuickBooks Account": st.column_config.SelectboxColumn(
                    "QuickBooks Account", options=revenue_accounts, width="large"
                ),
                "Status": st.column_config.TextColumn("Status", disabled=True, width="small")
            },
            key=editor_key,
            on_change=on_tour_mapping_change
        )

        # Process changes and update session state
        changes_made = False
        for idx, row in edited_df.iterrows():
            tour_name = row['Tour Name']
            qb_account = row['QuickBooks Account']

            # Only update if there's an actual account selected
            if qb_account and qb_account.strip():
                existing = existing_mappings.get(tour_name, {})
                # Only update if the account has changed
                if existing.get('quickbooks_account') != qb_account:
                    mapping = {
                        'mapping_type': 'tour_revenue',
                        'fareharbour_item': tour_name,
                        'quickbooks_account': qb_account,
                        'account_type': 'revenue'
                    }
                    update_session_mapping(mapping)
                    changes_made = True

        # Force a rerun if changes were made to ensure UI updates
        if changes_made:
            st.rerun()

def create_fee_revenue_mappings_table(fees_list):
    """Create editable table for fee to revenue account mappings"""
    qb_accounts = get_quickbooks_accounts()
    revenue_accounts = qb_accounts.get('Revenue Accounts', [])

    if not fees_list:
        st.info("💡 Add fees in Tours & Fees Management to create fee mappings.")
        return

    # Get existing mappings for this type
    existing_mappings = {
        mapping['fareharbour_item']: mapping
        for mapping in st.session_state.qb_mappings_data
        if mapping['mapping_type'] == 'fee_revenue'
    }

    # Prepare data for data editor - ensure consistency with session state
    mappings_data = []
    for fee in fees_list:
        existing = existing_mappings.get(fee, {})
        # Always use the value from session state if it exists, otherwise empty
        qb_account = existing.get('quickbooks_account', '') if existing else ''
        mappings_data.append({
            'Fee Name': fee,
            'QuickBooks Account': qb_account,
            'Status': 'Mapped' if existing and qb_account else 'Unmapped'
        })

    if mappings_data:
        # Create a unique key for this session to avoid conflicts
        editor_key = f"fee_mappings_editor_{len(fees_list)}_{hash(str(fees_list))}"

        # Use on_change callback to handle updates immediately
        def on_fee_mapping_change():
            # This will be called when data changes
            pass

        edited_df = st.data_editor(
            pd.DataFrame(mappings_data),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Fee Name": st.column_config.TextColumn("Fee Name", disabled=True, width="medium"),
                "QuickBooks Account": st.column_config.SelectboxColumn(
                    "QuickBooks Account", options=revenue_accounts, width="large"
                ),
                "Status": st.column_config.TextColumn("Status", disabled=True, width="small")
            },
            key=editor_key,
            on_change=on_fee_mapping_change
        )

        # Process changes and update session state
        changes_made = False
        for idx, row in edited_df.iterrows():
            fee_name = row['Fee Name']
            qb_account = row['QuickBooks Account']

            # Only update if there's an actual account selected
            if qb_account and qb_account.strip():
                existing = existing_mappings.get(fee_name, {})
                # Only update if the account has changed
                if existing.get('quickbooks_account') != qb_account:
                    mapping = {
                        'mapping_type': 'fee_revenue',
                        'fareharbour_item': fee_name,
                        'quickbooks_account': qb_account,
                        'account_type': 'revenue'
                    }
                    update_session_mapping(mapping)
                    changes_made = True

        # Force a rerun if changes were made to ensure UI updates
        if changes_made:
            st.rerun()

def create_payment_type_mappings_table(payment_types_list):
    """Create editable table for payment type to bank/clearing account mappings"""
    # Use dedicated asset accounts for payment mappings
    if hasattr(st.session_state, 'qb_asset_accounts'):
        asset_accounts = st.session_state.qb_asset_accounts
    else:
        # Fallback to general accounts if asset accounts not loaded
        qb_accounts = get_quickbooks_accounts()
        asset_accounts = qb_accounts.get('Asset Accounts', [])

    if not payment_types_list:
        st.info("💡 Upload a sales CSV to populate payment type mappings automatically.")
        return

    # Check if asset accounts are loaded
    asset_accounts_loaded = hasattr(st.session_state, 'qb_asset_accounts') and st.session_state.qb_asset_accounts

    if asset_accounts_loaded:
        st.success(f"✅ Using {len(asset_accounts)} QuickBooks asset accounts for payment mappings")
    else:
        st.warning("⚠️ **Asset accounts not loaded yet!** Payment type dropdowns will show fallback accounts.")
        st.info("💰 Click 'Load Asset Accounts' in the sidebar to get real QuickBooks asset accounts for payment mappings.")

    # Get existing mappings for this type
    existing_mappings = {
        mapping['fareharbour_item']: mapping
        for mapping in st.session_state.qb_mappings_data
        if mapping['mapping_type'] == 'payment_type'
    }

    # Prepare data for data editor - ensure consistency with session state
    mappings_data = []
    for payment_type in payment_types_list:
        existing = existing_mappings.get(payment_type, {})
        # Always use the value from session state if it exists, otherwise empty
        qb_account = existing.get('quickbooks_account', '') if existing else ''
        mappings_data.append({
            'Payment Type': payment_type,
            'QuickBooks Account': qb_account,
            'Status': 'Mapped' if existing and qb_account else 'Unmapped'
        })

    if mappings_data:
        # Create a unique key for this session to avoid conflicts
        editor_key = f"payment_mappings_editor_{len(payment_types_list)}_{hash(str(payment_types_list))}"

        # Use on_change callback to handle updates immediately
        def on_payment_mapping_change():
            # This will be called when data changes
            pass

        edited_df = st.data_editor(
            pd.DataFrame(mappings_data),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Payment Type": st.column_config.TextColumn("Payment Type", disabled=True, width="medium"),
                "QuickBooks Account": st.column_config.SelectboxColumn(
                    "QuickBooks Account", options=asset_accounts, width="large"
                ),
                "Status": st.column_config.TextColumn("Status", disabled=True, width="small")
            },
            key=editor_key,
            on_change=on_payment_mapping_change
        )

        # Process changes and update session state
        changes_made = False
        for idx, row in edited_df.iterrows():
            payment_type = row['Payment Type']
            qb_account = row['QuickBooks Account']

            # Only update if there's an actual account selected
            if qb_account and qb_account.strip():
                existing = existing_mappings.get(payment_type, {})
                # Only update if the account has changed
                if existing.get('quickbooks_account') != qb_account:
                    mapping = {
                        'mapping_type': 'payment_type',
                        'fareharbour_item': payment_type,
                        'quickbooks_account': qb_account,
                        'account_type': 'asset'
                    }
                    update_session_mapping(mapping)
                    changes_made = True

        # Force a rerun if changes were made to ensure UI updates
        if changes_made:
            st.rerun()

def update_session_mapping(mapping):
    """Update mapping in session state"""
    # Find existing mapping or add new one
    mapping_key = f"{mapping['mapping_type']}_{mapping['fareharbour_item']}"

    # Get account ID from QuickBooks accounts cache if available
    qb_accounts = get_quickbooks_accounts()
    account_ids = qb_accounts.get('Account IDs', {})
    quickbooks_account = mapping.get('quickbooks_account', '')

    # Add account ID to mapping if available
    if quickbooks_account and quickbooks_account in account_ids:
        mapping['quickbooks_account_id'] = account_ids[quickbooks_account]
    else:
        mapping['quickbooks_account_id'] = ''

    # Update existing or add new
    existing_index = None
    for i, existing in enumerate(st.session_state.qb_mappings_data):
        if (existing['mapping_type'] == mapping['mapping_type'] and
            existing['fareharbour_item'] == mapping['fareharbour_item']):
            existing_index = i
            break

    if existing_index is not None:
        st.session_state.qb_mappings_data[existing_index].update(mapping)
    else:
        st.session_state.qb_mappings_data.append(mapping)

def load_quickbooks_mappings():
    """Load QuickBooks mappings from database"""
    try:
        mappings = execute_query("""
            SELECT mapping_type, fareharbour_item, quickbooks_account, account_type, is_active, quickbooks_account_id
            FROM quickbooks_mappings
            WHERE is_active = true
            ORDER BY mapping_type, fareharbour_item
        """)

        if mappings:
            mapping_list = [
                {
                    'mapping_type': mapping[0],
                    'fareharbour_item': mapping[1],
                    'quickbooks_account': mapping[2],
                    'account_type': mapping[3],
                    'is_active': mapping[4],
                    'quickbooks_account_id': mapping[5] if len(mapping) > 5 else ''
                }
                for mapping in mappings
            ]
            st.success(f"✅ Loaded {len(mapping_list)} QuickBooks mappings from database")
            return mapping_list
        else:
            st.info("ℹ️ No QuickBooks mappings found in database")
            return []

    except Exception as e:
        if "SSL connection has been closed" in str(e) or "connection" in str(e).lower():
            st.warning("⚠️ Database connection issue. Unable to load existing mappings.")
            return []
        else:
            st.error(f"❌ Error loading QuickBooks mappings: {str(e)}")
            return []

def save_all_mappings():
    """Save all mappings to database with enhanced debugging"""
    import time
    start_time = time.time()

    try:
        debug_mode = st.session_state.get('qb_debug_mode', False)

        if debug_mode:
            st.write("🐛 **=== ENHANCED DEBUG MODE: Saving Mappings ===**")
            st.write("---")

            # Show initial state
            with st.expander("📊 **Initial State Analysis**", expanded=True):
                total_mappings = len(st.session_state.qb_mappings_data)
                st.write(f"📋 **Total mappings in session:** {total_mappings}")

                if total_mappings > 0:
                    # Group mappings by type
                    mapping_types = {}
                    for mapping in st.session_state.qb_mappings_data:
                        mt = mapping.get('mapping_type', 'unknown')
                        mapping_types[mt] = mapping_types.get(mt, 0) + 1

                    st.write("**Mapping breakdown by type:**")
                    for mt, count in mapping_types.items():
                        st.write(f"  • {mt}: {count} mappings")

                    # Show sample mappings
                    st.write("**Sample mappings (first 3):**")
                    for i, mapping in enumerate(st.session_state.qb_mappings_data[:3]):
                        st.write(f"  {i+1}. [{mapping.get('mapping_type', 'unknown')}] {mapping.get('fareharbour_item', 'N/A')} → {mapping.get('quickbooks_account', 'N/A')}")

                # Check database state before save
                try:
                    existing_count = execute_query("SELECT COUNT(*) FROM quickbooks_mappings WHERE is_active = true")
                    if existing_count:
                        st.write(f"📊 **Active mappings in database before save:** {existing_count[0][0]}")
                except Exception as db_check_error:
                    st.warning(f"⚠️ Could not check existing database state: {str(db_check_error)}")

        # Phase 1: Deactivate existing mappings
        if debug_mode:
            st.write("---")
            st.write("📝 **Phase 1: Deactivating existing mappings**")

        try:
            deactivate_result = execute_query("UPDATE quickbooks_mappings SET is_active = false, updated_at = CURRENT_TIMESTAMP")
            if debug_mode:
                st.success("✅ Successfully deactivated existing mappings")
                if deactivate_result is not None:
                    st.write(f"   Rows affected: {deactivate_result}")
        except Exception as deactivate_error:
            if debug_mode:
                st.error(f"❌ Error deactivating mappings: {str(deactivate_error)}")
            raise

        # Phase 2: Process each mapping
        if debug_mode:
            st.write("---")
            st.write("🔄 **Phase 2: Processing individual mappings**")

        success_count = 0
        failed_mappings = []
        skipped_mappings = []
        processed_mappings = []

        for i, mapping in enumerate(st.session_state.qb_mappings_data):
            mapping_start_time = time.time()

            if debug_mode:
                with st.expander(f"🔍 **Processing Mapping {i+1}/{len(st.session_state.qb_mappings_data)}**", expanded=False):
                    st.write(f"**Raw mapping data:** {mapping}")

            # Validation Phase
            fh_item = mapping.get('fareharbour_item')
            qb_account = mapping.get('quickbooks_account')

            if debug_mode:
                st.write("**Validation Results:**")

            if not fh_item:
                if debug_mode:
                    st.error("❌ Missing fareharbour_item")
                failed_mappings.append(f"Mapping {i+1}: Missing fareharbour_item")
                continue

            if not qb_account:
                if debug_mode:
                    st.warning("⚠️ No QuickBooks account selected - skipping")
                skipped_mappings.append(f"Mapping {i+1}: {fh_item} (no QB account)")
                continue

            # Field validation
            required_fields = ['mapping_type', 'fareharbour_item', 'quickbooks_account', 'account_type']
            missing_fields = [field for field in required_fields if not mapping.get(field)]
            if missing_fields:
                if debug_mode:
                    st.error(f"❌ Missing required fields: {missing_fields}")
                failed_mappings.append(f"Mapping {i+1}: Missing fields {missing_fields}")
                continue

            if debug_mode:
                st.success("✅ All validations passed")

            # Database operations
            try:
                if debug_mode:
                    st.write("**Database Operations:**")

                # First, try UPDATE
                update_params = {
                    'qb_account': mapping['quickbooks_account'],
                    'account_type': mapping['account_type'],
                    'mapping_type': mapping['mapping_type'],
                    'fh_item': mapping['fareharbour_item'],
                    'qb_account_id': mapping.get('quickbooks_account_id', '')
                }

                if debug_mode:
                    st.write("1️⃣ **UPDATE Query:**")
                    st.code(f"""
UPDATE quickbooks_mappings
SET quickbooks_account = '{mapping['quickbooks_account']}',
    account_type = '{mapping['account_type']}',
    quickbooks_account_id = '{mapping.get('quickbooks_account_id', '')}',
    is_active = true,
    updated_at = CURRENT_TIMESTAMP
WHERE mapping_type = '{mapping['mapping_type']}'
AND fareharbour_item = '{mapping['fareharbour_item']}'
""", language='sql')

                update_result = execute_query("""
                    UPDATE quickbooks_mappings
                    SET quickbooks_account = :qb_account,
                        account_type = :account_type,
                        quickbooks_account_id = :qb_account_id,
                        is_active = true,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE mapping_type = :mapping_type
                    AND fareharbour_item = :fh_item
                """, update_params)

                if debug_mode:
                    st.write(f"   UPDATE result: {update_result}")

                # Then INSERT with ON CONFLICT
                if debug_mode:
                    st.write("2️⃣ **INSERT Query (with ON CONFLICT):**")
                    st.code(f"""
INSERT INTO quickbooks_mappings (mapping_type, fareharbour_item, quickbooks_account, account_type, quickbooks_account_id)
VALUES ('{mapping['mapping_type']}', '{mapping['fareharbour_item']}', '{mapping['quickbooks_account']}', '{mapping['account_type']}', '{mapping.get('quickbooks_account_id', '')}')
ON CONFLICT (mapping_type, fareharbour_item) DO UPDATE SET
    quickbooks_account = EXCLUDED.quickbooks_account,
    account_type = EXCLUDED.account_type,
    quickbooks_account_id = EXCLUDED.quickbooks_account_id,
    is_active = true,
    updated_at = CURRENT_TIMESTAMP
""", language='sql')

                insert_result = execute_query("""
                    INSERT INTO quickbooks_mappings (mapping_type, fareharbour_item, quickbooks_account, account_type, quickbooks_account_id)
                    VALUES (:mapping_type, :fh_item, :qb_account, :account_type, :qb_account_id)
                    ON CONFLICT (mapping_type, fareharbour_item) DO UPDATE SET
                    quickbooks_account = EXCLUDED.quickbooks_account,
                    account_type = EXCLUDED.account_type,
                    quickbooks_account_id = EXCLUDED.quickbooks_account_id,
                    is_active = true,
                    updated_at = CURRENT_TIMESTAMP
                """, {
                    'mapping_type': mapping['mapping_type'],
                    'fh_item': mapping['fareharbour_item'],
                    'qb_account': mapping['quickbooks_account'],
                    'account_type': mapping['account_type'],
                    'qb_account_id': mapping.get('quickbooks_account_id', '')
                })

                success_count += 1
                processing_time = time.time() - mapping_start_time
                processed_mappings.append(mapping)

                if debug_mode:
                    st.success(f"✅ **SUCCESS** - Saved in {processing_time:.2f}s")
                    st.write(f"   Final mapping: {mapping['fareharbour_item']} → {mapping['quickbooks_account']}")
                    qb_account_id = mapping.get('quickbooks_account_id', '')
                    if qb_account_id:
                        st.write(f"   Account ID: {qb_account_id}")
                    else:
                        st.write(f"   Account ID: Not available")

            except Exception as db_error:
                processing_time = time.time() - mapping_start_time
                error_msg = f"Mapping {i+1}: DB error after {processing_time:.2f}s - {str(db_error)}"
                failed_mappings.append(error_msg)
                if debug_mode:
                    st.error(f"❌ **DATABASE ERROR** ({processing_time:.2f}s): {str(db_error)}")
                    st.code(f"Full error details: {str(db_error)}")

        # Phase 3: Summary and Verification
        total_time = time.time() - start_time

        if debug_mode:
            st.write("---")
            with st.expander("📈 **Final Summary & Verification**", expanded=True):
                st.write("**Performance Metrics:**")
                st.write(f"  • Total processing time: {total_time:.2f} seconds")
                st.write(f"  • Average time per mapping: {total_time/max(1, len(st.session_state.qb_mappings_data)):.2f} seconds")
                st.write(f"  • Success rate: {success_count}/{len(st.session_state.qb_mappings_data)} ({success_count/max(1, len(st.session_state.qb_mappings_data))*100:.1f}%)")

                st.write("**Results:**")
                st.write(f"  • ✅ Successfully saved: {success_count} mappings")
                st.write(f"  • ⚠️ Skipped (no QB account): {len(skipped_mappings)} mappings")
                st.write(f"  • ❌ Failed: {len(failed_mappings)} mappings")

                # Verify database state
                try:
                    final_count = execute_query("SELECT COUNT(*) FROM quickbooks_mappings WHERE is_active = true")
                    if final_count:
                        st.write(f"  • 📊 Active mappings in database: {final_count[0][0]}")

                    # Show breakdown by mapping type
                    type_breakdown = execute_query("""
                        SELECT mapping_type, COUNT(*) as count
                        FROM quickbooks_mappings
                        WHERE is_active = true
                        GROUP BY mapping_type
                        ORDER BY mapping_type
                    """)
                    if type_breakdown:
                        st.write("**Database breakdown by type:**")
                        for row in type_breakdown:
                            st.write(f"    • {row[0]}: {row[1]} mappings")

                    # Show account ID coverage
                    id_coverage = execute_query("""
                        SELECT
                            COUNT(*) as total_mappings,
                            COUNT(quickbooks_account_id) as mappings_with_id,
                            ROUND(
                                (COUNT(quickbooks_account_id)::numeric / NULLIF(COUNT(*), 0)) * 100, 1
                            ) as coverage_percentage
                        FROM quickbooks_mappings
                        WHERE is_active = true
                    """)
                    if id_coverage:
                        total, with_id, coverage = id_coverage[0]
                        st.write("**QuickBooks Account ID Coverage:**")
                        st.write(f"    • Total mappings: {total}")
                        st.write(f"    • With Account ID: {with_id}")
                        st.write(f"    • Coverage: {coverage}%")

                except Exception as verify_error:
                    st.warning(f"⚠️ Could not verify final database state: {str(verify_error)}")

        # Show user-friendly results
        if success_count > 0:
            st.success(f"✅ Successfully saved {success_count} mappings to database")
        else:
            st.warning("⚠️ No mappings were saved")

        if skipped_mappings:
            st.info(f"ℹ️ Skipped {len(skipped_mappings)} mappings with no QuickBooks account selected")

        # Show detailed error information in debug mode
        if failed_mappings and debug_mode:
            with st.expander("❌ **Detailed Error Report**", expanded=True):
                st.write(f"**Total failures: {len(failed_mappings)}**")
                for i, failure in enumerate(failed_mappings, 1):
                    st.write(f"{i}. {failure}")

        if skipped_mappings and debug_mode:
            with st.expander("⚠️ **Skipped Mappings**", expanded=False):
                st.write(f"**Total skipped: {len(skipped_mappings)}**")
                for i, skipped in enumerate(skipped_mappings, 1):
                    st.write(f"{i}. {skipped}")

        if debug_mode and processed_mappings:
            with st.expander("✅ **Successfully Processed Mappings**", expanded=False):
                st.write(f"**Total processed: {len(processed_mappings)}**")
                for i, mapping in enumerate(processed_mappings[:10], 1):  # Show first 10
                    account_id = mapping.get('quickbooks_account_id', '')
                    id_info = f" (ID: {account_id})" if account_id else " (No ID)"
                    st.write(f"{i}. [{mapping.get('mapping_type')}] {mapping.get('fareharbour_item')} → {mapping.get('quickbooks_account')}{id_info}")
                if len(processed_mappings) > 10:
                    st.write(f"... and {len(processed_mappings) - 10} more")

        return success_count > 0

    except Exception as e:
        total_time = time.time() - start_time
        if "SSL connection has been closed" in str(e) or "connection" in str(e).lower():
            st.error("❌ Database connection lost. Please try again later.")
            st.info("💡 Your mappings are still available in the session. Try saving again when connection is restored.")
        else:
            st.error(f"❌ Error saving mappings: {str(e)}")
            if debug_mode:
                st.code(f"Full error after {total_time:.2f}s: {str(e)}")
        return False

def show_mapping_summary():
    """Show summary of current mappings"""
    if not st.session_state.qb_mappings_data:
        st.info("💡 No mappings configured yet.")
        return

    # Group by mapping type
    tour_mappings = [m for m in st.session_state.qb_mappings_data if m['mapping_type'] == 'tour_revenue' and m.get('quickbooks_account')]
    fee_mappings = [m for m in st.session_state.qb_mappings_data if m['mapping_type'] == 'fee_revenue' and m.get('quickbooks_account')]
    payment_mappings = [m for m in st.session_state.qb_mappings_data if m['mapping_type'] == 'payment_type' and m.get('quickbooks_account')]

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Tour Mappings", len(tour_mappings))
        if tour_mappings:
            with st.expander("View Tour Mappings"):
                for mapping in tour_mappings:
                    account_id = mapping.get('quickbooks_account_id', '')
                    id_info = f" (ID: {account_id})" if account_id else ""
                    st.write(f"• {mapping['fareharbour_item']} → {mapping['quickbooks_account']}{id_info}")

    with col2:
        st.metric("Fee Mappings", len(fee_mappings))
        if fee_mappings:
            with st.expander("View Fee Mappings"):
                for mapping in fee_mappings:
                    account_id = mapping.get('quickbooks_account_id', '')
                    id_info = f" (ID: {account_id})" if account_id else ""
                    st.write(f"• {mapping['fareharbour_item']} → {mapping['quickbooks_account']}{id_info}")

    with col3:
        st.metric("Payment Mappings", len(payment_mappings))
        if payment_mappings:
            with st.expander("View Payment Mappings"):
                for mapping in payment_mappings:
                    account_id = mapping.get('quickbooks_account_id', '')
                    id_info = f" (ID: {account_id})" if account_id else ""
                    st.write(f"• {mapping['fareharbour_item']} → {mapping['quickbooks_account']}{id_info}")
