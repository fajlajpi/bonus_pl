# points/tasks.py
import pandas as pd
from django.utils import timezone
from django.db.models import Q
import logging

from .models import FileUpload, PointsTransaction, User, Brand, UserContract, BrandBonus

# Configure logging
logger = logging.getLogger(__name__)

def process_uploaded_file(upload_id):
    upload = FileUpload.objects.get(id=upload_id)
    logger.info(f"Starting to process upload {upload_id}")
    
    try:
        upload.status = 'PROCESSING'
        upload.save()
        
        # Read the file
        file_path = upload.file.path
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)
        
        logger.info(f"File read successfully. Shape: {df.shape}")
        
        # Validate required columns
        required_columns = ['ZČ', 'Cena', 'Kód', 'Faktura']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise ValueError(f"Missing required columns: {', '.join(missing_columns)}")
        
        # Process data
        successful_rows = 0
        errors = []
        
        # Get unique user numbers from the file
        unique_users = df['ZČ'].unique()
        logger.info(f"Found {len(unique_users)} unique users in file")
        
        # Process each unique user
        for user_number in unique_users:
            logger.debug(f"Processing user {user_number}")
            try:
                # Find the user and their active contract
                try:
                    user = User.objects.get(user_number=user_number)
                    logger.debug(f"Found user: {user.username}")
                    
                    contract = UserContract.objects.get(
                        user_id=user,
                        is_active=True,
                        contract_date_from__lte=upload.uploaded_at,
                        contract_date_to__gte=upload.uploaded_at
                    )
                    logger.debug(f"Found active contract for user: {contract}")
                    
                except User.DoesNotExist:
                    logger.info(f"User {user_number} not found in system - skipping")
                    continue
                except UserContract.DoesNotExist:
                    logger.info(f"No active contract found for user {user_number} - skipping")
                    continue
                
                # Get user's brand bonuses
                brand_bonuses = contract.brandbonuses.all()
                logger.debug(f"Found {brand_bonuses.count()} brand bonuses for user")
                
                if not brand_bonuses:
                    logger.info(f"No brand bonuses found for user {user_number} - skipping")
                    continue
                
                # Get user's data
                user_data = df[df['ZČ'] == user_number]
                
                # Get unique invoices for this user
                unique_invoices = user_data['Faktura'].unique()
                logger.debug(f"Found {len(unique_invoices)} invoices for user")
                
                # Process each invoice
                for invoice_id in unique_invoices:
                    logger.debug(f"Processing invoice {invoice_id}")
                    invoice_data = user_data[user_data['Faktura'] == invoice_id]
                    
                    # Process each brand bonus
                    for bonus in brand_bonuses:
                        brand = bonus.brand_id
                        logger.debug(f"Processing brand {brand.name} with prefix {brand.prefix}")
                        
                        # Filter rows for this brand
                        brand_rows = invoice_data[
                            invoice_data['Kód'].str.startswith(brand.prefix)
                        ]
                        
                        if not brand_rows.empty:
                            # Sum up all values for this brand in this invoice
                            total_amount = brand_rows['Cena'].sum()
                            points = int(total_amount * bonus.points_ratio)
                            
                            logger.debug(f"Calculated {points} points for amount {total_amount}")
                            
                            # Create transaction if points exist
                            if points > 0:
                                transaction = PointsTransaction.objects.create(
                                    user=user,
                                    value=points,
                                    date=upload.uploaded_at.date(),
                                    description=f'Invoice {invoice_id}',
                                    type='STANDARD_POINTS',
                                    status='PENDING',
                                    brand=brand
                                )
                                logger.debug(f"Created transaction: {transaction}")
                                successful_rows += 1
                
            except Exception as e:
                error_msg = f"Error processing user {user_number}: {str(e)}"
                logger.error(error_msg, exc_info=True)
                errors.append(error_msg)
        
        # Update upload record
        upload.status = 'COMPLETED'
        upload.processed_at = timezone.now()
        upload.rows_processed = successful_rows
        if errors:
            upload.error_message = "\n".join(errors)
        upload.save()
        
        logger.info(f"Processing completed. Successful rows: {successful_rows}, Errors: {len(errors)}")
        
    except Exception as e:
        error_msg = f"Fatal error processing upload: {str(e)}"
        logger.error(error_msg, exc_info=True)
        upload.status = 'FAILED'
        upload.error_message = error_msg
        upload.processed_at = timezone.now()
        upload.save()
        raise