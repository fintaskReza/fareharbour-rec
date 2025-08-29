# Tours and Fees Management View
import streamlit as st
import pandas as pd
from scripts.database import execute_query

def manage_tours_and_fees():
    """Tours and Fees Management Page"""
    st.title("🎯 Tours & Fees Management")

    # Compact CSS styling
    st.markdown("""
    <style>
    .stTabs [data-baseweb="tab-list"] {gap: 4px; margin-bottom: 1rem;}
    .stTabs [data-baseweb="tab"] {padding: 8px 16px; font-size: 0.9rem;}
    .stButton > button {border-radius: 6px; margin: 2px;}
    .element-container {margin-bottom: 0.5rem;}
    </style>
    """, unsafe_allow_html=True)

    # Create tabs for different operations
    tab1, tab2, tab3 = st.tabs(["🎪 Tours", "💰 Fees", "🔗 Mappings"])

    with tab1:
        st.subheader("🎪 Tours Management")

        # Add new tour
        col1, col2 = st.columns([3, 1])
        with col1:
            new_tour_name = st.text_input("New Tour Name", key="new_tour", placeholder="Enter tour name")
        with col2:
            if st.button("➕ Add Tour", key="add_tour_btn", type="primary"):
                if new_tour_name.strip():
                    result = execute_query("INSERT INTO tours (name) VALUES (:name)", {"name": new_tour_name.strip()})
                    if result:
                        st.success(f"✅ Tour '{new_tour_name}' added!")
                        st.rerun()
                else:
                    st.error("❌ Please enter a tour name")

        # Edit existing tours
        tours = execute_query("SELECT id, name FROM tours ORDER BY name")

        if tours:
            st.write(f"**{len(tours)} tours available**")

            # Initialize session state for tour editing
            if 'tour_edits' not in st.session_state:
                st.session_state.tour_edits = {tour[0]: {'name': tour[1]} for tour in tours}

            for tour in tours:
                tour_id, original_name = tour[0], tour[1]
                col1, col2 = st.columns([4, 1])
                with col1:
                    new_name = st.text_input(
                        f"Tour {tour_id}",
                        value=st.session_state.tour_edits.get(tour_id, {}).get('name', original_name),
                        key=f"tour_name_{tour_id}",
                        label_visibility="collapsed"
                    )
                    st.session_state.tour_edits[tour_id] = {'name': new_name}

                with col2:
                    if st.button("🗑️", key=f"delete_tour_{tour_id}", help=f"Delete '{original_name}'"):
                        result = execute_query("DELETE FROM tours WHERE id = :id", {"id": tour_id})
                        if result:
                            st.success(f"✅ Tour '{original_name}' deleted!")
                            if tour_id in st.session_state.tour_edits:
                                del st.session_state.tour_edits[tour_id]
                            st.rerun()

            # Quick actions
            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("🔄 Reset All", key="reset_tours"):
                    for tour in tours:
                        tour_id = tour[0]
                        st.session_state.tour_edits[tour_id] = {'name': tour[1]}
                    st.success("✅ Reset all tours!")
                    st.rerun()

            with col2:
                if st.button("💾 Save All", key="save_all_tours", type="primary"):
                    updated_count = 0
                    for tour_id, edit_data in st.session_state.tour_edits.items():
                        if edit_data['name'].strip():
                            result = execute_query(
                                "UPDATE tours SET name = :name, updated_at = CURRENT_TIMESTAMP WHERE id = :id",
                                {"name": edit_data['name'].strip(), "id": tour_id}
                            )
                            if result:
                                updated_count += 1
                    if updated_count > 0:
                        st.success(f"✅ Updated {updated_count} tour(s)!")
                        st.rerun()

            with col3:
                if st.button("🗑️ Delete All", key="delete_all_tours"):
                    if st.session_state.get('confirm_delete_all_tours', False):
                        result = execute_query("DELETE FROM tours")
                        if result:
                            st.success("✅ All tours deleted!")
                            st.session_state.tour_edits = {}
                            st.session_state.confirm_delete_all_tours = False
                            st.rerun()
                    else:
                        st.session_state.confirm_delete_all_tours = True
                        st.warning("⚠️ Click again to confirm deletion of ALL tours!")

        else:
            st.info("🎪 No tours yet. Add your first tour above to get started!")

    with tab2:
        st.subheader("💰 Fees Management")

        # Add new fee
        col1, col2, col3 = st.columns([3, 1.5, 1])
        with col1:
            new_fee_name = st.text_input("Fee Name", key="new_fee", placeholder="Enter fee name")
        with col2:
            new_fee_amount = st.number_input("Amount", min_value=0.0, step=0.01, key="new_fee_amount")
        with col3:
            if st.button("➕ Add", key="add_fee_btn", type="primary"):
                if new_fee_name.strip():
                    result = execute_query(
                        "INSERT INTO fees (name, per_person_amount, apply_to_all) VALUES (:name, :amount, :apply_all)",
                        {"name": new_fee_name.strip(), "amount": new_fee_amount, "apply_all": False}
                    )
                    if result:
                        st.success(f"✅ Fee '{new_fee_name}' added!")
                        st.rerun()
                else:
                    st.error("❌ Please enter a fee name")

        # Edit existing fees
        fees = execute_query("SELECT id, name, per_person_amount FROM fees ORDER BY name")

        if fees:
            st.write(f"**{len(fees)} fees available**")

            # Initialize session state for fee editing
            if 'fee_edits' not in st.session_state:
                st.session_state.fee_edits = {fee[0]: {'name': fee[1], 'amount': float(fee[2])} for fee in fees}

            for fee in fees:
                fee_id, original_name, original_amount = fee[0], fee[1], fee[2]
                col1, col2, col3 = st.columns([3, 1.5, 1])

                with col1:
                    new_name = st.text_input(
                        f"Fee {fee_id}",
                        value=st.session_state.fee_edits.get(fee_id, {}).get('name', original_name),
                        key=f"fee_name_{fee_id}",
                        label_visibility="collapsed"
                    )
                    st.session_state.fee_edits[fee_id] = st.session_state.fee_edits.get(fee_id, {})
                    st.session_state.fee_edits[fee_id]['name'] = new_name

                with col2:
                    new_amount = st.number_input(
                        f"Amount {fee_id}",
                        value=st.session_state.fee_edits.get(fee_id, {}).get('amount', float(original_amount)),
                        min_value=0.0,
                        step=0.01,
                        key=f"fee_amount_{fee_id}",
                        label_visibility="collapsed"
                    )
                    st.session_state.fee_edits[fee_id]['amount'] = new_amount

                with col3:
                    if st.button("🗑️", key=f"delete_fee_{fee_id}", help=f"Delete '{original_name}'"):
                        result = execute_query("DELETE FROM fees WHERE id = :id", {"id": fee_id})
                        if result:
                            st.success(f"✅ Fee '{original_name}' deleted!")
                            if fee_id in st.session_state.fee_edits:
                                del st.session_state.fee_edits[fee_id]
                            st.rerun()

            # Quick actions
            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("🔄 Reset All", key="reset_fees"):
                    for fee in fees:
                        fee_id = fee[0]
                        st.session_state.fee_edits[fee_id] = {'name': fee[1], 'amount': float(fee[2])}
                    st.success("✅ Reset all fees!")
                    st.rerun()

            with col2:
                if st.button("💾 Save All", key="save_all_fees", type="primary"):
                    updated_count = 0
                    for fee_id, edit_data in st.session_state.fee_edits.items():
                        if edit_data['name'].strip():
                            result = execute_query(
                                "UPDATE fees SET name = :name, per_person_amount = :amount, updated_at = CURRENT_TIMESTAMP WHERE id = :id",
                                {"name": edit_data['name'].strip(), "amount": edit_data['amount'], "id": fee_id}
                            )
                            if result:
                                updated_count += 1
                    if updated_count > 0:
                        st.success(f"✅ Updated {updated_count} fee(s)!")
                        st.rerun()

            with col3:
                if st.button("🗑️ Delete All", key="delete_all_fees"):
                    if st.session_state.get('confirm_delete_all', False):
                        result = execute_query("DELETE FROM fees")
                        if result:
                            st.success("✅ All fees deleted!")
                            st.session_state.fee_edits = {}
                            st.session_state.confirm_delete_all = False
                            st.rerun()
                    else:
                        st.session_state.confirm_delete_all = True
                        st.warning("⚠️ Click again to confirm deletion of ALL fees!")

        else:
            st.info("💰 No fees yet. Add your first fee above to get started!")

    with tab3:
        st.subheader("🔗 Tour-Fee Mappings")

        # Get tours and fees
        tours = execute_query("SELECT id, name FROM tours ORDER BY name")
        fees = execute_query("SELECT id, name, per_person_amount FROM fees ORDER BY name")

        if not tours:
            st.warning("🎪 Add tours first in the Tours tab.")
            return

        if not fees:
            st.warning("💰 Add fees first in the Fees tab.")
            return

        # Get existing mappings
        existing_mappings = execute_query("SELECT tour_id, fee_id FROM tour_fees")
        existing_set = set((mapping[0], mapping[1]) for mapping in existing_mappings) if existing_mappings else set()

        # Create matrix data
        matrix_data = []
        for tour in tours:
            tour_id, tour_name = tour[0], tour[1]
            row = {"Tour": tour_name, "tour_id": tour_id}
            for fee in fees:
                fee_id, fee_name, fee_amount = fee[0], fee[1], fee[2]
                row[f"{fee_name} (${fee_amount})"] = (tour_id, fee_id) in existing_set
            matrix_data.append(row)

        df = pd.DataFrame(matrix_data)
        st.write(f"**{len(tours)} tours × {len(fees)} fees** - Check boxes to assign fees to tours")

        # Configure data editor
        column_config = {
            "Tour": st.column_config.TextColumn("Tour Name", disabled=True, width="medium"),
            "tour_id": None
        }

        for fee in fees:
            fee_id, fee_name, fee_amount = fee[0], fee[1], fee[2]
            column_config[f"{fee_name} (${fee_amount})"] = st.column_config.CheckboxColumn(
                fee_name, default=False, width="small"
            )

        edited_df = st.data_editor(
            df,
            column_config=column_config,
            hide_index=True,
            use_container_width=True,
            key="tour_fee_mappings_editor"
        )

        # Save button
        if not edited_df.equals(df):
            st.warning("⚠️ You have unsaved changes!")

        col1, col2, col3 = st.columns(3)
        with col2:
            if st.button("💾 Save Changes", key="save_mappings_table", type="primary"):
                try:
                    old_mappings = set()
                    for _, row in df.iterrows():
                        tour_id = row["tour_id"]
                        for fee in fees:
                            fee_id, fee_name, fee_amount = fee[0], fee[1], fee[2]
                            if row[f"{fee_name} (${fee_amount})"]:
                                old_mappings.add((tour_id, fee_id))

                    new_mappings = set()
                    for _, row in edited_df.iterrows():
                        tour_id = row["tour_id"]
                        for fee in fees:
                            fee_id, fee_name, fee_amount = fee[0], fee[1], fee[2]
                            if row[f"{fee_name} (${fee_amount})"]:
                                new_mappings.add((tour_id, fee_id))

                    added = new_mappings - old_mappings
                    removed = old_mappings - new_mappings

                    if added or removed:
                        execute_query("DELETE FROM tour_fees")
                        if new_mappings:
                            for tour_id, fee_id in new_mappings:
                                execute_query("INSERT INTO tour_fees (tour_id, fee_id) VALUES (:tour_id, :fee_id)",
                                            {"tour_id": tour_id, "fee_id": fee_id})

                        st.success(f"✅ Saved! {len(added)} added, {len(removed)} removed. Total: {len(new_mappings)}")
                        st.rerun()
                    else:
                        st.info("💡 No changes detected")

                except Exception as e:
                    st.error(f"❌ Error saving: {e}")

        # Current mappings summary
        st.markdown("---")
        current_mappings = execute_query("""
            SELECT t.name as tour_name, f.name as fee_name, f.per_person_amount
            FROM tour_fees tf
            JOIN tours t ON tf.tour_id = t.id
            JOIN fees f ON tf.fee_id = f.id
            ORDER BY t.name, f.name
        """)

        if current_mappings:
            st.subheader("📊 Current Mappings")
            tour_mappings = {}
            for mapping in current_mappings:
                tour_name, fee_name, amount = mapping
                if tour_name not in tour_mappings:
                    tour_mappings[tour_name] = []
                tour_mappings[tour_name].append(f"{fee_name} (${amount})")

            for tour_name, fee_list in tour_mappings.items():
                with st.expander(f"🎪 {tour_name} ({len(fee_list)} fees)"):
                    for fee_info in fee_list:
                        st.write(f"• {fee_info}")
        else:
            st.info("💡 No mappings saved yet. Use the table above to assign fees to tours.")
