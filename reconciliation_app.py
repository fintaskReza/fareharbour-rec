import streamlit as st
from scripts.config import PAGE_CONFIG
from scripts.auth import check_authentication
from views.main_reconciliation_view import main_reconciliation_view
from views.tours_fees_view import manage_tours_and_fees
from views.sales_analysis_view import sales_report_analysis
from views.quickbooks_mappings_view import quickbooks_mappings_page

# Set page config
st.set_page_config(**PAGE_CONFIG)

# Check authentication first
check_authentication()

def main():
    """Main application entry point with navigation"""
    # Initialize current page if not set
    if "current_page" not in st.session_state:
        st.session_state.current_page = "sales_analysis"

    # Add navigation in sidebar
    st.sidebar.title("📋 Navigation")

    # Create sidebar navigation buttons with dynamic styling
    if st.sidebar.button("🔍 Reconciliation",
                       type="primary" if st.session_state.current_page == "reconciliation" else "secondary",
                       use_container_width=True):
        st.session_state.current_page = "reconciliation"
    if st.sidebar.button("🎯 Tours & Fees Management",
                       type="primary" if st.session_state.current_page == "tours_fees" else "secondary",
                       use_container_width=True):
        st.session_state.current_page = "tours_fees"
    if st.sidebar.button("📊 Sales Report Analysis",
                       type="primary" if st.session_state.current_page == "sales_analysis" else "secondary",
                       use_container_width=True):
        st.session_state.current_page = "sales_analysis"
    if st.sidebar.button("🔗 QuickBooks Mappings",
                       type="primary" if st.session_state.current_page == "qb_mappings" else "secondary",
                       use_container_width=True):
        st.session_state.current_page = "qb_mappings"

    # Add a separator
    st.sidebar.markdown("---")

    # Show current page indicator
    current_page_names = {
        "reconciliation": "🔍 Reconciliation",
        "tours_fees": "🎯 Tours & Fees Management",
        "sales_analysis": "📊 Sales Report Analysis",
        "qb_mappings": "🔗 QuickBooks Mappings"
    }

    st.sidebar.markdown(f"**Current Page:** {current_page_names[st.session_state.current_page]}")

    # Route to appropriate page
    if st.session_state.current_page == "tours_fees":
        manage_tours_and_fees()
    elif st.session_state.current_page == "sales_analysis":
        sales_report_analysis()
    elif st.session_state.current_page == "qb_mappings":
        quickbooks_mappings_page()
    else:
        # Default to sales report analysis page
        sales_report_analysis()


if __name__ == "__main__":
    main() 