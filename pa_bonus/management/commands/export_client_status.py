"""
Management command to export the current status of all clients in the system.

This command generates a comprehensive report including:
- Current confirmed points balance
- Pending points (not yet confirmed)
- Active goals and progress towards them

The export can be output in CSV or Excel format, and supports filtering
by region or active contracts only.

Usage examples:
    # Basic CSV export to stdout
    python manage.py export_client_status

    # Export to a specific file
    python manage.py export_client_status --output /path/to/report.csv

    # Export as Excel with all details
    python manage.py export_client_status --format xlsx --output status_report.xlsx

    # Filter by region
    python manage.py export_client_status --region NORTH

    # Only clients with active contracts
    python manage.py export_client_status --active-only

    # Verbose output (show processing progress)
    python manage.py export_client_status -v 2
"""

import csv
import sys
from datetime import date
from decimal import Decimal
from io import StringIO

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Sum, Value, Q
from django.db.models.functions import Coalesce
from django.utils import timezone

from pa_bonus.models import (
    User, 
    UserContract, 
    UserContractGoal,
    PointsTransaction, 
    Region,
)
from pa_bonus.utilities import calculate_turnover_for_goal


class Command(BaseCommand):
    help = 'Export current status of all clients including points and goal progress'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output', '-o',
            type=str,
            help='Output file path. If not specified, outputs to stdout (CSV only)',
        )
        parser.add_argument(
            '--format', '-f',
            type=str,
            choices=['csv', 'xlsx'],
            default='csv',
            help='Output format: csv or xlsx (default: csv)',
        )
        parser.add_argument(
            '--region', '-r',
            type=str,
            help='Filter by region code (e.g., NORTH, SOUTH)',
        )
        parser.add_argument(
            '--active-only',
            action='store_true',
            help='Only include clients with active contracts',
        )
        parser.add_argument(
            '--include-goals',
            action='store_true',
            default=True,
            help='Include goal progress in export (default: True)',
        )
        parser.add_argument(
            '--no-goals',
            action='store_true',
            help='Exclude goal progress from export (simpler output)',
        )
        # Note: We use Django's built-in --verbosity option instead of a custom --verbose
        # Use -v 2 or --verbosity 2 for detailed output

    def handle(self, *args, **options):
        output_path = options['output']
        output_format = options['format']
        region_code = options['region']
        active_only = options['active_only']
        include_goals = not options['no_goals']
        # Use Django's built-in verbosity: 0=minimal, 1=normal, 2=verbose, 3=very verbose
        verbose = options['verbosity'] >= 2

        # Validate output format and path combination
        if output_format == 'xlsx' and not output_path:
            raise CommandError(
                'Excel format requires an output file path. '
                'Use --output to specify the file path.'
            )

        # Build the client queryset
        clients = self._get_client_queryset(region_code, active_only)
        
        if verbose:
            self.stdout.write(f'Found {clients.count()} clients to process')

        # Collect all client data
        client_data = []
        goal_data = []  # Separate list for goal details
        
        today = timezone.now().date()
        
        for client in clients:
            if verbose:
                self.stdout.write(f'Processing client: {client.user_number}')
            
            # Get points data
            confirmed_points = client.get_balance()
            pending_points = self._get_pending_points(client)
            
            # Get contract info
            active_contract = self._get_active_contract(client)
            
            # Base client record
            client_record = {
                'client_number': client.user_number,
                'client_name': f'{client.first_name} {client.last_name}'.strip(),
                'email': client.email,
                'region': client.region.name if client.region else '',
                'confirmed_points': confirmed_points,
                'pending_points': pending_points,
                'total_points': confirmed_points + pending_points,
                'has_active_contract': 'Yes' if active_contract else 'No',
                'contract_from': active_contract.contract_date_from if active_contract else '',
                'contract_to': active_contract.contract_date_to if active_contract else '',
            }
            
            # Add goal information if requested
            if include_goals and active_contract:
                goals = self._get_active_goals(active_contract, today)
                
                if goals:
                    # Add summary to client record
                    client_record['active_goals_count'] = len(goals)
                    
                    # Calculate overall goal progress (average of all goals)
                    total_progress = sum(g['progress_percentage'] for g in goals)
                    client_record['avg_goal_progress'] = (
                        round(total_progress / len(goals), 1) if goals else 0
                    )
                    
                    # Add individual goal records
                    for goal in goals:
                        goal_record = {
                            'client_number': client.user_number,
                            'client_name': f'{client.first_name} {client.last_name}'.strip(),
                            **goal
                        }
                        goal_data.append(goal_record)
                else:
                    client_record['active_goals_count'] = 0
                    client_record['avg_goal_progress'] = 0
            elif include_goals:
                client_record['active_goals_count'] = 0
                client_record['avg_goal_progress'] = 0
            
            client_data.append(client_record)

        # Generate output
        if output_format == 'xlsx':
            self._write_excel(output_path, client_data, goal_data, include_goals)
            self.stdout.write(
                self.style.SUCCESS(f'Successfully exported {len(client_data)} clients to {output_path}')
            )
        else:
            self._write_csv(output_path, client_data, include_goals)
            if output_path:
                self.stdout.write(
                    self.style.SUCCESS(f'Successfully exported {len(client_data)} clients to {output_path}')
                )

    def _get_client_queryset(self, region_code, active_only):
        """
        Build the queryset for clients based on filters.
        
        Args:
            region_code: Optional region code to filter by
            active_only: Whether to include only clients with active contracts
            
        Returns:
            QuerySet of User objects
        """
        # Start with all users that have a user_number (i.e., actual clients)
        # Exclude staff users as they are typically not clients
        queryset = User.objects.filter(
            is_staff=False,
            is_active=True,
        ).exclude(
            user_number=''
        ).select_related('region')
        
        # Filter by region if specified
        if region_code:
            try:
                region = Region.objects.get(code__iexact=region_code)
                queryset = queryset.filter(region=region)
            except Region.DoesNotExist:
                raise CommandError(
                    f'Region with code "{region_code}" does not exist. '
                    f'Available regions: {", ".join(Region.objects.values_list("code", flat=True))}'
                )
        
        # Filter to only clients with active contracts if requested
        if active_only:
            queryset = queryset.filter(
                usercontract__is_active=True
            ).distinct()
        
        return queryset.order_by('region__name', 'last_name', 'first_name')

    def _get_pending_points(self, client):
        """
        Calculate the total pending points for a client.
        
        Args:
            client: User object
            
        Returns:
            int: Total pending points
        """
        result = PointsTransaction.objects.filter(
            user=client,
            status='PENDING'
        ).aggregate(
            total=Coalesce(Sum('value'), Value(0))
        )
        return result['total']

    def _get_active_contract(self, client):
        """
        Get the active contract for a client.
        
        Args:
            client: User object
            
        Returns:
            UserContract or None
        """
        try:
            return UserContract.objects.get(
                user_id=client,
                is_active=True
            )
        except UserContract.DoesNotExist:
            return None

    def _get_active_goals(self, contract, today):
        """
        Get active goals and their progress for a contract.
        
        Args:
            contract: UserContract object
            today: Current date
            
        Returns:
            List of goal dictionaries with progress information
        """
        goals = UserContractGoal.objects.filter(
            user_contract=contract,
            goal_period_from__lte=today,
            goal_period_to__gte=today
        ).prefetch_related('brands', 'evaluations')
        
        goal_list = []
        
        for goal in goals:
            # Get current evaluation period
            periods = goal.get_evaluation_periods()
            current_period = None
            
            for start, end, is_final in periods:
                if start <= today <= end:
                    current_period = (start, end, is_final)
                    break
            
            # Calculate turnover for the entire goal period up to today
            total_turnover = calculate_turnover_for_goal(
                contract.user_id,
                goal.brands.all(),
                goal.goal_period_from,
                min(today, goal.goal_period_to)
            )
            
            # Calculate overall progress percentage
            progress_percentage = (
                float(total_turnover) / goal.goal_value * 100 
                if goal.goal_value > 0 else 0
            )
            
            # Calculate remaining turnover needed
            remaining_turnover = max(0, goal.goal_value - float(total_turnover))
            
            # Get brand names
            brand_names = ', '.join([b.name for b in goal.brands.all()])
            
            # Get points already awarded from evaluations
            points_awarded = goal.evaluations.aggregate(
                total=Coalesce(Sum('bonus_points'), Value(0))
            )['total']
            
            goal_info = {
                'goal_brands': brand_names,
                'goal_period_from': goal.goal_period_from,
                'goal_period_to': goal.goal_period_to,
                'goal_target': goal.goal_value,
                'goal_baseline': goal.goal_base,
                'current_turnover': float(total_turnover),
                'remaining_turnover': float(remaining_turnover),
                'progress_percentage': round(progress_percentage, 1),
                'points_awarded': points_awarded,
            }
            
            # Add current period info if available
            if current_period:
                period_start, period_end, is_final = current_period
                period_targets = goal.get_period_targets(period_start, period_end)
                
                period_turnover = calculate_turnover_for_goal(
                    contract.user_id,
                    goal.brands.all(),
                    period_start,
                    min(today, period_end)
                )
                
                period_progress = (
                    float(period_turnover) / period_targets['goal_value'] * 100
                    if period_targets['goal_value'] > 0 else 0
                )
                
                goal_info.update({
                    'current_period_from': period_start,
                    'current_period_to': period_end,
                    'current_period_target': period_targets['goal_value'],
                    'current_period_turnover': float(period_turnover),
                    'current_period_progress': round(period_progress, 1),
                    'is_final_period': 'Yes' if is_final else 'No',
                })
            
            goal_list.append(goal_info)
        
        return goal_list

    def _write_csv(self, output_path, client_data, include_goals):
        """
        Write client data to CSV format.
        
        Args:
            output_path: Path to output file, or None for stdout
            client_data: List of client dictionaries
            include_goals: Whether goal columns are included
        """
        if not client_data:
            self.stdout.write(self.style.WARNING('No data to export'))
            return
        
        # Define column order
        columns = [
            'client_number',
            'client_name', 
            'email',
            'region',
            'confirmed_points',
            'pending_points',
            'total_points',
            'has_active_contract',
            'contract_from',
            'contract_to',
        ]
        
        if include_goals:
            columns.extend([
                'active_goals_count',
                'avg_goal_progress',
            ])
        
        # Determine output destination
        if output_path:
            output_file = open(output_path, 'w', newline='', encoding='utf-8')
        else:
            output_file = sys.stdout
        
        try:
            writer = csv.DictWriter(
                output_file, 
                fieldnames=columns,
                extrasaction='ignore'  # Ignore extra fields not in columns
            )
            writer.writeheader()
            
            for record in client_data:
                # Convert date objects to strings for CSV
                row = {}
                for col in columns:
                    value = record.get(col, '')
                    if isinstance(value, date):
                        row[col] = value.isoformat()
                    else:
                        row[col] = value
                writer.writerow(row)
                
        finally:
            if output_path:
                output_file.close()

    def _write_excel(self, output_path, client_data, goal_data, include_goals):
        """
        Write client data to Excel format with multiple sheets.
        
        Args:
            output_path: Path to output Excel file
            client_data: List of client dictionaries
            goal_data: List of goal dictionaries
            include_goals: Whether to include the goals sheet
        """
        try:
            import pandas as pd
        except ImportError:
            raise CommandError(
                'pandas is required for Excel export. '
                'Install it with: pip install pandas openpyxl'
            )
        
        try:
            # Create DataFrames
            df_clients = pd.DataFrame(client_data)
            
            # Reorder columns for better readability
            client_columns = [
                'client_number',
                'client_name',
                'email', 
                'region',
                'confirmed_points',
                'pending_points',
                'total_points',
                'has_active_contract',
                'contract_from',
                'contract_to',
            ]
            
            if include_goals:
                client_columns.extend([
                    'active_goals_count',
                    'avg_goal_progress',
                ])
            
            # Ensure all columns exist (some might be missing if no data)
            for col in client_columns:
                if col not in df_clients.columns:
                    df_clients[col] = ''
            
            df_clients = df_clients[client_columns]
            
            # Write to Excel
            with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
                # Client summary sheet
                df_clients.to_excel(
                    writer, 
                    sheet_name='Client Status', 
                    index=False
                )
                
                # Goals detail sheet (if applicable)
                if include_goals and goal_data:
                    df_goals = pd.DataFrame(goal_data)
                    
                    goal_columns = [
                        'client_number',
                        'client_name',
                        'goal_brands',
                        'goal_period_from',
                        'goal_period_to',
                        'goal_target',
                        'goal_baseline',
                        'current_turnover',
                        'remaining_turnover',
                        'progress_percentage',
                        'points_awarded',
                        'current_period_from',
                        'current_period_to',
                        'current_period_target',
                        'current_period_turnover',
                        'current_period_progress',
                        'is_final_period',
                    ]
                    
                    # Only include columns that exist in the data
                    goal_columns = [c for c in goal_columns if c in df_goals.columns]
                    df_goals = df_goals[goal_columns]
                    
                    df_goals.to_excel(
                        writer,
                        sheet_name='Goal Details',
                        index=False
                    )
                
                # Summary statistics sheet
                summary_data = {
                    'Metric': [
                        'Total Clients',
                        'Clients with Active Contracts',
                        'Total Confirmed Points',
                        'Total Pending Points',
                        'Clients with Active Goals',
                        'Export Date',
                    ],
                    'Value': [
                        len(client_data),
                        sum(1 for c in client_data if c.get('has_active_contract') == 'Yes'),
                        sum(c.get('confirmed_points', 0) for c in client_data),
                        sum(c.get('pending_points', 0) for c in client_data),
                        sum(1 for c in client_data if c.get('active_goals_count', 0) > 0),
                        timezone.now().strftime('%Y-%m-%d %H:%M:%S'),
                    ]
                }
                df_summary = pd.DataFrame(summary_data)
                df_summary.to_excel(
                    writer,
                    sheet_name='Summary',
                    index=False
                )
                
        except Exception as e:
            raise CommandError(f'Error writing Excel file: {e}')
