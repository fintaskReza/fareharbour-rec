# Tours & Fees Management Setup

## Overview
This document describes the new Tours & Fees Management feature added to the FareHarbour reconciliation application.

## Database Setup
A new Neon database has been created with the following tables:

### Tables Created
1. **tours** - Stores tour information
   - `id` (Primary Key)
   - `name` (Unique tour name)
   - `created_at`, `updated_at` (Timestamps)

2. **fees** - Stores fee information
   - `id` (Primary Key)
   - `name` (Unique fee name)
   - `per_person_amount` (Decimal amount)
   - `apply_to_all` (Boolean flag)
   - `created_at`, `updated_at` (Timestamps)

3. **tour_fees** - Maps tours to fees
   - `id` (Primary Key)
   - `tour_id` (Foreign Key to tours)
   - `fee_id` (Foreign Key to fees)
   - `created_at` (Timestamp)

### Pre-loaded Data
The following fees have been pre-loaded:
- BC Park Fee
- Field Surcharge
- Fuel surcharge CT
- Fuel Surcharge (WBF)
- BC Park Fee (WBF)
- Stewardship Fee
- Stewardship Fee (WBF)

Sample tours have also been added based on your existing data.

## Installation Requirements
Update your Python environment with the new dependencies:

```bash
pip install -r requirements.txt
```

New dependencies added:
- `psycopg2-binary>=2.9.0` - PostgreSQL adapter
- `sqlalchemy>=2.0.0` - Database ORM

## Environment Configuration
The application uses the following environment variable for database connection:

```
DATABASE_URL=postgresql://neondb_owner:npg_IRu7ADSfUxC6@ep-steep-star-af6ymzhg-pooler.c-2.us-west-2.aws.neon.tech/neondb?channel_binding=require&sslmode=require
```

This is currently hardcoded in the application but can be moved to an environment variable for production.

## Usage

### Accessing Tours & Fees Management
1. Run the application: `streamlit run reconciliation_app.py`
2. Authenticate with your password
3. In the sidebar, select "Tours & Fees Management" from the navigation dropdown

### Features Available

#### Tours Tab
- **Add New Tour**: Enter a tour name and click "Add Tour"
- **View Tours**: See all existing tours in a table
- **Delete Tours**: Select a tour from the dropdown and delete it

#### Fees Tab
- **Add New Fee**: Enter fee name, per-person amount, and "apply to all" setting
- **View Fees**: See all existing fees in a table
- **Edit Fees**: Select a fee to edit its name, amount, or apply-to-all setting
- **Delete Fees**: Delete selected fees

#### Tour-Fee Mappings Tab
- **Create Mappings**: Select a tour and fee to create a mapping
- **View Mappings**: See all existing tour-fee relationships
- **Delete Mappings**: Remove specific tour-fee mappings

## Database Connection Details
- **Project ID**: fragrant-hall-17290426
- **Database**: neondb
- **Connection**: Pooled connection with SSL required

## Security Notes
- Database credentials are currently embedded in the code
- For production, move sensitive credentials to environment variables
- The existing authentication system protects access to the new features

## Future Enhancements
Potential improvements could include:
- Bulk import/export of tours and fees
- Fee calculation integration with reconciliation process
- Historical tracking of fee changes
- Advanced fee rules and conditions
