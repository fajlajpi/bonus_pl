import pandas as pd
from django.utils import timezone
from django.db import transaction
from django.db.models import Q
import logging
from datetime import datetime

from .models import FileUpload, PointsTransaction, User, Brand, UserContract, BrandBonus

# Configure logging
logger = logging.getLogger(__name__)

# FILETYPE CONSTANTS TO BRANCH THE PROCESSING
FT_INVOICE = 'INVOICE'
FT_CREDIT_NOTE = 'CREDIT_NOTE'

def process_uploaded_file(upload_id: FileUpload):
    """Main function to process an uploaded file and create points transactions."""
    upload = FileUpload.objects.get(id=upload_id)
    logger.info(f"Starting to process upload {upload_id}")
    
    try:
        mark_upload_as_processing(upload)
        df = read_file(upload.file.path)
        filetype = validate_columns(df)
        
        # Convert and validate dates
        df = process_dates(df)
        
        successful_rows = process_data(df, upload, filetype)
        
        complete_upload(upload, successful_rows)
        logger.info(f"Processing completed. Successful rows: {successful_rows}")
        
    except Exception as e:
        handle_processing_error(upload, e)
        raise


def mark_upload_as_processing(upload: FileUpload):
    """Mark the upload as being processed."""
    upload.status = 'PROCESSING'
    upload.save()


def read_file(file_path: str) -> pd.DataFrame:
    """Read the uploaded file and return a dataframe."""
    if file_path.endswith('.csv'):
        df = pd.read_csv(file_path)
    else:
        df = pd.read_excel(file_path)
    
    logger.info(f"File read successfully. Shape: {df.shape}")
    return df


def validate_columns(df: pd.DataFrame):
    """Validate that the dataframe contains all required columns."""
    required_columns = ['ZČ', 'Cena', 'Kód', 'Datum']
    missing_columns = [col for col in required_columns if col not in df.columns]

    filetype_columns = ['Faktura', 'Dobropis']
    filetype_columns_checked = [col for col in filetype_columns if col in df.columns]

    if len(filetype_columns_checked) != 1:
        raise ValueError(f"Wrong columns for filetype (need either column 'Faktura' or 'Dobropis'), not both or none.")

    if missing_columns:
        raise ValueError(f"Missing required columns: {', '.join(missing_columns)}")

    if filetype_columns_checked[0] == 'Faktura':
        return FT_INVOICE
    elif filetype_columns_checked[0] == 'Dobropis':
        return FT_CREDIT_NOTE
    else:
        raise ValueError(f"Unknown type of document, neither invoice or credit note.")

def process_dates(df: pd.DataFrame):
    """Convert date strings in DD.MM.YYYY format to datetime objects."""
    try:
        # Convert 'Datum' from string to datetime
        df['Datum'] = pd.to_datetime(df['Datum'], format='%d.%m.%Y')
        logger.info("Successfully converted dates")
        
        # Check for invalid dates
        invalid_dates = df[df['Datum'].isnull()]
        if not invalid_dates.empty:
            invalid_rows = invalid_dates.index.tolist()
            logger.warning(f"Found {len(invalid_rows)} rows with invalid dates at indices: {invalid_rows}")
            # Filter out rows with invalid dates
            df = df.dropna(subset=['Datum'])
            logger.info(f"Removed {len(invalid_rows)} rows with invalid dates, new shape: {df.shape}")
            
        return df
    except Exception as e:
        logger.error(f"Error processing dates: {str(e)}", exc_info=True)
        raise ValueError(f"Failed to process dates: {str(e)}")


def process_data(df, upload, filetype):
    """Process the data in the dataframe and create transactions."""
    successful_rows = 0
    errors = []
    
    # Get unique user numbers from the file
    unique_users = df['ZČ'].unique()
    logger.info(f"Found {len(unique_users)} unique users in file")
    
    # Process each unique user
    for user_number in unique_users:
        try:
            user_successful_rows = process_user(user_number, df, upload, filetype)
            successful_rows += user_successful_rows
        except Exception as e:
            error_msg = f"Error processing user {user_number}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            errors.append(error_msg)
    
    if errors:
        upload.error_message = "\n".join(errors)
    
    return successful_rows


@transaction.atomic
def process_user(user_number, df, upload, filetype):
    """Process data for a single user within a transaction."""
    user = User.objects.get(user_number=user_number)
    user_data = df[df['ZČ'] == user_number]
    
    successful_rows = process_user_invoices(user, user_data, upload, filetype)
    
    # Update progress
    upload.processed_rows += successful_rows
    upload.save()
    
    return successful_rows


def process_user_invoices(user, user_data, upload, filetype):
    """Process all invoices / credit notes for a user."""
    successful_rows = 0
    
    # Group by invoice or credit note
    if filetype == FT_INVOICE:
        invoices = user_data.groupby('Faktura')
    elif filetype == FT_CREDIT_NOTE:
        invoices = user_data.groupby('Dobropis')
    else:
        raise Exception(f"Unknown filetype: {filetype}")
    
    # Process each invoice / credit note
    for invoice_id, invoice_data in invoices:
        # Get the invoice date (should be the same for all rows in this invoice)
        invoice_date = invoice_data['Datum'].iloc[0]
        logger.debug(f"Processing invoice {invoice_id} with date {invoice_date}")
        
        # Check if user had an active contract on the invoice date
        contract = get_active_contract(user, invoice_date)
        if not contract:
            logger.info(f"No active contract found for user {user.user_number} on date {invoice_date} - skipping invoice")
            continue
        
        # Get user's brand bonuses for this contract
        brand_bonuses = contract.brandbonuses.all()
        logger.debug(f"Found {brand_bonuses.count()} brand bonuses for user contract")
        
        if not brand_bonuses:
            logger.info(f"No brand bonuses found for user {user.user_number} - skipping invoice")
            continue
        
        # Process each brand bonus for this invoice
        for bonus in brand_bonuses:
            transactions_created = process_brand_bonus(user, invoice_id, invoice_data, bonus, invoice_date, filetype, upload)
            successful_rows += transactions_created
    
    return successful_rows


def get_active_contract(user, date):
    """Retrieve user's active contract for the specific date."""
    try:
        contract = UserContract.objects.get(
            user_id=user,
            is_active=True,
            contract_date_from__lte=date,
            contract_date_to__gte=date
        )
        logger.debug(f"Found active contract for user on date {date}: {contract}")
        return contract
    except UserContract.DoesNotExist:
        logger.info(f"No active contract found for user {user.user_number} on date {date}")
        return None


def process_brand_bonus(user, invoice_id, invoice_data, bonus, invoice_date, filetype, upload):
    """Process a single brand bonus for an invoice / credit note."""
    brand = bonus.brand_id
    logger.debug(f"Processing brand {brand.name} with prefix {brand.prefix}")
    
    # Filter rows for this brand
    brand_rows = invoice_data[
        invoice_data['Kód'].str.startswith(brand.prefix)
    ]
    
    if brand_rows.empty:
        return 0
    
    # Sum up all values for this brand in this invoice
    total_amount = brand_rows['Cena'].sum()
    points = int(total_amount * bonus.points_ratio)
    
    logger.debug(f"Calculated {points} points for amount {total_amount}")
    
    # Create transaction if points exist
    if points > 0:
        create_points_transaction(user, points, invoice_date, invoice_id, brand, filetype, upload)
        return 1
    
    return 0


def create_points_transaction(user, points, invoice_date, invoice_id, brand, filetype, upload):
    """Create a transaction with robust idempotency check."""
    # Convert invoice_id to string to ensure consistent comparison
    invoice_id_str = str(invoice_id)
    
    # Ensure invoice_date is a date object
    if hasattr(invoice_date, 'date'):
        invoice_date = invoice_date.date()
    
    # More comprehensive query to catch potential duplicates
    existing = PointsTransaction.objects.filter(
        user=user,
        date=invoice_date,
        brand=brand,
        type='STANDARD_POINTS' if filetype == FT_INVOICE else 'CREDIT_NOTE_ADJUST'
    ).filter(
        Q(description__contains=invoice_id_str) | 
        Q(description__contains=f"Invoice {invoice_id_str}") | 
        Q(description__contains=f"Dobropis {invoice_id_str}")
    ).first()
    
    if existing:
        logger.info(f"Skipping duplicate: {invoice_id} for user {user.username}")
        return existing
    
    # Create new transaction
    transaction = PointsTransaction.objects.create(
        user=user,
        value=points if filetype == FT_INVOICE else -points,
        date=invoice_date,
        description=f'{"Invoice" if filetype == FT_INVOICE else "Dobropis"} {invoice_id_str}',
        type='STANDARD_POINTS' if filetype == FT_INVOICE else 'CREDIT_NOTE_ADJUST',
        status='PENDING' if filetype == FT_INVOICE else 'CONFIRMED',
        brand=brand,
        file_upload=upload  # Link to the upload
    )
    
    logger.debug(f"Created new transaction: {transaction}")
    return transaction


def complete_upload(upload, successful_rows):
    """Mark the upload as completed and update statistics."""
    upload.status = 'COMPLETED'
    upload.processed_at = timezone.now()
    upload.rows_processed = successful_rows
    upload.save()


def handle_processing_error(upload, exception):
    """Handle a fatal error during processing."""
    error_msg = f"Fatal error processing upload: {str(exception)}"
    logger.error(error_msg, exc_info=True)
    upload.status = 'FAILED'
    upload.error_message = error_msg
    upload.processed_at = timezone.now()
    upload.save()